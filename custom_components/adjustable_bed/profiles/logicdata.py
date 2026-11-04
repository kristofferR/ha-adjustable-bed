"""LOGICDATA app profiles over the Jiecang codec.

The ``logicdata_app`` bed type selects one of ``APP_PROFILES``: the MOTIONrelax
phone 1.0.6 and tablet 1.0.4 apps, and the bed side of Sleep Smart Air
Mattress 1.0.0, each from its accepted APK Protocol Audit report. Every profile
drives two packet families, chosen independently of the GATT transport: P1
sends the codec's ``STANDARD`` payload and P2 its ``BILATERAL`` one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal

from ..codec import jiecang as codec
from ..codec.jiecang import BILATERAL, SHORT_RELEASE, STANDARD, Axis, MassageZone, Preset
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities
from .jiecang import NameRule, Schedule

AppKey = Literal["phone", "tablet", "sleep_smart"]
Family = Literal["p1", "p2"]
TransportChoice = Literal["t1", "t2", "t3"]
Layout = Literal[
    "standard_2",
    "standard_3_neck",
    "standard_3_lumbar",
    "standard_3_hi_low",
    "standard_3_split_upper",
    "standard_4",
    "split_series",
    "middle",
]
HeldPreset = Literal["flat", "zero_g", "anti_snore", "memory_1", "memory_2"]
Wake = Literal["flat", "zero_g", "anti_snore", "memory_1", "memory_2"]
MassageMode = Literal["long_interval", "short_interval", "wave", "continuous"]
Session = Literal["motionrelax", "sleep_smart"]

FAMILIES: Final[tuple[Family, ...]] = ("p1", "p2")
# The apps name the codec's G1, G2 and G3 transports T1, T2 and T3.
TRANSPORTS: Final[dict[TransportChoice, codec.Transport]] = {
    "t1": codec.TRANSPORTS["g1"],
    "t2": codec.TRANSPORTS["g2"],
    "t3": codec.TRANSPORTS["g3"],
}
WIRE_MASSAGE_LEVELS: Final = (0, 2, 3, 4)
WAKES: Final[tuple[Wake, ...]] = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")
_MASSAGE_MODES: Final[dict[int, MassageMode]] = {
    1: "long_interval",
    2: "short_interval",
    3: "wave",
    4: "continuous",
}

QUERY_SOFTWARE: Final = codec.query(b"\x40\x00")
QUERY_VIBRATION: Final = codec.query(b"\x08")
QUERY_HARDWARE: Final = codec.query(b"\x40")
QUERY_ACTUATOR: Final = codec.query(b"\x50")
QUERY_LIGHT: Final = codec.query(b"\x01\x00")
QUERY_STATUS: Final = codec.query()
QUERY_MASSAGE: Final = codec.query(b"\x08\x00")


@dataclass(frozen=True, kw_only=True)
class LogicdataProfile:
    key: AppKey
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    session: Session
    """Selects the controller's startup, name-role and clock-answer state machine."""
    layouts: dict[Layout, tuple[Axis, ...]]
    p2_controls: bool
    """P2 also changes presets, memory and light; otherwise they keep P1 frames."""
    presets: dict[Family, tuple[Preset, ...]]
    hold_only_presets: bool = False
    """Preset and memory buttons hold their frame instead of tapping it."""
    held_presets: dict[Family, tuple[HeldPreset, ...]]
    hold_repeat_ms: dict[HeldPreset, int]
    hold_final_frame: frozenset[HeldPreset] = frozenset()
    """Held presets that send one more frame when the hold ends normally."""
    movement_repeat_ms: int
    touch_release: Schedule
    """Release after movement, presets, memory recall and holds."""
    memory_slots: int
    memory_save_offsets: tuple[int, ...]
    memory_save_payload: bytes | None = None
    """``None`` saves with the family's payload."""
    light_releases: Schedule
    massage_mode_releases: Schedule
    massage_families: tuple[Family, ...]
    massage_query: Schedule = ()
    factory_reset: bool = False
    subscribe_delay_ms: int
    """Wait before the data subscription."""
    name_subscribe_ms: int
    """T3 name subscription: MOTIONrelax at this startup offset, Sleep Smart this
    long after its data subscription."""
    startup: dict[Family, Schedule]
    clock_request_length: int | None
    """Shortest clock request (``F2 F2 50``) the app answers; ``None``: no clock."""
    clock_startup_offsets: tuple[int, ...] = ()
    alarm_families: tuple[Family, ...] = ()
    family_reply: bool
    """The app decodes the bed's ``F2 F2 11`` packet-family reply."""
    massage_mode_reply: bool = False
    name_rule: NameRule
    bare_t1_name: bool
    """T1 takes the bare name; otherwise every name write is G3-wrapped."""
    rename_offsets: tuple[int, ...]


def _twice(*queries: tuple[int, bytes]) -> Schedule:
    """The MOTIONrelax startup burst sends each query twice, 100 ms apart."""
    return tuple((offset + repeat, command) for offset, command in queries for repeat in (0, 100))


def _motionrelax_startup(actuator: bytes) -> dict[Family, Schedule]:
    return {
        family: _twice(
            (1000, actuator),
            (1200, QUERY_SOFTWARE if family == "p2" else QUERY_HARDWARE),
            (1400, QUERY_VIBRATION),
        )
        for family in FAMILIES
    }


def _sleep_smart_startup(family: Family) -> Schedule:
    """Both ready-event handlers merged; ties keep the ViewModel query first."""
    view_model = (
        (300, QUERY_SOFTWARE),
        (600, QUERY_VIBRATION),
        (900, QUERY_HARDWARE),
        (1200, QUERY_ACTUATOR),
        (1500, QUERY_ACTUATOR),
        (1800, QUERY_LIGHT),
        (2100, QUERY_LIGHT),
        (2400, QUERY_STATUS),
        (2700, QUERY_STATUS),
    )
    activity = _twice(
        (1000, QUERY_ACTUATOR),
        (1200, QUERY_SOFTWARE if family == "p2" else QUERY_HARDWARE),
        (1400, QUERY_VIBRATION),
    )
    return tuple(sorted(view_model + activity, key=lambda item: item[0]))


MOTIONRELAX_LAYOUTS: Final[dict[Layout, tuple[Axis, ...]]] = {
    "standard_2": ("back", "legs", "both"),
    "standard_3_neck": ("back", "legs", "head"),
    "standard_3_lumbar": ("back", "legs", "lumbar"),
    "standard_3_hi_low": ("back", "legs", "bed_height"),
    "standard_3_split_upper": ("back", "right_back", "both_backs", "legs"),
    "standard_4": ("head", "back", "lumbar", "legs"),
    "split_series": ("back", "right_back", "legs"),
    "middle": ("back", "legs"),
}
_MOTIONRELAX_NAME: Final = NameRule(
    r"[ -~]{1,255}", "Name must contain 1..255 printable ASCII characters"
)
PHONE: Final = LogicdataProfile(
    key="phone",
    execution=STREAM_HOLD,
    session="motionrelax",
    layouts=MOTIONRELAX_LAYOUTS,
    p2_controls=True,
    presets={"p1": ("flat", "zero_g", "anti_snore"), "p2": ("flat",)},
    held_presets={"p1": (), "p2": ("flat", "memory_1", "memory_2")},
    hold_repeat_ms={"flat": 100, "memory_1": 200, "memory_2": 200},
    hold_final_frame=frozenset({"flat"}),
    movement_repeat_ms=100,
    touch_release=((100, SHORT_RELEASE),),
    memory_slots=2,
    memory_save_offsets=(0, 30, 60),
    light_releases=((80, SHORT_RELEASE), (80, codec.LONG_RELEASE), (100, SHORT_RELEASE)),
    massage_mode_releases=((1000, codec.LONG_RELEASE), (1100, SHORT_RELEASE)),
    massage_families=("p1",),
    subscribe_delay_ms=1000,
    name_subscribe_ms=3000,
    startup=_motionrelax_startup(QUERY_ACTUATOR),
    clock_request_length=6,
    clock_startup_offsets=(3000, 3100),
    alarm_families=("p1",),
    family_reply=True,
    name_rule=_MOTIONRELAX_NAME,
    bare_t1_name=True,
    rename_offsets=(0,),
)
# The tablet has no clock or alarm, queries a different actuator status,
# releases nothing after massage mode and writes each name twice.
TABLET: Final = replace(
    PHONE,
    key="tablet",
    execution=STREAM_HOLD,
    massage_mode_releases=(),
    startup=_motionrelax_startup(codec.query(b"\x01")),
    clock_request_length=None,
    clock_startup_offsets=(),
    alarm_families=(),
    rename_offsets=(0, 500),
)
# Sleep Smart's movement layout is always two motors; the series picks massage zones.
_SLEEP_SMART_AXES: Final[tuple[Axis, ...]] = ("back", "legs", "both")
_SLEEP_SMART_HELD: Final[tuple[HeldPreset, ...]] = ("flat", "zero_g", "anti_snore", "memory_1")
SLEEP_SMART: Final = LogicdataProfile(
    key="sleep_smart",
    execution=STREAM_HOLD,
    session="sleep_smart",
    layouts={"standard_2": _SLEEP_SMART_AXES, "split_series": _SLEEP_SMART_AXES},
    p2_controls=False,
    presets=dict.fromkeys(FAMILIES, ("flat", "zero_g", "anti_snore")),
    hold_only_presets=True,
    held_presets=dict.fromkeys(FAMILIES, _SLEEP_SMART_HELD),
    hold_repeat_ms=dict.fromkeys(_SLEEP_SMART_HELD, 200),
    movement_repeat_ms=100,
    touch_release=((100, SHORT_RELEASE),),
    memory_slots=1,
    # The memory dialog's return sends one save frame without a payload or release.
    memory_save_offsets=(0,),
    memory_save_payload=b"",
    light_releases=((80, SHORT_RELEASE), (80, codec.LONG_RELEASE), (100, SHORT_RELEASE)),
    massage_mode_releases=((1000, codec.LONG_RELEASE), (1100, SHORT_RELEASE)),
    massage_families=FAMILIES,
    # Entering the massage tab sends the massage-parameter query three times.
    massage_query=((100, QUERY_MASSAGE), (250, QUERY_MASSAGE), (450, QUERY_MASSAGE)),
    factory_reset=True,
    subscribe_delay_ms=300,
    name_subscribe_ms=100,
    startup={family: _sleep_smart_startup(family) for family in FAMILIES},
    clock_request_length=3,
    family_reply=False,
    massage_mode_reply=True,
    # The edit field's alphabet and maxLength 20; at most 40 UTF-8 bytes.
    name_rule=NameRule(
        r"[0-9a-zA-ZäöüÄÖÜß]{1,20}",
        "Name must contain 1..20 letters, digits, ä, ö, ü or ß",
        encoding="utf-8",
    ),
    bare_t1_name=False,
    rename_offsets=(0,),
)
APP_PROFILES: Final[dict[AppKey, LogicdataProfile]] = {
    "phone": PHONE,
    "tablet": TABLET,
    "sleep_smart": SLEEP_SMART,
}
ALL_AXES: Final = frozenset(axis for axes in MOTIONRELAX_LAYOUTS.values() for axis in axes)


def validate_setup(profile: LogicdataProfile, family: str, layout: str) -> None:
    if family not in FAMILIES:
        raise ValueError("Select a supported MOTIONrelax app edition and packet family")
    if layout not in profile.layouts:
        if profile.session == "sleep_smart":
            raise ValueError("Sleep Smart uses the two-motor standard or split-series layout")
        raise ValueError("The middle layout requires P2; other layouts require P1")
    if profile.session == "motionrelax" and (family == "p2") != (layout == "middle"):
        raise ValueError("The middle layout requires P2; other layouts require P1")


def _payload(profile: LogicdataProfile, family: Family) -> bytes:
    return BILATERAL if family == "p2" and profile.p2_controls else STANDARD


def motion_command(
    profile: LogicdataProfile, family: Family, layout: Layout, axis: Axis, up: bool
) -> bytes:
    """P2 moves the back and legs motors with the two-byte payload."""
    if axis not in profile.layouts.get(layout, ()):
        raise ValueError(f"Axis {axis} is unavailable in {layout}")
    return codec.motion(
        axis, up, BILATERAL if family == "p2" and axis in ("back", "legs") else STANDARD
    )


def preset_command(profile: LogicdataProfile, family: Family, preset: Preset) -> bytes:
    if preset not in profile.presets[family]:
        names = ", ".join(profile.presets[family])
        raise ValueError(f"{family.upper()} exposes only the {names} preset")
    return codec.preset(preset, _payload(profile, family))


def check_memory_slot(profile: LogicdataProfile, slot: int) -> None:
    if not 1 <= slot <= profile.memory_slots:
        raise ValueError(
            "Sleep Smart has one memory slot"
            if profile is SLEEP_SMART
            else f"memory slot must be between 1 and {profile.memory_slots}"
        )


def memory_command(profile: LogicdataProfile, family: Family, slot: int) -> bytes:
    check_memory_slot(profile, slot)
    return codec.memory(slot, payload=_payload(profile, family))


def memory_save_schedule(profile: LogicdataProfile, family: Family, slot: int) -> Schedule:
    check_memory_slot(profile, slot)
    payload = profile.memory_save_payload
    if payload is None:
        payload = _payload(profile, family)
    command = codec.memory(slot, save=True, payload=payload)
    return tuple((offset, command) for offset in profile.memory_save_offsets)


def held_preset_command(profile: LogicdataProfile, family: Family, preset: HeldPreset) -> bytes:
    if preset not in profile.held_presets[family]:
        raise ValueError(f"Held preset must be one of {', '.join(profile.held_presets[family])}")
    if preset in ("memory_1", "memory_2"):
        return memory_command(profile, family, int(preset[-1]))
    return preset_command(profile, family, preset)


def light_command(profile: LogicdataProfile, family: Family) -> bytes:
    return codec.light_toggle(BILATERAL if family == "p2" and profile.p2_controls else b"")


def massage_command(zone: MassageZone, level: int) -> bytes:
    """Encode the reachable UI range, not declaration-only intensity constants."""
    if not 0 <= level <= 3:
        raise ValueError("massage level must be between 0 and 3")
    return codec.massage(zone, WIRE_MASSAGE_LEVELS[level])


def rename_schedule(profile: LogicdataProfile, transport: TransportChoice, name: str) -> Schedule:
    """Build the name-characteristic writes for the selected app and transport."""
    payload = profile.name_rule.encode(name)
    if TRANSPORTS[transport].name_uuid is None:
        raise ValueError("T2 has no rename characteristic")
    command = payload if transport == "t1" and profile.bare_t1_name else codec.g3_name(payload)
    return tuple((offset, command) for offset in profile.rename_offsets)


@dataclass(frozen=True)
class Notification:
    middle: bool | None = None
    clock_requested: bool = False
    alarm: codec.AlarmState | None = None
    massage_back: int | None = None
    massage_legs: int | None = None
    light_on: bool | None = None
    # A reported massage mode; None with ``massage_mode_reported`` is the app's "--".
    massage_mode: MassageMode | None = None
    massage_mode_reported: bool = False


def parse_notification(profile: LogicdataProfile, data: bytes) -> Notification | None:
    """Decode the replies this app reads, guarding field bounds without checksums.

    The family reply (``F2 F2 11``) and Sleep Smart's massage mode (``F2 F2 0D``)
    are app-specific; the rest is the codec's parser.
    """
    prefix = data[:3]
    if prefix == b"\xf2\xf2\x11" and profile.family_reply and len(data) >= 5:
        return Notification(middle=data[4] == 1)
    if prefix == b"\xf2\xf2\x0d" and profile.massage_mode_reply and len(data) >= 5:
        text = f"{data[4]:02X}"
        if not text.isdigit():
            # The app's decimal parse of this hex text throws; nothing is shown.
            return None
        return Notification(massage_mode=_MASSAGE_MODES.get(int(text)), massage_mode_reported=True)
    length = profile.clock_request_length
    if prefix == b"\xf2\xf2\x50" and length is not None and len(data) >= length:
        return Notification(clock_requested=True)
    shared = codec.parse_notification(data, massage_levels=WIRE_MASSAGE_LEVELS)
    if shared is None:
        return None
    alarm = shared.alarm if profile.alarm_families else None
    if alarm is not None and alarm.wake not in WAKES:
        # The apps define no wake for codes outside their five presets.
        alarm = replace(alarm, wake=None)
    return Notification(
        alarm=alarm,
        light_on=shared.legacy_light,
        massage_back=shared.massage_back,
        massage_legs=shared.massage_legs,
    )
