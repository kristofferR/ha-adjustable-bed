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

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.field_visibility import ConditionOperator, FieldCondition

from .bed_traits import bed_type_has_position_feedback
from .beds.ergomotion4.profiles import PRODUCT_CHOICES as ERGOMOTION4_PRODUCTS
from .beds.gmmotor.discovery import resolve_selection, selector_from_name
from .beds.gmmotor.profiles import load_profile as load_gmmotor_profile
from .beds.gmmotor.profiles import profile_choices as gmmotor_profile_choices
from .beds.goodvibe.catalog import PROFILE_CHOICES as GOODVIBE_PROFILES
from .beds.hjbed.catalog import PROFILE_CHOICES as HJBED_PROFILES
from .beds.leggett.lp_legacy_profiles import LP_LEGACY_PROFILE_CODES
from .beds.sleeptracker.protocol import FOUNDATIONS as SLEEPTRACKER_FOUNDATIONS
from .beds.sleeptracker.protocol import MODELS as SLEEPTRACKER_MODELS
from .beds.starcode.m1x12_protocol import profile_from_name as m1x12_profile_from_name
from .const import (
    BED_TYPE_ADJUSTABLE_BED,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_ADJUSTAMATTRESS,
    BED_TYPE_BEDSENSE,
    BED_TYPE_BF,
    BED_TYPE_CASPER_BASE,
    BED_TYPE_CHERISH,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ESHINE,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_ISLEEP,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_CB24_BED_SELECTION,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_FSM_RELAX_MEMORY_NAMES,
    CONF_FURNIMOVE_REMOTE,
    CONF_GMMOTOR_SIDE,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_JENSEN_PIN,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_LIMOSS_REMOTE_THEME,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_READ_UUID,
    CONF_LP_LEGACY_WRITE_UUID,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_PRIMARY,
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    CONF_MOTION_BED_MOVEMENT,
    CONF_MOTION_BED_PRESET,
    CONF_MOTION_BED_RESTORED,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_OCTO_PIN,
    CONF_PAIR_MODE,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_REVERSE_MOTORS,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
    CONF_RICHMAT_REMOTE,
    CONF_RMCONTROL_PRODUCT,
    CONF_RMCONTROL_SIDE,
    CONF_SLEEPTRACKER_FOUNDATION,
    CONF_SLEEPTRACKER_PROCESSOR_TYPE,
    CONF_SLEEPTRACKER_RESTRICTED,
    CONF_SLEEPTRACKER_SNAPSHOT_SIDE,
    CONF_SLEEPTRACKER_UNIT,
    CONF_SLEEPYS_ELITE_SELECTOR,
    CONF_STARCODE_COMMAND_SELECTOR,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M1X12_PROFILE,
    CONF_STARCODE_M5X5_PROFILE,
    CONF_STARCODE_TRANSPORT_SELECTOR,
    CONF_STARCODE_UI_SELECTOR,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_DEFAULT,
    CONF_VIBRADORM_FLOOR_LIGHT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    CONF_VIBRADORM_RGB,
    CONF_VIBRADORM_VMAT_REMOTE,
    CONF_VMATBASIC_FLOOR_LEVEL,
    CONF_VMATBASIC_FLOOR_MINUTES,
    CONF_VMATBASIC_PROFILE,
    DEFAULT_OCTO_PIN,
    HAS_LIGHT_DEFAULTS,
    JIECANG_APP_LAYOUTS,
    JIECANG_APP_TRANSPORTS,
    KAIDI_VARIANT_FLOYD,
    KEESON_LAYOUT_APP_BED_TYPES,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_MAXCOIL_UNA,
    LOGICDATA_APP_FAMILIES,
    LOGICDATA_APP_LAYOUTS,
    LOGICDATA_APP_PROFILES,
    LOGICDATA_APP_TRANSPORTS,
    MALOUF_APP_MODELS,
    MALOUF_APP_PROFILES,
    MALOUF_APP_TRANSPORTS,
    MALOUF_LAYOUT_AUTO,
    MALOUF_LAYOUTS,
    MALOUF_MEMORY_SLOT_OPTIONS,
    MALOUF_MEMORY_SLOTS_AUTO,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    PAIR_MODE_SINGLE_ADDRESS,
    PRODUCT_TYPES,
    RICHMAT_MH_APPS,
    RICHMAT_MH_BED_TYPES,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTES,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    SLEEPYS_ELITE_SELECTORS,
    STAR_ELEVATE_VARIANT_M1X12,
    SVANE_VARIANT_JENSEN_LINON,
    VARIANT_AUTO,
    VIBRADORM_APP_PROFILES,
    VIBRADORM_RESTORED_CONTROLS,
    VIBRADORM_WERKMEISTER_CONTROLS,
    VMATBASIC_PROFILES,
)
from .import_executor import async_import_modules
from .profiles import jiecang as jiecang_profiles
from .profiles import limoss as limoss_profiles
from .profiles import logicdata as logicdata_profiles
from .profiles import malouf as malouf_profiles

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
    from homeassistant.core import HomeAssistant

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
    **dict.fromkeys(KEESON_LAYOUT_APP_BED_TYPES, _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT}),
    # OCTO motor layout comes from its advertised capability record, with an
    # OCTO-specific explicit override in the profile's own setup/options UI.
    BED_TYPE_OCTO: frozenset({CONF_MOTOR_COUNT}),
    "casper_remote": GENERIC_FIELDS,
    "casper_base": GENERIC_FIELDS - {CONF_PROTOCOL_VARIANT},
    "casper_sleep_mm": GENERIC_FIELDS,
    "casper_sleep_sxb": GENERIC_FIELDS,
    # The Hush Base product owns every generic field; the sensors and the remote
    # finder have no motors.
    "hush_remote": GENERIC_FIELDS,
    "hush_base": GENERIC_FIELDS - {CONF_PROTOCOL_VARIANT},
    "hush_sleep_mm": GENERIC_FIELDS,
    "hush_sleep_sxb": GENERIC_FIELDS,
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
    "richmat_sleep_receiver": _FIXED_LAYOUT,
    BED_TYPE_LOGICDATA_AIR_PUMP: _FIXED_LAYOUT,
    # AHF has no massage. Motor count still sizes the legacy covers.
    BED_TYPE_TIMOTION_AHF: frozenset({CONF_HAS_MASSAGE}),
    # These apps always show their massage page.
    BED_TYPE_ADJUSTAMATTRESS: _FIXED_LAYOUT | {CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING},
    BED_TYPE_ADJUSTABLE_BED: _FIXED_LAYOUT | _ALWAYS_MASSAGE,
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
    BED_TYPE_MOTOMOTION: _APP_DEFINED,
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
# A question without a default that may stay unanswered.
OPTIONAL: Final = object()

Choices = Mapping[Any, str] | Callable[[Mapping[str, Any]], Mapping[Any, str]]


@dataclass(frozen=True, slots=True)
class FlowContext:
    """What a question or check may read beyond the staged setup."""

    hass: HomeAssistant
    # The entry Configure edits; None during setup.
    entry_id: str | None = None
    # Setup checks the connection before it saves, through a connectable scanner.
    verifiable: bool = False


ContextChoices = Callable[[FlowContext, Mapping[str, Any]], Mapping[Any, str]]


@dataclass(frozen=True, slots=True)
class Question:
    """One setup question; its answer is stored under ``key``.

    ``choices`` lists the answers and their labels, or derives them from the
    staged setup; without choices the question is yes or no, or free ``text``.
    ``default`` is a value, a function of the staged setup, or :data:`REQUIRED`.
    An ``advanced`` question sits in a collapsed Advanced section. ``when`` is
    the condition for asking it, a Home Assistant field condition on another
    answer of the same form, rendered as a native conditional field: a hidden
    question is neither required nor saved. ``staged_when`` limits when a
    staged answer is the default, for a value the profile set itself rather than
    the user. ``validator`` replaces the one the choices imply, for a range or a
    format. A ``searchable`` question's choices are a picker searched by label.
    A ``multiple`` question takes a list: several of its choices, or several
    lines of text. ``context_choices`` reads its choices from Home Assistant,
    such as other config entries, in place of ``choices``.
    """

    key: str
    choices: Choices | None = None
    default: Any = REQUIRED
    advanced: bool = False
    text: bool = False
    when: FieldCondition | list[FieldCondition] | None = None
    staged_when: FieldCondition | None = None
    validator: Any = None
    # A long list of choices is a picker the user can search by label.
    searchable: bool = False
    multiple: bool = False
    context_choices: ContextChoices | None = None

    def asked(self, data: Mapping[str, Any]) -> bool:
        """Return True when the condition holds for these answers."""
        from homeassistant.helpers.field_visibility import is_field_visible

        return self.when is None or is_field_visible(self.when, data)

    def condition_fields(self) -> frozenset[str]:
        """Return the fields the condition reads."""
        if self.when is None:
            return frozenset()
        conditions = self.when if isinstance(self.when, list) else [self.when]
        return frozenset(condition["field"] for condition in conditions)

    def options(
        self, data: Mapping[str, Any], context: FlowContext | None = None
    ) -> Mapping[Any, str] | None:
        if self.context_choices is not None:
            if context is None:
                raise ValueError(f"{self.key} reads its choices from Home Assistant")
            return self.context_choices(context, data)
        if self.choices is None or isinstance(self.choices, Mapping):
            return self.choices
        return self.choices(data)

    def default_for(self, data: Mapping[str, Any], context: FlowContext | None = None) -> Any:
        """Return the staged answer when it is still valid, else the declared default."""
        from homeassistant.helpers.field_visibility import is_field_visible

        if self.multiple:
            staged = data.get(self.key)
            return staged if isinstance(staged, list) else list(self.default)
        options = self.options(data, context)
        staged = data.get(self.key)
        if (
            staged is not None
            and (options is None or staged in options)
            and (self.staged_when is None or is_field_visible(self.staged_when, data))
        ):
            return staged
        default = self.default(data) if callable(self.default) else self.default
        if (
            options is not None
            and default not in (REQUIRED, OPTIONAL)
            and default not in options
        ):
            return REQUIRED
        return default


@dataclass(frozen=True, slots=True)
class SetupProfile:
    """What one profile asks in setup and Configure, and what it sets itself.

    ``owns`` maps each generic field the profile owns to its fixed value, or to
    :data:`SET_BY_PROFILE` when the profile derives it. ``validate`` returns
    errors by field for the staged setup with the answers applied, and
    ``derive`` returns the fields the profile computes from them. ``normalize``
    builds the staged setup from the previous one and the submitted answers,
    for a profile whose answers need cleaning or clear other settings. ``seed``
    fills setup's defaults from the bed's advertisement (the discovery that
    started setup, if any) before the first form; Configure never runs it.
    ``check`` returns errors that read Home Assistant, such as other config
    entries or the live link, once ``validate`` has none. ``imports`` names the
    modules the callbacks read that load only on demand (controllers and large
    tables); :func:`async_import_profile` imports them off the event loop.
    """

    owns: Mapping[str, Any] = field(default_factory=dict)
    questions: tuple[Question, ...] = ()
    validate: Callable[[Mapping[str, Any]], dict[str, str]] | None = None
    normalize: Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]] | None = None
    derive: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None
    title: Callable[[Mapping[str, Any]], str] | None = None
    seed: (
        Callable[
            [HomeAssistant, Mapping[str, Any], BluetoothServiceInfoBleak | None], dict[str, Any]
        ]
        | None
    ) = None
    check: Callable[[FlowContext, Mapping[str, Any]], dict[str, str]] | None = None
    imports: tuple[str, ...] = ()

    def errors(self, data: Mapping[str, Any], context: FlowContext) -> dict[str, str]:
        """Return the staged setup's errors by field, its own checks first."""
        errors = self.validate(data) if self.validate else {}
        if not errors and self.check is not None:
            errors = self.check(context, data)
        return errors

    def staged(self, previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
        """Return the staged setup with the answers applied."""
        if self.normalize is not None:
            return self.normalize(previous, answers)
        return {**previous, **answers}

    def fixed_values(self) -> dict[str, Any]:
        """Return the owned fields that have a fixed value."""
        return {key: value for key, value in self.owns.items() if value is not SET_BY_PROFILE}

    def settled(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Return what saving sets beyond the answers: fixed and derived fields."""
        return {**self.fixed_values(), **(self.derive(data) if self.derive else {})}

    def hidden(self) -> frozenset[str]:
        """Return the generic fields no generic form shows: owned or asked here."""
        asked = {question.key for question in self.questions} & GENERIC_FIELDS
        return frozenset(self.owns) | asked


def _jiecang_profile(data: Mapping[str, Any]) -> jiecang_profiles.JiecangProfile | None:
    return jiecang_profiles.APP_PROFILES.get(data.get(CONF_JIECANG_APP_PROFILE, ""))


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
    profile = _jiecang_profile(data)
    if profile is None:
        return {CONF_JIECANG_APP_PROFILE: "jiecang_app_required"}
    error = (
        "comfort_motion_selection"
        if profile is jiecang_profiles.COMFORT_MOTION
        else "jiecang_app_required"
    )
    errors = {}
    if data.get(CONF_JIECANG_APP_LAYOUT) not in profile.layouts:
        errors[CONF_JIECANG_APP_LAYOUT] = error
    if data.get(CONF_JIECANG_APP_TRANSPORT, "auto") not in ("auto", *profile.transports):
        errors[CONF_JIECANG_APP_TRANSPORT] = error
    return errors


def _jiecang_title(data: Mapping[str, Any]) -> str:
    from .const import JIECANG_APP_PROFILES

    return JIECANG_APP_PROFILES.get(data.get(CONF_JIECANG_APP_PROFILE, ""), "Jiecang app")


def _logicdata_profile(data: Mapping[str, Any]) -> logicdata_profiles.LogicdataProfile | None:
    return logicdata_profiles.APP_PROFILES.get(data.get(CONF_LOGICDATA_APP_PROFILE, ""))


def _logicdata_layouts(data: Mapping[str, Any]) -> Mapping[str, str]:
    """The chosen app's layouts. A MOTIONrelax app's middle layout is its P2 answer."""
    profile = _logicdata_profile(data)
    keys = profile.layouts if profile is not None else LOGICDATA_APP_LAYOUTS
    if profile is not None and profile.session == "motionrelax":
        keys = [key for key in keys if key != "middle"]
    return {key: LOGICDATA_APP_LAYOUTS[key] for key in keys}


def _logicdata_normalize(previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    """A MOTIONrelax app's P2 family runs the middle layout, which it never asks."""
    data = {**previous, **answers}
    profile = _logicdata_profile(data)
    if (
        profile is not None
        and profile.session == "motionrelax"
        and data.get(CONF_LOGICDATA_APP_FAMILY) == "p2"
    ):
        data[CONF_LOGICDATA_APP_LAYOUT] = "middle"
    return data


def _logicdata_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Require the app's own family, layout and transport; nothing is inferred."""
    profile = _logicdata_profile(data)
    if profile is None:
        return {CONF_LOGICDATA_APP_PROFILE: "logicdata_app_required"}
    errors = {}
    family = data.get(CONF_LOGICDATA_APP_FAMILY)
    layout = data.get(CONF_LOGICDATA_APP_LAYOUT)
    if family not in LOGICDATA_APP_FAMILIES:
        errors[CONF_LOGICDATA_APP_FAMILY] = "logicdata_app_required"
    elif layout not in profile.layouts:
        errors[CONF_LOGICDATA_APP_LAYOUT] = (
            "logicdata_app_sleep_smart_layout"
            if profile.session == "sleep_smart"
            else "logicdata_app_family_layout"
        )
    elif profile.session == "motionrelax" and (family == "p2") != (layout == "middle"):
        errors[CONF_LOGICDATA_APP_LAYOUT] = "logicdata_app_family_layout"
    if data.get(CONF_LOGICDATA_APP_TRANSPORT, "auto") not in LOGICDATA_APP_TRANSPORTS:
        errors[CONF_LOGICDATA_APP_TRANSPORT] = "logicdata_app_required"
    return errors


def _logicdata_title(data: Mapping[str, Any]) -> str:
    return LOGICDATA_APP_PROFILES.get(data.get(CONF_LOGICDATA_APP_PROFILE, ""), "LOGICDATA app")


# A MOTIONrelax app asks its layout only for the P1 family.
_LOGICDATA_P1: Final[FieldCondition] = {"field": CONF_LOGICDATA_APP_FAMILY, "value": "p1"}
# The app's layout sets the axes and its own cadence; its pulse count still
# bounds each held movement, and none of these apps reports positions.
_LOGICDATA_OWNS: Final[Mapping[str, Any]] = {
    CONF_MOTOR_COUNT: SET_BY_PROFILE,
    CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
    CONF_DISABLE_ANGLE_SENSING: True,
}


def _logicdata_questions(
    *, app: bool = False, layout_when: FieldCondition | None = None
) -> tuple[Question, ...]:
    return (
        *((Question(CONF_LOGICDATA_APP_PROFILE, LOGICDATA_APP_PROFILES),) if app else ()),
        Question(CONF_LOGICDATA_APP_FAMILY, LOGICDATA_APP_FAMILIES),
        Question(CONF_LOGICDATA_APP_LAYOUT, _logicdata_layouts, when=layout_when),
        Question(CONF_HAS_LIGHT, default=HAS_LIGHT_DEFAULTS[BED_TYPE_LOGICDATA_APP]),
        Question(CONF_LOGICDATA_APP_TRANSPORT, LOGICDATA_APP_TRANSPORTS, "auto", advanced=True),
    )


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
    # The family step asks the app. An entry switched in from another bed type
    # with Configure's bed-type list answers the app here too.
    BED_TYPE_LOGICDATA_APP: SetupProfile(
        owns=_LOGICDATA_OWNS,
        questions=_logicdata_questions(app=True),
        validate=_logicdata_errors,
        title=_logicdata_title,
    ),
    **{
        f"{BED_TYPE_LOGICDATA_APP}@{app}": SetupProfile(
            owns=_LOGICDATA_OWNS,
            questions=_logicdata_questions(layout_when=_LOGICDATA_P1),
            normalize=_logicdata_normalize,
            validate=_logicdata_errors,
            title=_logicdata_title,
        )
        for app in ("phone", "tablet")
    },
    # Sleep Smart's two-motor layout or split series, under either family.
    f"{BED_TYPE_LOGICDATA_APP}@sleep_smart": SetupProfile(
        owns=_LOGICDATA_OWNS,
        questions=_logicdata_questions(),
        validate=_logicdata_errors,
        title=_logicdata_title,
    ),
}


def _owned_only(fields: frozenset[str]) -> SetupProfile:
    return SetupProfile(owns=dict.fromkeys(fields, SET_BY_PROFILE))


def _routes(bed_type: str) -> Callable[[Mapping[str, Any]], Mapping[Any, str]]:
    def choices(data: Mapping[str, Any]) -> Mapping[Any, str]:
        from .config_flow import _labelled_routes, get_variants_for_bed_type

        routes = dict(_labelled_routes(bed_type))
        # A saved route that new setups no longer offer stays this entry's choice.
        saved = data.get(CONF_PROTOCOL_VARIANT)
        variants = get_variants_for_bed_type(bed_type) or {}
        if data.get(CONF_BED_TYPE) == bed_type and saved in variants and saved not in routes:
            routes[saved] = variants[saved]
        return routes

    return choices


def _motor_counts(bed_type: str) -> Callable[[Mapping[str, Any]], Mapping[Any, str]]:
    def choices(data: Mapping[str, Any]) -> Mapping[Any, str]:
        from .config_flow import _motor_count_options

        variant = data.get(CONF_PROTOCOL_VARIANT)
        counts = _motor_count_options(bed_type, variant if isinstance(variant, str) else "auto")
        return {count: str(count) for count in counts}

    return choices


def _angle_sensing(bed_type: str, variant: str = VARIANT_AUTO) -> tuple[Question, ...]:
    """Ask whether to ignore a route's position reports; a route without them asks nothing."""
    if not bed_type_has_position_feedback(bed_type, variant):
        return ()
    return (Question(CONF_DISABLE_ANGLE_SENSING, default=False),)


def _furnimove_handsets(data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.furnimove.profiles import furnimove_handset_choices

    return furnimove_handset_choices(data.get(CONF_FURNIMOVE_REMOTE))


def _furnimove_errors(data: Mapping[str, Any]) -> dict[str, str]:
    if data.get(CONF_FURNIMOVE_REMOTE) not in _furnimove_handsets(data):
        return {CONF_FURNIMOVE_REMOTE: "furnimove_remote_required"}
    return {}


def _furnimove_table(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The handset's table sets the motors and massage."""
    from .beds.furnimove.profiles import get_furnimove_profile

    profile = get_furnimove_profile(data[CONF_FURNIMOVE_REMOTE])
    return {
        CONF_FURNIMOVE_REMOTE: profile.handset_id,
        CONF_MOTOR_COUNT: profile.motor_count,
        CONF_HAS_MASSAGE: bool(profile.by_type("massage-function")),
    }


_LP_LEGACY_MODES: Final[Mapping[Any, str]] = {"legacy": "Legacy", "framed": "Framed"}


def _lp_legacy_codes(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    return {code: code for code in LP_LEGACY_PROFILE_CODES}


def _uuid_text(value: object) -> str:
    """Return a UUID in canonical form, or the trimmed text when it is not one."""
    raw = str(value or "").strip()
    try:
        return str(UUID(raw))
    except ValueError:
        return raw


def _lp_legacy_normalize(previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    data = {**previous, **answers}
    # Only answered fields are cleaned, so an unanswered one stays required.
    if CONF_LP_LEGACY_MODEL in data:
        data[CONF_LP_LEGACY_MODEL] = str(data[CONF_LP_LEGACY_MODEL]).strip().upper()
    for key in (CONF_LP_LEGACY_WRITE_UUID, CONF_LP_LEGACY_READ_UUID):
        if key in data:
            data[key] = _uuid_text(data[key])
    return data


def _lp_legacy_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Reject incomplete protocol settings; nothing is guessed from the bed."""
    errors: dict[str, str] = {}
    if data.get(CONF_LP_LEGACY_MODEL) not in _lp_legacy_codes(data):
        errors[CONF_LP_LEGACY_MODEL] = "invalid_lp_legacy_model"
    if data.get(CONF_LP_LEGACY_MODE) not in _LP_LEGACY_MODES:
        errors[CONF_LP_LEGACY_MODE] = "invalid_lp_legacy_mode"
    for key in (CONF_LP_LEGACY_WRITE_UUID, CONF_LP_LEGACY_READ_UUID):
        value = data.get(key, "")
        if key == CONF_LP_LEGACY_READ_UUID and not value:
            continue
        try:
            UUID(str(value))
        except ValueError:
            errors[key] = "invalid_characteristic_uuid"
    return errors


# The 2M, 3M and 4M screens of the ORE and INNOVA apps (keeson.md).
_APP_SCREENS: Final[Mapping[Any, str]] = {
    2: "2M: back and feet",
    3: "3M: back, feet and head",
    4: "4M: back, feet, waist and lumbar",
}
_SCREEN_VARIANTS: Final = (
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_MAXCOIL_UNA,
)

_BASE: Final[dict[str, SetupProfile]] = {
    **{key: _owned_only(fields) for key, fields in _OWNED_BY_BED_TYPE.items()},
    **{f"{bed}:{variant}": _owned_only(fields) for (bed, variant), fields in _OWNED_BY_VARIANT.items()},
}


def _vibradorm_normalize(previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    """Clear retained settings an answer no longer allows, and the stale app metadata."""
    from .config_flow import _vibradorm_app_data

    data = _vibradorm_app_data(previous, answers)
    if any(
        data.get(key) != previous.get(key)
        for key in (CONF_VIBRADORM_CONTROL_TYPE, CONF_VIBRADORM_VMAT_REMOTE)
    ):
        data.pop(CONF_VIBRADORM_APP_METADATA, None)
    return data


def _vibradorm_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .config_flow import _vibradorm_app_errors

    return _vibradorm_app_errors(data)


def _vibradorm_profile(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The validated app profile sets the motor groups and massage."""
    from .profiles.vibradorm import validate_vibradorm_app_profile

    control = data[CONF_VIBRADORM_CONTROL_TYPE]
    profile = validate_vibradorm_app_profile(
        data[CONF_VIBRADORM_APP_PROFILE],
        "other" if control == "other" else int(control),
        restored=data[CONF_VIBRADORM_RESTORED],
        floor_light=data[CONF_VIBRADORM_FLOOR_LIGHT],
        rgb=data[CONF_VIBRADORM_RGB],
        massage=data[CONF_HAS_MASSAGE],
        light_extension=data[CONF_VIBRADORM_LIGHT_EXTENSION],
        remote=data.get(CONF_VIBRADORM_VMAT_REMOTE),
    )
    return {
        CONF_MOTOR_COUNT: max(2, len(profile.groups)),
        CONF_HAS_MASSAGE: profile.massage,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_MOTOR_PULSE_USER_SET: False,
    }


def _vibradorm_title(data: Mapping[str, Any]) -> str:
    """The app or V-MAT Basic product, and the remote or controls chosen for it."""
    if data.get(CONF_BED_TYPE) == BED_TYPE_VMATBASIC:
        product = VMATBASIC_PROFILES.get(data.get(CONF_VMATBASIC_PROFILE, ""))
        return f"V-MAT Basic: {product}" if product else "V-MAT Basic"
    app = data.get(CONF_VIBRADORM_APP_PROFILE, "")
    control = str(data.get(CONF_VIBRADORM_CONTROL_TYPE))
    if app == "vmat":
        from .profiles.vibradorm import VMAT_REMOTES

        remote = data.get(CONF_VIBRADORM_VMAT_REMOTE)
        detail = (
            f"Remote {remote} ({VMAT_REMOTES[remote].asset})" if remote in VMAT_REMOTES else None
        )
    elif app == "werkmeister":
        detail = VIBRADORM_WERKMEISTER_CONTROLS.get(control)
    elif data.get(CONF_VIBRADORM_RESTORED):
        detail = VIBRADORM_RESTORED_CONTROLS.get(control)
    else:
        detail = "Standard controls"
    name = VIBRADORM_APP_PROFILES.get(app, "Vibradorm app")
    return f"{name}: {detail}" if detail else name


def _vmat_remotes(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .profiles.vibradorm import VMAT_REMOTES

    return {remote: f"Remote {remote} ({profile.asset})" for remote, profile in VMAT_REMOTES.items()}


def _vmatbasic_normalize(previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    from .config_flow import _vmatbasic_data

    return _vmatbasic_data(previous, answers)


def _vmatbasic_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .config_flow import _vmatbasic_errors as errors

    return errors(data)


def vmatbasic_integer(value: object) -> int:
    """Keep whole numeric form values without silently truncating fractions."""
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as error:
            raise vol.Invalid("Expected a whole number") from error
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise vol.Invalid("Expected a whole number")
    if not math.isfinite(value) or value != int(value):
        raise vol.Invalid("Expected a whole number")
    return int(value)


def _whole_number(maximum: int) -> Any:
    """A whole number up to ``maximum``; the product's own range is checked on save."""
    return vol.All(vmatbasic_integer, vol.Range(min=0, max=maximum))


_RESTORED: Final[FieldCondition] = {"field": CONF_VIBRADORM_RESTORED, "value": True}
_FLOOR_PRODUCTS: Final[FieldCondition] = {
    "field": CONF_VMATBASIC_PROFILE,
    "operator": ConditionOperator.IN,
    "value": ["cbi", "xtbox"],
}


# Diagnostic layouts, and the ZRS6 screen that only picks another layout.
_CLASSIC_EXCLUDED: Final = frozenset({"TEST", "RMCS", "ZRS6"})


def _classic_layouts(data: Mapping[str, Any]) -> Mapping[Any, str]:
    """The chosen app's own layout codes, aliases and ZRS6 layout picks."""
    from .beds.richmat_classic.models import LAYOUT_PICKER_CHOICES, MANUAL_ALIASES, MODEL_CHOICES

    app = str(data.get(CONF_PROTOCOL_VARIANT, ""))
    codes = {
        *MODEL_CHOICES.get(app, ()),
        *MANUAL_ALIASES.get(app, {}),
        *LAYOUT_PICKER_CHOICES.get(app, {}),
    } - _CLASSIC_EXCLUDED
    return {code: code for code in sorted(codes)}


def _classic_normalize(previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve an alias or a ZRS6 pick to the layout the app opens."""
    from .beds.richmat_classic.models import LAYOUT_PICKER_CHOICES, MANUAL_ALIASES

    data = {**previous, **answers}
    if CONF_PRODUCT_TYPE in answers:
        app = str(data.get(CONF_PROTOCOL_VARIANT, ""))
        layout = str(data[CONF_PRODUCT_TYPE]).strip().upper()
        layout = MANUAL_ALIASES.get(app, {}).get(layout, layout)
        data[CONF_PRODUCT_TYPE] = LAYOUT_PICKER_CHOICES.get(app, {}).get(layout, layout)
    return data


def _classic_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Require a layout the chosen app ships; a shared service never selects one."""
    from .beds.richmat_classic.models import MODEL_CHOICES

    layout = data.get(CONF_PRODUCT_TYPE)
    shipped = MODEL_CHOICES.get(str(data.get(CONF_PROTOCOL_VARIANT, "")), ())
    if layout in _CLASSIC_EXCLUDED or layout not in shipped:
        return {CONF_PRODUCT_TYPE: "richmat_classic_layout"}
    return {}


def _classic_title(data: Mapping[str, Any]) -> str:
    from .beds.richmat_classic.profiles import APP_NAMES

    return APP_NAMES.get(str(data.get(CONF_PROTOCOL_VARIANT, "")), "Classic Richmat app")


# The app's control box selectors, named as the app names them.
_SLEEPYS_SELECTORS: Final[Mapping[Any, str]] = {
    selector: selector for selector in SLEEPYS_ELITE_SELECTORS
}


def _sleepys_app_features(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The BOX25 selectors carry the app's massage and position feedback."""
    box25 = data.get(CONF_SLEEPYS_ELITE_SELECTOR) in ("BOX25", "BOX25_STAR")
    return {
        CONF_HAS_MASSAGE: box25,
        CONF_DISABLE_ANGLE_SENSING: not box25,
        CONF_MOTOR_PULSE_USER_SET: False,
    }


def _sleepys_title(data: Mapping[str, Any]) -> str:
    """Every control box selector runs the same bed type, so name the selector."""
    from .profile_review import route_label

    selector = data.get(CONF_SLEEPYS_ELITE_SELECTOR)
    return f"{route_label(data)}: {selector}" if selector else route_label(data)


def _gmmotor_products(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    return gmmotor_profile_choices()


def _gmmotor_product_default(data: Mapping[str, Any]) -> str:
    """The product the raw Bluetooth name selects, or the app's empty fallback."""
    product = data.get(CONF_PRODUCT_TYPE)
    if product is None:
        try:
            product = resolve_selection(selector_from_name(data.get(CONF_BLE_DEVICE_NAME, "")))
        except ValueError:
            product = ""
    return product if product in _gmmotor_products(data) else ""


_GMMOTOR_SIDES: Final[Mapping[Any, str]] = {"left": "Left", "right": "Right", "both": "Both"}


def _gmmotor_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Require a catalog product, and an app side the product exposes."""
    try:
        profile = load_gmmotor_profile(data.get(CONF_PRODUCT_TYPE, ""))
    except ValueError:
        return {CONF_PRODUCT_TYPE: "gmmotor_product"}
    if {"left": 0, "right": 1, "both": 2}.get(data.get(CONF_GMMOTOR_SIDE, "left")) not in profile.sides:
        return {CONF_GMMOTOR_SIDE: "gmmotor_side"}
    return {}


def _goodvibe_seed(
    hass: HomeAssistant, data: Mapping[str, Any], discovered: BluetoothServiceInfoBleak | None
) -> dict[str, Any]:
    """The product the app's own name rule suggests, never over a chosen one."""
    from .beds.goodvibe.discovery import suggested_profile

    if data.get(CONF_PROTOCOL_VARIANT) in GOODVIBE_PROFILES or discovered is None:
        return dict(data)
    suggested = suggested_profile(discovered.name)
    return {**data, CONF_PROTOCOL_VARIANT: suggested} if suggested else dict(data)


def _isleep_products(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .profiles.kaidi import ISLEEP_PRODUCTS

    return {product: str(product) for product in ISLEEP_PRODUCTS}


def _isleep_seed(
    hass: HomeAssistant, data: Mapping[str, Any], discovered: BluetoothServiceInfoBleak | None
) -> dict[str, Any]:
    """The advertised product, room and actuator descriptor, never over a chosen one."""
    from homeassistant.components import bluetooth

    from .profiles.kaidi import add_isleep_metadata

    info = discovered or bluetooth.async_last_service_info(
        hass, data[CONF_ADDRESS], connectable=False
    )
    return add_isleep_metadata(data, info.manufacturer_data if info else {})


def _isleep_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .profiles.kaidi import validate_isleep_profile

    try:
        profile = validate_isleep_profile(data)
    except ValueError:
        return {"base": "isleep_profile"}
    # A single-address pair needs the product's separate side controls.
    if data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS and not profile.split:
        return {"base": "isleep_unpair_first"}
    return {}


def _isleep_layout(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The product's rendered axes set the motor count."""
    from .profiles.kaidi import validate_isleep_profile

    return {
        CONF_MOTOR_COUNT: len(validate_isleep_profile(data).axes),
        CONF_MOTOR_PULSE_USER_SET: False,
    }


def _doublesleep_models(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.doublesleep.protocol import MODELS

    return {str(key): label for key, label in MODELS.items()}


def _doublesleep_seed(
    _hass: HomeAssistant, data: Mapping[str, Any], discovered: BluetoothServiceInfoBleak | None
) -> dict[str, Any]:
    """The app model the platform name and advertisement select, unless one is chosen."""
    if discovered is None:
        return dict(data)
    from .beds.doublesleep.protocol import select_model

    model = select_model(discovered.device.name or "", discovered.manufacturer_data)
    return {CONF_PRODUCT_TYPE: str(model), **data}


def _doublesleep_normalize(
    previous: Mapping[str, Any], answers: Mapping[str, Any]
) -> dict[str, Any]:
    data = {**previous, **answers}
    if CONF_PRODUCT_TYPE in data:
        data[CONF_PRODUCT_TYPE] = str(data[CONF_PRODUCT_TYPE])
    return data


def _doublesleep_errors(data: Mapping[str, Any]) -> dict[str, str]:
    if data.get(CONF_PRODUCT_TYPE) not in _doublesleep_models(data) or data.get(
        CONF_PROTOCOL_VARIANT, "auto"
    ) not in ("auto", "p1", "p2", "p3"):
        return {"base": "doublesleep_profile"}
    return {}


def _sleeptracker_models(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    return {key: model.label for key, model in SLEEPTRACKER_MODELS.items()}


def _sleeptracker_foundations(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    return {foundation: foundation for foundation in SLEEPTRACKER_FOUNDATIONS}


# A signed 32-bit value, as the apps store their mesh and processor identities.
_INT32_RANGE: Final = vol.Range(min=-(2**31), max=2**31 - 1)
_INT32: Final = vol.All(int, _INT32_RANGE)


def _sleeptracker_errors(data: Mapping[str, Any]) -> dict[str, str]:
    if data.get(CONF_PRODUCT_TYPE) not in SLEEPTRACKER_MODELS:
        return {CONF_PRODUCT_TYPE: "sleeptracker_profile"}
    if type(
        snapshot := data.get(CONF_SLEEPTRACKER_SNAPSHOT_SIDE, 0)
    ) is not int or snapshot not in range(4):
        return {CONF_SLEEPTRACKER_SNAPSHOT_SIDE: "sleeptracker_profile"}
    if (
        type(processor := data.get(CONF_SLEEPTRACKER_PROCESSOR_TYPE, 0)) is not int
        or not -(2**31) <= processor < 2**31
    ):
        return {CONF_SLEEPTRACKER_PROCESSOR_TYPE: "sleeptracker_profile"}
    if type(unit := data.get(CONF_SLEEPTRACKER_UNIT, 0)) is not int or not -(2**31) <= unit < 2**31:
        return {CONF_SLEEPTRACKER_UNIT: "sleeptracker_profile"}
    if data.get(CONF_SLEEPTRACKER_RESTRICTED, False) and unit != 0:
        return {CONF_SLEEPTRACKER_UNIT: "sleeptracker_restricted_unit"}
    if data.get(CONF_SLEEPTRACKER_FOUNDATION, "Unspecified") not in SLEEPTRACKER_FOUNDATIONS:
        return {CONF_SLEEPTRACKER_FOUNDATION: "sleeptracker_profile"}
    if not isinstance(data.get(CONF_SLEEPTRACKER_RESTRICTED, False), bool):
        return {CONF_SLEEPTRACKER_RESTRICTED: "sleeptracker_profile"}
    return {}


def _sleeptracker_layout(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """A layout with lumbar adds the third motor."""
    return {
        CONF_MOTOR_COUNT: 3 if SLEEPTRACKER_MODELS[data[CONF_PRODUCT_TYPE]].lumbar else 2,
        CONF_MOTOR_PULSE_USER_SET: False,
    }


def _motion_bed_seed(
    _hass: HomeAssistant, data: Mapping[str, Any], discovered: BluetoothServiceInfoBleak | None
) -> dict[str, Any]:
    """The advertised name, unless one is saved; the editable title is no identity."""
    if discovered is None or not discovered.name:
        return dict(data)
    return {CONF_BLE_DEVICE_NAME: discovered.name, **data}


def _motomotion_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """The app reads its panel and feature flags from the exact Bluetooth name."""
    from .profiles.motomotion import Profile

    try:
        Profile(str(data.get(CONF_BLE_DEVICE_NAME, "")))
    except (ValueError, TypeError):
        return {CONF_BLE_DEVICE_NAME: "motomotion_profile"}
    return {}


def _motion_bed_choices(layouts: tuple[str, ...]) -> Mapping[Any, str]:
    return {layout: layout for layout in ("auto", *layouts)}


def _motion_bed_presets(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.motion_bed.models import PRESET_VARIANTS

    return _motion_bed_choices(tuple(PRESET_VARIANTS))


def _motion_bed_movements(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.motion_bed.models import MOVEMENT_LAYOUTS

    return _motion_bed_choices(tuple(MOVEMENT_LAYOUTS))


def _motion_bed_normalize(
    previous: Mapping[str, Any], answers: Mapping[str, Any]
) -> dict[str, Any]:
    """Auto follows the name, so it is stored as no retained layout."""
    data = {**previous, **answers}
    for key in (CONF_MOTION_BED_PRESET, CONF_MOTION_BED_MOVEMENT):
        if data.get(key) == "auto":
            data.pop(key)
    return data


def _motion_bed_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .beds.motion_bed.models import select_motion_bed

    try:
        select_motion_bed(
            data.get(CONF_BLE_DEVICE_NAME, ""),
            restored=data.get(CONF_MOTION_BED_RESTORED, False),
            preset_override=None
            if data.get(CONF_MOTION_BED_PRESET, "auto") == "auto"
            else data[CONF_MOTION_BED_PRESET],
            movement_override=None
            if data.get(CONF_MOTION_BED_MOVEMENT, "auto") == "auto"
            else data[CONF_MOTION_BED_MOVEMENT],
        )
    except ValueError:
        return {"base": "motion_bed_profile"}
    return {}


_NO_PULSE_CHOICE: Final[Mapping[str, Any]] = {CONF_MOTOR_PULSE_USER_SET: False}


def _malouf_models(data: Mapping[str, Any]) -> Mapping[Any, str]:
    """The chosen app's model picker, plus a stored model the picker no longer lists."""
    app = malouf_profiles.APP_PROFILES.get(data.get(CONF_MALOUF_APP_PROFILE, ""))
    models = {model: MALOUF_APP_MODELS[model] for model in (app.models if app else ())}
    stored = data.get(CONF_MALOUF_APP_MODEL)
    if app is not None and stored in MALOUF_APP_MODELS:
        models.setdefault(stored, MALOUF_APP_MODELS[stored])
    return models


def _malouf_app_normalize(
    previous: Mapping[str, Any], answers: Mapping[str, Any]
) -> dict[str, Any]:
    """Drop a model the app's picker did not offer, so it reads as unanswered."""
    data = {**previous, **answers}
    if answers.get(CONF_MALOUF_APP_MODEL, previous.get(CONF_MALOUF_APP_MODEL)) not in (
        _malouf_models(previous)
    ):
        data.pop(CONF_MALOUF_APP_MODEL, None)
    return data


def _malouf_app_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Refuse to save without a model instead of guessing one from a retail name."""
    if data.get(CONF_MALOUF_APP_MODEL) in MALOUF_APP_MODELS:
        return {}
    return {CONF_MALOUF_APP_MODEL: "malouf_app_required"}


def _every_malouf_model(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    """Every app's model picker, for a form that asks the app at the same time."""
    return {
        model: MALOUF_APP_MODELS[model]
        for app in malouf_profiles.APP_PROFILES.values()
        for model in app.models
    }


def _malouf_switch_in_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Check the app and model chosen together, since one form asked both."""
    app = malouf_profiles.APP_PROFILES.get(data.get(CONF_MALOUF_APP_PROFILE, ""))
    if app is None:
        return {CONF_MALOUF_APP_PROFILE: "malouf_app_required"}
    if data.get(CONF_MALOUF_APP_MODEL) not in app.models:
        return {CONF_MALOUF_APP_MODEL: "malouf_app_required"}
    return {}


def _malouf_title(data: Mapping[str, Any]) -> str:
    """The app, and the model chosen in it: both apps run one bed type."""
    app = MALOUF_APP_PROFILES.get(data.get(CONF_MALOUF_APP_PROFILE, ""), "")
    model = MALOUF_APP_MODELS.get(data.get(CONF_MALOUF_APP_MODEL, ""))
    return f"{app}: {model}" if model else app


_MALOUF_APP_OWNS: Final[Mapping[str, Any]] = {
    CONF_MOTOR_COUNT: SET_BY_PROFILE,
    CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
    CONF_DISABLE_ANGLE_SENSING: True,
}
# The physical receiver's role and transport, asked after the model.
_MALOUF_RECEIVER_QUESTIONS: Final = (
    Question(CONF_MALOUF_APP_PRIMARY, default=True),
    Question(CONF_MALOUF_APP_TRANSPORT, MALOUF_APP_TRANSPORTS, "auto", advanced=True),
)


def _reverie_models(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.reverie.profiles import REVERIE_MODEL_CHOICES

    return REVERIE_MODEL_CHOICES


def _reverie_angle_sensing() -> Question:
    """Ask angle sensing only for a model whose app reads positions.

    The model is asked on the same form, so the question follows that answer,
    and a staged answer is the default only for a model that reads positions.
    """
    from .beds.reverie.profiles import REVERIE_MODEL_CHOICES, resolve_reverie_model

    reports: FieldCondition = {
        "field": CONF_PROTOCOL_VARIANT,
        "operator": ConditionOperator.IN,
        "value": [model for model in REVERIE_MODEL_CHOICES if resolve_reverie_model(model).positions],
    }
    return Question(CONF_DISABLE_ANGLE_SENSING, default=False, when=reports, staged_when=reports)


def _reverie_quiet_model(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """A model whose app reads no positions never reads them."""
    from .beds.reverie.profiles import resolve_reverie_model

    if resolve_reverie_model(data.get(CONF_PROTOCOL_VARIANT)).positions:
        return {}
    return {CONF_DISABLE_ANGLE_SENSING: True}


# The RMControl app's standing-desk products run a separate desk protocol.
_RMCONTROL_DESKS: Final = frozenset({"FWRM", "WFRM"})
# The app's command side; Home Assistant's paired sides route separately.
_RMCONTROL_SIDES: Final[Mapping[Any, str]] = {"left": "Left", "right": "Right", "both": "Both"}
_RMCONTROL_CHOSEN: Final[FieldCondition] = {
    "field": CONF_RMCONTROL_PRODUCT,
    "operator": ConditionOperator.EXISTS,
}
_NO_RMCONTROL: Final[FieldCondition] = {
    "field": CONF_RMCONTROL_PRODUCT,
    "operator": ConditionOperator.NOT_EXISTS,
}


def _rmcontrol_products(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.rmcontrol.profiles import RICHMAT_PRODUCT_CODES

    return {
        "": "None: Richmat remote controls",
        **{code: code for code in RICHMAT_PRODUCT_CODES if code not in _RMCONTROL_DESKS},
    }


def _rmcontrol_default(data: Mapping[str, Any]) -> Any:
    """The RMControl answer still names its product; the remote answer has none.

    The Richmat question stages ``None`` for the RMControl app until the product
    is chosen, so nothing is saved without one.
    """
    if CONF_RMCONTROL_PRODUCT in data and data[CONF_RMCONTROL_PRODUCT] is None:
        return REQUIRED
    return ""


def _richmat_remotes(data: Mapping[str, Any]) -> Mapping[Any, str]:
    """The listed remote codes, plus a detected or saved code the list lacks."""
    remotes: dict[Any, str] = dict(RICHMAT_REMOTES)
    current = data.get(CONF_RICHMAT_REMOTE)
    if isinstance(current, str) and current not in remotes:
        remotes[current] = f"{current.upper()} (detected code)"
    return remotes


def _richmat_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """An RMControl product runs only over the app's Nordic or WiLinke transport."""
    if data.get(CONF_RMCONTROL_PRODUCT) and data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO) not in (
        VARIANT_AUTO,
        RICHMAT_VARIANT_NORDIC,
        RICHMAT_VARIANT_WILINKE,
    ):
        return {CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"}
    return {}


def _richmat_mh_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Report a model the app's name rule cannot resolve from the raw name."""
    from .beds.richmat_mh.controller import resolve_model
    from .detection import is_mac_like_name

    app = RICHMAT_MH_APPS.get(str(data.get(CONF_BED_TYPE)))
    if app is None:
        return {}
    name = data.get(CONF_BLE_DEVICE_NAME)
    name = name if isinstance(name, str) and not is_mac_like_name(name) else None
    _model, problem = resolve_model(app, data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO), name)
    return {CONF_PROTOCOL_VARIANT: f"richmat_mh_{problem}"} if problem else {}


def _limoss_remote_themes(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    return {theme: theme for theme in limoss_profiles.REMOTE_THEMES}


def _limoss_remote_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .config_flow import _limoss_remote_errors as errors

    return errors(dict(data))


def _hush_products(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    """The app's own twelve products first, then the profiles it restores."""
    from .profiles.hush import HUSH_BASE_VARIANTS, PROFILES

    return {
        key: HUSH_BASE_VARIANTS[key]
        for key in sorted(PROFILES, key=lambda key: (not PROFILES[key].current, PROFILES[key].index))
    }


_OCTO_MOTOR_OVERRIDES: Final[Mapping[Any, str]] = {
    "auto": "Use advertised motor count",
    "1": "1 motor",
    "2": "2 motors",
    "3": "3 motors",
    "4": "4 motors",
}


def _octo_normalize(previous: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    from .validators import normalize_octo_pin

    data = {**previous, **answers}
    if CONF_OCTO_PIN in answers:
        data[CONF_OCTO_PIN] = normalize_octo_pin(answers[CONF_OCTO_PIN])
    return data


def _octo_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .validators import is_valid_octo_pin

    if not is_valid_octo_pin(data.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN)):
        return {CONF_OCTO_PIN: "invalid_pin"}
    return {}


# The native CB24 A/B selector; Both uses the broadcast selector.
_CB24_SIDES: Final[Mapping[Any, str]] = {
    CB24_BED_SELECTION_DEFAULT: "Both sides",
    CB24_BED_SELECTION_A: "Side A / Left",
    CB24_BED_SELECTION_B: "Side B / Right",
}


def _discovered_name_seed(
    _hass: HomeAssistant, data: Mapping[str, Any], discovered: BluetoothServiceInfoBleak | None
) -> dict[str, Any]:
    """The advertised name, unless one is saved; the editable title is no identity."""
    if discovered is None or not discovered.name:
        return dict(data)
    return {CONF_BLE_DEVICE_NAME: discovered.name, **data}


def _starcode_selectors(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.starcode.abm5_4_profiles import SELECTORS

    return {selector: selector for selector in SELECTORS}


_STARCODE_TRANSPORTS: Final[Mapping[Any, str]] = {
    "auto": "From original Bluetooth device name",
    "BOX1220": "BLE / 1000 service",
    "BOX3633": "62741523 service",
    "BOX25": "Star / Nordic UART",
    "BOX25_STAR": "Exact star manufacturer / Nordic UART",
}


def _starcode_app_normalize(
    previous: Mapping[str, Any], answers: Mapping[str, Any]
) -> dict[str, Any]:
    """The app's UI selector follows a changed command selector; Auto reads the name."""
    from .beds.starcode.abm5_4_profiles import SELECTORS
    from .config_flow import _starcode_initial_transport

    data = {**previous, **answers}
    command = data.get(CONF_STARCODE_COMMAND_SELECTOR, "none")
    if command != previous.get(CONF_STARCODE_COMMAND_SELECTOR) or previous.get(
        CONF_STARCODE_UI_SELECTOR, "none"
    ) not in SELECTORS:
        data[CONF_STARCODE_UI_SELECTOR] = command
    if data.get(CONF_STARCODE_TRANSPORT_SELECTOR) == "auto":
        del data[CONF_STARCODE_TRANSPORT_SELECTOR]
        if (transport := _starcode_initial_transport(data, None)) is not None:
            data[CONF_STARCODE_TRANSPORT_SELECTOR] = transport
    return data


def _starcode_app_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .beds.starcode.abm5_4_profiles import SELECTORS, TRANSPORTS

    errors: dict[str, str] = {}
    if data.get(CONF_STARCODE_COMMAND_SELECTOR, "none") not in SELECTORS:
        errors[CONF_STARCODE_COMMAND_SELECTOR] = "starcode_app_invalid"
    if (data.get(CONF_STARCODE_TRANSPORT_SELECTOR) or "auto") not in (*TRANSPORTS, "auto"):
        errors[CONF_STARCODE_TRANSPORT_SELECTOR] = "starcode_app_invalid"
    if CONF_STARCODE_UI_SELECTOR in data and data[CONF_STARCODE_UI_SELECTOR] not in SELECTORS:
        errors[CONF_STARCODE_COMMAND_SELECTOR] = "starcode_app_invalid"
    return errors


def _starcode_app_check(context: FlowContext, data: Mapping[str, Any]) -> dict[str, str]:
    """Require a transport the bed offers.

    Setup's connection check reads it from the bed's own name, so only setup
    without a scanner needs it now. Configure checks a changed transport on the
    live link, without connecting.
    """
    from .config_flow import _starcode_initial_transport, starcode_live_transport_valid

    transport = data.get(CONF_STARCODE_TRANSPORT_SELECTOR)
    invalid = {CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
    if context.entry_id is None:
        return invalid if transport is None and not context.verifiable else {}
    saved = context.hass.config_entries.async_get_entry(context.entry_id)
    saved_transport = _starcode_initial_transport(saved.data, None) if saved else None
    if transport == saved_transport:
        return {}
    if transport is None or (
        starcode_live_transport_valid(context.hass, context.entry_id, transport) is False
    ):
        return invalid
    return {}


# The bedding class the exact Bluetooth name prefix selects.
_STARCODE_CLASSES: Final[Mapping[Any, str]] = {"cb25": "CB25", "f23": "F23", "kneading": "Kneading"}


def _lift_choices(context: FlowContext, data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .beds.starcode.accessory_group import lift_choices

    return lift_choices(context.hass, context.entry_id, main_data=data)


def _lift_check(context: FlowContext, data: Mapping[str, Any]) -> dict[str, str]:
    from .beds.starcode.accessory_group import validate_lift_entries

    try:
        validate_lift_entries(
            context.hass,
            data,
            data.get(CONF_STARCODE_LIFT_ENTRIES, []),
            main_entry_id=context.entry_id,
        )
    except ValueError as err:
        if data.get(CONF_BED_TYPE) != BED_TYPE_STARCODE_M1X12:
            return {CONF_STARCODE_LIFT_ENTRIES: "starcode_invalid_lifts"}
        return {
            CONF_STARCODE_LIFT_ENTRIES: "starcode_m1x12_elevate_reconfigure"
            if "M1X12 ELEVATE" in str(err)
            else "starcode_invalid_m1x12_lifts"
        }
    return {}


_LIFTS: Final = Question(
    CONF_STARCODE_LIFT_ENTRIES, default=[], multiple=True, context_choices=_lift_choices
)
# The lift helpers import the StarCode controllers; AdjustableM5X5's name rule is one.
_LIFT_IMPORTS: Final = ("beds.starcode.accessory_group",)
# The exact Bluetooth name the app reads; a friendly title is no identity.
_EXACT_NAME: Final = Question(
    CONF_BLE_DEVICE_NAME, default=lambda data: data.get(CONF_NAME, REQUIRED), text=True
)


def _m5x5_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .beds.starcode.m5x5 import profile_from_name

    name = data.get(CONF_BLE_DEVICE_NAME)
    if isinstance(name, str) and name.startswith("ELEVATE"):
        return {CONF_STARCODE_M5X5_PROFILE: "starcode_elevate_bed_type"}
    if not isinstance(name, str) or profile_from_name(name) != data.get(CONF_STARCODE_M5X5_PROFILE):
        return {CONF_STARCODE_M5X5_PROFILE: "starcode_profile_mismatch"}
    return {}


def _m1x12_errors(data: Mapping[str, Any]) -> dict[str, str]:
    name = data.get(CONF_BLE_DEVICE_NAME)
    if not isinstance(name, str) or m1x12_profile_from_name(name) != data.get(
        CONF_STARCODE_M1X12_PROFILE
    ):
        return {CONF_STARCODE_M1X12_PROFILE: "starcode_m1x12_profile_mismatch"}
    return {}


def _fsm_relax_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .beds.fsm_relax.controller import FsmRelaxSetup
    from .beds.fsm_relax.state import validate_names

    try:
        r = tuple(data.get(key, False) for key in CONF_REVERSE_MOTORS)
        FsmRelaxSetup(
            data.get(CONF_PRODUCT_TYPE, "chair"),
            data.get(CONF_HAS_LIGHT, False),
            data.get(CONF_HAS_MASSAGE, False),
            (r[0], r[1], r[2], r[3]),
        )
        validate_names(data.get(CONF_FSM_RELAX_MEMORY_NAMES, [""] * 8))
    except ValueError:
        return {"base": "fsm_relax_invalid"}
    return {}


def _app_layouts(bed_type: str) -> Callable[[Mapping[str, Any]], Mapping[Any, str]]:
    """The layouts the app shows, or Ergomotion 4.0's catalog products."""

    def choices(_data: Mapping[str, Any]) -> Mapping[Any, str]:
        if bed_type == "ergomotion_4":
            return ERGOMOTION4_PRODUCTS
        from .profiles.keeson import APP_LAYOUTS

        return {layout: layout for layout in APP_LAYOUTS[bed_type]}

    return choices


def _app_layout_default(bed_type: str) -> Callable[[Mapping[str, Any]], str]:
    def default(_data: Mapping[str, Any]) -> str:
        if bed_type == "ergomotion_4":
            return "H"
        from .profiles.keeson import DEFAULT_LAYOUTS

        return DEFAULT_LAYOUTS[bed_type]

    return default


def _app_layout_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Require one of the app's own layouts; an Other product needs its exact keys."""
    bed_type = data[CONF_BED_TYPE]
    if data.get(CONF_PRODUCT_TYPE) not in _app_layouts(bed_type)(data):
        return {"base": "keeson_app_layout"}
    if bed_type == "ergomotion_4" and data[CONF_PRODUCT_TYPE] == "custom":
        from .beds.ergomotion4.controller import (
            CONF_MASSAGE_KEYS,
            CONF_MODEL_KEYS,
            CONF_PRODUCT_NAME,
            CONF_RGB,
            custom_product,
        )

        try:
            custom_product(
                data.get(CONF_PRODUCT_NAME, "Custom"),
                tuple(data.get(CONF_MODEL_KEYS, ())),
                tuple(data.get(CONF_MASSAGE_KEYS, ())),
                data.get(CONF_HAS_LIGHT, False),
                data.get(CONF_RGB, False),
            )
        except ValueError:
            return {"base": "keeson_app_layout"}
    return {}


def _app_layout_title(data: Mapping[str, Any]) -> str:
    from .profiles.keeson import APP_NAMES

    return APP_NAMES.get(data[CONF_BED_TYPE], "Ergomotion 4.0")


def _ergomotion4_keys(kind: Literal["model", "massage"]) -> Choices:
    """The catalog's model or massage feature keys, for an Other product."""

    def choices(_data: Mapping[str, Any]) -> Mapping[Any, str]:
        from .beds.ergomotion4.controller import MASSAGE_KEYS, MODEL_KEYS

        return {key: key for key in (MODEL_KEYS if kind == "model" else MASSAGE_KEYS)}

    return choices


# The Serta MP Remote app's four local memories, a head and a foot angle each.
CONF_SERTA_MP_MEMORIES: Final = tuple(
    f"serta_mp_memory_{slot}_{axis}" for slot in range(1, 5) for axis in ("head", "foot")
)


def _app_layout_profile(bed_type: str) -> SetupProfile:
    """An app's exact layout; its labelled controls own their entities."""
    questions: tuple[Question, ...] = (
        Question(CONF_PRODUCT_TYPE, _app_layouts(bed_type), _app_layout_default(bed_type)),
    )
    if bed_type == "ergomotion_4":
        # Other catalog product's fields stay visible so switching the product
        # takes one submission; they apply only to it.
        questions += (
            Question("ergomotion4_model_keys", _ergomotion4_keys("model"), [], multiple=True),
            Question("ergomotion4_massage_keys", _ergomotion4_keys("massage"), [], multiple=True),
            Question("ergomotion4_product_name", default="Custom", text=True),
            Question(CONF_HAS_LIGHT, default=False),
            Question("ergomotion4_rgb", default=False),
        )
    if bed_type == "qplus_app":
        questions += (
            Question(CONF_PROTOCOL_VARIANT, {side: side for side in ("both", "side_a", "side_b")}, "both"),
        )
    if bed_type == "serta_mp_remote":
        questions += tuple(
            Question(
                f"serta_mp_memory_{slot}_{axis}",
                default=15 if axis == "head" else 0 if slot == 4 else 35,
                validator=vol.All(int, vol.Range(min=0, max=maximum)),
            )
            for slot in range(1, 5)
            for axis, maximum in (("head", 60), ("foot", 45))
        )
    owns: dict[str, Any] = {
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        # Serta MP Remote reads its positions for its local memories.
        CONF_DISABLE_ANGLE_SENSING: bed_type != "serta_mp_remote",
        CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
    }
    if bed_type != "qplus_app":
        owns[CONF_PROTOCOL_VARIANT] = SET_BY_PROFILE
    return SetupProfile(
        owns=owns,
        questions=questions,
        validate=_app_layout_errors,
        derive=lambda _data: _NO_PULSE_CHOICE,
        title=_app_layout_title,
        imports=(
            ("profiles.keeson", "beds.ergomotion4.controller")
            if bed_type == "ergomotion_4"
            else ("profiles.keeson",)
        ),
    )


def _asking(key: str, **declared: Any) -> SetupProfile:
    """Add questions and rules to a profile's owned-field declaration."""
    return replace(_BASE.get(key, SetupProfile()), **declared)


SETUP_PROFILES: Final[dict[str, SetupProfile]] = {
    **_BASE,
    **_DECLARED,
    # The handset table, chosen in the app, sets the layout and massage.
    BED_TYPE_FURNIMOVE: _asking(
        BED_TYPE_FURNIMOVE,
        owns={**_BASE[BED_TYPE_FURNIMOVE].owns, CONF_DISABLE_ANGLE_SENSING: True},
        questions=(Question(CONF_FURNIMOVE_REMOTE, _furnimove_handsets),),
        validate=_furnimove_errors,
        derive=_furnimove_table,
    ),
    # The remote code picks the buttons and presets; the motor count sizes them.
    # The Okin row's form is drawn for FurniMove, whose handset table sets
    # massage and angle sensing, so a remote route asks them here.
    **{
        bed_type: _asking(
            bed_type,
            questions=(
                Question(CONF_PROTOCOL_VARIANT, _routes(bed_type), "auto"),
                Question(CONF_MOTOR_COUNT, _motor_counts(bed_type), 2),
                Question(CONF_HAS_MASSAGE, default=False),
                *_angle_sensing(bed_type),
            ),
        )
        for bed_type in (BED_TYPE_OKIN_UUID, BED_TYPE_OKIMAT, BED_TYPE_OKIN_DOT)
    },
    # The app's screen sets the motor count.
    **{
        f"{BED_TYPE_KEESON}:{variant}": _asking(
            f"{BED_TYPE_KEESON}:{variant}",
            questions=(Question(CONF_MOTOR_COUNT, _APP_SCREENS, 2),),
        )
        for variant in _SCREEN_VARIANTS
    },
    # The one older Keeson remote route with position reports. The family step
    # resets angle sensing to each route's default, so this route asks it.
    f"{BED_TYPE_KEESON}:{KEESON_VARIANT_ERGOMOTION}": _asking(
        f"{BED_TYPE_KEESON}:{KEESON_VARIANT_ERGOMOTION}",
        questions=_angle_sensing(BED_TYPE_KEESON, KEESON_VARIANT_ERGOMOTION),
    ),
    # The legacy app's model code, protocol mode and confirmed characteristics.
    BED_TYPE_LEGGETT_LP_LEGACY: _asking(
        BED_TYPE_LEGGETT_LP_LEGACY,
        questions=(
            Question(CONF_LP_LEGACY_MODEL, _lp_legacy_codes),
            Question(CONF_LP_LEGACY_MODE, _LP_LEGACY_MODES),
            Question(CONF_LP_LEGACY_WRITE_UUID, text=True),
            Question(CONF_LP_LEGACY_READ_UUID, default="", text=True),
        ),
        normalize=_lp_legacy_normalize,
        validate=_lp_legacy_errors,
    ),
    # The Vibradorm question's legacy setup asks the settings its old row showed:
    # a form drawn for a detected V-MAT Basic or app setup sets them itself.
    BED_TYPE_VIBRADORM: _asking(
        BED_TYPE_VIBRADORM,
        questions=(
            Question(CONF_MOTOR_COUNT, _motor_counts(BED_TYPE_VIBRADORM), 2),
            Question(CONF_HAS_MASSAGE, default=False),
            *_angle_sensing(BED_TYPE_VIBRADORM),
        ),
    ),
    # The Vibradorm family step picks the app; each app asks its own controls.
    f"{BED_TYPE_VIBRADORM_APP}@werkmeister": _asking(
        BED_TYPE_VIBRADORM_APP,
        questions=(
            Question(CONF_VIBRADORM_CONTROL_TYPE, VIBRADORM_WERKMEISTER_CONTROLS, "5"),
        ),
        normalize=_vibradorm_normalize,
        validate=_vibradorm_errors,
        derive=_vibradorm_profile,
        title=_vibradorm_title,
    ),
    f"{BED_TYPE_VIBRADORM_APP}@vmat": _asking(
        BED_TYPE_VIBRADORM_APP,
        questions=(Question(CONF_VIBRADORM_VMAT_REMOTE, _vmat_remotes),),
        normalize=_vibradorm_normalize,
        validate=_vibradorm_errors,
        derive=_vibradorm_profile,
        title=_vibradorm_title,
    ),
    # Caresse Diamant asks the retained settings only for a restored setup.
    f"{BED_TYPE_VIBRADORM_APP}@caresse": _asking(
        BED_TYPE_VIBRADORM_APP,
        owns={
            key: value
            for key, value in _BASE[BED_TYPE_VIBRADORM_APP].owns.items()
            if key != CONF_HAS_MASSAGE
        },
        questions=(
            Question(CONF_VIBRADORM_RESTORED, default=False),
            Question(
                CONF_VIBRADORM_CONTROL_TYPE, VIBRADORM_RESTORED_CONTROLS, "2", when=_RESTORED
            ),
            *(
                Question(key, default=False, when=_RESTORED)
                for key in (
                    CONF_VIBRADORM_FLOOR_LIGHT,
                    CONF_VIBRADORM_RGB,
                    CONF_HAS_MASSAGE,
                    CONF_VIBRADORM_LIGHT_EXTENSION,
                )
            ),
            Question(
                CONF_VIBRADORM_FLOOR_DEFAULT,
                default=lambda data: 6 if data.get(CONF_VIBRADORM_LIGHT_EXTENSION) else 8,
                when=_RESTORED,
                # A fresh Caresse stores 6 itself; that is not a retained preference.
                staged_when=_RESTORED,
                validator=vol.All(int, vol.Range(min=1, max=8)),
            ),
        ),
        normalize=_vibradorm_normalize,
        validate=_vibradorm_errors,
        derive=_vibradorm_profile,
        title=_vibradorm_title,
    ),
    # The CBI and XT-Box products also ask the floor light level and timer.
    BED_TYPE_VMATBASIC: _asking(
        BED_TYPE_VMATBASIC,
        questions=(
            Question(CONF_VMATBASIC_PROFILE, VMATBASIC_PROFILES),
            Question(
                CONF_VMATBASIC_FLOOR_LEVEL,
                default=OPTIONAL,
                when=_FLOOR_PRODUCTS,
                validator=_whole_number(255),
            ),
            Question(
                CONF_VMATBASIC_FLOOR_MINUTES,
                default=0,
                when=_FLOOR_PRODUCTS,
                validator=_whole_number(1439),
            ),
        ),
        normalize=_vmatbasic_normalize,
        validate=_vmatbasic_errors,
        title=_vibradorm_title,
    ),
    # The app is the variant, chosen from the bed-type list. Its layout owns
    # every control and the app its own refresh; none reports positions.
    BED_TYPE_RICHMAT_CLASSIC_APPS: SetupProfile(
        owns={
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
        },
        questions=(
            Question(CONF_PRODUCT_TYPE, _classic_layouts),
            Question(CONF_RICHMAT_CLASSIC_THIRD_SERVICE, default=False, advanced=True),
        ),
        normalize=_classic_normalize,
        validate=_classic_errors,
        title=_classic_title,
    ),
    # The Jensen / Svane family step picks the app and bed, and the form before
    # it was drawn for Svane, which sets these itself. The JMC400 box asks for
    # its PIN (empty uses the default PIN) and the generic settings its old row
    # showed: its motors, whether massage motors are fitted, and whether to read
    # its position reports.
    BED_TYPE_JENSEN: _asking(
        BED_TYPE_JENSEN,
        questions=(
            Question(CONF_JENSEN_PIN, default="", text=True),
            Question(CONF_MOTOR_COUNT, _motor_counts(BED_TYPE_JENSEN), 2),
            Question(CONF_HAS_MASSAGE, default=False),
            Question(CONF_DISABLE_ANGLE_SENSING, default=False),
        ),
    ),
    # The Jensen app's LinOn profile has no massage and no position reports;
    # its motor count was the one generic setting its row needed.
    f"{BED_TYPE_SVANE}:{SVANE_VARIANT_JENSEN_LINON}": _asking(
        f"{BED_TYPE_SVANE}:{SVANE_VARIANT_JENSEN_LINON}",
        questions=(
            Question(CONF_MOTOR_COUNT, _motor_counts(BED_TYPE_SVANE), 2),
        ),
    ),
    # The Malouf family step picks the app. Its model sets the controls, and the
    # role and transport belong to the one physical receiver; neither the model
    # nor a retail name identifies the hardware, so the model has no default.
    **{
        f"{BED_TYPE_MALOUF_APP}@{app}": _asking(
            BED_TYPE_MALOUF_APP,
            owns=_MALOUF_APP_OWNS,
            title=_malouf_title,
            questions=(
                Question(CONF_MALOUF_APP_MODEL, _malouf_models),
                *_MALOUF_RECEIVER_QUESTIONS,
            ),
            normalize=_malouf_app_normalize,
            validate=_malouf_app_errors,
        )
        for app in MALOUF_APP_PROFILES
    },
    # An entry Configure switches in from another bed type answers the app
    # here too, with every app's models; the pair is checked on save.
    BED_TYPE_MALOUF_APP: _asking(
        BED_TYPE_MALOUF_APP,
        owns=_MALOUF_APP_OWNS,
        questions=(
            Question(CONF_MALOUF_APP_PROFILE, MALOUF_APP_PROFILES),
            Question(CONF_MALOUF_APP_MODEL, _every_malouf_model),
            *_MALOUF_RECEIVER_QUESTIONS,
        ),
        validate=_malouf_switch_in_errors,
        title=_malouf_title,
    ),
    # A receiver route's controls come from the physical remote, which neither
    # the protocol nor a retail name identifies.
    **{
        bed_type: _asking(
            bed_type,
            questions=(
                Question(CONF_MOTOR_COUNT, _motor_counts(bed_type), 2),
                Question(CONF_MALOUF_LAYOUT, MALOUF_LAYOUTS, MALOUF_LAYOUT_AUTO),
                Question(
                    CONF_MALOUF_MEMORY_SLOTS, MALOUF_MEMORY_SLOT_OPTIONS, MALOUF_MEMORY_SLOTS_AUTO
                ),
            ),
        )
        for bed_type in (BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN)
    },
    # SimplicityFrame sizes its motor controls from the count. The LOGICDATA
    # row's form is drawn for the apps, whose layout sets it.
    BED_TYPE_LOGICDATA: _asking(
        BED_TYPE_LOGICDATA,
        questions=(Question(CONF_MOTOR_COUNT, _motor_counts(BED_TYPE_LOGICDATA), 2),),
    ),
    # The Sleepy's family step picks the app or receiver. The app's control box
    # selector sets its routes; it belongs to one physical bed.
    BED_TYPE_SLEEPYS_ELITE_APP: _asking(
        BED_TYPE_SLEEPYS_ELITE_APP,
        questions=(Question(CONF_SLEEPYS_ELITE_SELECTOR, _SLEEPYS_SELECTORS, "none"),),
        derive=_sleepys_app_features,
        title=_sleepys_title,
    ),
    # The BOX15 and BOX24 receivers size their motor controls from the count.
    **{
        bed_type: _asking(
            bed_type, questions=(Question(CONF_MOTOR_COUNT, _motor_counts(bed_type), 2),)
        )
        for bed_type in (BED_TYPE_SLEEPYS_BOX15, BED_TYPE_SLEEPYS_BOX24)
    },
    # BOX25 shows massage only when asked; Auto picks the packet dialect from the
    # receiver's Device Information. The Sleepy's row's form is drawn for the
    # app, which sets the motors and angle sensing, so BOX25 asks them too.
    BED_TYPE_SLEEPYS_BOX25: _asking(
        BED_TYPE_SLEEPYS_BOX25,
        questions=(
            Question(CONF_MOTOR_COUNT, _motor_counts(BED_TYPE_SLEEPYS_BOX25), 2),
            Question(CONF_HAS_MASSAGE, default=False),
            *_angle_sensing(BED_TYPE_SLEEPYS_BOX25),
            Question(
                CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_SLEEPYS_BOX25), "auto", advanced=True
            ),
        ),
    ),
    # The Reverie question confirms the receiver; the model the app shows sets
    # the controls of either one. Nothing detects the model, so the app's own
    # list and its explicit Other fallback are offered, never an automatic one.
    # Both receivers report positions for most models; the family step resets
    # angle sensing to the confirmed receiver's default, so each asks it for a
    # model that reads positions.
    **{
        bed_type: _asking(
            bed_type,
            questions=(
                Question(CONF_PROTOCOL_VARIANT, _reverie_models, "Other"),
                _reverie_angle_sensing(),
            ),
            derive=_reverie_quiet_model,
        )
        for bed_type in (BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND)
    },
    # The Richmat question picks RMControl or the remote controls. RMControl
    # names the exact product and the side the app commands; the remote code
    # picks a remote's buttons. Configure asks the same, so an entry can opt in
    # to RMControl or leave it. The packet dialect belongs to each receiver, as
    # every answer here does in a two-address pair.
    BED_TYPE_RICHMAT: _asking(
        BED_TYPE_RICHMAT,
        questions=(
            Question(CONF_RMCONTROL_PRODUCT, _rmcontrol_products, _rmcontrol_default),
            Question(CONF_RMCONTROL_SIDE, _RMCONTROL_SIDES, "left", when=_RMCONTROL_CHOSEN),
            Question(CONF_RICHMAT_REMOTE, _richmat_remotes, RICHMAT_REMOTE_AUTO, when=_NO_RMCONTROL),
            Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_RICHMAT), "auto", advanced=True),
        ),
        validate=_richmat_errors,
        imports=("beds.rmcontrol.profiles",),
    ),
    # Each Richmat MH app's model sets its controls. Auto applies the app's name
    # rule to the raw Bluetooth name setup stores.
    **{
        bed_type: _asking(
            bed_type,
            questions=(Question(CONF_PROTOCOL_VARIANT, _routes(bed_type), "auto"),),
            validate=_richmat_mh_errors,
            imports=("beds.richmat_mh.controller",),
        )
        for bed_type in RICHMAT_MH_BED_TYPES
    },
    # A Fuzion entry controls one side; a standalone BAM/MCR entry exposes both,
    # so only Fuzion asks. Auto keeps the left side, as before. Both transports
    # report positions, and each asks angle sensing as Reverie does.
    BED_TYPE_SLEEP_NUMBER: _asking(
        BED_TYPE_SLEEP_NUMBER,
        questions=(
            Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_SLEEP_NUMBER), "auto"),
            *_angle_sensing(BED_TYPE_SLEEP_NUMBER),
        ),
    ),
    BED_TYPE_SLEEP_NUMBER_MCR: _asking(
        BED_TYPE_SLEEP_NUMBER_MCR, questions=_angle_sensing(BED_TYPE_SLEEP_NUMBER_MCR)
    ),
    # The Limoss Remote app's bed or chair, its local light and massage choices,
    # reversals and artwork theme. The connected device supplies the key layout.
    BED_TYPE_LIMOSS_REMOTE: _asking(
        BED_TYPE_LIMOSS_REMOTE,
        owns={
            **{
                key: value
                for key, value in _BASE[BED_TYPE_LIMOSS_REMOTE].owns.items()
                if key != CONF_HAS_MASSAGE
            },
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        questions=(
            Question(CONF_PRODUCT_TYPE, PRODUCT_TYPES),
            Question(CONF_HAS_LIGHT, default=HAS_LIGHT_DEFAULTS[BED_TYPE_LIMOSS_REMOTE]),
            Question(CONF_HAS_MASSAGE, default=False),
            *(Question(key, default=False) for key in CONF_REVERSE_MOTORS),
            Question(CONF_LIMOSS_REMOTE_THEME, _limoss_remote_themes, OPTIONAL),
        ),
        validate=_limoss_remote_errors,
        derive=lambda _data: {CONF_MOTOR_PULSE_USER_SET: False},
        imports=("beds.limoss.remote",),
    ),
    # The app's layout is its route, asked on the app's one row.
    BED_TYPE_COMFORT_ENHANCEMENTS: _asking(
        BED_TYPE_COMFORT_ENHANCEMENTS,
        questions=(Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_COMFORT_ENHANCEMENTS)),),
    ),
    # MC3 has no massage page; the other layouts' controllers turn massage on.
    f"{BED_TYPE_COMFORT_ENHANCEMENTS}:mc3": _asking(
        BED_TYPE_COMFORT_ENHANCEMENTS,
        owns={**_BASE[BED_TYPE_COMFORT_ENHANCEMENTS].owns, CONF_HAS_MASSAGE: False},
        questions=(Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_COMFORT_ENHANCEMENTS)),),
    ),
    # The Casper Base app's product is its route, a long list searched by label.
    BED_TYPE_CASPER_BASE: _asking(
        BED_TYPE_CASPER_BASE,
        questions=(
            Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_CASPER_BASE), searchable=True),
        ),
    ),
    # The app's product sets every control, so its one row asks it.
    BED_TYPE_GOODVIBE: _asking(
        BED_TYPE_GOODVIBE,
        questions=(Question(CONF_PROTOCOL_VARIANT, GOODVIBE_PROFILES, searchable=True),),
        seed=_goodvibe_seed,
    ),
    BED_TYPE_HJBED: _asking(
        BED_TYPE_HJBED,
        questions=(Question(CONF_PROTOCOL_VARIANT, HJBED_PROFILES, searchable=True),),
    ),
    # The product the Hush Base app shows sets every control; nothing detects it.
    "hush_base": _asking("hush_base", questions=(Question(CONF_PROTOCOL_VARIANT, _hush_products),)),
    # The layout owns the motion controls; Auto reads it from the Bluetooth name.
    BED_TYPE_BEDSENSE: _asking(
        BED_TYPE_BEDSENSE,
        questions=(Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_BEDSENSE), "auto"),),
    ),
    # The exact catalog product sets the layout; the raw Bluetooth name suggests it.
    BED_TYPE_GMMOTOR: _asking(
        BED_TYPE_GMMOTOR,
        owns={**_BASE[BED_TYPE_GMMOTOR].owns, CONF_DISABLE_ANGLE_SENSING: True},
        questions=(
            Question(CONF_PRODUCT_TYPE, _gmmotor_products, _gmmotor_product_default),
            Question(CONF_GMMOTOR_SIDE, _GMMOTOR_SIDES, "left"),
        ),
        validate=_gmmotor_errors,
    ),
    # The app's product and the mesh room it joins; the advertisement suggests both.
    BED_TYPE_ISLEEP: _asking(
        BED_TYPE_ISLEEP,
        owns={
            **_BASE[BED_TYPE_ISLEEP].owns,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_DELAY_MS: 100,
        },
        questions=(
            Question(CONF_PRODUCT_TYPE, _isleep_products, 129),
            Question(
                CONF_KAIDI_ROOM_ID, default=10000, validator=vol.All(vol.Coerce(int), _INT32_RANGE)
            ),
            Question(
                CONF_KAIDI_SOFA_ACU_NO,
                default=2,
                validator=vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
            ),
        ),
        validate=_isleep_errors,
        derive=_isleep_layout,
        seed=_isleep_seed,
    ),
    # The app saves its model apart from the BLE driver the bed advertises.
    BED_TYPE_DOUBLESLEEP: _asking(
        BED_TYPE_DOUBLESLEEP,
        owns={
            **{
                key: value
                for key, value in _BASE[BED_TYPE_DOUBLESLEEP].owns.items()
                if key != CONF_PROTOCOL_VARIANT
            },
            # Controller-declared app actions own these controls.
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_DELAY_MS: 300,
        },
        questions=(
            Question(
                CONF_PRODUCT_TYPE,
                _doublesleep_models,
                lambda data: str(data.get(CONF_PRODUCT_TYPE, "3")),
            ),
            Question(CONF_PROTOCOL_VARIANT, _routes(BED_TYPE_DOUBLESLEEP), "auto"),
        ),
        normalize=_doublesleep_normalize,
        validate=_doublesleep_errors,
        derive=lambda _data: _NO_PULSE_CHOICE,
        seed=_doublesleep_seed,
    ),
    # The processor's app layout and the selectors the app recorded for it.
    BED_TYPE_SLEEPTRACKER: _asking(
        BED_TYPE_SLEEPTRACKER,
        owns={
            **_BASE[BED_TYPE_SLEEPTRACKER].owns,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        questions=(
            Question(CONF_SLEEPTRACKER_FOUNDATION, _sleeptracker_foundations, "Unspecified"),
            Question(CONF_PRODUCT_TYPE, _sleeptracker_models, "unknown"),
            Question(CONF_SLEEPTRACKER_UNIT, default=0, validator=_INT32),
            Question(
                CONF_SLEEPTRACKER_SNAPSHOT_SIDE,
                default=0,
                validator=vol.All(int, vol.Range(min=0, max=3)),
            ),
            Question(CONF_SLEEPTRACKER_RESTRICTED, default=False),
            Question(CONF_SLEEPTRACKER_PROCESSOR_TYPE, default=0, validator=_INT32),
        ),
        validate=_sleeptracker_errors,
        derive=_sleeptracker_layout,
    ),
    # The exact Bluetooth name identifies the app's model; a restored profile or a
    # retained layout is the user's explicit choice.
    BED_TYPE_MOTION_BED: _asking(
        BED_TYPE_MOTION_BED,
        owns={
            **_BASE[BED_TYPE_MOTION_BED].owns,
            # Named app controls own their capabilities.
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        questions=(
            Question(
                CONF_BLE_DEVICE_NAME, default=lambda data: data.get(CONF_NAME, ""), text=True
            ),
            Question(CONF_MOTION_BED_RESTORED, default=False),
            Question(CONF_MOTION_BED_PRESET, _motion_bed_presets, "auto"),
            Question(CONF_MOTION_BED_MOVEMENT, _motion_bed_movements, "auto"),
        ),
        normalize=_motion_bed_normalize,
        validate=_motion_bed_errors,
        derive=lambda _data: _NO_PULSE_CHOICE,
        seed=_motion_bed_seed,
    ),
    # AdjustableM5X4's saved command selector and transport. A shared UART is
    # no app identity.
    BED_TYPE_STARCODE_ABM5_4: SetupProfile(
        owns={
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
        },
        questions=(
            Question(CONF_STARCODE_COMMAND_SELECTOR, _starcode_selectors, "none"),
            Question(CONF_STARCODE_TRANSPORT_SELECTOR, _STARCODE_TRANSPORTS, "auto"),
        ),
        normalize=_starcode_app_normalize,
        validate=_starcode_app_errors,
        check=_starcode_app_check,
        seed=_discovered_name_seed,
        title=lambda _data: "AdjustableM5X4",
    ),
    # The bedding class the exact Bluetooth name selects, and the lifts it
    # drives; a lift is another config entry.
    BED_TYPE_STARCODE_M5X5: SetupProfile(
        owns={
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
            CONF_PROTOCOL_VARIANT: SET_BY_PROFILE,
        },
        questions=(_EXACT_NAME, Question(CONF_STARCODE_M5X5_PROFILE, _STARCODE_CLASSES), _LIFTS),
        validate=_m5x5_errors,
        check=_lift_check,
        title=lambda _data: "AdjustableM5X5",
        imports=_LIFT_IMPORTS,
    ),
    BED_TYPE_STARCODE_M1X12: SetupProfile(
        owns={
            CONF_MOTOR_COUNT: SET_BY_PROFILE,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_DELAY_MS: 100,
            CONF_PROTOCOL_VARIANT: SET_BY_PROFILE,
        },
        questions=(_EXACT_NAME, Question(CONF_STARCODE_M1X12_PROFILE, _STARCODE_CLASSES), _LIFTS),
        validate=_m1x12_errors,
        check=_lift_check,
        derive=lambda _data: _NO_PULSE_CHOICE,
        title=lambda _data: "Adjustable Comfort M1X12",
        imports=_LIFT_IMPORTS,
    ),
    # An ELEVATE may itself be the main of AdjustableM5X5 lifts.
    **{
        key: _asking(key, questions=(_LIFTS,), check=_lift_check, imports=_LIFT_IMPORTS)
        for key in (BED_TYPE_STAR_ELEVATE, f"{BED_TYPE_STAR_ELEVATE}:{STAR_ELEVATE_VARIANT_M1X12}")
    },
    # The app's bed or chair, its optional controls, reversals and the eight
    # memory names. Shared advertisements do not identify the app.
    BED_TYPE_FSM_RELAX: SetupProfile(
        owns={
            CONF_MOTOR_COUNT: SET_BY_PROFILE,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_DELAY_MS: SET_BY_PROFILE,
            CONF_PROTOCOL_VARIANT: SET_BY_PROFILE,
        },
        questions=(
            Question(CONF_PRODUCT_TYPE, PRODUCT_TYPES, "chair"),
            Question(CONF_HAS_LIGHT, default=HAS_LIGHT_DEFAULTS[BED_TYPE_FSM_RELAX]),
            Question(CONF_HAS_MASSAGE, default=False),
            *(Question(key, default=False) for key in CONF_REVERSE_MOTORS),
            Question(CONF_FSM_RELAX_MEMORY_NAMES, default=[""] * 8, text=True, multiple=True),
        ),
        validate=_fsm_relax_errors,
        title=lambda _data: "FSM Relax",
        imports=("beds.fsm_relax.controller",),
    ),
    # Each app's exact layout, chosen from its own list.
    **{
        bed_type: _app_layout_profile(bed_type)
        for bed_type in sorted(KEESON_LAYOUT_APP_BED_TYPES | {"ergomotion_4"})
    },
    # Standard OCTO Smart Control's PIN, and an explicit motor layout over the
    # advertised one. A route without an app step asks these in its final settings.
    BED_TYPE_OCTO: _asking(
        BED_TYPE_OCTO,
        questions=(
            Question(CONF_OCTO_PIN, default=DEFAULT_OCTO_PIN, text=True),
            Question(CONF_OCTO_MOTOR_COUNT_OVERRIDE, _OCTO_MOTOR_OVERRIDES, "auto"),
        ),
        normalize=_octo_normalize,
        validate=_octo_errors,
    ),
    BED_TYPE_OKIN_CB24: _asking(
        BED_TYPE_OKIN_CB24,
        questions=(
            Question(CONF_CB24_BED_SELECTION, _CB24_SIDES, CB24_BED_SELECTION_DEFAULT),
        ),
    ),
    # The exact Bluetooth name selects MotoMotion's panel and its independent
    # feature flags; the app's own controls replace massage and angle sensing.
    BED_TYPE_MOTOMOTION: _asking(
        BED_TYPE_MOTOMOTION,
        owns={
            **_BASE[BED_TYPE_MOTOMOTION].owns,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        questions=(
            Question(
                CONF_BLE_DEVICE_NAME, default=lambda data: data.get(CONF_NAME, ""), text=True
            ),
        ),
        validate=_motomotion_errors,
        derive=lambda _data: _NO_PULSE_CHOICE,
        seed=_motion_bed_seed,
        title=lambda _data: "MotoMotion",
    ),
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


async def async_import_profile(hass: HomeAssistant, profile: SetupProfile | None) -> None:
    """Import the modules ``profile``'s callbacks read, off the event loop."""
    if profile is not None and profile.imports:
        await async_import_modules(hass, *profile.imports)


def profile_massage(data: Mapping[str, Any]) -> bool | None:
    """Return the massage a saved route's profile settles, or None if it leaves it open.

    This is the value setup and Configure save for the profile, from its fixed
    owned fields and what it derives from the saved answers. Data the profile
    cannot read, such as an unknown handset, settles nothing.
    """
    profile = setup_profile_for(data)
    if profile is None:
        return None
    try:
        massage = profile.settled(data).get(CONF_HAS_MASSAGE)
    except KeyError, ValueError:
        return None
    return massage if isinstance(massage, bool) else None


def owned_fields(bed_type: str | None, variant: str | None) -> frozenset[str]:
    """Return the generic fields no generic form shows for this route."""
    profile = setup_profile(bed_type, variant)
    return profile.hidden() if profile is not None else frozenset()
