"""What each bed type or app profile owns in the setup and options forms.

Two tables, read by every setup route and the options flow:

- ``hidden_generic_fields``: generic fields a profile sets itself or never
  reads, so no form shows them. A profile that needs one of them asks for it
  in its own app step instead.
- ``per_side_profile``: app settings that belong to one physical bed. The
  shared form of a two-address pair refuses to change them, or to change
  either side to, from or between such profiles; each side is configured
  alone instead.

A profile is keyed by bed type, or by bed type and protocol variant when the
variant selects the app. A variant entry replaces the bed type's entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .const import (
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MOTION_BED,
    BED_TYPE_REMACRO,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SOLACE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_FSM_RELAX_MEMORY_NAMES,
    CONF_FURNIMOVE_REMOTE,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_LEGGETT_APP_PROFILE,
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
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_REVERSE_MOTORS,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M5X5_PROFILE,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_SIMON_LI,
    LEGGETT_VARIANT_OKIN,
    LIMOSS_REMOTE_CONFIG_KEYS,
    MOTION_BED_CONFIG_KEYS,
    RICHMAT_MH_BED_TYPES,
    SOLACE_VARIANT_WOOSA,
    STARCODE_APP_CONFIG_KEYS,
    SVANE_VARIANT_JENSEN_LINON,
    VIBRADORM_APP_CONFIG_KEYS,
    VMATBASIC_CONFIG_KEYS,
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

_HIDDEN_BY_BED_TYPE: Final[dict[str, frozenset[str]]] = {
    BED_TYPE_SERENITY: _FIXED_LAYOUT,
    BED_TYPE_TRANQUIL: _FIXED_LAYOUT,
    BED_TYPE_ZSERIES: _FIXED_LAYOUT,
    BED_TYPE_SIMMONS: _FIXED_LAYOUT,
    **dict.fromkeys(RICHMAT_MH_BED_TYPES, _FIXED_LAYOUT),
    BED_TYPE_LOGICDATA_AIR_PUMP: _FIXED_LAYOUT,
    # These apps always show their massage page.
    BED_TYPE_ADJUSTABLE_LUMBAR: _FIXED_LAYOUT | _ALWAYS_MASSAGE,
    BED_TYPE_STARCODE_ABM5_4: _FIXED_LAYOUT | _ALWAYS_MASSAGE,
    # The handset table sets the layout and massage; the receiver sets the protocol.
    BED_TYPE_FURNIMOVE: _FIXED_LAYOUT | {CONF_HAS_MASSAGE, CONF_PROTOCOL_VARIANT},
    BED_TYPE_STARCODE_M5X5: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    # The app step asks for massage; the pulse count bounds a held control.
    BED_TYPE_FSM_RELAX: _APP_DEFINED - {CONF_MOTOR_PULSE_COUNT},
    BED_TYPE_LIMOSS_REMOTE: _APP_DEFINED,
    BED_TYPE_VIBRADORM_APP: _APP_DEFINED,
    BED_TYPE_VMATBASIC: _APP_DEFINED,
    BED_TYPE_MOTION_BED: _APP_DEFINED,
    # The variant selects the Svane Remote app profile or Jensen LinOn.
    BED_TYPE_SVANE: _APP_DEFINED - {CONF_PROTOCOL_VARIANT},
}
_HIDDEN_BY_VARIANT: Final[dict[tuple[str, str], frozenset[str]]] = {
    (BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON): frozenset(),
    **{
        (BED_TYPE_KEESON, variant): _ALWAYS_MASSAGE
        for variant in (
            KEESON_VARIANT_INNOVA,
            KEESON_VARIANT_MAXCOIL_UNA,
            KEESON_VARIANT_DYNASTY_BASES,
            KEESON_VARIANT_BEDSENSE_BASES,
            KEESON_VARIANT_HEAL_EVERY_NIGHT,
        )
    },
}


def hidden_generic_fields(bed_type: str | None, variant: str | None) -> frozenset[str]:
    """Return the generic fields no form shows for this profile."""
    if bed_type is None:
        return frozenset()
    if variant is not None and (bed_type, variant) in _HIDDEN_BY_VARIANT:
        return _HIDDEN_BY_VARIANT[bed_type, variant]
    return _HIDDEN_BY_BED_TYPE.get(bed_type, frozenset())


@dataclass(frozen=True, slots=True)
class SideProfile:
    """App settings that belong to one physical bed of a two-address pair."""

    # Shown as {profile} in the "unpair first" error.
    label: str
    # Settings stored for each side.
    keys: frozenset[str] = frozenset()
    # True when every protocol variant of the bed type is a side's own choice.
    variant_owned: bool = False


_BY_BED_TYPE: Final[dict[str, SideProfile]] = {
    BED_TYPE_FSM_RELAX: SideProfile(
        "FSM Relax",
        frozenset(
            {CONF_PRODUCT_TYPE, CONF_HAS_LIGHT, CONF_HAS_MASSAGE, CONF_FSM_RELAX_MEMORY_NAMES, *CONF_REVERSE_MOTORS}
        ),
    ),
    BED_TYPE_LIMOSS_REMOTE: SideProfile("Limoss Remote", LIMOSS_REMOTE_CONFIG_KEYS),
    BED_TYPE_FURNIMOVE: SideProfile("FurniMove", frozenset({CONF_FURNIMOVE_REMOTE})),
    BED_TYPE_LOGICDATA_APP: SideProfile(
        "Logicdata bed app",
        frozenset(
            {
                CONF_LOGICDATA_APP_PROFILE,
                CONF_LOGICDATA_APP_FAMILY,
                CONF_LOGICDATA_APP_LAYOUT,
                CONF_LOGICDATA_APP_TRANSPORT,
                CONF_HAS_LIGHT,
            }
        ),
    ),
    BED_TYPE_JIECANG_APP: SideProfile(
        "Jiecang app",
        frozenset(
            {CONF_JIECANG_APP_PROFILE, CONF_JIECANG_APP_LAYOUT, CONF_JIECANG_APP_TRANSPORT, CONF_HAS_LIGHT}
        ),
    ),
    BED_TYPE_MALOUF_APP: SideProfile(
        "Malouf / Lucid app",
        frozenset(
            {CONF_MALOUF_APP_PROFILE, CONF_MALOUF_APP_MODEL, CONF_MALOUF_APP_TRANSPORT, CONF_MALOUF_APP_PRIMARY}
        ),
    ),
    BED_TYPE_LEGGETT_LP_LEGACY: SideProfile(
        "L&P legacy app",
        frozenset(
            {CONF_LP_LEGACY_MODEL, CONF_LP_LEGACY_MODE, CONF_LP_LEGACY_WRITE_UUID, CONF_LP_LEGACY_READ_UUID}
        ),
    ),
    BED_TYPE_LEGGETT_OKIN: SideProfile("Leggett & Platt app", frozenset({CONF_LEGGETT_APP_PROFILE})),
    BED_TYPE_MOTION_BED: SideProfile("Motion Bed", MOTION_BED_CONFIG_KEYS | {CONF_BLE_DEVICE_NAME}),
    BED_TYPE_STARCODE_ABM5_4: SideProfile("AdjustableM5X4", STARCODE_APP_CONFIG_KEYS),
    BED_TYPE_STARCODE_M5X5: SideProfile(
        "AdjustableM5X5",
        frozenset({CONF_STARCODE_M5X5_PROFILE, CONF_BLE_DEVICE_NAME, CONF_STARCODE_LIFT_ENTRIES}),
    ),
    BED_TYPE_VIBRADORM_APP: SideProfile("Vibradorm app", VIBRADORM_APP_CONFIG_KEYS | {CONF_HAS_MASSAGE}),
    BED_TYPE_VMATBASIC: SideProfile("V-MAT Basic", VMATBASIC_CONFIG_KEYS),
    BED_TYPE_TRANQUIL: SideProfile("Tranquil"),
    BED_TYPE_ZSERIES: SideProfile("Customatic Z-Series", variant_owned=True),
    BED_TYPE_ADJUSTABLE_LUMBAR: SideProfile("Adjustable bed (Lumbar)", variant_owned=True),
    BED_TYPE_SIMMONS: SideProfile("SIMMONS", variant_owned=True),
    **dict.fromkeys(RICHMAT_MH_BED_TYPES, SideProfile("Richmat app model", variant_owned=True)),
    BED_TYPE_REMACRO: SideProfile("Remacro app", variant_owned=True),
    BED_TYPE_SVANE: SideProfile("Svane Remote", variant_owned=True),
}
_BY_VARIANT: Final[dict[tuple[str, str], SideProfile]] = {
    (BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA): SideProfile("Woosa Sleep"),
    (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN): SideProfile(
        "Leggett & Platt app", frozenset({CONF_LEGGETT_APP_PROFILE})
    ),
    (BED_TYPE_KEESON, KEESON_VARIANT_SIMON_LI): SideProfile("Simon Li"),
    # The motor count picks the Healing 6/7/8 product of one receiver.
    (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT): SideProfile(
        "Heal Every Night", frozenset({CONF_MOTOR_COUNT})
    ),
    (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_SEATING): SideProfile("OKIN-Seating"),
    (BED_TYPE_KEESON, KEESON_VARIANT_BEDSENSE_BASES): SideProfile("Bedsense Bases"),
    (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA): SideProfile("INNOVA"),
    (BED_TYPE_KEESON, KEESON_VARIANT_MAXCOIL_UNA): SideProfile("MaxCoil Una"),
    (BED_TYPE_KEESON, KEESON_VARIANT_DYNASTY_BASES): SideProfile("Dynasty Bases"),
}


def per_side_profile(bed_type: str | None, variant: str | None) -> SideProfile | None:
    """Return the per-side app profile of a bed type and variant, if any."""
    if bed_type is None:
        return None
    if variant is not None and (bed_type, variant) in _BY_VARIANT:
        return _BY_VARIANT[bed_type, variant]
    return _BY_BED_TYPE.get(bed_type)


def is_per_side_variant(bed_type: str | None, variant: str | None) -> bool:
    """Return True when this variant is a side's own app or model choice."""
    if bed_type is None:
        return False
    if variant is not None and (bed_type, variant) in _BY_VARIANT:
        return True
    profile = _BY_BED_TYPE.get(bed_type)
    return profile is not None and profile.variant_owned
