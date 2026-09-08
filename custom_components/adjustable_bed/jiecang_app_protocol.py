"""Packets proven by the frozen Dreamask 1.0.8 and Dreamotion 1.0.5 reports.

The apps share packet values; their held-movement release schedules differ.
These profiles intentionally do not change the older Jiecang controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AppProfile = Literal["dreamask", "dreamotion"]
Layout = Literal[
    "standard_2",
    "standard_3_neck",
    "standard_3_lumbar",
    "standard_3_hi_low",
    "standard_3_split_upper",
    "standard_4_legacy",
    "standard_4_bilateral",
    "split_series",
    "split_after_bilateral",
]
Axis = Literal[
    "back",
    "legs",
    "head",
    "lumbar",
    "bed_height",
    "right_back",
    "both_backs",
    "right_legs",
    "both_legs",
    "both",
]
Preset = Literal["flat", "zero_g", "anti_snore", "yoga"]
Wake = Literal["flat", "anti_snore", "zero_g", "memory_1", "memory_2", "yoga"]
MassageZone = Literal["back", "legs", "right"]
Schedule = tuple[tuple[int, bytes], ...]

LAYOUT_AXES: dict[Layout, tuple[Axis, ...]] = {
    "standard_2": ("back", "legs", "both"),
    "standard_3_neck": ("back", "legs", "head"),
    "standard_3_lumbar": ("back", "legs", "lumbar"),
    "standard_3_hi_low": ("back", "legs", "bed_height"),
    "standard_3_split_upper": ("back", "legs", "right_back", "both_backs"),
    "standard_4_legacy": ("head", "back", "lumbar", "legs"),
    "standard_4_bilateral": (
        "back",
        "both_backs",
        "right_back",
        "legs",
        "both_legs",
        "right_legs",
    ),
    "split_series": ("back", "legs", "right_back", "both_backs"),
    "split_after_bilateral": ("back", "legs", "right_back", "both_backs"),
}
_AXIS_OPCODES: dict[Axis, int] = {
    "back": 0x01,
    "legs": 0x03,
    "both": 0x05,
    "head": 0x19,
    "bed_height": 0x19,
    "lumbar": 0x1B,
    "right_back": 0x20,
    "both_backs": 0x23,
    "right_legs": 0x2A,
    "both_legs": 0x2C,
}
_PRESET_OPCODES: dict[Preset, int] = {
    "zero_g": 0x07,
    "flat": 0x08,
    "anti_snore": 0x09,
    "yoga": 0x28,
}
_WAKE_CODES: dict[Wake, int] = {
    "flat": 0,
    "anti_snore": 1,
    "zero_g": 2,
    "memory_1": 3,
    "memory_2": 4,
    "yoga": 6,
}
_CODE_TO_WAKE: dict[int, Wake] = {code: wake for wake, code in _WAKE_CODES.items()}
WIRE_MASSAGE_LEVELS = (0, 2, 3, 4)
LIGHT_TIMEOUTS = (0, 60, 120, 180, 240, 300, 600, 900, 1200, 1500, 1800)
APP_PROFILES: tuple[AppProfile, ...] = ("dreamask", "dreamotion")
LAYOUTS: tuple[Layout, ...] = tuple(LAYOUT_AXES)


def _range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def build_frame(opcode: int, payload: bytes = b"") -> bytes:
    """Encode the variable-length F1 request, including the additive checksum."""
    _range("opcode", opcode, 0, 255)
    _range("payload length", len(payload), 0, 255)
    body = bytes((opcode, len(payload))) + payload
    return b"\xf1\xf1" + body + bytes((sum(body) & 0xFF, 0x7E))


SHORT_RELEASE = build_frame(0x4E)
LONG_RELEASE = build_frame(0x4E, b"\x00\x00")
LIGHT_TOGGLE = build_frame(0x0F, b"\x00\x00")
AUTOMATIC_LIGHT_TOGGLE = build_frame(0x29, b"\x00\x00")
QUERY_SOFTWARE = build_frame(0, b"\x40\x00")
QUERY_LIGHT = build_frame(0, b"\x01\x00")
QUERY_ACTUATOR = build_frame(0, b"\x50")
QUERY_HARDWARE = build_frame(0, b"\x40")
QUERY_VIBRATION = build_frame(0, b"\x08")
QUERY_ALARM = build_frame(0, b"\x10")
BOOTSTRAP_SCHEDULE: Schedule = tuple(
    (offset + repeat, command)
    for offset, command in (
        (0, QUERY_SOFTWARE),
        (800, QUERY_LIGHT),
        (1000, QUERY_ACTUATOR),
        (1200, QUERY_HARDWARE),
        (1400, QUERY_VIBRATION),
        (1600, QUERY_ALARM),
        (1800, QUERY_SOFTWARE),
    )
    for repeat in (0, 100)
)


def is_bilateral(layout: Layout) -> bool:
    """Global controls retain bilateral routing in the explicit mixed layout."""
    return layout in ("standard_4_bilateral", "split_after_bilateral")


def layout_axes(layout: Layout) -> tuple[Axis, ...]:
    return LAYOUT_AXES[layout]


def motion_command(layout: Layout, axis: Axis, up: bool) -> bytes:
    if axis not in layout_axes(layout):
        raise ValueError(f"{axis} is unavailable for {layout}")
    payload = b"\x00\x00" if layout == "standard_4_bilateral" else b"\x01"
    return build_frame(_AXIS_OPCODES[axis] + (0 if up else 1), payload)


def movement_releases(profile: AppProfile) -> Schedule:
    if profile == "dreamask":
        return ((50, LONG_RELEASE), (150, LONG_RELEASE))
    if profile == "dreamotion":
        return ((100, SHORT_RELEASE), (800, LONG_RELEASE))
    raise ValueError(f"Unknown app profile: {profile}")


def preset_command(layout: Layout, preset: Preset) -> bytes:
    payload = b"\x00\x00" if is_bilateral(layout) or preset == "yoga" else b"\x01"
    return build_frame(_PRESET_OPCODES[preset], payload)


def memory_command(slot: int, save: bool = False) -> bytes:
    _range("memory slot", slot, 1, 2)
    return build_frame(0x0A + 2 * (slot - 1) + (0 if save else 1), b"\x00\x00")


def massage_zones(layout: Layout) -> tuple[MassageZone, ...]:
    if is_bilateral(layout):
        return ("back", "right")
    if layout in ("standard_3_split_upper", "split_series"):
        return ("back", "right", "legs")
    return ("back", "legs")


def massage_command(layout: Layout, zone: MassageZone, level: int) -> bytes:
    """Use UI intensities 0..3, which encode as 00/02/03/04."""
    if zone not in massage_zones(layout):
        raise ValueError(f"{zone} massage is unavailable for {layout}")
    _range("massage level", level, 0, 3)
    opcode = {"back": 0x12, "legs": 0x14, "right": 0x22}[zone]
    return build_frame(
        opcode, bytes((0 if is_bilateral(layout) else 8, WIRE_MASSAGE_LEVELS[level]))
    )


def massage_close_command(layout: Layout) -> bytes:
    return build_frame(0x11, b"\x00\x00" if is_bilateral(layout) else b"\x08")


def massage_mode_command(layout: Layout) -> bytes:
    return build_frame(0x16, b"\x00\x00" if is_bilateral(layout) else b"\x0a")


def rgb_command(red: int, green: int, blue: int, brightness: int, seconds: int, on: bool) -> bytes:
    for name, value in (("red", red), ("green", green), ("blue", blue)):
        _range(name, value, 0, 255)
    _range("brightness", brightness, 0, 100)
    if seconds not in LIGHT_TIMEOUTS:
        raise ValueError("Unsupported light timeout")
    return build_frame(
        0x52, bytes((blue, green, red, brightness, seconds >> 8, seconds & 255, int(on)))
    )


def alarm_command(
    enabled: bool,
    weekdays: tuple[bool, ...],
    hour: int,
    minute: int,
    wake: Wake,
    back_level: int,
    leg_level: int,
) -> bytes:
    if len(weekdays) != 7:
        raise ValueError("Weekdays must contain Monday through Sunday")
    _range("hour", hour, 0, 23)
    _range("minute", minute, 0, 59)
    _range("back level", back_level, 0, 3)
    _range("leg level", leg_level, 0, 3)
    mask = sum(1 << (index + 1) for index, selected in enumerate(weekdays) if selected)
    return build_frame(
        0x51,
        bytes(
            (
                int(enabled),
                int(any(weekdays)),
                mask,
                hour,
                minute,
                _WAKE_CODES[wake],
                back_level,
                leg_level,
            )
        ),
    )


def clock_command(value: datetime) -> bytes:
    _range("year", value.year, 1970, 2225)
    return build_frame(
        0x50,
        bytes(
            (
                value.year - 1970,
                value.month,
                value.day,
                (value.weekday() + 1) % 7,
                value.hour,
                value.minute,
                value.second,
            )
        ),
    )


def rename_command(name: str, g1: bool, g3: bool) -> bytes:
    if not name.isascii() or not name.isalnum() or not 1 <= len(name) <= 20:
        raise ValueError("Name must contain 1..20 ASCII letters or digits")
    payload = name.encode("ascii")
    if g1:
        return payload
    if g3:
        return bytes((1, 0xFC, 7, len(payload))) + payload
    raise ValueError("The selected transport has no name characteristic")


def wake_schedule(
    layout: Layout,
    wake: Wake,
    back_level: int = 0,
    leg_level: int = 0,
    right_level: int | None = None,
) -> Schedule:
    """Return the artifact's absolute alarm execution offsets, preserving duplicates.

    Alarm massage always uses payload-08 commands, including bilateral layouts.
    Yoga may be stored in the alarm but the apps have no Yoga wake executor.
    """
    if wake == "yoga":
        raise ValueError("The apps do not execute Yoga wake alarms")
    for level in (back_level, leg_level):
        _range("alarm massage level", level, 0, 3)
    split = layout in ("split_series", "split_after_bilateral")
    expected_right = back_level if split else 0
    if right_level is not None and right_level != expected_right:
        raise ValueError("Split alarm right massage must match the back level")
    result: list[tuple[int, bytes]] = []
    zones = [(0, 0x12, back_level), (500 if split else 300, 0x14, leg_level)]
    if split:
        zones.append((180, 0x22, back_level))
    for offset, opcode, level in zones:
        if level:
            command = build_frame(opcode, bytes((8, WIRE_MASSAGE_LEVELS[level])))
            result.extend((offset + delay, command) for delay in (0, 30, 60))
            result.extend((offset + delay, SHORT_RELEASE) for delay in (90, 120, 150))
    if wake == "memory_1":
        command = memory_command(1)
    elif wake == "memory_2":
        command = memory_command(2)
    else:
        command = preset_command(layout, wake)
    result.extend((offset, command) for offset in (800, 830, 860, 890, 920))
    if wake == "memory_2" and not split:
        result.append((1600, LONG_RELEASE))
    result.extend((offset, LONG_RELEASE) for offset in (1690, 1720))
    return tuple(sorted(result, key=lambda item: item[0]))


@dataclass(frozen=True)
class Capabilities:
    yoga: bool
    light_config: bool


@dataclass(frozen=True)
class RGBState:
    red: int
    green: int
    blue: int
    brightness: int
    seconds: int
    on: bool


@dataclass(frozen=True)
class AlarmState:
    enabled: bool
    weekdays: tuple[bool, ...]
    hour: int
    minute: int
    wake: Wake | None
    back_level: int
    leg_level: int


@dataclass(frozen=True)
class Notification:
    clock_requested: bool = False
    capabilities: Capabilities | None = None
    reapply_layout: bool = False
    alarm_visible: bool = False
    alarm: AlarmState | None = None
    rgb: RGBState | None = None
    automatic_light: bool | None = None
    massage_back: int | None = None
    massage_legs: int | None = None
    legacy_light: bool | None = None


def parse_notification(data: bytes) -> Notification | None:
    """Parse one callback without reading incomplete fields or trusting invalid ranges.

    No response checksum requirement is invented: both apps accept bad trailers.
    Generic 05/06 replies deliberately retain their header-independent dispatch.
    Unlike Android, malformed fields never throw or overwrite state with nonsense.
    """
    prefix = data[:3]
    if prefix == b"\xf2\xf2\x50" and len(data) >= 6:
        return Notification(clock_requested=True)
    if prefix == b"\xf2\xf2\x0e" and len(data) >= 7:
        value = data[4]
        # This unusual conversion is proven in both frozen parser vectors.
        bits = (f"{value:b}" + "00000000")[:8][::-1]
        return Notification(capabilities=Capabilities(bool(value & 2), bits[5] == "1"))
    if prefix == b"\xf2\xf2\x0f" and len(data) >= 7:
        return Notification(reapply_layout=True)
    if prefix == b"\xf2\xf2\x51" and len(data) >= 7:
        if len(data) < 14 or data[7] > 23 or data[8] > 59 or max(data[10:12]) > 3:
            return Notification(alarm_visible=True)
        wake = _CODE_TO_WAKE.get(data[9])
        return Notification(
            alarm_visible=True,
            alarm=AlarmState(
                data[4] == 1,
                tuple(bool(data[6] & (1 << bit)) for bit in range(1, 8)),
                data[7],
                data[8],
                wake,
                data[10],
                data[11],
            ),
        )
    if prefix == b"\xf2\xf2\x53" and len(data) >= 7:
        return Notification(automatic_light=data[4] == 0)
    if data[:4] == b"\xf2\xf2\x52\x07" and len(data) >= 13:
        if data[7] > 100 or data[10] not in (0, 1):
            return None
        return Notification(
            rgb=RGBState(
                data[6], data[5], data[4], data[7], int.from_bytes(data[8:10], "big"), data[10] == 1
            )
        )
    if len(data) >= 9 and data[2] in (5, 6):
        return Notification(
            legacy_light=bool(data[8] & 0x40),
            massage_back=data[4] if data[2] == 6 and data[4] in WIRE_MASSAGE_LEVELS else None,
            massage_legs=data[6] if data[2] == 6 and data[6] in WIRE_MASSAGE_LEVELS else None,
        )
    return None
