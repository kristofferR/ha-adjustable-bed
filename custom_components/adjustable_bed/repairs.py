"""Repair issues and fix flows for the Adjustable Bed integration.

Surfaces the Dual Bed combine suggestion and a guided fix for the
``pairing_required`` issue. The latter walks the user through putting the base
into Bluetooth pairing mode, follows the controller-specific connection/bond
ordering, and verifies the bond by reading an auth-gated characteristic before
resolving the issue. It also offers to replace a bond this host is still
holding but the bed no longer honours, whenever the evidence points at the
host.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow, repairs_flow_manager
from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry
from homeassistant.helpers.translation import async_get_translations

from .adapter import get_discovered_service_info
from .address_lock import async_get_connect_lock
from .ble_auth import is_ble_authentication_error
from .bluetooth_transport import TransportClass, async_path_for_source, client_source
from .bond_recovery import (
    RecoveryEligibility,
    RecoveryOffer,
    async_recover_local_bond,
    async_recovery_offer,
    evidence_is_proxy_auth_failure,
    recovery_context,
)
from .bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
    bond_context_matches,
    bond_owner_from_entry,
    build_bond_context,
)
from .combine_suggestion import async_dismiss, async_is_dismissed, normalize_addresses
from .const import (
    ADAPTER_AUTO,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DEVICE_INFO_CHARS,
    DOMAIN,
    grants_one_connection_per_pairing_window,
)
from .pairing import is_paired
from .pairing_candidates import (
    active_pairing_candidates,
    build_pair_selection_schema,
)
from .setup_operation import (
    BluetoothOperationMixin,
    OperationOutcome,
    OperationResult,
    SetupAction,
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

    addresses = [entry.data[CONF_ADDRESS] for entry in candidates]
    if async_is_dismissed(hass, addresses):
        # The user has said these are separate beds. Asking again about the
        # same beds or a remaining subset would make the answer meaningless.
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
        self._candidate_addresses: frozenset[str] | None = None

    def _description_placeholders(
        self, candidates: list[ConfigEntry] | None = None
    ) -> dict[str, str]:
        """Describe active candidates without exposing addresses."""
        if candidates is None:
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
        """Ask which of the two answers applies before showing any form.

        A fixable Repairs issue gets no Ignore action from Home Assistant, so
        without this the only exit for someone who owns two separate beds is to
        close the dialog, leaving the suggestion in Repairs forever.
        """
        # RepairsFlowManager passes its internal {"issue_id": ...} payload to
        # the init step. It is flow metadata, not a submitted side assignment.
        candidates = active_pairing_candidates(self.hass)
        if len(candidates) < 2:
            async_refresh_combine_beds_issue(self.hass)
            return self.async_abort(reason="not_enough_beds")

        self._candidate_addresses = normalize_addresses(
            entry.data[CONF_ADDRESS] for entry in candidates
        )
        return self.async_show_menu(
            step_id="init",
            menu_options=["pair_beds", "separate_beds"],
            description_placeholders=self._description_placeholders(candidates),
        )

    async def async_step_separate_beds(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Record that these beds are separate and stop suggesting them."""
        current_addresses = normalize_addresses(
            entry.data[CONF_ADDRESS]
            for entry in active_pairing_candidates(self.hass)
        )
        if (
            self._candidate_addresses is None
            or current_addresses != self._candidate_addresses
        ):
            async_refresh_combine_beds_issue(self.hass)
            return self.async_abort(reason="beds_changed")

        await async_dismiss(self.hass, self._candidate_addresses)
        async_refresh_combine_beds_issue(self.hass)
        return self.async_abort(reason="beds_are_separate")

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


class PairingRequiredRepairFlow(BluetoothOperationMixin, RepairsFlow):
    """Guided flow to (re-)pair a bed that requires Bluetooth bonding.

    Two branches. The ordinary one puts the bed back into pairing mode and bonds
    it. The other replaces a bond this host is still holding but the bed no
    longer honours, and it is offered only when the evidence that raised this
    repair actually points at the host (issue #459).
    """

    def __init__(
        self,
        address: str,
        name: str,
        entry_id: str | None,
        issue_data: dict[str, Any] | None = None,
        evidence: BondEvidence | None = None,
    ) -> None:
        """Store the target bed details from the issue data."""
        self._address = address
        self._name = name
        self._entry_id = entry_id
        self._issue_data = dict(issue_data or {})
        # The same evidence as ``_issue_data``, already parsed. Kept so a repair
        # can record what the pre-repair state was without re-deriving it.
        self._evidence = evidence
        self._offer: RecoveryOffer | None = None
        self._result_shown = False

    def _async_flow_manager(self) -> Any:
        """Repairs flows are driven by their own manager, not the config one."""
        return repairs_flow_manager(self.hass)

    def _entry(self) -> ConfigEntry | None:
        """Return the config entry this repair belongs to, if it still exists."""
        if self._entry_id is None:
            return None
        return self.hass.config_entries.async_get_entry(self._entry_id)

    def _bed_type(self) -> tuple[str | None, str | None]:
        """Return the bed type and protocol variant for this bed."""
        entry = self._entry()
        if entry is None:
            return None, None
        return entry.data.get(CONF_BED_TYPE), entry.data.get(CONF_PROTOCOL_VARIANT)

    def _is_combined_pair(self) -> bool:
        """Return True when this repair belongs to a combined Dual Bed entry.

        A combined pair is one entry with two sides, and each side keeps its own
        address and bond state on a child descriptor. Nothing recovery needs is
        at the top level: the bond markers it writes would land where no child
        coordinator reads them, and the parent coordinator has no per-side
        transport to serialize the remove-reconnect-pair sequence against.
        Recovery is refused rather than performed into the void; the guided
        pairing branch still applies.
        """
        entry = self._entry()
        return entry is not None and is_paired(entry.data)

    def _proxy_bond_recorded(self) -> bool:
        """Return True when this entry records a bond that a proxy made.

        An authentication failure carried by a proxy is not by itself evidence
        that the proxy holds a bond. The coordinator reports exactly the same
        evidence for a bed that is simply not bonded: ``pair=True`` fails, the
        fallback connects without pairing, and the auth-gated read then reports
        insufficient authentication. Sending that user to read-only guidance
        tells them to factory-reset or reflash a proxy, which erases every
        unrelated bond on it and still leaves this bed unpaired.

        Provenance is the independent signal, because it is only ever written
        from a verification that positively proved a bond.
        """
        entry = self._entry()
        if entry is None or not entry.data.get(CONF_BLE_BOND_ESTABLISHED):
            return False
        return bond_owner_from_entry(entry.data).transport is TransportClass.PROXY

    def _paired_entry_data(self, verified_owner: BondOwner | None) -> dict[str, Any] | None:
        """Return entry data for a repaired bond without stale ownership."""
        entry = self._entry()
        if entry is None:
            return None

        data = {**entry.data, CONF_BLE_BOND_ESTABLISHED: True}
        if verified_owner is not None and verified_owner.transport is not TransportClass.UNKNOWN:
            prior_status = (
                str(self._evidence.status)
                if self._evidence is not None
                else "unknown"
            )
            context = build_bond_context(
                BondEvidence(
                    status=BondVerificationStatus.VERIFIED,
                    owner=verified_owner,
                    operation=f"repair_authenticated_read_after_{prior_status}",
                    observed_at=datetime.now(UTC).isoformat(),
                )
            )
            stored = entry.data.get(CONF_BLE_BOND_CONTEXT)
            # A coordinator that proved the bond has already recorded the same
            # owner. Restating it with a fresh timestamp is still a real change
            # to the entry, and this write is not tagged as an internal
            # bond-marker update, so the reload it triggers would drop the link
            # a one-connection-per-pairing-window bed will not grant again.
            data[CONF_BLE_BOND_CONTEXT] = (
                stored if bond_context_matches(stored, context) else context
            )
        else:
            # Pairing may have succeeded while the auth probe was inconclusive.
            # The old context describes the bond that was just replaced and can
            # no longer authorize host-side removal.
            data.pop(CONF_BLE_BOND_CONTEXT, None)
        return data

    def _persist_repaired_bond(self, verified_owner: BondOwner | None) -> None:
        """Persist a successful repair and its freshly verified owner."""
        entry = self._entry()
        data = self._paired_entry_data(verified_owner)
        if entry is None or data is None or data == dict(entry.data):
            return
        coordinator = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
        claim = getattr(coordinator, "begin_internal_bond_update", None)
        if callable(claim):
            # Let a loaded coordinator claim this as one of its own bond writes,
            # so the update listener does not reload. That reload would drop the
            # link this repair just paired on, and a bed that grants one
            # connection per pairing window never offers another.
            claim(bool(data.get(CONF_BLE_BOND_ESTABLISHED, False)))
        self.hass.config_entries.async_update_entry(entry, data=data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Entry point — offer the branch that fits the evidence."""
        bed_type, variant = self._bed_type()
        if self._is_combined_pair():
            self._offer = RecoveryOffer(
                eligibility=RecoveryEligibility.COMBINED_PAIR
            )
        else:
            self._offer = await async_recovery_offer(
                self.hass,
                address=self._address,
                issue_data=self._issue_data,
                bed_type=bed_type,
                protocol_variant=variant,
            )
        if self._offer.is_eligible:
            return await self.async_step_stale_bond_confirm()
        if evidence_is_proxy_auth_failure(self._issue_data) and self._proxy_bond_recorded():
            # A proxy carried an authentication failure *and* this entry records
            # a bond the proxy proved, so the suspect is that bond, and it lives
            # in a store this host cannot read. Nothing here can clear it, and
            # offering a host-side action would only look like it had. Without
            # both halves the bed is simply unbonded and keeps guided pairing.
            #
            # Checked ahead of KEEPS_FIRST_LINK deliberately. async_recovery_offer
            # answers that first, without looking at the transport, so a bed
            # granting one connection per pairing window would otherwise be sent
            # to a pairing form that cannot reach the proxy's bond store and
            # would hit the identical failure again.
            return await self.async_step_proxy_bond()
        # Everything else, KEEPS_FIRST_LINK included, is a bed that simply needs
        # pairing rather than a bond removed.
        return await self.async_step_confirm()

    async def async_step_proxy_bond(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Explain a proxy-owned bond rather than pretending to fix it."""
        if user_input is not None:
            return self.async_abort(reason="proxy_bond_guidance")
        return self.async_show_form(
            step_id="proxy_bond",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._name,
                "address": self._address,
                "transport": self._issue_data.get("evidence_source") or "a Bluetooth proxy",
            },
        )

    async def async_step_stale_bond_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm replacing a host bond the bed no longer honours."""
        offer = self._offer
        record = offer.record if offer is not None else None
        # ``is_eligible`` already implies a record; naming it keeps that
        # guarantee visible to the type checker rather than only at runtime.
        if offer is None or not offer.is_eligible or record is None:
            return await self.async_step_confirm()

        if user_input is not None:
            self._result_shown = False
            self.async_begin_operation(
                name=self._name,
                address=self._address,
                action=SetupAction.LOCATING,
                placeholders={"name": self._name, "address": self._address},
            )
            return await self.async_step_stale_bond_progress()

        return self.async_show_form(
            step_id="stale_bond_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._name,
                "address": self._address,
                "transport": record.adapter_address or record.adapter_path,
            },
        )

    async def _async_recovery_worker(self) -> OperationResult:
        """Remove the stale host bond and make a verified new one."""
        previous_offer = self._offer
        assert previous_offer is not None
        bed_type, variant = self._bed_type()
        entry = self._entry()
        issue_id = f"pairing_required_{self._address.replace(':', '_').lower()}"
        issue = async_get_issue_registry(self.hass).async_get_issue(DOMAIN, issue_id)
        if issue is None:
            return OperationResult(
                outcome=OperationOutcome.UNPAIR_FAILED,
                detail="pairing_issue_no_longer_exists",
            )
        current_offer = await async_recovery_offer(
            self.hass,
            address=self._address,
            issue_data=dict(issue.data or {}),
            bed_type=bed_type,
            protocol_variant=variant,
        )
        if (
            not current_offer.is_eligible
            or current_offer.record is None
            or previous_offer.record is None
            or not current_offer.record.is_same_bond_as(previous_offer.record)
            or current_offer.owner != previous_offer.owner
        ):
            return OperationResult(
                outcome=OperationOutcome.UNPAIR_FAILED,
                detail="pairing_evidence_changed",
            )
        self._offer = current_offer

        coordinator = (
            self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if entry is not None
            else None
        )
        return await async_recover_local_bond(
            self.hass,
            address=self._address,
            name=self._name,
            offer=current_offer,
            bed_type=bed_type,
            protocol_variant=variant,
            transport_operation=(
                coordinator.async_transport_operation
                if coordinator is not None
                else None
            ),
            on_verified=self._async_persist_recovered_bond,
            on_bond_removed=self._async_clear_removed_bond,
            report_action=self.async_report_action,
            report_progress=self.async_report_progress,
            report_path=self.async_report_path,
        )

    async def async_step_stale_bond_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Run the recovery behind a live progress view."""
        return await self.async_run_operation_step(
            step_id="stale_bond_progress",
            worker=self._async_recovery_worker,
            next_step_id="stale_bond_result",
        )

    async def async_step_stale_bond_result(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Resolve the repair only when the new bond was actually proven."""
        result = self.operation.result
        succeeded = result is not None and result.succeeded

        if user_input is not None and self._result_shown:
            if succeeded:
                return self.async_create_entry(title="", data={})
            return self.async_abort(reason="stale_bond_recovery_failed")

        self._result_shown = True
        return self.async_show_form(
            step_id="stale_bond_result",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._name,
                "outcome": await self._async_recovery_note(result, succeeded),
            },
        )

    async def _async_recovery_note(
        self, result: OperationResult | None, succeeded: bool
    ) -> str:
        """Return the localized description of what recovery achieved."""
        if succeeded:
            note_key = "recovery_success"
        elif result is None or result.outcome is OperationOutcome.CANCELLED:
            note_key = "recovery_not_run"
        elif result.outcome is OperationOutcome.NOT_ADVERTISING:
            note_key = "recovery_not_advertising"
        elif result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED and (
            result.detail != "authentication_state_unconfirmed"
        ):
            note_key = "recovery_partial"
        elif result.outcome is OperationOutcome.UNPAIR_UNCONFIRMED:
            note_key = "recovery_unpair_unconfirmed"
        elif result.outcome is OperationOutcome.UNPAIR_FAILED:
            note_key = "recovery_unpair_failed"
        else:
            note_key = "recovery_failed_unchanged"

        translations = await async_get_translations(
            self.hass,
            self.hass.config.language,
            "issues",
            integrations={DOMAIN},
        )
        return translations.get(
            f"component.{DOMAIN}.issues.pairing_required.fix_flow.abort.{note_key}",
            note_key,
        )

    async def _async_persist_recovered_bond(self, result: OperationResult | None) -> None:
        """Record the new bond and its owner, then ensure the entry reloads."""
        entry = self._entry()
        if entry is None or result is None or result.payload is None:
            return
        coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        data = {
            **entry.data,
            CONF_BLE_BOND_ESTABLISHED: True,
            CONF_BLE_BOND_CONTEXT: recovery_context(result.payload),
        }
        data.pop(CONF_BLE_BOND_MARKER_UNRELIABLE, None)
        self.hass.config_entries.async_update_entry(entry, data=data)
        if coordinator is None:
            # A loaded entry has an update listener which schedules the reload.
            # Setup-retry entries have no listener yet, so reload those here.
            await self.hass.config_entries.async_reload(entry.entry_id)

    async def _async_clear_removed_bond(self) -> None:
        """Drop the marker and provenance for a bond that was just removed.

        Only ever called once removal was confirmed and the replacement was not.
        The repair stays open, so no reload is forced here: what matters is that
        the entry no longer claims a bond, so the next connection asks to pair
        instead of repeating the authentication failure on an unbonded device.
        """
        entry = self._entry()
        if entry is None:
            return
        data = dict(entry.data)
        data.pop(CONF_BLE_BOND_ESTABLISHED, None)
        data.pop(CONF_BLE_BOND_CONTEXT, None)
        data.pop(CONF_BLE_BOND_MARKER_UNRELIABLE, None)
        if data != dict(entry.data):
            self.hass.config_entries.async_update_entry(entry, data=data)

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
                paired = bool(await coordinator.async_pair_now())
            except Exception as err:  # noqa: BLE001 - any failure means "not paired"
                _LOGGER.warning("Repair: pairing failed for %s: %s", self._address, err)
                return False
            if paired:
                # What matters is whether this pairing was proven, not whether
                # the stored context changed. The coordinator deliberately skips
                # rewriting provenance when the owner is identical, so comparing
                # contexts would read a correctly re-verified same-adapter bond
                # as "nothing was established" and delete a valid record.
                evidence = getattr(coordinator, "last_bond_evidence", None)
                if isinstance(evidence, BondEvidence) and evidence.proves_bond:
                    self._persist_repaired_bond(evidence.owner)
                else:
                    # Nothing established an owner this time, so the stored
                    # context still describes the pre-repair bond and can no
                    # longer authorize a host-side removal.
                    self._persist_repaired_bond(None)
            return paired

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
        bonded = self._bonded_now()
        if bonded:
            # Same rule as the coordinator-driven branch above: an unchanged
            # context is the expected result of re-verifying the same adapter,
            # so ask the reloaded coordinator what it actually proved rather
            # than reading "unchanged" as "unproven".
            reloaded = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
            evidence = getattr(reloaded, "last_bond_evidence", None)
            if isinstance(evidence, BondEvidence) and evidence.proves_bond:
                self._persist_repaired_bond(evidence.owner)
            else:
                self._persist_repaired_bond(None)
        return bonded

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
        verified_owner: BondOwner | None = None
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
                    source = client_source(client)
                    path = async_path_for_source(self.hass, source) if source else None
                    if path is not None:
                        verified_owner = BondOwner.from_path(path)
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
                        self._persist_repaired_bond(verified_owner)
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
    if issue_id == COMBINE_BEDS_ISSUE_ID:
        return CombineBedsRepairFlow()

    payload = data or {}
    evidence: BondEvidence | None = None
    raw_status = payload.get("evidence_status")
    status: BondVerificationStatus | None = None
    if isinstance(raw_status, str):
        try:
            status = BondVerificationStatus(raw_status)
        except ValueError:
            pass
    if status is not None:
        raw_transport = payload.get("evidence_transport")
        transport = TransportClass.UNKNOWN
        if isinstance(raw_transport, str):
            try:
                transport = TransportClass(raw_transport)
            except ValueError:
                pass
        observed_at = payload.get("evidence_observed_at")
        evidence = BondEvidence(
            status=status,
            owner=BondOwner(
                transport=transport,
                source=payload.get("evidence_source"),
                adapter=payload.get("evidence_adapter"),
            ),
            operation="pairing_required_issue",
            observed_at=(
                observed_at
                if isinstance(observed_at, str)
                else datetime.now(UTC).isoformat()
            ),
        )
    return PairingRequiredRepairFlow(
        address=payload.get("address", ""),
        name=payload.get("name", "your bed"),
        entry_id=payload.get("entry_id"),
        issue_data=payload,
        evidence=evidence,
    )
