"""Evidence-backed profile suggestions, independent of the one-time upgrade review.

Observe existing connections only. A rule identifies a possible improvement,
never permission to switch protocols. Decisions live with the physical address
so reloads, upgrades and pairing do not reset them.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Final, Literal

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.components.repairs.const import FlowType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType, UnknownFlow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector

from .app_state_store import app_state_store
from .const import (
    ADJUSTABLE_LUMBAR_VARIANT_STAR,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_KEESON,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_STARCODE_ABM5_4,
    CONF_BED_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DOMAIN,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_KSBT04C,
    KEESON_VARIANT_KSBT_CR,
    LEGACY_BED_TYPE_MAPPING,
    NORDIC_UART_SERVICE_UUID,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTE_BT6500,
    RICHMAT_REMOTE_LP_QRRM,
    RICHMAT_REMOTES,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
)
from .detection import (
    APP_VARIANT_CHOICES,
    bed_type_choice,
    detect_bed_type_detailed,
    detect_richmat_remote_from_name,
    keeson_variant_from_device_name,
)
from .pairing import effective_child_data, get_child, is_paired
from .profile_decisions import (
    PROFILE_DECISIONS_SLOT,
    async_record_profile_decision,
    decision_timestamp,
    profile_selection,
)
from .profile_review import (
    async_clear_profile_review_issue,
    async_refresh_profile_review_issue,
    choice_label,
    profile_review_mark,
    related_app_choices,
)
from .validators import get_variants_for_bed_type

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

ISSUE_PREFIX: Final = "profile_recommendation_"
_WATCHES: Final = f"{DOMAIN}_profile_recommendations"
_SLOT: Final = PROFILE_DECISIONS_SLOT
_REMOTE_PREFIX: Final = "richmat_remote:"
_TEMPUR_PROCESSOR_RULE: Final = "tempur_sleeptracker_processor"
# The companion processor profile is registered independently by PR #684.
_SLEEPTRACKER_PROFILE: Final = "sleeptracker"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A stable decision key and the user-facing explanation's translation key."""

    rule: str
    current: str
    suggested: str | None
    choices: tuple[str, ...] = ()
    translation_key: str = "lumbar_star254202_box25"


def _recommendation_label(choice: str) -> str:
    """Label app selector values and ordinary Configure protocol variants."""
    if choice.startswith(_REMOTE_PREFIX):
        return f"Richmat remote, {RICHMAT_REMOTES[choice.removeprefix(_REMOTE_PREFIX)]}"
    bed_type, separator, variant = choice.partition(":")
    if (bed_type, variant) in APP_VARIANT_CHOICES:
        return choice_label(choice)
    variants = get_variants_for_bed_type(bed_type) or {}
    if separator and variant in variants:
        return f"{choice_label(bed_type)}, {variants[variant]}"
    return choice_label(choice)


def _variant_review(bed_type: str, variant: str, observed: str) -> Recommendation:
    """Offer existing variants without submitting a non-app selector value."""
    choices = (f"{bed_type}:{VARIANT_AUTO}", f"{bed_type}:{observed}")
    identity = repr((bed_type, variant, choices)).encode()
    return Recommendation(
        f"profile_variant_{sha256(identity).hexdigest()[:20]}",
        f"{bed_type}:{variant}",
        None,
        choices,
        "profile_ambiguous",
    )


def _reported_recommendation(
    data: Mapping[str, object],
    info: bluetooth.BluetoothServiceInfoBleak | None,
    protocol_state: Mapping[str, object],
) -> Recommendation | None:
    """Match only the user-confirmed identity in #670, not every Star/BOX25 bed.

    The accepted row054 report proves the current profile's table selection.
    #670 adds physical evidence for numbered memory on the suggested profile.
    See docs/design/profile-recommendations.md for the limits of that evidence.
    """
    if (
        data.get(CONF_BED_TYPE) != BED_TYPE_ADJUSTABLE_LUMBAR
        or data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
        not in (None, VARIANT_AUTO, ADJUSTABLE_LUMBAR_VARIANT_STAR)
        or info is None
        or re.fullmatch(r"Star254202[0-9]{6}", info.name or "", re.IGNORECASE) is None
        or protocol_state.get("adjustable_lumbar_branch") != "star"
        or protocol_state.get("adjustable_lumbar_table") != "35_22_01"
        or protocol_state.get("adjustable_lumbar_manufacturer") != "53 54 41 52"
    ):
        return None
    detected = detect_bed_type_detailed(info)
    if (
        detected.bed_type != BED_TYPE_SLEEPYS_BOX25
        or detected.requires_characteristic_check
        or set(detected.ambiguous_types or ()) - {BED_TYPE_STARCODE_ABM5_4}
    ):
        return None
    # This key changes only for materially different evidence, not releases,
    # RSSI, serial suffixes, display names or auto/explicit Star selection.
    return Recommendation(
        "lumbar_star254202_box25", BED_TYPE_ADJUSTABLE_LUMBAR, BED_TYPE_SLEEPYS_BOX25
    )


def recommend_profile(
    data: Mapping[str, object],
    info: bluetooth.BluetoothServiceInfoBleak | None,
    protocol_state: Mapping[str, object],
) -> Recommendation | None:
    """Assess any configured route using existing detection and app metadata.

    Detection confidence ranks known matches; it is not a probability of correct
    controls. Ambiguous routes therefore offer review without choosing a winner.
    """
    if info is None:
        return None
    if (
        _SLEEPTRACKER_PROFILE in SUPPORTED_BED_TYPES
        and data.get(CONF_BED_TYPE) == BED_TYPE_KEESON
        and data.get(CONF_PROTOCOL_VARIANT) == KEESON_VARIANT_ADJUSTABLE_LITE
        and re.fullmatch(r"KSSF05C[0-9]{9}", info.name or "", re.IGNORECASE) is not None
        and NORDIC_UART_SERVICE_UUID in {uuid.lower() for uuid in info.service_uuids or ()}
    ):
        # #681 confirms this compatibility setup, not an app or endpoint identity
        # for every receiver with this name. Ask about the app and guide adding
        # its separate processor; never preselect JSON for the UART address.
        return Recommendation(
            _TEMPUR_PROCESSOR_RULE,
            bed_type_choice(BED_TYPE_KEESON, KEESON_VARIANT_ADJUSTABLE_LITE),
            None,
            (_SLEEPTRACKER_PROFILE,),
            _TEMPUR_PROCESSOR_RULE,
        )
    reported = _reported_recommendation(data, info, protocol_state)
    if reported is not None:
        return reported
    bed_type = data.get(CONF_BED_TYPE)
    variant = data.get(CONF_PROTOCOL_VARIANT)
    if not isinstance(bed_type, str) or bed_type not in SUPPORTED_BED_TYPES:
        return None
    current = bed_type_choice(bed_type, variant if isinstance(variant, str) else None)
    detected = detect_bed_type_detailed(info)
    if detected.bed_type not in SUPPORTED_BED_TYPES or detected.confidence < 0.6:
        return None
    assert detected.bed_type is not None
    if bed_type == detected.bed_type:
        if (
            bed_type == BED_TYPE_OCTO
            and variant == OCTO_VARIANT_STANDARD
            and "uuid:octo_star2" in detected.signals
        ):
            return _variant_review(bed_type, OCTO_VARIANT_STANDARD, OCTO_VARIANT_STAR2)
        if (
            bed_type == BED_TYPE_KEESON
            and variant in {KEESON_VARIANT_KSBT, KEESON_VARIANT_KSBT_CR, KEESON_VARIANT_KSBT04C}
            and (observed := keeson_variant_from_device_name(info.name)) is not None
            and observed != variant
        ):
            return _variant_review(bed_type, str(variant), observed)
    # A bare shared service is not enough to question a configured bed. Name,
    # manufacturer or a high-confidence dedicated signature must corroborate it.
    if detected.confidence < 0.9 and not any(
        signal.startswith(("name:", "manufacturer", "mac:")) for signal in detected.signals
    ):
        return None
    matches = {detected.bed_type, *(detected.ambiguous_types or ())}
    apps = related_app_choices(
        detected.bed_type, variant if bed_type == detected.bed_type else VARIANT_AUTO
    )
    if current in apps or (current != bed_type and bed_type in matches):
        # An explicitly selected app already resolves this generic identity.
        return None
    if bed_type in matches and bed_type != detected.bed_type:
        return None  # Detection explicitly accepts the selected alternative.
    if variant in (None, VARIANT_AUTO) and (
        LEGACY_BED_TYPE_MAPPING.get(bed_type, bed_type)
        == LEGACY_BED_TYPE_MAPPING.get(detected.bed_type, detected.bed_type)
        and bed_type != detected.bed_type
    ):
        return None  # Existing aliases already use the same protocol route.
    remote_choices: set[str] = set()
    if (
        bed_type == detected.bed_type == BED_TYPE_RICHMAT
        and detect_richmat_remote_from_name(info.name) == "qrrm"
        and str(data.get(CONF_RICHMAT_REMOTE) or RICHMAT_REMOTE_AUTO).lower()
        in {RICHMAT_REMOTE_AUTO, "qrrm"}
    ):
        # QRRM identifies neither layout. #194 and #504 confirm these existing
        # surfaces on QRRM receivers; ask the user to compare physical controls.
        remote_choices = {
            f"{_REMOTE_PREFIX}{RICHMAT_REMOTE_BT6500}",
            f"{_REMOTE_PREFIX}{RICHMAT_REMOTE_LP_QRRM}",
        }
    choices = tuple(
        sorted(
            choice
            for choice in {*matches, *apps, *remote_choices}
            if choice != current
            and LEGACY_BED_TYPE_MAPPING.get(choice, choice)
            != LEGACY_BED_TYPE_MAPPING.get(bed_type, bed_type)
            and (
                choice in SUPPORTED_BED_TYPES
                or choice in remote_choices
                or any(choice == f"{bed}:{app}" for bed, app in APP_VARIANT_CHOICES)
            )
        )
    )
    if not choices:
        return None
    suggested = (
        detected.bed_type
        if bed_type != detected.bed_type
        and detected.confidence >= 0.9
        and not detected.ambiguous_types
        and not detected.requires_characteristic_check
        and not apps
        else None
    )
    kind = "profile_mismatch" if suggested else "profile_ambiguous"
    # Dismissals change only with the selected route/variant or available choices.
    identity = repr((kind, bed_type, variant or VARIANT_AUTO, choices)).encode()
    return Recommendation(
        f"{kind}_{sha256(identity).hexdigest()[:20]}", current, suggested, choices, kind
    )


@callback
def has_profile_assessment(hass: HomeAssistant, entry_id: str) -> bool:
    """Avoid a duplicate upgrade notice, including after keeping this assessment."""
    relevant = [
        watch
        for watch in _watches(hass).values()
        if watch.entry.entry_id == entry_id
        and (watch.side is None or get_child(watch.entry.data, watch.side) is not None)
        and watch.upgrade_review_key is not None
    ]
    return bool(relevant) and all(
        watch.recommendation is not None or watch.dismissed.get(watch.upgrade_review_key or "")
        for watch in relevant
    )


def _upgrade_review_key(data: Mapping[str, object]) -> str | None:
    """Identify the upgrade review an explicit decision also confirms."""
    profile = {
        CONF_BED_TYPE: data.get(CONF_BED_TYPE),
        CONF_PROTOCOL_VARIANT: data.get(CONF_PROTOCOL_VARIANT),
    }
    mark = profile_review_mark(profile)
    if mark is None:
        return None
    choices = tuple(
        sorted(related_app_choices(data.get(CONF_BED_TYPE), data.get(CONF_PROTOCOL_VARIANT)))
    )
    identity = repr((mark, choices)).encode()
    return f"upgrade_review_{sha256(identity).hexdigest()[:20]}"


def _watches(hass: HomeAssistant) -> dict[str, ProfileRecommendationWatch]:
    return hass.data.setdefault(_WATCHES, {})


class ProfileRecommendationWatch:
    """Observe one physical bed and retain its explicit dismissal decisions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: AdjustableBedCoordinator,
        side: str | None,
        dismissed: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.side = side
        self.issue_id = f"{ISSUE_PREFIX}{entry.entry_id}_{side or 'standalone'}"
        self.dismissed = dismissed
        self.recommendation: Recommendation | None = None
        self._protocol_state: Mapping[str, object] = {}
        self._last_evidence: object = None
        self._observed_name = ""
        self._last_info: bluetooth.BluetoothServiceInfoBleak | None = None
        self.review_flow_id: str | None = None
        self.review_recommendation: Recommendation | None = None
        self.review_profile: dict[str, str] | None = None

    @property
    def profile_data(self) -> Mapping[str, object]:
        """Return this physical bed's effective configuration."""
        return (
            effective_child_data(self.entry.data, self.side, self.entry.options)
            if self.side is not None
            else {**self.entry.data, **self.entry.options}
        )

    @property
    def upgrade_review_key(self) -> str | None:
        return _upgrade_review_key(self.profile_data)

    @callback
    def refresh(self, info: bluetooth.BluetoothServiceInfoBleak | None = None) -> None:
        """Re-evaluate observed evidence without reading or writing the bed."""
        if info is None:
            info = bluetooth.async_last_service_info(
                self.hass, self.coordinator.address, connectable=True
            )
            if info is None:
                info = self._last_info
        if info is not None and info.address.upper() == self.coordinator.address.upper():
            self._last_info = info
        if self.side is not None and get_child(self.entry.data, self.side) is None:
            self.recommendation = None
            self._last_evidence = None
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
            return
        data = self.profile_data
        self._observed_name = (info.name if info is not None else None) or self.coordinator.address
        # Keep observations over an idle disconnect; an offline capability
        # controller has not read the manufacturer. A later connection replaces
        # this evidence even when its manufacturer read fails or changes.
        controller = self.coordinator.controller
        if controller is not None and self.coordinator.is_connected:
            self._protocol_state = controller.protocol_diagnostics
        evidence = (
            data.get(CONF_BED_TYPE),
            data.get(CONF_PROTOCOL_VARIANT),
            data.get(CONF_RICHMAT_REMOTE),
            data.get(CONF_ADDRESS),
            (
                info.address,
                info.name,
                tuple(info.service_uuids or ()),
                dict(info.manufacturer_data or {}),
                dict(info.service_data or {}),
            )
            if info is not None
            else None,
            dict(self._protocol_state),
        )
        # Detection logs its matches. Do not re-run it for RSSI-only updates or
        # repeated advertisements, and do not use another side's cached identity.
        if evidence != self._last_evidence:
            self._last_evidence = evidence
            self.recommendation = (
                recommend_profile(data, info, self._protocol_state)
                if isinstance(data.get(CONF_ADDRESS), str)
                and str(data[CONF_ADDRESS]).upper() == self.coordinator.address.upper()
                and info is not None
                and info.address.upper() == self.coordinator.address.upper()
                else None
            )
        recommendation = self.recommendation
        if has_profile_assessment(self.hass, self.entry.entry_id):
            async_clear_profile_review_issue(self.hass, self.entry.entry_id)
        else:
            async_refresh_profile_review_issue(self.hass, self.entry)
        if recommendation is None or self.dismissed.get(recommendation.rule):
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=recommendation.translation_key,
            translation_placeholders=self.placeholders(),
            data={"rule": recommendation.rule},
        )

    def placeholders(self) -> dict[str, str]:
        """Name the physical side rather than implying the whole pair should switch."""
        assert self.recommendation is not None
        return {
            "name": self.entry.title,
            "target": f"{self.entry.title} ({self.side})" if self.side else self.entry.title,
            "side": self.side or "",
            "address": self.coordinator.address,
            "bluetooth_name": self._observed_name,
            "current": _recommendation_label(self.recommendation.current),
            "suggested": choice_label(self.recommendation.suggested)
            if self.recommendation.suggested
            else "",
            "choices": "\n".join(
                f"- {_recommendation_label(choice)}" for choice in self.recommendation.choices
            ),
            "pair_action": "Split into two beds" if self.side else "Restore standalone controls",
            "processor_guide_url": (
                "https://github.com/kristofferR/ha-adjustable-bed/blob/main/docs/beds/sleeptracker.md"
            ),
        }

    async def async_keep(
        self, recommendation: Recommendation, *, source: Literal["keep", "ignore"] = "keep"
    ) -> None:
        """Persist the exact recommendation before closing its notice."""
        await self.async_record_decision(
            recommendation, source=source, selected_data=self.profile_data
        )
        self.refresh()

    async def async_record_decision(
        self,
        recommendation: Recommendation,
        *,
        source: Literal["keep", "ignore", "configure"],
        selected_data: Mapping[str, object],
        previous_profile: dict[str, str] | None = None,
        confirmed_rules: tuple[str, ...] = (),
        defer_on_error: bool = False,
    ) -> None:
        """Retain the original suggestion even when the new profile needs no notice."""
        previous = (
            previous_profile
            if previous_profile is not None
            else profile_selection(self.profile_data)
        )
        selected = profile_selection(selected_data)
        rules = [recommendation.rule, *confirmed_rules]
        if (key := _upgrade_review_key(selected_data)) is not None:
            rules.append(key)
        self.dismissed = await async_record_profile_decision(
            self.hass,
            self.coordinator.address,
            {
                "decided_at": decision_timestamp(),
                "decision": "accepted" if selected != previous else "dismissed",
                "source": source,
                "rule": recommendation.rule,
                "current": recommendation.current,
                "suggested": recommendation.suggested,
                "choices": list(recommendation.choices),
                "previous_profile": previous,
                "selected_profile": selected,
            },
            rules,
            defer_on_error=defer_on_error,
        )

    @callback
    def seen(self, info: bluetooth.BluetoothServiceInfoBleak, _: bluetooth.BluetoothChange) -> None:
        self.refresh(info)

    @callback
    def connected(self, connected: bool) -> None:
        if connected:
            self.refresh()

    async def async_issue_updated(self, event: Event[ir.EventIssueRegistryUpdatedData]) -> None:
        """HA's Ignore action also means keep, including across future HA versions."""
        if event.data["domain"] != DOMAIN or event.data["issue_id"] != self.issue_id:
            return
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        if issue is not None and issue.dismissed_version and self.recommendation is not None:
            try:
                await self.async_keep(self.recommendation, source="ignore")
            except OSError:
                _LOGGER.warning(
                    "Unable to save ignored profile recommendation; restoring notice", exc_info=True
                )
                # HA ignored the issue before firing this event. Undo that state
                # so the user can retry; Keep already exposes a retry form.
                if ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id) is not None:
                    ir.async_ignore_issue(self.hass, DOMAIN, self.issue_id, False)

    @callback
    def unload(self) -> None:
        _watches(self.hass).pop(self.issue_id, None)
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)


async def async_watch_profile_recommendations(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinators: Iterable[tuple[str | None, AdjustableBedCoordinator]],
) -> None:
    """Check after setup and on normal connections or passive advertisements."""
    watches: list[ProfileRecommendationWatch] = []
    for side, coordinator in coordinators:
        decisions = await app_state_store(hass, coordinator.address).async_slot(_SLOT)
        watch = ProfileRecommendationWatch(hass, entry, coordinator, side, decisions)
        _watches(hass)[watch.issue_id] = watch
        watches.append(watch)
    for watch in watches:
        coordinator = watch.coordinator
        entry.async_on_unload(watch.unload)
        entry.async_on_unload(coordinator.register_connection_state_callback(watch.connected))
        entry.async_on_unload(
            bluetooth.async_register_callback(
                hass,
                watch.seen,
                bluetooth.BluetoothCallbackMatcher(address=coordinator.address),
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )
        entry.async_on_unload(
            hass.bus.async_listen(
                ir.EVENT_REPAIRS_ISSUE_REGISTRY_UPDATED, watch.async_issue_updated
            )
        )
        watch.refresh()


async def async_confirm_profile_review(
    hass: HomeAssistant, entry: ConfigEntry, flow_id: str, data: Mapping[str, object]
) -> None:
    """A saved Repairs handoff confirms the selected route, including ambiguity.

    Cancellation never reaches this hook. Keep dismissal separate from options
    so no confirmation flag leaks into paired-side configuration.
    """
    for watch in tuple(_watches(hass).values()):
        if (
            watch.entry is not entry
            or watch.review_flow_id != flow_id
            or watch.side is not None
            or watch.review_recommendation is None
            or watch.review_profile is None
            or not isinstance(data.get(CONF_ADDRESS), str)
            or str(data[CONF_ADDRESS]).upper() != watch.coordinator.address.upper()
        ):
            continue
        recommendation = recommend_profile(
            data,
            watch._last_info,
            watch._protocol_state
            if data.get(CONF_BED_TYPE) == watch.review_profile.get(CONF_BED_TYPE)
            else {},
        )
        await watch.async_record_decision(
            watch.review_recommendation,
            source="configure",
            selected_data=data,
            previous_profile=watch.review_profile,
            confirmed_rules=(recommendation.rule,) if recommendation is not None else (),
            defer_on_error=True,
        )


@callback
def async_complete_profile_review(hass: HomeAssistant, entry: ConfigEntry, flow_id: str) -> None:
    """Retire the notice even when an unchanged save fires no update listener."""
    for watch in tuple(_watches(hass).values()):
        if watch.entry is entry and watch.review_flow_id == flow_id:
            watch.review_flow_id = None
            watch.review_recommendation = None
            watch.review_profile = None
            watch.refresh()


class ProfileRecommendationRepairFlow(RepairsFlow):
    """Review a suggestion; options owns validation and the final confirmation."""

    def __init__(self, issue_id: str, rule: str) -> None:
        self._issue_id = issue_id
        self._rule = rule

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        watch = _watches(self.hass).get(self._issue_id)
        if watch is None:
            return self.async_abort(reason="recommendation_changed")
        watch.refresh()
        recommendation = watch.recommendation
        if (
            recommendation is None
            or recommendation.rule != self._rule
            or watch.dismissed.get(recommendation.rule)
        ):
            return self.async_abort(reason="recommendation_changed")
        action = (user_input or {}).get("action")
        errors: dict[str, str] = {}
        if action == "keep":
            try:
                await watch.async_keep(recommendation)
            except OSError:
                errors["base"] = "save_failed"
            else:
                return self.async_create_entry(title="", data={})
        elif action == "review":
            if recommendation.rule == _TEMPUR_PROCESSOR_RULE:
                return self.async_show_form(
                    step_id="processor",
                    description_placeholders=watch.placeholders(),
                )
            if is_paired(watch.entry.data):
                # Existing per-side profile restrictions require an explicit split.
                # Open the menu; never split or change either side from this repair.
                result = await self.hass.config_entries.options.async_init(watch.entry.entry_id)
            else:
                manager = self.hass.config_entries.options
                original_data, original_options = watch.entry.data, watch.entry.options
                result = await manager.async_init(watch.entry.entry_id)
                flow_id = result["flow_id"]
                try:
                    result = await manager.async_configure(flow_id, {"next_step_id": "settings"})
                    watch.refresh()
                    if (
                        _watches(self.hass).get(self._issue_id) is not watch
                        or watch.entry.data != original_data
                        or watch.entry.options != original_options
                        or watch.recommendation != recommendation
                        or watch.dismissed.get(recommendation.rule)
                    ):
                        manager.async_abort(flow_id)
                        return self.async_abort(reason="recommendation_changed")
                    # A bed-type change only re-renders settings. The user must
                    # submit that form to apply it, exactly as in Configure.
                    if recommendation.suggested is not None:
                        result = await manager.async_configure(
                            flow_id, {CONF_BED_TYPE: recommendation.suggested}
                        )
                except BaseException:
                    try:
                        manager.async_abort(flow_id)
                    except UnknownFlow:
                        pass
                    raise
            if result.get("type") in (FlowResultType.FORM, FlowResultType.MENU):
                watch.review_flow_id = result["flow_id"]
                watch.review_recommendation = recommendation
                watch.review_profile = profile_selection(watch.profile_data)
                return self.async_abort(
                    reason="review_started", next_flow=(FlowType.OPTIONS_FLOW, result["flow_id"])
                )
            return self.async_abort(reason="recommendation_changed")
        # Use HA's schema class across its 2026.9/2026.10 validation-engine change.
        schema_type = type(cv.PLATFORM_SCHEMA)
        return self.async_show_form(
            step_id="paired" if is_paired(watch.entry.data) else "init",
            description_placeholders=watch.placeholders(),
            errors=errors,
            data_schema=schema_type(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["review", "keep"],
                            translation_key=(
                                "tempur_processor_action"
                                if recommendation.rule == _TEMPUR_PROCESSOR_RULE
                                else "profile_recommendation_action"
                            ),
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_paired(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        return await self.async_step_init(user_input)

    async def async_step_processor(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Acknowledge setup guidance, without claiming the processor was added."""
        return await self.async_step_init(
            {"action": "keep" if user_input is not None else "review"}
        )
