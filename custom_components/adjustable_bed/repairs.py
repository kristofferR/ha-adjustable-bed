"""Repair flows for the Adjustable Bed integration.

Currently provides a guided fix for the ``pairing_required`` issue: it walks the
user through putting the base into Bluetooth pairing mode, follows the
controller-specific connection/bond ordering, and verifies the bond by reading
an auth-gated characteristic before resolving the issue.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .adapter import get_discovered_service_info
from .address_lock import async_get_connect_lock
from .ble_auth import is_ble_authentication_error
from .const import (
    ADAPTER_AUTO,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DEVICE_INFO_CHARS,
    DOMAIN,
    grants_one_connection_per_pairing_window,
    requires_pairing_after_service_discovery,
)

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)


class PairingRequiredRepairFlow(RepairsFlow):
    """Guided flow to (re-)pair a bed that requires Bluetooth bonding."""

    def __init__(self, address: str, name: str, entry_id: str | None) -> None:
        """Store the target bed details from the issue data."""
        self._address = address
        self._name = name
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Entry point — show pairing instructions and a confirm button."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pair with the bed when the user confirms."""
        if user_input is not None:
            if await self._async_try_pair():
                return self.async_create_entry(title="", data={})
            return self.async_abort(reason="pairing_failed")

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._name,
                "address": self._address,
            },
        )

    def _find_device(self) -> BLEDevice | None:
        """Find the BLE device, honoring the entry's preferred adapter.

        BLE bonds live on the adapter/proxy that performed pairing, so a repair
        must pair on the same source the coordinator will use — otherwise it can
        bond one source, mark the entry bonded, and leave the configured source
        still unauthenticated.
        """
        preferred = ADAPTER_AUTO
        if self._entry_id is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                preferred = entry.data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)

        if not preferred or preferred == ADAPTER_AUTO:
            return bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )

        address_upper = self._address.upper()
        for service_info in get_discovered_service_info(
            self.hass, include_non_connectable=True
        ):
            if service_info.address.upper() != address_upper:
                continue
            if getattr(service_info, "source", None) == preferred:
                return service_info.device
        return None

    async def _async_pair_via_coordinator(self) -> bool | None:
        """Pair by driving the entry's own coordinator connection.

        Returns True/False once the coordinator has run, or None when this
        repair must fall back to its own client (no entry, or the entry is not
        loaded).

        For a bed that grants one connection per pairing window, opening a
        second client here would consume that connection and then close it, so
        the reload afterwards would find the box refusing every reconnect. The
        coordinator's own connect path performs the same connect -> discover ->
        bond ordering and, crucially, *keeps* the link it establishes.
        """
        if self._entry_id is None:
            return None
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return None
        if not grants_one_connection_per_pairing_window(
            entry.data.get(CONF_BED_TYPE) or "",
            entry.data.get(CONF_PROTOCOL_VARIANT),
        ):
            return None

        coordinator = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
        if coordinator is None:
            return None

        # Clear any stale marker so the connect actually requests the bond.
        if entry.data.get(CONF_BLE_BOND_ESTABLISHED):
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_BLE_BOND_ESTABLISHED: False},
            )

        _LOGGER.info(
            "Repair: pairing %s through the existing coordinator so the bed's "
            "single connection is kept rather than spent",
            self._address,
        )
        try:
            connected = await coordinator.async_connect()
        except Exception as err:  # noqa: BLE001 - any failure means "not paired"
            _LOGGER.warning("Repair: pairing failed for %s: %s", self._address, err)
            return False
        if not connected:
            _LOGGER.warning(
                "Repair: could not connect to %s to pair it", self._address
            )
        return bool(connected)

    async def _async_try_pair(self) -> bool:
        """Create a bond with the controller-specific ordering and verify it."""
        from bleak import BleakClient
        from bleak.exc import BleakError
        from bleak_retry_connector import establish_connection

        via_coordinator = await self._async_pair_via_coordinator()
        if via_coordinator is not None:
            return via_coordinator

        device = self._find_device()
        if device is None:
            _LOGGER.warning(
                "Repair: bed %s not reachable on the configured adapter — cannot pair",
                self._address,
            )
            return False

        pair_after_service_discovery = False
        if self._entry_id is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                bed_type = entry.data.get(CONF_BED_TYPE)
                pair_after_service_discovery = bool(
                    bed_type
                    and requires_pairing_after_service_discovery(
                        bed_type,
                        entry.data.get(CONF_PROTOCOL_VARIANT),
                    )
                )

        client: BleakClient | None = None
        reload_entry_id: str | None = None
        try:
            try:
                async with async_get_connect_lock(self.hass, self._address):
                    client = await establish_connection(
                        BleakClient,
                        device,
                        self._name,
                        max_attempts=1,
                        pair=not pair_after_service_discovery,
                        use_services_cache=False,
                    )
                    if pair_after_service_discovery:
                        await client.pair()
            except Exception as err:  # noqa: BLE001 - any failure means "not paired"
                _LOGGER.warning("Repair: pairing failed for %s: %s", self._address, err)
                return False

            bonded = False
            try:
                # Verify the bond by reading a known auth-gated characteristic. A
                # still-unbonded link fails with GATT error=5; non-auth errors
                # (e.g. the characteristic is absent) are inconclusive, not failures.
                await client.read_gatt_char(DEVICE_INFO_CHARS["model_number"])
                bonded = True
            except BleakError as err:
                if is_ble_authentication_error(err):
                    _LOGGER.warning(
                        "Repair: bond verification failed for %s: %s",
                        self._address,
                        err,
                    )
                else:
                    _LOGGER.debug(
                        "Repair: bond verification inconclusive for %s: %s",
                        self._address,
                        err,
                    )
                    bonded = True
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "Repair: bond verification inconclusive for %s: %s",
                    self._address,
                    err,
                )
                bonded = True

            if not bonded:
                return False

            # Persist the confirmed bond and reload so the coordinator reuses it
            # (and does not try to re-pair on top of the existing bond).
            if self._entry_id is not None:
                entry = self.hass.config_entries.async_get_entry(self._entry_id)
                if entry is not None:
                    if not entry.data.get(CONF_BLE_BOND_ESTABLISHED):
                        self.hass.config_entries.async_update_entry(
                            entry,
                            data={**entry.data, CONF_BLE_BOND_ESTABLISHED: True},
                        )
                    reload_entry_id = self._entry_id
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    pass

        if reload_entry_id is not None:
            await self.hass.config_entries.async_reload(reload_entry_id)

        _LOGGER.info("Repair: pairing succeeded for %s", self._address)
        return True


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create the repair flow for a fixable issue."""
    payload = data or {}
    return PairingRequiredRepairFlow(
        address=payload.get("address", ""),
        name=payload.get("name", "your bed"),
        entry_id=payload.get("entry_id"),
    )
