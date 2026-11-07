"""Profiles over the Kaidi mesh codec.

The ``kaidi`` bed type resolves one profile per protocol variant. The Seat
profiles (``seat_1``, ``seat_2``, ``seat_3``, ``seat_1_2``) hold the SEAT_*
tables the Rize 1.3.0, ISleep 1.6.3 and Floyd 1.0.7 bundles share, as the
pre-v5 controller sent them; product IDs gate their optional controls. ``FLOYD``
(``floyd``) is Floyd Home 1.0.7, product 139, from the accepted row117 report.
``IsleepProfile`` serves the ``isleep`` bed type from the accepted row064 report
(ISleep 1.6.3 (45), ``com.kaidi_test4``) for one selected product. Each app keeps
its own command table; none reuses a sibling's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from typing import Any, ClassVar, Final

from ..beds.kaidi.protocol import (
    KaidiAdvertisement,
    KaidiSeatBars,
    decode_kaidi_sofa_acu_no,
    parse_kaidi_manufacturer_payload,
)
from ..const import (
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    KAIDI_VARIANT_FLOYD,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_1_2,
    KAIDI_VARIANT_SEAT_2,
    KAIDI_VARIANT_SEAT_3,
    VARIANT_AUTO,
)
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

# ---------------------------------------------------------------------------
# Seat profiles (``kaidi`` bed type)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class KaidiCommandProfile:
    """Command bytes of one Kaidi command family, from the apps' SEAT_* tables."""

    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """The controller declares its own (#483)."""
    # Core motors (all beds)
    head_up: int
    head_down: int
    head_stop: int
    foot_up: int
    foot_down: int
    foot_stop: int
    stop_all: int | None = None
    # Memory presets
    memory_save: Mapping[int, int] = field(default_factory=dict)
    memory_recall: Mapping[int, int] = field(default_factory=dict)
    # Standard presets
    preset_flat: int | None = None
    preset_zero_g: int | None = None
    preset_anti_snore: int | None = None
    # Extended motors (3+ motor beds)
    back_up: int | None = None
    back_down: int | None = None
    back_stop: int | None = None
    waist_up: int | None = None
    waist_down: int | None = None
    waist_stop: int | None = None
    neck_up: int | None = None
    neck_down: int | None = None
    neck_stop: int | None = None
    all_up: int | None = None
    all_down: int | None = None
    all_stop: int | None = None
    new_all_up: int | None = None
    new_all_down: int | None = None
    new_all_stop: int | None = None
    # Lights
    light_on: int | None = None
    light_off: int | None = None
    # Extended presets
    preset_book: int | None = None
    preset_leisure: int | None = None
    # Direct position targeting; the parameter byte carries the 0-100 target
    head_setting: int | None = None
    leg_setting: int | None = None
    # Massage
    massage_start: int | None = None
    massage_stop: int | None = None
    massage_timer_15: int | None = None
    massage_timer_30: int | None = None
    massage_timer_45: int | None = None
    massage_mode_1: int | None = None
    massage_mode_2: int | None = None
    massage_mode_3: int | None = None


_SCALAR_FIELDS: Final = tuple(
    f.name
    for f in fields(KaidiCommandProfile)
    if f.name not in ("key", "execution", "memory_save", "memory_recall")
)

SEAT_1: Final = KaidiCommandProfile(
    key=KAIDI_VARIANT_SEAT_1,
    head_up=0x01,
    head_down=0x02,
    head_stop=0x03,
    foot_up=0x04,
    foot_down=0x05,
    foot_stop=0x06,
    stop_all=0x1C,
    memory_save={1: 0x25, 2: 0x26, 3: 0x27, 4: 0x28},
    memory_recall={1: 0x29, 2: 0x2A, 3: 0x2B, 4: 0x2C},
    preset_zero_g=0x62,
    preset_anti_snore=0x65,
    preset_flat=0x68,
    # Extended motors
    back_up=0x7A,  # SEAT_1_BACK_UP = 122
    back_down=0x7B,  # SEAT_1_BACK_DOWN = 123
    back_stop=0x7C,  # SEAT_1_BACK_STOP = 124
    waist_up=0x83,  # SEAT_1_WAIST_UP = 131
    waist_down=0x84,  # SEAT_1_WAIST_DOWN = 132
    waist_stop=0x85,  # SEAT_1_WAIST_STOP = 133
    neck_up=0x8C,  # SEAT_1_NECK_UP = 140
    neck_down=0x8D,  # SEAT_1_NECK_DOWN = 141
    neck_stop=0x8E,  # SEAT_1_NECK_STOP = 142
    all_up=0x07,  # SEAT_1_ALL_UP = 7
    all_down=0x08,  # SEAT_1_ALL_DOWN = 8
    all_stop=0x09,  # SEAT_1_ALL_STOP = 9
    new_all_up=0x95,  # SEAT_1_NEW_ALL_UP = 149
    new_all_down=0x96,  # SEAT_1_NEW_ALL_DOWN = 150
    new_all_stop=0x97,  # SEAT_1_NEW_ALL_STOP = 151
    # Lights
    light_on=0x5C,  # SEAT_1_BED_LIGHT_ON = 92
    light_off=0x5D,  # SEAT_1_BED_LIGHT_OFF = 93
    # Extended presets
    preset_book=0x9E,  # SEAT_1_BOOK = 158
    preset_leisure=0xA1,  # SEAT_1_LEISURE = 161
    # Direct position targeting
    head_setting=0x4D,  # SEAT_1_HEAD_SETTING = 77
    leg_setting=0x4F,  # SEAT_1_LEG_SETTING = 79
    # Massage
    massage_start=0x47,  # SEAT_1_MASSAGE_START = 71
    massage_stop=0x48,  # SEAT_1_MASSAGE_STOP = 72
    massage_timer_15=0x53,  # SEAT_1_MASSAGE_15 = 83
    massage_timer_30=0x54,  # SEAT_1_MASSAGE_30 = 84
    massage_timer_45=0x55,  # SEAT_1_MASSAGE_45 = 85
)
SEAT_2: Final = KaidiCommandProfile(
    key=KAIDI_VARIANT_SEAT_2,
    head_up=0x0A,
    head_down=0x0B,
    head_stop=0x0C,
    foot_up=0x0D,
    foot_down=0x0E,
    foot_stop=0x0F,
    stop_all=0x1D,
    memory_save={1: 0x2D, 2: 0x2E, 3: 0x2F, 4: 0x30},
    memory_recall={1: 0x31, 2: 0x32, 3: 0x33, 4: 0x34},
    preset_zero_g=0x63,
    preset_anti_snore=0x66,
    preset_flat=0x69,
    # Extended motors
    back_up=0x7D,  # SEAT_2_BACK_UP = 125
    back_down=0x7E,  # SEAT_2_BACK_DOWN = 126
    back_stop=0x7F,  # SEAT_2_BACK_STOP = 127
    waist_up=0x86,  # SEAT_2_WAIST_UP = 134
    waist_down=0x87,  # SEAT_2_WAIST_DOWN = 135
    waist_stop=0x88,  # SEAT_2_WAIST_STOP = 136
    neck_up=0x8F,  # SEAT_2_NECK_UP = 143
    neck_down=0x90,  # SEAT_2_NECK_DOWN = 144
    neck_stop=0x91,  # SEAT_2_NECK_STOP = 145
    new_all_up=0x98,  # SEAT_2_NEW_ALL_UP = 152
    new_all_down=0x99,  # SEAT_2_NEW_ALL_DOWN = 153
    new_all_stop=0x9A,  # SEAT_2_NEW_ALL_STOP = 154
    # Lights
    light_on=0x5E,  # SEAT_2_BED_LIGHT_ON = 94
    light_off=0x5F,  # SEAT_2_BED_LIGHT_OFF = 95
    # Extended presets
    preset_book=0x9F,  # SEAT_2_BOOK = 159
    preset_leisure=0xA2,  # SEAT_2_LEISURE = 162
    # Direct position targeting
    head_setting=0x4E,  # SEAT_2_HEAD_SETTING = 78
    leg_setting=0x50,  # SEAT_2_LEG_SETTING = 80
    # Massage
    massage_start=0x49,  # SEAT_2_MASSAGE_START = 73
    massage_stop=0x4A,  # SEAT_2_MASSAGE_STOP = 74
    massage_timer_15=0x56,  # SEAT_2_MASSAGE_15 = 86
    massage_timer_30=0x57,  # SEAT_2_MASSAGE_30 = 87
    massage_timer_45=0x58,  # SEAT_2_MASSAGE_45 = 88
)
SEAT_3: Final = KaidiCommandProfile(
    key=KAIDI_VARIANT_SEAT_3,
    head_up=0x13,
    head_down=0x14,
    head_stop=0x15,
    foot_up=0x16,
    foot_down=0x17,
    foot_stop=0x18,
    memory_save={1: 0x35, 2: 0x36, 3: 0x37, 4: 0x38},
    memory_recall={1: 0x39, 2: 0x3A, 3: 0x3B, 4: 0x3C},
    # Seat 3 has limited extended commands
    waist_up=0x19,  # SEAT_3_WAIST_UP = 25
    waist_down=0x1A,  # SEAT_3_WAIST_DOWN = 26
    waist_stop=0x1B,  # SEAT_3_WAIST_STOP = 27
    neck_up=0x92,  # SEAT_3_NECK_UP = 146
    neck_down=0x93,  # SEAT_3_NECK_DOWN = 147
    neck_stop=0x94,  # SEAT_3_NECK_STOP = 148
    new_all_up=0x9B,  # SEAT_3_NEW_ALL_UP = 155
    new_all_down=0x9C,  # SEAT_3_NEW_ALL_DOWN = 156
    new_all_stop=0x9D,  # SEAT_3_NEW_ALL_STOP = 157
    # Lights
    light_on=0x60,  # SEAT_3_BED_LIGHT_ON = 96
    light_off=0x61,  # SEAT_3_BED_LIGHT_OFF = 97
    # Extended presets
    preset_book=0xA0,  # SEAT_3_BOOK = 160
    preset_leisure=0xA3,  # SEAT_3_LEISURE = 163
)
# Seat 1+2 sends the Seat 1 table, then each command's Seat 2 equivalent.
SEAT_1_2: Final = replace(SEAT_1, key=KAIDI_VARIANT_SEAT_1_2)
SEAT_PROFILES: Final[dict[str, KaidiCommandProfile]] = {
    profile.key: profile for profile in (SEAT_1, SEAT_2, SEAT_3, SEAT_1_2)
}


def dual_command_map(
    primary: KaidiCommandProfile, secondary: KaidiCommandProfile
) -> dict[int, int]:
    """Map each primary command to the secondary table's command for the same control."""
    mapping: dict[int, int] = {}
    for name in _SCALAR_FIELDS:
        p, s = getattr(primary, name), getattr(secondary, name)
        if p is not None and s is not None:
            mapping[p] = s
    for p_table, s_table in (
        (primary.memory_save, secondary.memory_save),
        (primary.memory_recall, secondary.memory_recall),
    ):
        for slot, p_cmd in p_table.items():
            if (s_cmd := s_table.get(slot)) is not None:
                mapping[p_cmd] = s_cmd
    return mapping


SEAT_1_2_SECONDARY: Final = dual_command_map(SEAT_1, SEAT_2)


@dataclass(frozen=True, slots=True)
class KaidiProductFamily:
    """Capabilities for a product ID, derived from the OEM app's bedUI mapping."""

    bed_ui: int
    has_back: bool = False
    has_waist: bool = False
    has_neck: bool = False
    has_all: bool = False
    has_lights: bool = False
    has_massage: bool = False
    has_book: bool = False
    has_leisure: bool = False


# Product ID → capability set.  Derived from the Rize/Floyd/ISleep JS bundles.
# bedUI 2: head + foot only
# bedUI 3: back + foot + all
# bedUI 4: back + foot + waist + all
# bedUI 5-6: back + foot + waist + all + book + leisure presets
# bedUI 7-8: back + foot + waist + all + leisure preset (+ neck for bedUI 8)
# fmt: off
KAIDI_PRODUCT_FAMILIES: Final[dict[int, KaidiProductFamily]] = {
    129: KaidiProductFamily(bed_ui=2),
    130: KaidiProductFamily(bed_ui=2),
    131: KaidiProductFamily(bed_ui=3, has_back=True, has_all=True),
    132: KaidiProductFamily(bed_ui=4, has_back=True, has_waist=True, has_all=True),
    133: KaidiProductFamily(bed_ui=3, has_back=True, has_all=True),
    134: KaidiProductFamily(bed_ui=4, has_back=True, has_waist=True, has_all=True),
    135: KaidiProductFamily(
        bed_ui=5, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_book=True, has_leisure=True,
    ),
    136: KaidiProductFamily(
        bed_ui=6, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_book=True, has_leisure=True,
    ),
    137: KaidiProductFamily(
        bed_ui=7, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_leisure=True,
    ),
    138: KaidiProductFamily(
        bed_ui=8, has_back=True, has_waist=True, has_neck=True, has_all=True,
        has_lights=True, has_massage=True, has_leisure=True,
    ),
    139: KaidiProductFamily(bed_ui=2),
    142: KaidiProductFamily(
        bed_ui=5, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_book=True, has_leisure=True,
    ),
    143: KaidiProductFamily(bed_ui=2),
}
# fmt: on
# Default for beds without a known product ID.
DEFAULT_PRODUCT_FAMILY: Final = KaidiProductFamily(bed_ui=2)

# ---------------------------------------------------------------------------
# Variant resolution
# ---------------------------------------------------------------------------

KAIDI_MANUAL_VARIANTS: Final[frozenset[str]] = frozenset(
    {
        KAIDI_VARIANT_FLOYD,
        KAIDI_VARIANT_SEAT_1,
        KAIDI_VARIANT_SEAT_2,
        KAIDI_VARIANT_SEAT_3,
        KAIDI_VARIANT_SEAT_1_2,
    }
)

# Product IDs from the OEM APKs (Rize 1.3.0, ISleep 1.6.3, Floyd 1.0.7).
# All three apps use ONLY SEAT_* commands.  Single-base products use seat_1,
# dual-base products use seat_1 + seat_2 (seat_1_2).
#
# IDs 140-141 do not appear in any of the three APK versions and are
# intentionally omitted.  Devices with unmapped IDs fall through to the
# sofa_acu_no seat-bar heuristic or resolve to "unresolved_metadata".
#
# ID  | Name              | App         | bedUI | Classification
# ----|-------------------|-------------|-------|---------------
# 129 | BED_TYPE_SINGLE   | All         | 2     | seat_1
# 130 | BED_TYPE_DOUBLE2_4| All         | 2     | seat_1_2
# 131 | BED_TYPE_SINGLE3  | All         | 3     | seat_1
# 132 | BED_TYPE_SINGLE4  | All         | 4     | seat_1
# 133 | BED_TYPE_DOUBLE3  | All         | 3     | seat_1_2
# 134 | BED_TYPE_DOUBLE4  | All         | 4     | seat_1_2
# 135 | REMEDY_3          | Rize/Floyd  | 5     | seat_1
# 136 | REMEDY_4          | Rize/Floyd  | 6     | seat_1
# 137 | CONTEMPORARY_4    | Rize/Floyd  | 7     | seat_1
# 138 | CONTEMPORARY_5    | Rize/Floyd  | 8     | seat_1
# 139 | TRANQUILITY_II    | Floyd       | —     | floyd
# 142 | BED_TYPE_SINGLE5  | ISleep      | 5     | seat_1
# 143 | BED_TYPE_DOUBLE_NEW | ISleep    | —     | seat_1_2
KAIDI_SINGLE_PRODUCT_IDS: Final[frozenset[int]] = frozenset(
    {129, 131, 132, 135, 136, 137, 138, 139, 142}
)
KAIDI_DOUBLE_PRODUCT_IDS: Final[frozenset[int]] = frozenset({130, 133, 134, 143})


@dataclass(frozen=True, slots=True)
class KaidiVariantResolution:
    """Result of resolving a Kaidi profile variant."""

    variant: str | None
    source: str
    product_id: int | None
    sofa_acu_no: int | None
    seat_bars: KaidiSeatBars | None


def _coerce_int(value: object) -> int | None:
    """Return an integer value when the input is already int-like."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def resolve_kaidi_variant(
    protocol_variant: str | None,
    *,
    product_id: int | None = None,
    sofa_acu_no: int | None = None,
) -> KaidiVariantResolution:
    """Resolve the effective Kaidi command family."""
    seat_bars = decode_kaidi_sofa_acu_no(sofa_acu_no)

    def resolved(variant: str | None, source: str) -> KaidiVariantResolution:
        return KaidiVariantResolution(variant, source, product_id, sofa_acu_no, seat_bars)

    if protocol_variant in KAIDI_MANUAL_VARIANTS:
        return resolved(protocol_variant, "manual_override")
    if product_id == FLOYD.product:
        return resolved(KAIDI_VARIANT_FLOYD, "product_id")
    if product_id in KAIDI_SINGLE_PRODUCT_IDS:
        return resolved(KAIDI_VARIANT_SEAT_1, "product_id")
    if product_id in KAIDI_DOUBLE_PRODUCT_IDS:
        return resolved(KAIDI_VARIANT_SEAT_1_2, "product_id")
    if seat_bars is not None and len(seat_bars.populated_seats) == 1:
        seat_variant = {
            1: KAIDI_VARIANT_SEAT_1,
            2: KAIDI_VARIANT_SEAT_2,
            3: KAIDI_VARIANT_SEAT_3,
        }[seat_bars.populated_seats[0]]
        return resolved(seat_variant, "sofa_acu_no")
    if product_id is not None or sofa_acu_no is not None:
        return resolved(None, "unresolved_metadata")
    return resolved(KAIDI_VARIANT_SEAT_1, "legacy_fallback")


def resolve_kaidi_variant_from_entry_data(
    entry_data: Mapping[str, Any],
    protocol_variant: str | None = None,
) -> KaidiVariantResolution:
    """Resolve a Kaidi variant from config-entry metadata."""
    return resolve_kaidi_variant(
        protocol_variant or entry_data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO),
        product_id=_coerce_int(entry_data.get(CONF_KAIDI_PRODUCT_ID)),
        sofa_acu_no=_coerce_int(entry_data.get(CONF_KAIDI_SOFA_ACU_NO)),
    )


# ---------------------------------------------------------------------------
# Floyd Home 1.0.7 (``kaidi`` bed type, ``floyd`` variant)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class FloydProfile(KaidiCommandProfile):
    """Floyd Home: the standard controls above, plus its own holds and setup commands."""

    product: int
    family: KaidiProductFamily
    """Capability gates of the app's one product."""
    holds: Mapping[str, tuple[int, int]]
    """Held control -> (start, release); one start, no refresh."""
    presets: Mapping[str, Mapping[str, int]]
    """Preset and recall commands per internal side selector."""
    confirm_add: int
    """Addition confirmation after a room assignment."""
    save_preset: int
    save_parameters: Mapping[str, int]
    """Built-in preset overwrite: ``save_preset`` with this parameter."""
    write_spacing_ms: int
    """Minimum gap between writes, from the app's write queue."""
    battery_event: int
    """Control reply command whose value 1 reports battery mode."""


# fmt: off
FLOYD: Final = FloydProfile(
    key=KAIDI_VARIANT_FLOYD,
    head_up=1, head_down=2, head_stop=3,
    foot_up=4, foot_down=5, foot_stop=6,
    stop_all=9, preset_flat=0x1C, preset_zero_g=0x62, preset_anti_snore=0x65,
    memory_save={1: 0x25, 2: 0x26, 3: 0x27},
    memory_recall={1: 0x29, 2: 0x2A, 3: 0x2B},
    light_on=0x5C, light_off=0x5D,
    product=139,
    family=KaidiProductFamily(bed_ui=2, has_lights=True),
    holds={
        "head_up": (1, 3), "head_down": (2, 3),
        "feet_up": (4, 6), "feet_down": (5, 6),
        "head_feet_up": (7, 9), "head_feet_down": (8, 9),
    },
    # E7 normal UI, E16 independently reachable exported Android receiver.
    presets={
        "first": {"zero_g": 0x62, "flat": 0x1C, "anti_snore": 0x65,
                  "memory_1": 0x29, "memory_2": 0x2A, "memory_3": 0x2B},
        "both": {"zero_g": 0x64, "flat": 0x1E, "anti_snore": 0x67,
                 "memory_1": 0x39, "memory_2": 0x3A, "memory_3": 0x3B},
        "second": {"zero_g": 0x63, "flat": 0x1D, "anti_snore": 0x66,
                   "memory_1": 0x31, "memory_2": 0x32, "memory_3": 0x33},
    },
    confirm_add=0x45,
    save_preset=0xA7,
    save_parameters={"save_zero_g": 1, "save_anti_snore": 4},
    write_spacing_ms=50,
    battery_event=0xA6,
)
# fmt: on

# ---------------------------------------------------------------------------
# ISleep 1.6.3 (``isleep`` bed type)
# ---------------------------------------------------------------------------

ISLEEP_PRODUCTS: Final = (129, 130, 131, 132, 133, 134, 142, 143)
# Values are the app's live UI, including Flat despite its misleading constant name.
# tuple order: single/left, right, both (only role1 uses columns 2 and 3).
ISLEEP_COMMANDS: Final[Mapping[str, tuple[int, int, int]]] = {
    "head_up": (1, 10, 19),
    "head_down": (2, 11, 20),
    "head_stop": (3, 12, 21),
    "legs_up": (4, 13, 22),
    "legs_down": (5, 14, 23),
    "legs_stop": (6, 15, 24),
    "all_up": (7, 16, 25),
    "all_down": (8, 17, 26),
    "all_stop": (9, 18, 27),
    "flat": (28, 29, 30),
    "save_1": (37, 45, 53),
    "save_2": (38, 46, 54),
    "save_3": (39, 47, 55),
    "memory_1": (41, 49, 57),
    "memory_2": (42, 50, 58),
    "memory_3": (43, 51, 59),
    "massage_on": (71, 73, 75),
    "massage_off": (72, 74, 76),
    "head_strength": (77, 78, 81),
    "foot_strength": (79, 80, 82),
    "timer_1": (83, 86, 89),
    "timer_2": (84, 87, 90),
    "timer_3": (85, 88, 91),
    "light_on": (92, 94, 96),
    "light_off": (93, 95, 97),
    "zero_g": (98, 99, 100),
    "anti_snore": (101, 102, 103),
    "pattern_1": (107, 108, 109),
    "pattern_2": (110, 111, 112),
    "pattern_3": (113, 114, 115),
    "pattern_cancel": (116, 117, 118),
    "timer_cancel": (119, 120, 121),
    "back_up": (122, 122, 122),
    "back_down": (123, 123, 123),
    "back_stop": (124, 124, 124),
    "lumbar_up": (131, 131, 131),
    "lumbar_down": (132, 132, 132),
    "lumbar_stop": (133, 133, 133),
    "new_all_up": (149, 149, 149),
    "new_all_down": (150, 150, 150),
    "new_all_stop": (151, 151, 151),
}


@dataclass(frozen=True)
class IsleepProfile:
    """ISleep for one selected product, room and actuator descriptor.

    Only rendered controls, rather than the numeric product's implied motors.
    """

    key: ClassVar[str] = "isleep"
    execution: ClassVar[ExecutionCapabilities] = NO_EXECUTION_CAPABILITIES
    """The controller declares its own (#483)."""
    commands: ClassVar[Mapping[str, tuple[int, int, int]]] = ISLEEP_COMMANDS
    enroll_ack: ClassVar[int] = 69
    """Sent once, after the first session that follows an accepted enrollment."""
    enroll_wait_s: ClassVar[int] = 8

    product: int
    room: int
    actuators: int

    @property
    def split(self) -> bool:
        """Only role1 uses one-address left/both/right opcodes."""
        return self.product in (130, 143) and self.actuators != 2

    @property
    def axes(self) -> tuple[str, ...]:
        if self.product in (132, 134):
            return ("back", "legs", "head", "lumbar")
        if self.product in (131, 133):
            return ("back", "legs", "head")
        return ("back", "legs")


def validate_isleep_profile(data: Mapping[str, object]) -> IsleepProfile:
    """Reject unknown products and invalid explicit session identities before writing."""
    product = data.get(CONF_PRODUCT_TYPE)
    room = data.get(CONF_KAIDI_ROOM_ID)
    actuators = data.get(CONF_KAIDI_SOFA_ACU_NO, 2)
    if type(product) is not int or product not in ISLEEP_PRODUCTS:
        raise ValueError("Select one of the eight ISleep products")
    if type(room) is not int or not -(2**31) <= room < 2**31:
        raise ValueError("ISleep requires the selected signed 32-bit room ID")
    if type(actuators) is not int or not 0 <= actuators <= 65535:
        raise ValueError("Invalid ISleep actuator descriptor")
    return IsleepProfile(product, room, actuators)


def isleep_advertisement(manufacturer_data: Mapping[int, bytes]) -> KaidiAdvertisement | None:
    """Apply the live inventory's company/product/actuator gates, with safe bounds."""
    for company, payload in manufacturer_data.items():
        if company != 0xFFFF:
            continue
        ad = parse_kaidi_manufacturer_payload(payload)
        if ad is None or ad.adv_type not in (1, 2, 9) or ad.product_id not in ISLEEP_PRODUCTS:
            continue
        if ad.adv_type == 9 and ad.company_id != 0x4B44:
            continue
        acu = ad.sofa_acu_no
        if acu is None or (acu >> 8 & 7) > 5 or (acu & 15) > 5 or (acu & 240) > 5:
            continue
        return ad
    return None


def add_isleep_metadata(data: Mapping[str, object], manufacturer_data: Mapping[int, bytes]) -> dict:
    """Seed the explicit app form; never replace an already selected room."""
    result = dict(data)
    ad = isleep_advertisement(manufacturer_data)
    if ad is not None:
        result.setdefault(CONF_PRODUCT_TYPE, ad.product_id)
        result.setdefault(CONF_KAIDI_SOFA_ACU_NO, ad.sofa_acu_no)
        if ad.room_id is not None:
            room = ad.room_id if ad.room_id < 2**31 else ad.room_id - 2**32
            result.setdefault(CONF_KAIDI_ROOM_ID, room)
    return result
