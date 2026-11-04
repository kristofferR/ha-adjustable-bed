"""Setup questions and owned generic fields, declared per profile (#779).

A profile declares the questions setup and Configure ask for it, and the
generic fields it sets itself, so no form shows them. One generic config-flow
step renders the questions; a dedicated step remains only for what data cannot
express (authentication sessions, bonding, product catalogs, pairing).

Declarations are keyed like a profile id (``profile_id.py``): ``bed_type``,
``bed_type:variant``, ``bed_type@app`` or ``bed_type:variant@app``. The most
specific key that matches a route wins.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .const import (
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_ADJUSTAMATTRESS,
    BED_TYPE_BEDSENSE,
    BED_TYPE_BF,
    BED_TYPE_CHERISH,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ESHINE,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_ISLEEP,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MOTION_BED,
    BED_TYPE_OCTO,
    BED_TYPE_OKIN_CST,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CLUSTER033_BED_TYPES,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    HAS_LIGHT_DEFAULTS,
    JIECANG_APP_LAYOUTS,
    JIECANG_APP_TRANSPORTS,
    KAIDI_VARIANT_FLOYD,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_MAXCOIL_UNA,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    RICHMAT_MH_BED_TYPES,
    STAR_ELEVATE_VARIANT_M1X12,
    SVANE_VARIANT_JENSEN_LINON,
)

# The generic fields a profile can own.
GENERIC_FIELDS: Final = frozenset(
    {
        CONF_MOTOR_COUNT,
        CONF_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROTOCOL_VARIANT,
    }
)
# The app fixes the layout and its own refresh interval.
_FIXED_LAYOUT: Final = frozenset({CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS})
# The app step defines every control and its held behavior.
_APP_DEFINED: Final = GENERIC_FIELDS
_ALWAYS_MASSAGE: Final = frozenset({CONF_HAS_MASSAGE})
# The pulse count stays visible: it bounds each HA movement at the app's cadence.
_NECTAR_MOVE: Final = _FIXED_LAYOUT | _ALWAYS_MASSAGE | {CONF_DISABLE_ANGLE_SENSING}

_OWNED_BY_BED_TYPE: Final[dict[str, frozenset[str]]] = {
    "ergomotion_4": _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    "gmmotor": GENERIC_FIELDS,
    "gmmotor_sleep_mm": GENERIC_FIELDS,
    "gmmotor_sleep_sxb": GENERIC_FIELDS,
    BED_TYPE_BF: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_CHERISH: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    **dict.fromkeys(CLUSTER033_BED_TYPES, _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT}),
    # OCTO motor layout comes from its advertised capability record, with an
    # OCTO-specific explicit override in the profile's own setup/options UI.
    BED_TYPE_OCTO: frozenset({CONF_MOTOR_COUNT}),
    "casper_remote": GENERIC_FIELDS,
    "casper_base": GENERIC_FIELDS - {CONF_PROTOCOL_VARIANT},
    "casper_sleep_mm": GENERIC_FIELDS,
    "casper_sleep_sxb": GENERIC_FIELDS,
    BED_TYPE_COMFORT_ENHANCEMENTS: _APP_DEFINED - {CONF_PROTOCOL_VARIANT, CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_ESHINE_OKIN: _APP_DEFINED - {CONF_PROTOCOL_VARIANT, CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_ESHINE: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_GOODVIBE: _APP_DEFINED - {CONF_PROTOCOL_VARIANT},
    BED_TYPE_HJBED: _APP_DEFINED - {CONF_PROTOCOL_VARIANT, CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_GLIDEAWAY_MOTION: _APP_DEFINED - {CONF_PROTOCOL_VARIANT, CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_ISLEEP: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_BEDSENSE: frozenset({CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING}),
    BED_TYPE_SERENITY: _FIXED_LAYOUT,
    BED_TYPE_TRANQUIL: _FIXED_LAYOUT,
    BED_TYPE_ZSERIES: _FIXED_LAYOUT,
    BED_TYPE_SIMMONS: _FIXED_LAYOUT,
    **dict.fromkeys(RICHMAT_MH_BED_TYPES, _FIXED_LAYOUT),
    BED_TYPE_LOGICDATA_AIR_PUMP: _FIXED_LAYOUT,
    # AHF has no massage. Motor count still sizes the legacy covers.
    BED_TYPE_TIMOTION_AHF: frozenset({CONF_HAS_MASSAGE}),
    # These apps always show their massage page.
    BED_TYPE_ADJUSTAMATTRESS: _FIXED_LAYOUT | {CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING},
    BED_TYPE_ADJUSTABLE_LUMBAR: _FIXED_LAYOUT | _ALWAYS_MASSAGE,
    BED_TYPE_STARCODE_ABM5_4: _FIXED_LAYOUT | _ALWAYS_MASSAGE,
    # The handset table sets the layout and massage; the receiver sets the protocol.
    BED_TYPE_FURNIMOVE: _FIXED_LAYOUT | {CONF_HAS_MASSAGE, CONF_PROTOCOL_VARIANT},
    BED_TYPE_STARCODE_M5X5: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_STARCODE_M1X12: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    # The app step asks for massage; the pulse count bounds a held control.
    BED_TYPE_FSM_RELAX: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_LIMOSS_REMOTE: _APP_DEFINED,
    BED_TYPE_VIBRADORM_APP: _APP_DEFINED,
    BED_TYPE_VMATBASIC: _APP_DEFINED,
    BED_TYPE_MOTION_BED: _APP_DEFINED,
    BED_TYPE_DOUBLESLEEP: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_SLEEPTRACKER: _APP_DEFINED,
    BED_TYPE_SLEEPYS_ELITE_APP: _APP_DEFINED,
    # The variant selects the Svane Remote app profile or Jensen LinOn.
    BED_TYPE_SVANE: _APP_DEFINED - {CONF_PROTOCOL_VARIANT},
    # The app's layout or model sets the axes and its own command cadence. The
    # Logicdata pulse count still bounds each held movement.
    BED_TYPE_MALOUF_APP: _FIXED_LAYOUT,
    BED_TYPE_LOGICDATA_APP: _FIXED_LAYOUT,
}
_OWNED_BY_VARIANT: Final[dict[tuple[str, str], frozenset[str]]] = {
    # Nectar Move fixes two axes, has massage, and uses its own refresh interval.
    (BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE): _NECTAR_MOVE,
    (BED_TYPE_KAIDI, KAIDI_VARIANT_FLOYD): _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT, CONF_MOTOR_PULSE_DELAY_MS},
    (BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON): frozenset(),
    (BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12): _FIXED_LAYOUT | {CONF_PROTOCOL_VARIANT},
    (BED_TYPE_KEESON, KEESON_VARIANT_AVANTI_BASES): frozenset(
        {CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING, CONF_MOTOR_PULSE_DELAY_MS}
    ),
    **{
        (BED_TYPE_KEESON, variant): _ALWAYS_MASSAGE
        for variant in (
            KEESON_VARIANT_INNOVA,
            KEESON_VARIANT_MAXCOIL_UNA,
            KEESON_VARIANT_DYNASTY_BASES,
            KEESON_VARIANT_AMERICANSTAR,
            KEESON_VARIANT_BEDSENSE_BASES,
            KEESON_VARIANT_HEAL_EVERY_NIGHT,
        )
    },
}




class _SetByProfile:
    """An owned field the profile sets from its answers or at runtime."""

    def __repr__(self) -> str:
        return "SET_BY_PROFILE"


SET_BY_PROFILE: Final = _SetByProfile()
# A question without a default: setup cannot finish until it is answered.
REQUIRED: Final = object()

Choices = Mapping[str, str] | Callable[[Mapping[str, Any]], Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class Question:
    """One setup question; its answer is stored under ``key``.

    ``choices`` lists the answers and their labels, or derives them from the
    staged setup; without choices the question is yes or no. ``default`` is a
    value, a function of the staged setup, or :data:`REQUIRED`. An ``advanced``
    question sits in a collapsed Advanced section.
    """

    key: str
    choices: Choices | None = None
    default: Any = REQUIRED
    advanced: bool = False

    def options(self, data: Mapping[str, Any]) -> Mapping[str, str] | None:
        if self.choices is None or isinstance(self.choices, Mapping):
            return self.choices
        return self.choices(data)

    def default_for(self, data: Mapping[str, Any]) -> Any:
        """Return the staged answer when it is still valid, else the declared default."""
        options = self.options(data)
        staged = data.get(self.key)
        if staged is not None and (options is None or staged in options):
            return staged
        default = self.default(data) if callable(self.default) else self.default
        if options is not None and default is not REQUIRED and default not in options:
            return REQUIRED
        return default


@dataclass(frozen=True, slots=True)
class SetupProfile:
    """What one profile asks in setup and Configure, and what it sets itself.

    ``owns`` maps each generic field the profile owns to its fixed value, or to
    :data:`SET_BY_PROFILE` when the profile derives it. ``validate`` returns
    errors by field for the staged setup with the answers applied.
    """

    owns: Mapping[str, Any] = field(default_factory=dict)
    questions: tuple[Question, ...] = ()
    validate: Callable[[Mapping[str, Any]], dict[str, str]] | None = None
    title: Callable[[Mapping[str, Any]], str] | None = None

    def fixed_values(self) -> dict[str, Any]:
        """Return the owned fields that have a fixed value."""
        return {key: value for key, value in self.owns.items() if value is not SET_BY_PROFILE}


def _jiecang_profile(data: Mapping[str, Any]):  # noqa: ANN202 - a profiles.jiecang AppProfile
    from .profiles.jiecang import APP_PROFILES

    return APP_PROFILES.get(data.get(CONF_JIECANG_APP_PROFILE, ""))


def _jiecang_layouts(data: Mapping[str, Any]) -> Mapping[str, str]:
    profile = _jiecang_profile(data)
    keys = profile.layouts if profile is not None else JIECANG_APP_LAYOUTS
    return {key: JIECANG_APP_LAYOUTS[key] for key in keys}


def _jiecang_transports(data: Mapping[str, Any]) -> Mapping[str, str]:
    profile = _jiecang_profile(data)
    keys = ("auto", *profile.transports) if profile is not None else JIECANG_APP_TRANSPORTS
    return {key: JIECANG_APP_TRANSPORTS[key] for key in keys}


def _jiecang_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Require the app's own layout and transport; nothing is inferred from hardware."""
    from .profiles.jiecang import COMFORT_MOTION

    profile = _jiecang_profile(data)
    if profile is None:
        return {CONF_JIECANG_APP_PROFILE: "jiecang_app_required"}
    error = "comfort_motion_selection" if profile is COMFORT_MOTION else "jiecang_app_required"
    errors = {}
    if data.get(CONF_JIECANG_APP_LAYOUT) not in profile.layouts:
        errors[CONF_JIECANG_APP_LAYOUT] = error
    if data.get(CONF_JIECANG_APP_TRANSPORT, "auto") not in ("auto", *profile.transports):
        errors[CONF_JIECANG_APP_TRANSPORT] = error
    return errors


def _jiecang_title(data: Mapping[str, Any]) -> str:
    from .const import JIECANG_APP_PROFILES

    return JIECANG_APP_PROFILES.get(data.get(CONF_JIECANG_APP_PROFILE, ""), "Jiecang app")


_DECLARED: Final[dict[str, SetupProfile]] = {
    # The family step asks the app; the app's layout sets the axes and its own
    # cadence, and none of these apps reports positions.
    BED_TYPE_JIECANG_APP: SetupProfile(
        owns={
            CONF_MOTOR_COUNT: SET_BY_PROFILE,
            CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        questions=(
            Question(CONF_JIECANG_APP_LAYOUT, _jiecang_layouts),
            Question(CONF_HAS_LIGHT, default=HAS_LIGHT_DEFAULTS[BED_TYPE_JIECANG_APP]),
            Question(CONF_JIECANG_APP_TRANSPORT, _jiecang_transports, "auto", advanced=True),
        ),
        validate=_jiecang_errors,
        title=_jiecang_title,
    ),
}


def _owned_only(fields: frozenset[str]) -> SetupProfile:
    return SetupProfile(owns=dict.fromkeys(fields, SET_BY_PROFILE))


SETUP_PROFILES: Final[dict[str, SetupProfile]] = {
    **{key: _owned_only(fields) for key, fields in _OWNED_BY_BED_TYPE.items()},
    **{f"{bed}:{variant}": _owned_only(fields) for (bed, variant), fields in _OWNED_BY_VARIANT.items()},
    **_DECLARED,
}


def setup_profile(
    bed_type: str | None, variant: str | None = None, app: str | None = None
) -> SetupProfile | None:
    """Return the most specific declaration for a route, or None."""
    if not bed_type:
        return None
    keys = []
    if variant is not None and app is not None:
        keys.append(f"{bed_type}:{variant}@{app}")
    if variant is not None:
        keys.append(f"{bed_type}:{variant}")
    if app is not None:
        keys.append(f"{bed_type}@{app}")
    keys.append(bed_type)
    return next((SETUP_PROFILES[key] for key in keys if key in SETUP_PROFILES), None)


def setup_profile_for(data: Mapping[str, Any]) -> SetupProfile | None:
    """Return the declaration for staged or saved setup data."""
    from .profile_id import app_profile_key

    bed_type = data.get(CONF_BED_TYPE)
    if not isinstance(bed_type, str):
        return None
    variant = data.get(CONF_PROTOCOL_VARIANT)
    variant = variant if isinstance(variant, str) else None
    key = app_profile_key(bed_type, variant)
    app = data.get(key) if key is not None else None
    return setup_profile(bed_type, variant, app if isinstance(app, str) else None)


def owned_fields(bed_type: str | None, variant: str | None) -> frozenset[str]:
    """Return the generic fields no form shows for this route."""
    profile = setup_profile(bed_type, variant)
    return frozenset(profile.owns) if profile is not None else frozenset()
