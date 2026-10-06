"""Evidence-backed profile suggestions, independent of the one-time upgrade review.

Observe existing connections only. A rule identifies a possible improvement,
never permission to switch protocols. Decisions live with the physical address
so reloads, upgrades and pairing do not reset them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.components.repairs.const import FlowType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType, UnknownFlow
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector

from .app_state_store import app_state_store
from .const import (
    ADJUSTABLE_LUMBAR_VARIANT_STAR,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_STARCODE_ABM5_4,
    CONF_BED_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    VARIANT_AUTO,
)
from .detection import detect_bed_type_detailed
from .pairing import effective_child_data, get_child, is_paired
from .profile_review import choice_label

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

ISSUE_PREFIX: Final = "profile_recommendation_"
_WATCHES: Final = f"{DOMAIN}_profile_recommendations"
_SLOT: Final = "profile_recommendations"


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A stable decision key and the user-facing explanation's translation key."""

    rule: str
    current: str
    suggested: str


def recommend_profile(
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
        or re.fullmatch(r"Star254202[0-9]{6}", info.name, re.IGNORECASE) is None
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

    @callback
    def refresh(self, info: bluetooth.BluetoothServiceInfoBleak | None = None) -> None:
        """Re-evaluate observed evidence without reading or writing the bed."""
        if info is None:
            info = bluetooth.async_last_service_info(
                self.hass, self.coordinator.address, connectable=True
            )
        if self.side is not None and get_child(self.entry.data, self.side) is None:
            self.recommendation = None
            self._last_evidence = None
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
            return
        data = (
            effective_child_data(self.entry.data, self.side, self.entry.options)
            if self.side is not None
            else {**self.entry.data, **self.entry.options}
        )
        # Keep observations over an idle disconnect; an offline capability
        # controller has not read the manufacturer. A later connection replaces
        # this evidence even when its manufacturer read fails or changes.
        controller = self.coordinator.controller
        if controller is not None and self.coordinator.is_connected:
            self._protocol_state = controller.protocol_diagnostics
        evidence = (
            data.get(CONF_BED_TYPE),
            data.get(CONF_PROTOCOL_VARIANT),
            data.get(CONF_ADDRESS),
            (
                info.address,
                info.name,
                tuple(info.service_uuids),
                dict(info.manufacturer_data),
                dict(info.service_data),
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
                if data.get(CONF_ADDRESS) == self.coordinator.address
                and info is not None
                and info.address == self.coordinator.address
                else None
            )
        recommendation = self.recommendation
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
            translation_key=recommendation.rule,
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
            "current": choice_label(self.recommendation.current),
            "suggested": choice_label(self.recommendation.suggested),
        }

    async def async_keep(self, recommendation: Recommendation) -> None:
        """Persist the exact recommendation before closing its notice."""
        store = app_state_store(self.hass, self.coordinator.address)
        decisions = {**await store.async_slot(_SLOT), recommendation.rule: True}
        await store.async_write(_SLOT, decisions)
        self.dismissed = decisions
        self.refresh()

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
            await self.async_keep(self.recommendation)

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
    for side, coordinator in coordinators:
        if coordinator.bed_type != BED_TYPE_ADJUSTABLE_LUMBAR:
            continue
        decisions = await app_state_store(hass, coordinator.address).async_slot(_SLOT)
        watch = ProfileRecommendationWatch(hass, entry, coordinator, side, decisions)
        _watches(hass)[watch.issue_id] = watch
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
                return self.async_abort(
                    reason="review_started", next_flow=(FlowType.OPTIONS_FLOW, result["flow_id"])
                )
            return self.async_abort(reason="recommendation_changed")
        return self.async_show_form(
            step_id="paired" if is_paired(watch.entry.data) else "init",
            description_placeholders=watch.placeholders(),
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["review", "keep"],
                            translation_key="profile_recommendation_action",
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
