"""What each bed type or app profile owns in the setup and options forms.

- ``hidden_generic_fields``: generic fields a profile sets itself or never
  reads, so no form shows them. Each profile declares them in
  ``setup_questions.py`` with its setup questions.
- ``per_side_profile``: app settings that belong to one physical bed. The
  shared form of a two-address pair refuses to change them, or to change
  either side to, from or between such profiles; each side is configured
  alone instead. Every question a route's declarations ask is one of them;
  the table below adds what the declarations cannot say (see "Per-side
  settings" in docs/design/setup-questions.md).
- ``profile_settings``: every setting a bed type's profiles own. Changing the
  bed type drops the settings other bed types own (``foreign_settings``).

A profile is keyed by bed type, or by bed type and protocol variant when the
variant selects the app. A variant entry replaces the bed type's entry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cache
from typing import Final

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
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MLILY,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_OKIN_CST,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_PROFILE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_LEGGETT_APP_PROFILE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PAIRLINK_HOME_ID,
    CONF_PAIRLINK_HOST_SOURCE,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    CONF_PAIRLINK_ROLE,
    CONF_PROTOCOL_VARIANT,
    CONF_STARCODE_UI_SELECTOR,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    KAIDI_VARIANT_FLOYD,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_SIMON_LI,
    LEGGETT_VARIANT_OKIN,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    RICHMAT_MH_BED_TYPES,
    SOLACE_VARIANT_WOOSA,
    STAR_ELEVATE_VARIANT_M1X12,
)


def hidden_generic_fields(bed_type: str | None, variant: str | None) -> frozenset[str]:
    """Return the generic fields no form shows for this profile."""
    from .setup_questions import owned_fields

    return owned_fields(bed_type, variant)


@dataclass(frozen=True, slots=True)
class SideProfile:
    """App settings that belong to one physical bed of a two-address pair."""

    # Shown as {profile} in the "unpair first" error.
    label: str
    # Settings stored for each side that no setup question asks, such as a
    # detected product or values an action saves. Declared questions are added.
    keys: frozenset[str] = frozenset()
    # True when every protocol variant of the bed type is a side's own choice.
    variant_owned: bool = False


_BY_BED_TYPE: Final[dict[str, SideProfile]] = {
    "gmmotor": SideProfile("GM Control product", frozenset({CONF_BLE_DEVICE_NAME})),
    "gmmotor_sleep_mm": SideProfile("GM Control MM sleep module"),
    "gmmotor_sleep_sxb": SideProfile("GM Control SXB sleep module"),
    BED_TYPE_BF: SideProfile("BF"),
    BED_TYPE_CHERISH: SideProfile("Cherish"),
    "tempur_curve": SideProfile("Tempur Curve"),
    "qplus_app": SideProfile("Q-Plus Adjustable Remote"),
    "serta_mp_remote": SideProfile("Serta MP Remote"),
    "omazz_adjusto_iii": SideProfile("Omazz Adjusto III"),
    "ergomotion_app": SideProfile("Ergomotion (app)"),
    "ergomotion_4": SideProfile("Ergomotion 4.0", frozenset({CONF_BLE_DEVICE_NAME})),
    "row_control": SideProfile("ROW Control"),
    "ergo_slim": SideProfile("Ergo Slim"),
    "tempur_au": SideProfile("TEMPUR AU"),
    "casper_base": SideProfile("Casper Base product", variant_owned=True),
    "hush_base": SideProfile("Hush Base product", variant_owned=True),
    "casper_sleep_mm": SideProfile("Casper Base MM sensor"),
    "casper_sleep_sxb": SideProfile("Casper Base SXB sensor"),
    "hush_sleep_mm": SideProfile("Hush Base MM sensor"),
    "hush_sleep_sxb": SideProfile("Hush Base SXB sensor"),
    # The layout, handset or control box decides one side's massage (#787).
    BED_TYPE_COMFORT_ENHANCEMENTS: SideProfile(
        "Comfort Enhancements", frozenset({CONF_HAS_MASSAGE}), variant_owned=True
    ),
    BED_TYPE_GOODVIBE: SideProfile("Good Vibe Sleep", variant_owned=True),
    BED_TYPE_MLILY: SideProfile("MLILY Control", variant_owned=True),
    BED_TYPE_RICHMAT_CLASSIC_APPS: SideProfile("Classic Richmat apps", variant_owned=True),
    BED_TYPE_MOTOMOTION: SideProfile("MotoMotion"),
    BED_TYPE_HJBED: SideProfile("HJBed", variant_owned=True),
    BED_TYPE_GLIDEAWAY_MOTION: SideProfile("Glideaway Motion", variant_owned=True),
    BED_TYPE_ISLEEP: SideProfile("ISleep"),
    BED_TYPE_BEDSENSE: SideProfile("BedSense", frozenset({CONF_BLE_DEVICE_NAME}), variant_owned=True),
    BED_TYPE_FSM_RELAX: SideProfile("FSM Relax"),
    BED_TYPE_LIMOSS_REMOTE: SideProfile("Limoss Remote"),
    BED_TYPE_FURNIMOVE: SideProfile("FurniMove", frozenset({CONF_HAS_MASSAGE})),
    BED_TYPE_LOGICDATA_APP: SideProfile("Logicdata bed app"),
    # The family step picks the app, so no question asks its key.
    BED_TYPE_JIECANG_APP: SideProfile(
        "Jiecang / Comfort Motion app",
        frozenset({CONF_JIECANG_APP_PROFILE, CONF_HAS_MASSAGE}),
    ),
    BED_TYPE_MALOUF_APP: SideProfile("Malouf / Lucid app"),
    BED_TYPE_LEGGETT_LP_LEGACY: SideProfile("L&P legacy app"),
    BED_TYPE_LEGGETT_OKIN: SideProfile(
        "Leggett & Platt app", frozenset({CONF_LEGGETT_APP_PROFILE})
    ),
    BED_TYPE_DOUBLESLEEP: SideProfile("OKIN SleepEase"),
    BED_TYPE_SLEEPTRACKER: SideProfile("Sleeptracker Smart Bed"),
    BED_TYPE_SLEEPYS_ELITE_APP: SideProfile("Sleepy's Elite app", frozenset({CONF_HAS_MASSAGE})),
    BED_TYPE_MOTION_BED: SideProfile("Motion Bed"),
    # The command selector's change sets the app's UI selector.
    BED_TYPE_STARCODE_ABM5_4: SideProfile("AdjustableM5X4", frozenset({CONF_STARCODE_UI_SELECTOR})),
    BED_TYPE_STARCODE_M5X5: SideProfile("AdjustableM5X5"),
    BED_TYPE_STARCODE_M1X12: SideProfile("Adjustable Comfort M1X12"),
    BED_TYPE_VIBRADORM_APP: SideProfile("Vibradorm app", frozenset({CONF_VIBRADORM_APP_PROFILE})),
    BED_TYPE_VMATBASIC: SideProfile("V-MAT Basic"),
    BED_TYPE_ESHINE_OKIN: SideProfile("eShine E2000/E3000/E3100/E5000", variant_owned=True),
    BED_TYPE_ESHINE: SideProfile("Eshine E6000"),
    BED_TYPE_TRANQUIL: SideProfile("Tranquil"),
    BED_TYPE_ZSERIES: SideProfile("Customatic Z-Series", variant_owned=True),
    BED_TYPE_ADJUSTAMATTRESS: SideProfile("AdjustaMattress", variant_owned=True),
    BED_TYPE_ADJUSTABLE_LUMBAR: SideProfile("Adjustable bed (Lumbar)", variant_owned=True),
    BED_TYPE_SIMMONS: SideProfile("SIMMONS", variant_owned=True),
    **dict.fromkeys(RICHMAT_MH_BED_TYPES, SideProfile("Richmat app model", variant_owned=True)),
    "richmat_sleep_receiver": SideProfile("Richmat sleep receiver app", variant_owned=True),
    BED_TYPE_REMACRO: SideProfile("Remacro app", variant_owned=True),
    # The model sets the motors and massage; the model and angle sensing are asked.
    BED_TYPE_REVERIE: SideProfile("Reverie Protocol 108", frozenset({CONF_MOTOR_COUNT, CONF_HAS_MASSAGE})),
    # The model sets the motors and massage; the model and angle sensing are asked.
    BED_TYPE_REVERIE_NIGHTSTAND: SideProfile("Reverie Protocol 110", frozenset({CONF_MOTOR_COUNT, CONF_HAS_MASSAGE})),
    BED_TYPE_REVERIE_PAIRLINK: SideProfile(
        "Reverie Pairlink R510L / Harmoniq",
        frozenset(
            {
                CONF_PROTOCOL_VARIANT,
                CONF_PAIRLINK_ROLE,
                CONF_PAIRLINK_HOST_SOURCE,
                CONF_PAIRLINK_HOME_ID,
                CONF_PAIRLINK_PASSWORD_TEXT,
                CONF_PAIRLINK_PASSWORD_HEX,
                CONF_DISABLE_ANGLE_SENSING,
            }
        ),
    ),
    BED_TYPE_SVANE: SideProfile("Svane Remote", variant_owned=True),
}
_BY_VARIANT: Final[dict[tuple[str, str], SideProfile]] = {
    (BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12): SideProfile(
        "Adjustable Comfort M1X12 ELEVATE", frozenset({CONF_PROTOCOL_VARIANT})
    ),
    (BED_TYPE_KAIDI, KAIDI_VARIANT_FLOYD): SideProfile(
        "Floyd Home", frozenset({CONF_KAIDI_ROOM_ID, CONF_KAIDI_TARGET_VADDR,
                                 CONF_KAIDI_PRODUCT_ID, CONF_KAIDI_SOFA_ACU_NO}),
    ),
    (BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA): SideProfile("Woosa Sleep"),
    (BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE): SideProfile("Nectar Move"),
    (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN): SideProfile(
        "Leggett & Platt app", frozenset({CONF_LEGGETT_APP_PROFILE})
    ),
    (BED_TYPE_KEESON, KEESON_VARIANT_SIMON_LI): SideProfile("Simon Li"),
    # The motor count picks the Healing 6/7/8 product of one receiver.
    (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT): SideProfile(
        "Heal Every Night", frozenset({CONF_MOTOR_COUNT})
    ),
    (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_SEATING): SideProfile("OKIN-Seating"),
    (BED_TYPE_KEESON, KEESON_VARIANT_AVANTI_BASES): SideProfile("Avanti Bases"),
    (BED_TYPE_KEESON, KEESON_VARIANT_AMERICANSTAR): SideProfile("AMERICANSTAR"),
    (BED_TYPE_KEESON, KEESON_VARIANT_BEDSENSE_BASES): SideProfile("Bedsense Bases"),
    (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA): SideProfile("INNOVA"),
    (BED_TYPE_KEESON, KEESON_VARIANT_MAXCOIL_UNA): SideProfile("MaxCoil Una"),
    (BED_TYPE_KEESON, KEESON_VARIANT_DYNASTY_BASES): SideProfile("Dynasty Bases"),
}


@cache
def per_side_profile(bed_type: str | None, variant: str | None) -> SideProfile | None:
    """Return the per-side app profile of a bed type and variant, if any.

    Its keys include every question the route's setup declarations ask, for
    any app, since each receiver answers those for itself.
    """
    if bed_type is None:
        return None
    if variant is not None and (bed_type, variant) in _BY_VARIANT:
        profile = _BY_VARIANT[bed_type, variant]
    elif (found := _BY_BED_TYPE.get(bed_type)) is not None:
        profile = found
    else:
        return None
    return replace(profile, keys=profile.keys | _declared_questions(bed_type, variant))


def _declared_questions(bed_type: str, variant: str | None) -> frozenset[str]:
    """Return the questions a route's declarations ask, under every app they name."""
    from .profile_id import profile_route
    from .setup_questions import SETUP_PROFILES, setup_profile

    apps = {None} | {
        route.app_profile
        for route in map(profile_route, SETUP_PROFILES)
        if route.bed_type == bed_type
    }
    return frozenset(
        question.key
        for app in apps
        if (profile := setup_profile(bed_type, variant, app)) is not None
        for question in profile.questions
    )


# Settings a bed type saves that no declared question asks and no side profile
# lists: repair markers, app metadata and its own settings outside a profile.
_STORED_BY_BED_TYPE: Final[dict[str, frozenset[str]]] = {
    BED_TYPE_OKIN_CST: frozenset({"okimat_model_on_cst", "okin_cst_kept"}),
    BED_TYPE_VIBRADORM_APP: frozenset({CONF_VIBRADORM_APP_METADATA}),
}
# Settings every route reads, which no profile owns.
_SHARED_SETTINGS: Final = frozenset(
    {
        CONF_MOTOR_COUNT,
        CONF_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROTOCOL_VARIANT,
        CONF_BLE_DEVICE_NAME,
    }
)


@cache
def profile_settings(bed_type: str) -> frozenset[str]:
    """Return the settings a bed type's profiles own, under every variant and app.

    That is every question its declarations ask, every per-side setting of its
    side profiles and what it stores outside them.
    """
    from .profile_id import profile_route
    from .setup_questions import SETUP_PROFILES
    from .validators import get_variants_for_bed_type

    owned = set(_STORED_BY_BED_TYPE.get(bed_type, ()))
    for variant in (None, *(get_variants_for_bed_type(bed_type) or ())):
        if (side := per_side_profile(bed_type, variant)) is not None:
            owned |= side.keys
    for key, profile in SETUP_PROFILES.items():
        if profile_route(key).bed_type == bed_type:
            owned.update(question.key for question in profile.questions)
    return frozenset(owned) - _SHARED_SETTINGS


@cache
def _every_profile_setting() -> frozenset[str]:
    from .const import SUPPORTED_BED_TYPES

    return frozenset().union(*map(profile_settings, SUPPORTED_BED_TYPES))


def foreign_settings(bed_type: str) -> frozenset[str]:
    """Return the settings other bed types own that this bed type does not."""
    return _every_profile_setting() - profile_settings(bed_type)


def is_per_side_variant(bed_type: str | None, variant: str | None) -> bool:
    """Return True when this variant is a side's own app or model choice."""
    if bed_type is None:
        return False
    if variant is not None and (bed_type, variant) in _BY_VARIANT:
        return True
    profile = _BY_BED_TYPE.get(bed_type)
    return profile is not None and profile.variant_owned
