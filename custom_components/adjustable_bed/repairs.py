"""Repair flows for the Adjustable Bed integration.

Currently provides a guided fix for the ``pairing_required`` issue: it walks the
user through putting an OKIN-style base into Bluetooth pairing mode (by
power-cycling the control box), pairs with ``pair=True``, and verifies the bond
by reading an auth-gated characteristic before resolving the issue.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .adapter import get_discovered_service_info
from .ble_auth import is_ble_authentication_error
from .const import (
    ADAPTER_AUTO,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_PREFERRED_ADAPTER,
    DEVICE_INFO_CHARS,
)

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

    def _find_device(self) -> object | None:
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

    async def _async_try_pair(self) -> bool:
        """Connect with pair=True and verify the encrypted link is bonded."""
        from bleak import BleakClient
        from bleak.exc import BleakError
        from bleak_retry_connector import establish_connection

        device = self._find_device()
        if device is None:
            _LOGGER.warning(
                "Repair: bed %s not reachable on the configured adapter — cannot pair",
                self._address,
            )
            return False

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
                    "Repair: bond verification failed for %s: %s", self._address, err
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
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

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
                await self.hass.config_entries.async_reload(self._entry_id)

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
