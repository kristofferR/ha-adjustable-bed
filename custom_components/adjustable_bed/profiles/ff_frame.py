"""Profiles over the FFFF frame codec.

``SOLACE_PROFILES`` are the ``solace`` bed type's routes: the name-selected
HomeKobo 1.4, Sealy MotionFlex 1.0.3 and Sweet Night 1.0.6 routes, the explicit
Woosa Sleep 1.1.9 variant, and two routes without a report (the user-confirmed
S4-Y layout and unidentified manual entries). ``BEDSENSE`` is BedSense 1.8
(row108) and ``MOTION_BED`` is Motion Bed 1.24 (row032), whose callsite table
and typed builders live in ``beds/motion_bed/protocol.py``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from ..beds.motion_bed.protocol import SOURCE_COMMANDS
from ..codec import ff_frame as codec
from ..codec.ff_frame import control, query, summed
from ..const import SOLACE_NAME_PATTERNS
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

Axis = Literal["back", "legs", "head", "hip", "lumbar", "bed_height", "tilt"]
QueryFamily = Literal["q1", "q2", "home_k2", "woosa"]


class SolaceCommands:
    """Frames of the name-selected Solace routes. ``arg`` selects slot, branch or level."""

    PRESET_TV = control(0x05)
    PRESET_ZERO_G = control(0x09)
    PRESET_ANTI_SNORE = control(0x0F)
    PRESET_FLAT_BED = control(0x08)
    PRESET_RELAXING_BEDTIME = control(0x6A)
    PRESET_LEGACY_ALL_FLAT = control(0x2A)

    # Recall, then the branches sent while a preset is reported selected.
    PRESET_MEMORY_1 = control(0x0A, arg=0xA1)
    PRESET_MEMORY_2 = control(0x0B, arg=0xB1)
    PRESET_TV_SELECTED = control(0x05, arg=0x51)
    PRESET_ZERO_G_SELECTED = control(0x09, arg=0x91)
    PRESET_ANTI_SNORE_SELECTED = control(0x0F, arg=0xF1)

    # Program; ``*_SELECTED`` and ``*_DESELECTED`` are the branches that clear a slot.
    PROGRAM_MEMORY_1 = control(0x0A, arg=0xA0)
    PROGRAM_MEMORY_1_SELECTED = control(0x0A, arg=0xAF)
    PROGRAM_MEMORY_2 = control(0x0B, arg=0xB0)
    PROGRAM_MEMORY_2_SELECTED = control(0x0B, arg=0xBF)
    PROGRAM_TV = control(0x05, arg=0x50)
    PROGRAM_TV_DESELECTED = control(0x05, arg=0x5F)
    PROGRAM_ZERO_G = control(0x09, arg=0x90)
    PROGRAM_ZERO_G_DESELECTED = control(0x09, arg=0x9F)
    PROGRAM_ANTI_SNORE = control(0x0F, arg=0xF0)
    PROGRAM_ANTI_SNORE_DESELECTED = control(0x0F, arg=0xFF)

    MOTOR_HEAD_UP = control(0x01)
    MOTOR_HEAD_DOWN = control(0x02)
    MOTOR_BACK_UP = control(0x03)
    MOTOR_BACK_DOWN = control(0x04)
    MOTOR_LEGS_UP = control(0x06)
    MOTOR_LEGS_DOWN = control(0x07)
    MOTOR_HIP_UP = control(0x0D)
    MOTOR_HIP_DOWN = control(0x0E)
    MOTOR_LIFT_UP = control(0x21)
    MOTOR_LIFT_DOWN = control(0x22)
    MOTOR_TILT_UP = control(0x28)
    MOTOR_TILT_DOWN = control(0x29)
    MOTOR_STOP = codec.STOP

    # Preset-state queries. Q1 and Q2 are distinct firmware response families.
    QUERY_Q1 = tuple(query(register, 0x09) for register in (0x28, 0x31, 0x16, 0x1F, 0x3A))
    QUERY_Q2 = tuple(query(register, 0x03) for register in (0x28, 0x30, 0x18, 0x20, 0x38))

    MASSAGE_HEAD_UP = control(0x10)
    MASSAGE_HEAD_DOWN = control(0x11)
    MASSAGE_FOOT_UP = control(0x12)
    MASSAGE_FOOT_DOWN = control(0x13)
    MASSAGE_FREQUENCY_UP = control(0x14)
    MASSAGE_FREQUENCY_DOWN = control(0x15)
    MASSAGE_STOP = control(0x1C)
    MASSAGE_TIMER_10_MIN = control(0x16)
    MASSAGE_TIMER_20_MIN = control(0x17)
    MASSAGE_TIMER_30_MIN = control(0x18)
    MASSAGE_CIRCULATION_FULL_BODY = control(0xE4, group=0x05)
    MASSAGE_CIRCULATION_HEAD = control(0xE3, group=0x05)
    MASSAGE_CIRCULATION_LEG = control(0xE5, group=0x05)
    MASSAGE_CIRCULATION_HIP = control(0xE6, group=0x05)

    LIGHT_LEVELS = tuple(control(0x23, arg=level) for level in range(11))
    LIGHT_STATUS_QUERY = control(0x23, arg=0xFF, group=0x05)
    LIGHT_TIMER_10_MIN = control(0x19)
    LIGHT_TIMER_8_HOURS = control(0x1A)
    LIGHT_TIMER_10_HOURS = control(0x1B)

    # MotionFlex audio uses the additive-checksum frames.
    MUSIC_TOGGLE = summed(0x01, 0x13, b"\xff")
    MUSIC_OFF = summed(0x01, 0x13, b"\x00")
    AUDIO_VOLUME_QUERY = summed(0x01, 0x15, b"\x00")


@dataclass(frozen=True, kw_only=True)
class SolaceProfile:
    """One evidence-backed capability route of the ``solace`` bed type."""

    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    axes: tuple[Axis, ...]
    """Motor covers in order. Every route has back and legs."""
    presets: bool
    """Flat, TV, zero-G, anti-snore and the numbered memories."""
    memory_slots: int
    queries: QueryFamily | None
    """Startup preset-state query family; ``None`` also skips the notification channel."""
    massage: bool = False
    circulation: bool = False
    light_levels: bool = False
    """Brightness 0-10, which also adds an "Off" light timer."""
    light_timer: bool = False
    relaxing_bedtime: bool = False
    audio: bool = False
    alarm: bool = False
    clock_sync: bool = False
    """Startup sends the clock first and the light-status query last."""
    flat: bytes = SolaceCommands.PRESET_FLAT_BED
    query_delay_ms: int = 0
    """Wait after notifications start before the first status query."""
    query_spacing_ms: int = 0
    """Wait between consecutive startup queries."""
    # Woosa only, unused elsewhere:
    preset_preamble_ms: int = 0
    """Presets send STOP, wait this long, then the preset."""
    massage_step_ms: int = 0
    """Spacing of the massage start sequence (off, timer, head, foot, mode)."""
    save_requery_ms: int = 0
    """After a save, re-send each preset query this long apart."""


SOLACE_PROFILES: Final[dict[str, SolaceProfile]] = {
    profile.key: profile
    for profile in (
        # HomeKobo and Sweet Night route these names; neither proves optional hardware.
        SolaceProfile(
            key="common",
            # One start frame, then STOP at release (#483).
            execution=ExecutionCapabilities(hold="latched"),
            axes=("back", "legs"),
            presets=True,
            memory_slots=2,
            queries="q2",
            light_timer=True,
            query_delay_ms=300,
            query_spacing_ms=500,
        ),
        SolaceProfile(
            key="home_k1",
            # One start frame, then STOP at release (#483).
            execution=ExecutionCapabilities(hold="latched"),
            axes=("back", "legs", "head", "hip"),
            presets=True,
            memory_slots=2,
            queries="q1",
            massage=True,
            circulation=True,
            light_timer=True,
            query_delay_ms=300,
            query_spacing_ms=500,
        ),
        SolaceProfile(
            key="home_k2",
            # One start frame, then STOP at release (#483).
            execution=ExecutionCapabilities(hold="latched"),
            axes=("back", "legs", "head", "lumbar"),
            presets=True,
            memory_slots=2,
            queries="home_k2",
            massage=True,
            light_timer=True,
            query_delay_ms=300,
            query_spacing_ms=500,
        ),
        SolaceProfile(
            key="motion_flex",
            # One start frame, then STOP at release (#483).
            execution=ExecutionCapabilities(hold="latched"),
            axes=("back", "legs"),
            presets=True,
            memory_slots=2,
            queries="q2",
            light_levels=True,
            light_timer=True,
            relaxing_bedtime=True,
            audio=True,
            alarm=True,
            clock_sync=True,
            query_delay_ms=300,
            query_spacing_ms=500,
        ),
        SolaceProfile(
            key="woosa",
            # One start frame, then STOP at release (#483).
            execution=ExecutionCapabilities(hold="latched"),
            axes=("back", "legs"),
            presets=True,
            memory_slots=1,
            queries="woosa",
            massage=True,
            light_levels=True,
            light_timer=True,
            alarm=True,
            preset_preamble_ms=200,
            massage_step_ms=400,
            save_requery_ms=300,
        ),
        # Hardware-confirmed four-cover layout with the deployed legacy flat; no report.
        SolaceProfile(
            key="legacy_s4_y",
            axes=("back", "legs", "bed_height", "tilt"),
            presets=True,
            memory_slots=2,
            queries=None,
            flat=SolaceCommands.PRESET_LEGACY_ALL_FLAT,
        ),
        # Unidentified manual entries keep only movement and STOP.
        SolaceProfile(
            key="unverified",
            axes=("back", "legs"),
            presets=False,
            memory_slots=0,
            queries=None,
        ),
    )
}

_HOME_K1_PRIMARY_NAMES = ("qms-iq", "qms-i06", "qms-lq", "qms-l04")
_HOME_K1_FALLBACK_NAMES = ("qms-nq", "qms3")
_HOME_K2_NAMES = ("qms-jq-d", "qms4")
_LEGACY_S4_Y_PATTERN = re.compile(r"^s4-y-\d+-[a-z0-9]+$", re.IGNORECASE)


def resolve_solace_profile(device_name: str) -> SolaceProfile:
    """Resolve the narrowest name-selected route proven for an observed BLE name."""
    name = device_name.strip().lower()
    if _LEGACY_S4_Y_PATTERN.fullmatch(name):
        key = "legacy_s4_y"
    elif not (
        any(name.startswith(prefix) for prefix in SOLACE_NAME_PATTERNS)
        or name.startswith("my qms2")
    ):
        key = "unverified"
    elif name.startswith("sealymf"):
        key = "motion_flex"
    elif any(name.startswith(prefix) for prefix in _HOME_K1_PRIMARY_NAMES):
        key = "home_k1"
    elif any(name.startswith(prefix) for prefix in _HOME_K2_NAMES):
        key = "home_k2"
    elif name.startswith(("qms-mq", "qms2", "my qms2")):
        key = "common"
    elif any(name.startswith(prefix) for prefix in _HOME_K1_FALLBACK_NAMES):
        key = "home_k1"
    else:
        key = "unverified"
    return SOLACE_PROFILES[key]


def solace_query_family(profile: SolaceProfile, device_name: str) -> str | None:
    """Home K2 names that also carry a Q2 token answer Q2; other K2 names answer Q1."""
    if profile.queries != "home_k2":
        return profile.queries
    name = device_name.lower()
    return "q2" if any(token in name for token in ("qms-mq", "qms2", "qms3", "s3-2")) else "q1"


# Woosa Sleep 1.1.9 frames beyond the shared Solace set.
WOOSA_INIT: Final = summed(0x02, 0x0E, b"\x00")
WOOSA_ALARM_QUERY: Final = summed(0x01, 0x0A, b"\x0f")
WOOSA_PRESET_QUERIES: Final = tuple(query(register, 0x03) for register in (0x28, 0x18, 0x20, 0x38))
WOOSA_LIGHT_OFF: Final = control(0x4B)
WOOSA_MODE_STEP: Final = control(0x14, group=0x05)
WOOSA_HEAD_LEVELS: Final = tuple(control(code) for code in range(0x4F, 0x53))
WOOSA_FOOT_LEVELS: Final = tuple(control(code) for code in range(0x53, 0x57))
WOOSA_MODES: Final = tuple(control(code) for code in range(0x57, 0x5B))
# Massage replies: ``arg`` is the zone (1 head, 2 foot, 3 mode); one code per level.
WOOSA_MASSAGE_REPLIES: Final = {
    "head": tuple(control(code, arg=1) for code in (0x00, 0x1E, 0x1F, 0x20)),
    "foot": tuple(control(code, arg=2) for code in (0x00, 0x21, 0x22, 0x23)),
    "mode": tuple(control(code, arg=3) for code in range(0x24, 0x28)),
}
WOOSA_SAVES: Final = {
    "memory_1": SolaceCommands.PROGRAM_MEMORY_1,
    "love": SolaceCommands.PROGRAM_ANTI_SNORE,
    "tv": SolaceCommands.PROGRAM_TV,
    "zero_g": SolaceCommands.PROGRAM_ZERO_G,
}
WOOSA_STARTUP: Final[tuple[tuple[int, bytes | None], ...]] = (
    (500, WOOSA_INIT),
    (600, WOOSA_PRESET_QUERIES[0]),
    (900, WOOSA_PRESET_QUERIES[1]),
    (1000, None),
    (1200, WOOSA_PRESET_QUERIES[2]),
    (1500, WOOSA_ALARM_QUERY),
    (1500, WOOSA_PRESET_QUERIES[3]),
    (1500, SolaceCommands.LIGHT_STATUS_QUERY),
)
"""Both app startup workers' offsets in milliseconds, serialized; ``None`` is the clock."""


@dataclass(frozen=True, slots=True)
class BedSenseAction:
    row: str
    label: str
    frame: bytes
    variants: frozenset[int]


@dataclass(frozen=True, slots=True)
class MemoryRule:
    """One ordered app memory-indicator rule, matched against the spaced hex string."""

    pattern: str
    exact: bool
    required_n: int | None
    excluded: tuple[str, ...]
    excluded_exact: bool
    slot: int
    saved: bool
    next_n: int | None


@dataclass(frozen=True, kw_only=True)
class BedSenseProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    layouts: Mapping[int, tuple[str, ...]]
    actions: Mapping[str, BedSenseAction]
    memory_rules: tuple[MemoryRule, ...]
    read_delay_ms: int
    """After subscribing, wait this long, then read every FFE1 characteristic."""
    query_start_ms: int
    """The first memory query follows setup (or a refresh request) by this long."""
    query_spacing_ms: int


def _variants(spec: str) -> frozenset[int]:
    return frozenset(int(digit) for digit in spec)


def _actions(*rows: tuple[str, str, str, bytes, str]) -> dict[str, BedSenseAction]:
    return {
        key: BedSenseAction(row, label, frame, _variants(v)) for key, row, label, frame, v in rows
    }


_ALL = "123456789"
_DEFAULT = "1234579"
# Accepted row108 report C001-C079, in report order. Shared frames are literal app
# reuse: one byte sequence can drive different axes on different layouts.
BEDSENSE_ACTIONS: Final = _actions(
    ("back_up", "C001", "back up", control(0x03), _ALL),
    ("back_down", "C002", "back down", control(0x04), _ALL),
    ("head_up", "C003", "head up", control(0x01), "2345"),
    ("head_down", "C004", "head down", control(0x02), "2345"),
    ("lift_up", "C005", "lift up", control(0x01), "9"),
    ("lift_down", "C006", "lift down", control(0x02), "9"),
    ("waist_up", "C007", "waist up (TYPE 3 pressed label HIP)", control(0x0D), "123"),
    ("waist_down", "C008", "waist down (TYPE 3 pressed label HIP)", control(0x0E), "123"),
    ("hip_up", "C009", "hip up", control(0x0D), "459"),
    ("hip_down", "C010", "hip down", control(0x0E), "459"),
    ("legs_up", "C011", "leg up", control(0x06), _DEFAULT),
    ("legs_down", "C012", "leg down", control(0x07), _DEFAULT),
    ("rise_and_fall_up", "C013", "rise and fall up", control(0x06), "8"),
    ("rise_and_fall_down", "C014", "rise and fall down", control(0x07), "8"),
    ("back_and_leg_up", "C015", "back and leg up", control(0x2B), "1"),
    ("back_and_leg_down", "C016", "back and leg down", control(0x2C), "1"),
    ("release", "C017", "Release / quick-background or light-background tap", codec.STOP, _ALL),
    # The app ships this tap with a trailer that is not its CRC; it is sent verbatim.
    (
        "background_tap",
        "C018",
        "Movement or massage background tap (physical meaning unverified)",
        codec.STOP[:-2] + b"\xd8\x14",
        _ALL,
    ),
    ("circulation_whole_body", "C019", "whole body circulation", control(0xE4, group=5), "1245"),
    ("circulation_default", "C020", "whole body circulation default", control(0xE7), "3"),
    ("circulation_back_and_leg", "C021", "back and leg circulation", control(0xE8, group=5), "1"),
    ("circulation_head", "C022", "head circulation", control(0xE3, group=5), "2345"),
    ("circulation_waist", "C023", "waist circulation", control(0xE6, group=5), "123"),
    ("circulation_hip", "C024", "hip circulation", control(0xE6, group=5), "45"),
    ("circulation_legs", "C025", "leg circulation", control(0xE5, group=5), "12345"),
    ("flat", "C026", "Flat Bed / recovery", control(0x08), _DEFAULT),
    ("lumbar", "C027", "Lumbar shortcut", control(0x2E), "68"),
    ("music", "C028", "Music shortcut", control(0x28), "45"),
    ("leg_relax", "C029", "Leg Relax shortcut", control(0x29), "45"),
    ("rise", "C030", "RISE click", control(0x01), "9"),
    ("decline", "C031", "DECLINE click", control(0x02), "9"),
    ("save_m1", "C032", "M1 save", control(0x0A, arg=0xA0), _ALL),
    ("clear_m1", "C033", "M1 clear", control(0x0A, arg=0xAF), _ALL),
    ("recall_m1", "C034", "M1 recall", control(0x0A, arg=0xA1), _ALL),
    ("save_m2", "C035", "M2 save", control(0x0B, arg=0xB0), _ALL),
    ("clear_m2", "C036", "M2 clear", control(0x0B, arg=0xBF), _ALL),
    ("recall_m2", "C037", "M2 recall", control(0x0B, arg=0xB1), _ALL),
    ("save_tv", "C038", "TV save", control(0x05, arg=0x50), _ALL),
    ("clear_tv", "C039", "TV clear", control(0x05, arg=0x5F), _ALL),
    ("recall_tv", "C040", "TV recall", control(0x05, arg=0x51), _ALL),
    ("builtin_tv", "C041", "TV built-in recall", control(0x05), _ALL),
    ("save_zero_g", "C042", "Zero Gravity save", control(0x09, arg=0x90), _ALL),
    ("clear_zero_g", "C043", "Zero Gravity clear", control(0x09, arg=0x9F), _ALL),
    ("recall_zero_g", "C044", "Zero Gravity recall", control(0x09, arg=0x91), _ALL),
    ("builtin_zero_g", "C045", "Zero Gravity built-in recall", control(0x09), _ALL),
    ("save_anti_snore", "C046", "Anti Snore save", control(0x0F, arg=0xF0), _DEFAULT),
    ("clear_anti_snore", "C047", "Anti Snore clear", control(0x0F, arg=0xFF), _DEFAULT),
    ("recall_anti_snore", "C048", "Anti Snore recall", control(0x0F, arg=0xF1), _DEFAULT),
    ("builtin_anti_snore", "C049", "Anti Snore built-in recall", control(0x0F), _DEFAULT),
    ("save_flat", "C050", "Special Flat Bed save (slot 5)", control(0x0F, arg=0xF0), "68"),
    ("recall_flat", "C051", "Special Flat Bed recall (slot 5)", control(0x0F, arg=0xF1), "68"),
    ("massage_head_up", "C052", "Head massage increase", control(0x10), _ALL),
    ("massage_head_down", "C053", "Head massage decrease", control(0x11), _ALL),
    ("massage_foot_up", "C054", "Foot massage increase", control(0x12), _ALL),
    ("massage_foot_down", "C055", "Foot massage decrease", control(0x13), _ALL),
    ("massage_wave_up", "C056", "Wave/frequency increase", control(0x14), _ALL),
    ("massage_wave_down", "C057", "Wave/frequency decrease", control(0x15), _ALL),
    ("massage_timer_10", "C058", "Massage 10-minute selection", control(0x16), _ALL),
    ("massage_timer_20", "C059", "Massage 20-minute selection", control(0x17), _ALL),
    ("massage_timer_30", "C060", "Massage 30-minute selection", control(0x18), _ALL),
    ("massage_timer_cancel", "C061", "Cancel selected massage timer", control(0x1C), _ALL),
    ("light_10_min", "C062", "Light duration 10 min", control(0x19), _ALL),
    ("light_8_h", "C063", "Light duration 8 h", control(0x1A), _ALL),
    ("light_10_h", "C064", "Light duration 10 h", control(0x1B), _ALL),
    ("query_default_3", "C065", "Qdefault query 1 TV/M3", query(0x16, 0x09), "123459"),
    ("query_default_4", "C066", "Qdefault query 2 Zero Gravity/M4", query(0x1F, 0x09), "123459"),
    ("query_default_1", "C067", "Qdefault query 3 M1", query(0x28, 0x09), "123459"),
    ("query_default_2", "C068", "Qdefault query 4 M2", query(0x31, 0x09), "123459"),
    ("query_default_5", "C069", "Qdefault query 5 Anti Snore/M5", query(0x3A, 0x09), "123459"),
    ("query_68_3", "C070", "Q68 query 1 TV/M3", query(0x14, 0x03), "68"),
    ("query_68_4", "C071", "Q68 query 2 Zero Gravity/M4", query(0x1C, 0x03), "68"),
    ("query_68_1", "C072", "Q68 query 3 M1", query(0x24, 0x03), "68"),
    ("query_68_2", "C073", "Q68 query 4 M2", query(0x2C, 0x03), "68"),
    ("query_68_5", "C074", "Q68 query 5 Anti Snore/M5", query(0x3A, 0x09), "68"),
    ("query_7_3", "C075", "Q7 query 1 TV/M3", query(0x18, 0x03), "7"),
    ("query_7_4", "C076", "Q7 query 2 Zero Gravity/M4", query(0x20, 0x03), "7"),
    ("query_7_1", "C077", "Q7 query 3 M1", query(0x28, 0x03), "7"),
    ("query_7_2", "C078", "Q7 query 4 M2", query(0x30, 0x03), "7"),
    ("query_7_5", "C079", "Q7 query 5 Anti Snore/M5", query(0x38, 0x03), "7"),
)


def _rule(
    pattern: str | bytes,
    slot: int,
    saved: bool,
    *,
    exact: bool = False,
    required_n: int | None = None,
    excluded: tuple[str, ...] = (),
    excluded_exact: bool = False,
    next_n: int | None = None,
) -> MemoryRule:
    """A rule for a frame matches the frame's spaced hex string with its trailing space."""
    if isinstance(pattern, bytes):
        pattern = _spaced(pattern)
    return MemoryRule(pattern, exact, required_n, excluded, excluded_exact, slot, saved, next_n)


def _spaced(frame: bytes) -> str:
    return frame.hex(" ").upper() + " "


_ACT = {key: action.frame for key, action in BEDSENSE_ACTIONS.items()}
# Ordered app memory-indicator rules from HHKuaiJieFragment:691-919. They describe
# app indicators, not independently confirmed hardware state.
BEDSENSE_MEMORY_RULES: Final = (
    _rule("00 A5", 3, True),
    _rule("00 A9", 4, True),
    _rule("00 AA", 1, True),
    _rule("00 AB", 2, True),
    _rule("00 AF", 5, True, excluded=(_spaced(_ACT["clear_m1"]),), excluded_exact=True),
    _rule(_ACT["save_m1"], 1, True, exact=True),
    _rule(_ACT["clear_m1"], 1, False, exact=True),
    _rule(_ACT["save_m2"], 2, True, exact=True),
    _rule(_ACT["clear_m2"], 2, False, exact=True),
    _rule(_ACT["save_tv"], 3, True, exact=True),
    _rule(_ACT["clear_tv"], 3, False, exact=True),
    _rule(_ACT["save_zero_g"], 4, True, exact=True),
    _rule(_ACT["clear_zero_g"], 4, False, exact=True),
    _rule(_ACT["save_anti_snore"], 5, True),
    _rule(_ACT["clear_anti_snore"], 5, False, exact=True),
    # Each query arms the parser state ``n`` that its reply selector must match.
    _rule(_ACT["query_68_1"], 1, False, next_n=1),
    _rule("00 0A ", 1, True, required_n=1),
    _rule(_ACT["query_7_1"], 1, False, next_n=2),
    _rule("00 0A ", 1, True, required_n=2),
    _rule(_ACT["query_68_2"], 2, False, next_n=3),
    _rule("00 0B ", 2, True, required_n=3),
    _rule(_ACT["query_default_2"], 2, False, next_n=11),
    _rule("00 0B ", 2, True, required_n=11),
    _rule(_ACT["query_7_2"], 2, False, next_n=4),
    _rule("00 0B ", 2, True, required_n=4),
    _rule(_ACT["query_68_3"], 3, False, next_n=5),
    _rule("00 05 ", 3, True, required_n=5),
    _rule(_ACT["query_default_3"], 3, False, next_n=15),
    _rule("00 05 ", 3, True, required_n=15),
    _rule(_ACT["query_7_3"], 3, False, next_n=6),
    _rule("00 05 ", 3, True, required_n=6),
    _rule(_ACT["query_68_4"], 4, False, next_n=7),
    _rule("00 09 ", 4, True, required_n=7),
    _rule(_ACT["query_default_4"], 4, False, next_n=14),
    _rule("00 09 ", 4, True, required_n=14, excluded=("BF 0B ", "AE C0 ", "7E C2 ")),
    _rule(_ACT["query_7_4"], 4, False, next_n=8),
    _rule("00 09 ", 4, True, required_n=8),
    _rule(_ACT["query_default_5"], 5, False, next_n=13),
    _rule("00 0F ", 5, True, required_n=13),
    _rule(_ACT["query_7_5"], 5, False, next_n=9),
    _rule("00 0F ", 5, True, required_n=9),
)

BEDSENSE: Final = BedSenseProfile(
    key="bedsense",
    # One start write, then the pause frame at release (#483).
    execution=ExecutionCapabilities(hold="latched"),
    layouts={
        1: ("back", "waist", "back_and_leg", "legs"),
        2: ("back", "waist", "head", "legs"),
        3: ("back", "waist", "head", "legs"),
        4: ("back", "hip", "head", "legs"),
        5: ("back", "hip", "head", "legs"),
        6: ("back",),
        7: ("back", "legs"),
        8: ("back", "rise_and_fall"),
        9: ("back", "hip", "lift", "legs"),
    },
    actions=BEDSENSE_ACTIONS,
    memory_rules=BEDSENSE_MEMORY_RULES,
    read_delay_ms=200,
    query_start_ms=2000,
    query_spacing_ms=200,
)


def bedsense_layout(name: str | None) -> int:
    """Exact, case-sensitive selection precedence; not a discovery signature."""
    name = name or ""
    if "JQ-D" in name:
        return 2
    if "JQ" in name or "NQ" in name:
        return 1
    if "IQ" in name:
        return 4
    if "LQ" in name:
        return 5
    if "KQ" in name and "H" not in name:
        return 6
    if "MQ" in name or "UPS" in name:
        return 7
    if "S4-2" in name:
        return 9
    if "H" in name and "S4" not in name:
        return 8
    return 3


@dataclass(frozen=True, kw_only=True)
class MotionBedProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    commands: Mapping[str, bytes]
    """Every app callsite's frame; the controller gates each by model and state."""
    stop: bytes


MOTION_BED: Final = MotionBedProfile(key="motion_bed", commands=SOURCE_COMMANDS, stop=codec.STOP)
