"""Ask beds set up before the explicit app profiles, once, whether one fits.

v4.0.2 had none of the app profiles, so an older entry keeps the generic route
it was set up with, even where an app profile now controls the bed correctly.
The minor-version 3 migration marks each older entry whose route gained app
profiles: ``CONF_PROFILE_REVIEW_PENDING`` stores the route it reviews. While
the entry still uses that route, setup raises one fixable issue per entry
listing only the relevant apps:

- the app profiles whose beds v4.0.2 put on the stored route and that
  advertisements cannot tell apart (``_ROUTE_APPS``), and
- the app candidates detection lists for this bed's latest advertisement,
  plus a route detection now picks instead of the stored v4.0.2 one
  (``_DETECTION_DRIFT``).

Switching submits the chosen app to the options flow, so the change is
validated and stored exactly as Configure stores it, keeping device and entity
IDs. Vibradorm hands off to its managed, verified reconfigure wizard; closing
that wizard leaves the review pending. Other apps with their own settings are
left to Configure. Keeping the current
configuration, finishing the flow in any other way, or any later change of bed
type or variant removes the mark; entries created later never get it. FurniMove is not offered: its own repairs cover the
routes its handsets used.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.components.repairs.const import FlowType
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType, UnknownFlow
from homeassistant.helpers import selector
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .const import (
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COOLBASE,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_KEESON,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MOTION_BED,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REMACRO,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
    KEESON_VARIANT_SIMON_LI,
    KEESON_VARIANT_SINO,
    PAIR_SIDES,
    REMACRO_VARIANT_JEROMES,
    REMACRO_VARIANT_THE_BRICK,
    RICHMAT_MH_BED_TYPES,
    VARIANT_AUTO,
    ZSERIES_VARIANT_Z230,
    ZSERIES_VARIANT_Z280,
)
from .detection import (
    APP_VARIANT_CHOICES,
    BED_TYPE_DISPLAY_NAMES,
    bed_type_choice,
    detect_bed_type_detailed,
    resolve_bed_type_choice,
)
from .pairing import effective_child_data, get_child, is_paired
from .validators import get_variants_for_bed_type

ISSUE_PREFIX: Final = "app_profile_review_"
_REVIEW: Final = "app_profile_review"
_MATCH: Final = "app_profile_match"
_KEEP: Final = "keep"
# Detection must be this sure before it may contradict a stored route.
_DRIFT_MIN_CONFIDENCE: Final = 0.7


@dataclass(frozen=True, slots=True)
class _RouteApps:
    """App profiles whose beds v4.0.2 put on one of these routes."""

    bed_types: frozenset[str]
    # Stored variants this applies to (v4.0.2 stored "auto" by default); None
    # for every variant.
    variants: frozenset[str] | None
    # Bed-type selector values: ``bed_type`` or ``bed_type:variant``.
    choices: tuple[str, ...]


def _keeson(*variants: str) -> tuple[str, ...]:
    return tuple(bed_type_choice(BED_TYPE_KEESON, variant) for variant in variants)


# Same Keeson frame, different keys and release timing (row060).
_OKIN_SEATING_APPS: Final = _keeson(
    KEESON_VARIANT_SIMON_LI, KEESON_VARIANT_HEAL_EVERY_NIGHT, KEESON_VARIANT_OKIN_SEATING
)
# ORE-named bases; v4.0.2's sino label named Dynasty and INNOVA (row056, row059).
_ORE_APPS: Final = _keeson(
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_BEDSENSE_BASES,
)
# The app accepts base-i4 (Keeson Base) and base-i5 (Cool Base) names (row058).
_RESTONIC_APPS: Final = _keeson(KEESON_VARIANT_RESTONIC_A, KEESON_VARIANT_RESTONIC_B)
# Same 14-byte CST frame as the OKIN routes (serenity.md, row052).
_OKIN_BEDDING_APPS: Final = (
    BED_TYPE_SERENITY,
    BED_TYPE_TRANQUIL,
    bed_type_choice(BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z230),
    bed_type_choice(BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280),
)
_AUTO: Final = frozenset({VARIANT_AUTO})

_ROUTE_APPS: Final[tuple[_RouteApps, ...]] = (
    # Keeson auto ran KSBT for KSBT names and Base for other FFE5 beds.
    _RouteApps(
        frozenset({BED_TYPE_KEESON}),
        _AUTO,
        (*_keeson(KEESON_VARIANT_ADJUSTABLE_LITE), *_OKIN_SEATING_APPS, *_ORE_APPS, *_RESTONIC_APPS),
    ),
    _RouteApps(
        frozenset({BED_TYPE_KEESON}),
        frozenset({KEESON_VARIANT_BASE}),
        (*_OKIN_SEATING_APPS, *_ORE_APPS, *_RESTONIC_APPS),
    ),
    # Adjustable Lite's frames all exist in the KSBT profile (row051).
    _RouteApps(
        frozenset({BED_TYPE_KEESON}),
        frozenset({KEESON_VARIANT_KSBT}),
        _keeson(KEESON_VARIANT_ADJUSTABLE_LITE),
    ),
    _RouteApps(
        frozenset({BED_TYPE_KEESON}),
        frozenset({KEESON_VARIANT_SINO}),
        (*_OKIN_SEATING_APPS, *_ORE_APPS),
    ),
    # v4.0.2 labelled Okin ORE "Dynasty, INNOVA"; both apps use the Keeson frame.
    _RouteApps(
        frozenset({BED_TYPE_OKIN_ORE}),
        None,
        _keeson(KEESON_VARIANT_INNOVA, KEESON_VARIANT_DYNASTY_BASES),
    ),
    _RouteApps(frozenset({BED_TYPE_COOLBASE}), None, _RESTONIC_APPS),
    # okin-named 62741523 beds were Okimat, refined to Okin CST by GATT.
    _RouteApps(
        frozenset({BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID, BED_TYPE_OKIN_CST}),
        None,
        _OKIN_BEDDING_APPS,
    ),
    # v4.0.2 sent Simmons and Glory names, and Tranquil Sleep, to DewertOkin.
    _RouteApps(
        frozenset({BED_TYPE_DEWERTOKIN}),
        None,
        (BED_TYPE_SIMMONS, *_OKIN_BEDDING_APPS[1:]),
    ),
    # okin names on 62741523, and Star names on Nordic UART (row054).
    _RouteApps(
        frozenset(
            {
                BED_TYPE_OKIMAT,
                BED_TYPE_OKIN_UUID,
                BED_TYPE_OKIN_64BIT,
                BED_TYPE_OKIN_CB35,
                BED_TYPE_SLEEPYS_BOX25,
            }
        ),
        None,
        (BED_TYPE_ADJUSTABLE_LUMBAR,),
    ),
    # Shared OKIN FFE, CB24, Keeson and Richmat routes (row049).
    _RouteApps(
        frozenset({BED_TYPE_OKIN_FFE, BED_TYPE_OKIN_CB24, BED_TYPE_RICHMAT}),
        None,
        (BED_TYPE_SIMMONS,),
    ),
    _RouteApps(
        frozenset({BED_TYPE_KEESON}),
        frozenset({VARIANT_AUTO, KEESON_VARIANT_BASE}),
        (BED_TYPE_SIMMONS,),
    ),
    _RouteApps(frozenset({BED_TYPE_RICHMAT}), None, tuple(sorted(RICHMAT_MH_BED_TYPES))),
    _RouteApps(frozenset({BED_TYPE_LIMOSS}), None, (BED_TYPE_LIMOSS_REMOTE, BED_TYPE_FSM_RELAX)),
    _RouteApps(frozenset({BED_TYPE_VIBRADORM}), None, (BED_TYPE_VIBRADORM_APP, BED_TYPE_VMATBASIC)),
    # The Sleep Smart bed profile of the LOGICDATA app (row053).
    _RouteApps(frozenset({BED_TYPE_COMFORT_MOTION}), None, (BED_TYPE_LOGICDATA_APP,)),
    # v4.0.2 always used the Slumberland screens (remacro.md).
    _RouteApps(
        frozenset({BED_TYPE_REMACRO}),
        _AUTO,
        (
            bed_type_choice(BED_TYPE_REMACRO, REMACRO_VARIANT_THE_BRICK),
            bed_type_choice(BED_TYPE_REMACRO, REMACRO_VARIANT_JEROMES),
        ),
    ),
)

# Detection rules that now pick another primary route than v4.0.2 did for the
# same advertisement: detected bed type -> the stored types v4.0.2 chose.
# Cool Base matches "base-i5" anywhere in the name (row047 D40); v4.0.2 only
# matched the prefix, so the rest landed on the shared Keeson route.
_DETECTION_DRIFT: Final[dict[str, frozenset[str]]] = {
    BED_TYPE_COOLBASE: frozenset({BED_TYPE_KEESON}),
}

# App profiles detection lists as alternatives for an advertisement. They are
# offered only when detection still picks the stored route for this bed.
_ADVERTISED_APPS: Final = frozenset(
    {
        BED_TYPE_FSM_RELAX,
        BED_TYPE_MOTION_BED,
        BED_TYPE_STARCODE_ABM5_4,
        BED_TYPE_STARCODE_M5X5,
        BED_TYPE_VMATBASIC,
    }
)
# Routes whose advertisement can add an app above or drift to another route.
_ADVERTISED_ROUTES: Final = frozenset(
    {
        BED_TYPE_SOLACE,  # Motion Bed names
        BED_TYPE_OCTO,  # Motion Bed names on FFE0
        BED_TYPE_LIMOSS,  # FSM Relax names
        BED_TYPE_OKIN_CB35,  # Star names: AdjustableM5X4
        BED_TYPE_SLEEPYS_BOX25,  # Star names: AdjustableM5X4; STAR25: AdjustableM5X5
        BED_TYPE_VIBRADORM,  # V-MAT Basic manufacturer record
        *(stored for stored_types in _DETECTION_DRIFT.values() for stored in stored_types),
    }
)


def _is_app_choice(bed_type: str, variant: object) -> bool:
    """Return True when the stored variant already selects an app."""
    return isinstance(variant, str) and (bed_type, variant) in APP_VARIANT_CHOICES


def related_app_choices(bed_type: object, variant: object) -> list[str]:
    """Known app choices for a generic route, not proof of a better match."""
    if not isinstance(bed_type, str) or _is_app_choice(bed_type, variant):
        return []
    stored_variant = variant if isinstance(variant, str) else VARIANT_AUTO
    return [
        choice
        for route in _ROUTE_APPS
        if bed_type in route.bed_types and (route.variants is None or stored_variant in route.variants)
        for choice in route.choices
    ]


def _last_service_info(
    hass: HomeAssistant, address: str
) -> bluetooth.BluetoothServiceInfoBleak | None:
    for connectable in (True, False):
        info = bluetooth.async_last_service_info(hass, address, connectable=connectable)
        if info is not None:
            return info
    return None


@dataclass(frozen=True, slots=True)
class _Review:
    """The app profiles worth offering for an entry."""

    choices: tuple[str, ...]
    # The route detection now picks instead of the stored one, if any.
    drift: str | None = None
    # False while an advertisement that could add choices is not yet known.
    complete: bool = True


def _review_target(hass: HomeAssistant, data: Mapping[str, Any]) -> _Review:
    bed_type = data.get(CONF_BED_TYPE)
    choices = related_app_choices(bed_type, data.get(CONF_PROTOCOL_VARIANT))
    address = data.get(CONF_ADDRESS)
    if (
        bed_type not in _ADVERTISED_ROUTES
        or _is_app_choice(bed_type, data.get(CONF_PROTOCOL_VARIANT))
        or not isinstance(address, str)
    ):
        return _Review(tuple(choices))
    info = _last_service_info(hass, address)
    if info is None:
        return _Review(tuple(choices), complete=False)
    result = detect_bed_type_detailed(info)
    if result.bed_type == bed_type:
        choices.extend(app for app in result.ambiguous_types or () if app in _ADVERTISED_APPS)
        return _Review(tuple(choices))
    if (
        result.bed_type is not None
        and bed_type in _DETECTION_DRIFT.get(result.bed_type, frozenset())
        and result.confidence >= _DRIFT_MIN_CONFIDENCE
        and not result.requires_characteristic_check
    ):
        return _Review((result.bed_type, *choices), drift=result.bed_type)
    return _Review(tuple(choices))


def _targets(entry_data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the configuration of each physical bed the entry controls."""
    if not is_paired(entry_data):
        return [entry_data]
    return [
        effective_child_data(entry_data, side)
        for side in PAIR_SIDES
        if get_child(entry_data, side) is not None
    ]


def _sorted(choices: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(choices), key=lambda choice: choice_label(choice).lower()))


def _review(hass: HomeAssistant, entry_data: Mapping[str, Any]) -> _Review:
    reviews = [_review_target(hass, target) for target in _targets(entry_data)]
    drifts = {review.drift for review in reviews}
    drift = drifts.pop() if len(drifts) == 1 else None
    choices = _sorted(choice for review in reviews for choice in review.choices if choice != drift)
    complete = all(review.complete for review in reviews)
    if drift is None:
        return _Review(choices, complete=complete)
    # The detected route comes first; the issue names it when it is the only one.
    return _Review((drift, *choices), drift=drift if not choices else None, complete=complete)


def covers_profile_review(
    hass: HomeAssistant, data: Mapping[str, Any], presented_choices: Iterable[str]
) -> bool:
    """Confirm an upgrade review only when its candidates were all presented."""
    review = _review(hass, data)
    return (
        review.complete
        and bool(review.choices)
        and set(review.choices).issubset(presented_choices)
    )


def _route_signature(entry_data: Mapping[str, Any]) -> str:
    """Return the bed type and variant of every physical bed, in side order."""
    return "|".join(
        f"{target.get(CONF_BED_TYPE)}:{target.get(CONF_PROTOCOL_VARIANT) or VARIANT_AUTO}"
        for target in _targets(entry_data)
    )


def profile_review_mark(entry_data: Mapping[str, Any]) -> str | None:
    """Return the review mark for an older entry whose route gained app profiles."""
    if any(
        related_app_choices(target.get(CONF_BED_TYPE), target.get(CONF_PROTOCOL_VARIANT))
        or (
            target.get(CONF_BED_TYPE) in _ADVERTISED_ROUTES
            and not _is_app_choice(target[CONF_BED_TYPE], target.get(CONF_PROTOCOL_VARIANT))
        )
        for target in _targets(entry_data)
    ):
        return _route_signature(entry_data)
    return None


def _pending(entry_data: Mapping[str, Any]) -> bool:
    mark = entry_data.get(CONF_PROFILE_REVIEW_PENDING)
    return bool(mark) and mark == _route_signature(entry_data)


def choice_label(choice: str) -> str:
    """Return the bed-type selector label of a choice."""
    bed_type, variant = resolve_bed_type_choice(choice)
    if variant is not None:
        return APP_VARIANT_CHOICES[bed_type, variant]
    return BED_TYPE_DISPLAY_NAMES.get(bed_type, bed_type)


def _route_label(data: Mapping[str, Any]) -> str:
    bed_type = data.get(CONF_BED_TYPE)
    if not isinstance(bed_type, str):
        return "an unknown bed type"
    label = BED_TYPE_DISPLAY_NAMES.get(bed_type, bed_type)
    variant = data.get(CONF_PROTOCOL_VARIANT)
    variants = get_variants_for_bed_type(bed_type) or {}
    if isinstance(variant, str) and variant != VARIANT_AUTO and variant in variants:
        return f"{label}, {variants[variant]}"
    return label


def _issue_id(entry_id: str) -> str:
    return f"{ISSUE_PREFIX}{entry_id}"


def _placeholders(entry: ConfigEntry, choices: tuple[str, ...], app: str) -> dict[str, str]:
    return {
        "name": entry.title,
        "apps": "\n".join(f"- {choice_label(choice)}" for choice in choices),
        "app": choice_label(app),
        "current": _route_label(_targets(entry.data)[0]),
    }


@callback
def async_refresh_profile_review_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise, update or retire the entry's app profile review.

    Runs during setup before the update listener exists, so retiring the mark
    does not reload the entry.
    """
    from .profile_recommendations import has_profile_assessment

    issue_id = _issue_id(entry.entry_id)
    if has_profile_assessment(hass, entry.entry_id):
        async_delete_issue(hass, DOMAIN, issue_id)
        return
    if CONF_PROFILE_REVIEW_PENDING not in entry.data:
        async_delete_issue(hass, DOMAIN, issue_id)
        return
    if not _pending(entry.data):
        # The bed type or variant changed since the upgrade, through this
        # review or Configure: the user has chosen.
        async_delete_issue(hass, DOMAIN, issue_id)
        _clear_mark(hass, entry)
        return
    review = _review(hass, entry.data)
    if not review.choices:
        async_delete_issue(hass, DOMAIN, issue_id)
        if review.complete:
            _clear_mark(hass, entry)
        return
    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        is_persistent=False,
        severity=IssueSeverity.WARNING,
        translation_key=_MATCH if review.drift else _REVIEW,
        translation_placeholders=_placeholders(entry, review.choices, review.choices[0]),
        data={"entry_id": entry.entry_id},
    )


@callback
def async_clear_profile_review_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the review when its config entry is removed."""
    async_delete_issue(hass, DOMAIN, _issue_id(entry_id))


@callback
def _clear_mark(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {key: value for key, value in entry.data.items() if key != CONF_PROFILE_REVIEW_PENDING}
    hass.config_entries.async_update_entry(entry, data=data)


@callback
def async_keep_current_profile(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Record an explicit decision to keep the current setup."""
    _clear_mark(hass, entry)
    async_clear_profile_review_issue(hass, entry.entry_id)


# A bed type change re-renders the form once, and a variant can re-render it
# for its own fields; a form still open after this needs real input.
_MAX_OPTIONS_SUBMISSIONS: Final = 4


async def _async_switch_via_options(hass: HomeAssistant, entry: ConfigEntry, choice: str) -> bool:
    """Submit an app choice through the options flow; True once it is saved.

    Every other field keeps the value Configure shows, so the options flow
    applies its own validation, cleanup and pair guards. A form that reports
    an error, or still waits for input, is abandoned without saving anything.
    """
    manager = hass.config_entries.options
    result = await manager.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    try:
        result = await manager.async_configure(flow_id, {"next_step_id": "settings"})
        submission: dict[str, Any] = {CONF_BED_TYPE: choice}
        for _ in range(_MAX_OPTIONS_SUBMISSIONS):
            if result.get("type") is not FlowResultType.FORM or result.get("errors"):
                break
            result = await manager.async_configure(flow_id, submission)
            submission = {}
    finally:
        if result.get("type") is not FlowResultType.CREATE_ENTRY:
            try:
                manager.async_abort(flow_id)
            except UnknownFlow:
                pass
    return result.get("type") is FlowResultType.CREATE_ENTRY


def _needs_app_settings(choice: str) -> bool:
    """Return True for apps whose own settings this shared repair cannot collect."""
    from .config_flow import APP_SETTINGS_BED_TYPES

    return resolve_bed_type_choice(choice)[0] in APP_SETTINGS_BED_TYPES


class ProfileReviewRepairFlow(RepairsFlow):
    """Switch an older entry to one listed app profile, or keep it."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._choice: str | None = None

    def _entry(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or not _pending(entry.data):
            return None
        return entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="entry_missing")
        choices = _review(self.hass, entry.data).choices
        if not choices:
            return self._finish(entry)
        if any(target.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM for target in _targets(entry.data)):
            if (user_input or {}).get("choice") == _KEEP:
                return self._finish(entry)
            if (user_input or {}).get("choice") == "configure":
                result = await self.hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
                )
                if result.get("type") is not FlowResultType.FORM:
                    return self.async_abort(reason="vibradorm_setup_unavailable")
                return self.async_abort(
                    reason="vibradorm_setup_started",
                    next_flow=(FlowType.CONFIG_FLOW, result["flow_id"]),
                )
            return self.async_show_form(
                step_id="vibradorm",
                data_schema=vol.Schema({vol.Required("choice"): selector.SelectSelector(selector.SelectSelectorConfig(options=[selector.SelectOptionDict(value="configure", label="Choose my app and remote"), selector.SelectOptionDict(value=_KEEP, label="Keep current setup")], mode=selector.SelectSelectorMode.DROPDOWN))}),
            )
        if is_paired(entry.data):
            # App profiles are per physical bed and none supports paired
            # controls, so Configure refuses the switch until the pair is split.
            return await self.async_step_unpair()
        # Home Assistant opens the flow with the issue ID, not a choice.
        choice = (user_input or {}).get("choice")
        if choice == _KEEP:
            return self._finish(entry)
        if choice in choices:
            self._choice = choice
            if _needs_app_settings(choice) or not await _async_switch_via_options(
                self.hass, entry, choice
            ):
                return await self.async_step_configure()
            # The saved options reload the entry; its setup retires the mark
            # because the entry no longer uses the reviewed route.
            async_delete_issue(self.hass, DOMAIN, _issue_id(entry.entry_id))
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            description_placeholders=_placeholders(entry, choices, choices[0]),
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                *(
                                    selector.SelectOptionDict(value=value, label=choice_label(value))
                                    for value in choices
                                ),
                                selector.SelectOptionDict(
                                    value=_KEEP, label="Keep current configuration"
                                ),
                            ],
                            translation_key=_REVIEW,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_configure(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        """Point to Configure for an app this flow cannot apply by itself."""
        entry = self._entry()
        if entry is None or self._choice is None:
            return self.async_abort(reason="entry_missing")
        if user_input is not None:
            return self._finish(entry)
        return self.async_show_form(
            step_id="configure",
            description_placeholders=_placeholders(entry, (self._choice,), self._choice),
        )

    async def async_step_unpair(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        """Explain that a paired bed changes its app after the pair is split."""
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="entry_missing")
        choices = _review(self.hass, entry.data).choices
        if user_input is not None or not choices:
            return self._finish(entry)
        return self.async_show_form(
            step_id="unpair",
            description_placeholders=_placeholders(entry, choices, choices[0]),
        )

    def _finish(self, entry: ConfigEntry) -> RepairsFlowResult:
        """Record the answer so this entry is never asked again."""
        async_keep_current_profile(self.hass, entry)
        return self.async_create_entry(title="", data={})
