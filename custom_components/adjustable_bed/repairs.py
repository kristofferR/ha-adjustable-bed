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

    def _bonded_now(self) -> bool:
        """Return True when the entry currently records a confirmed BLE bond."""
        if self._entry_id is None:
            return False
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        return bool(entry is not None and entry.data.get(CONF_BLE_BOND_ESTABLISHED))

    async def _async_pair_via_coordinator(self) -> bool | None:
        """Pair without ever opening a throwaway connection.

        Returns True/False for a bed that grants one connection per pairing
        window, or None when this repair may use its own client.

        For such a bed, opening a second client here would consume the single
        connection and then close it in ``finally``, so the reload afterwards
        would find the box refusing every reconnect. Two routes avoid that:

        * A loaded coordinator pairs on its own link via ``async_pair_now()``,
          which bonds an already-live link instead of reconnecting.
        * With no loaded coordinator the entry is typically in SETUP_RETRY (the
          very state that raises this repair), so reloading it lets
          ``async_setup_entry`` make exactly one connection that connects,
          discovers, bonds and stays up.

        Success is reported only when the bond is actually confirmed. Connecting
        is not the same as pairing: the connect path deliberately keeps an
        unbonded link, so treating a connection as success would resolve the
        pairing issue while the bed is still unbonded.
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
        if coordinator is not None:
            _LOGGER.info(
                "Repair: pairing %s through the existing coordinator so the "
                "bed's single connection is kept rather than spent",
                self._address,
            )
            try:
                # async_pair_now() clears the runtime bond marker itself, which
                # editing entry.data alone would not do.
                return bool(await coordinator.async_pair_now())
            except Exception as err:  # noqa: BLE001 - any failure means "not paired"
                _LOGGER.warning("Repair: pairing failed for %s: %s", self._address, err)
                return False

        # No coordinator: the entry failed setup and is retrying. Clear the bond
        # marker so the next setup requests the bond, then let setup own the one
        # connection instead of racing it with a client of our own.
        if entry.data.get(CONF_BLE_BOND_ESTABLISHED):
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_BLE_BOND_ESTABLISHED: False},
            )
        _LOGGER.info(
            "Repair: reloading %s so its setup makes the single pairing "
            "connection (no coordinator is loaded to drive)",
            self._address,
        )
        try:
            await self.hass.config_entries.async_reload(self._entry_id)
        except Exception as err:  # noqa: BLE001 - any failure means "not paired"
            _LOGGER.warning("Repair: pairing failed for %s: %s", self._address, err)
            return False
        return self._bonded_now()

    async def _async_try_pair(self) -> bool:
        """Create a bond for beds that pair at connect time, and verify it.

        Beds that must bond after service discovery never reach this path: they
        are one-connection beds and are handled by _async_pair_via_coordinator,
        which refuses to open a throwaway client at all.
        """
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

        client: BleakClient | None = None
        reload_entry_id: str | None = None
        # Hold the address lock for the whole client lifetime. Releasing it after
        # the connect would let the disconnect below land inside another caller's
        # connect attempt, where bleak's cleanup can abort it.
        async with async_get_connect_lock(self.hass, self._address):
            try:
                client = await establish_connection(
                    BleakClient,
                    device,
                    self._name,
                    max_attempts=1,
                    pair=True,
                    use_services_cache=False,
                )
            except Exception as err:  # noqa: BLE001 - any failure means "not paired"
                _LOGGER.warning("Repair: pairing failed for %s: %s", self._address, err)
                return False

            try:
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
