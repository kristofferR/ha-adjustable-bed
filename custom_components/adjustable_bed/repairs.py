"""Repair issues and fix flows for the Adjustable Bed integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .adapter import get_discovered_service_info
from .ble_auth import is_ble_authentication_error
from .const import (
    ADAPTER_AUTO,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_PREFERRED_ADAPTER,
    DEVICE_INFO_CHARS,
    DOMAIN,
)
from .pairing_candidates import (
    active_pairing_candidates,
    build_pair_selection_schema,
)

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

COMBINE_BEDS_ISSUE_ID = "combine_two_beds"


@callback
def async_refresh_combine_beds_issue(hass: HomeAssistant) -> None:
    """Create or clear the Dual Bed suggestion from current entry state."""
    candidates = active_pairing_candidates(hass)
    if len(candidates) < 2:
        async_delete_issue(hass, DOMAIN, COMBINE_BEDS_ISSUE_ID)
        return

    async_create_issue(
        hass,
        DOMAIN,
        COMBINE_BEDS_ISSUE_ID,
        is_fixable=True,
        is_persistent=True,
        severity=IssueSeverity.WARNING,
        translation_key="combine_two_beds",
        data={"entry_count": len(candidates)},
    )


@callback
def async_setup_combine_beds_issue(hass: HomeAssistant) -> None:
    """Reconcile the suggestion once startup entry loading has settled.

    A persistent issue retains the user's dismissed state across restarts. Do
    not delete it while config entries are only temporarily not loaded during
    startup, because recreating it would make a dismissed suggestion nag again.
    """
    if hass.state is CoreState.running:
        async_refresh_combine_beds_issue(hass)
        return

    @callback
    def refresh_after_start(_: Event) -> None:
        async_refresh_combine_beds_issue(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, refresh_after_start)


@callback
def async_track_combine_beds_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Refresh the suggestion whenever this entry changes lifecycle state."""

    @callback
    def refresh() -> None:
        if hass.state is CoreState.running:
            async_refresh_combine_beds_issue(hass)

    entry.async_on_unload(entry.async_on_state_change(refresh))
    refresh()


class CombineBedsRepairFlow(RepairsFlow):
    """Route a Repairs suggestion through the canonical pairing config flow."""

    def __init__(self) -> None:
        """Track the delegated config flow across validation retries."""
        self._pairing_flow_id: str | None = None

    def _description_placeholders(self) -> dict[str, str]:
        """Describe the currently active candidates without exposing addresses."""
        candidates = active_pairing_candidates(self.hass)
        return {
            "count": str(len(candidates)),
            "names": ", ".join(entry.title for entry in candidates),
        }

    def _schema(self) -> vol.Schema:
        """Build ordered side assignments without any same-bed choices."""
        return build_pair_selection_schema(
            active_pairing_candidates(self.hass)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Open the pairing selection directly from Repairs."""
        # RepairsFlowManager passes its internal {"issue_id": ...} payload to
        # the init step. It is flow metadata, not a submitted side assignment.
        return await self.async_step_pair_beds()

    async def async_step_pair_beds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select sides and delegate validation/creation to the config flow."""
        if len(active_pairing_candidates(self.hass)) < 2:
            self._pairing_flow_id = None
            async_refresh_combine_beds_issue(self.hass)
            return self.async_abort(reason="not_enough_beds")

        if user_input is None:
            return self.async_show_form(
                step_id="pair_beds",
                data_schema=self._schema(),
                description_placeholders=self._description_placeholders(),
            )

        if self._pairing_flow_id is None:
            result = await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
                data={CONF_ADDRESS: "pair_beds"},
            )
            if (
                result.get("type") is not FlowResultType.FORM
                or result.get("step_id") != "pair_beds"
            ):
                return self.async_abort(
                    reason=result.get("reason") or "pairing_flow_failed"
                )
            self._pairing_flow_id = result["flow_id"]

        result = await self.hass.config_entries.flow.async_configure(
            self._pairing_flow_id, user_input
        )
        if result.get("type") is FlowResultType.CREATE_ENTRY:
            self._pairing_flow_id = None
            return self.async_create_entry(title="", data={})
        if result.get("type") is FlowResultType.FORM:
            self._pairing_flow_id = (
                result.get("flow_id") or self._pairing_flow_id
            )
            return self.async_show_form(
                step_id="pair_beds",
                data_schema=result.get("data_schema") or self._schema(),
                errors=result.get("errors"),
                description_placeholders=self._description_placeholders(),
            )
        self._pairing_flow_id = None
        return self.async_abort(reason=result.get("reason") or "pairing_flow_failed")


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
    if issue_id == COMBINE_BEDS_ISSUE_ID:
        return CombineBedsRepairFlow()

    payload = data or {}
    return PairingRequiredRepairFlow(
        address=payload.get("address", ""),
        name=payload.get("name", "your bed"),
        entry_id=payload.get("entry_id"),
    )
