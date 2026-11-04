"""Jiecang F1 wire codec.

Every request is one frame: ``F1 F1 opcode length payload checksum 7E``. The
checksum is the low byte of the sum of opcode, length and payload. Responses
use the same layout behind an ``F2 F2`` header. Three GATT transports carry it.

Controllers address one of two payload shapes: a single controller takes
``01`` (``STANDARD``) and a bilateral one takes ``00 00`` (``BILATERAL``).
Which shape, timing and command set an app uses belongs to its profile
(``profiles/jiecang.py``), never to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from ..const import (
    COMFORT_MOTION_BTNAME_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_BTNAME_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
    COMFORT_MOTION_PEILIN_CHAR_UUID,
    COMFORT_MOTION_PEILIN_SERVICE_UUID,
    COMFORT_MOTION_READ_CHAR_UUID,
    COMFORT_MOTION_SERVICE_UUID,
    COMFORT_MOTION_WRITE_CHAR_UUID,
)

TransportKey = Literal["g1", "g2", "g3"]
Axis = Literal[
    "back",
    "legs",
    "both",
    "head",
    "bed_height",
    "lumbar",
    "right_back",
    "both_backs",
    "right_legs",
    "both_legs",
]
Preset = Literal["flat", "zero_g", "anti_snore", "yoga"]
Wake = Literal["flat", "anti_snore", "zero_g", "memory_1", "memory_2", "yoga"]
MassageZone = Literal["back", "legs", "right"]


@dataclass(frozen=True)
class Transport:
    """GATT roles of one transport generation. G2 has one shared characteristic."""

    service_uuid: str
    write_uuid: str
    notify_uuid: str
    name_uuid: str | None


TRANSPORTS: Final[dict[TransportKey, Transport]] = {
    "g1": Transport(
        COMFORT_MOTION_SERVICE_UUID,
        COMFORT_MOTION_WRITE_CHAR_UUID,
        COMFORT_MOTION_READ_CHAR_UUID,
        COMFORT_MOTION_BTNAME_CHAR_UUID,
    ),
    "g2": Transport(
        COMFORT_MOTION_PEILIN_SERVICE_UUID,
        COMFORT_MOTION_PEILIN_CHAR_UUID,
        COMFORT_MOTION_PEILIN_CHAR_UUID,
        None,
    ),
    "g3": Transport(
        COMFORT_MOTION_LIERDA3_SERVICE_UUID,
        COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
        COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
        COMFORT_MOTION_LIERDA3_BTNAME_CHAR_UUID,
    ),
}

STANDARD: Final = b"\x01"
BILATERAL: Final = b"\x00\x00"


def _range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def frame(opcode: int, payload: bytes = b"") -> bytes:
    """Encode one request, including the additive checksum."""
    _range("opcode", opcode, 0, 255)
    _range("payload length", len(payload), 0, 255)
    body = bytes((opcode, len(payload))) + payload
    return b"\xf1\xf1" + body + bytes((sum(body) & 0xFF, 0x7E))


SHORT_RELEASE: Final = frame(0x4E)
LONG_RELEASE: Final = frame(0x4E, BILATERAL)
AUTOMATIC_LIGHT_TOGGLE: Final = frame(0x29, BILATERAL)

# Up opcodes; each down opcode is the next value. Head and height share 0x19.
AXIS_OPCODES: Final[dict[Axis, int]] = {
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
PRESET_OPCODES: Final[dict[Preset, int]] = {
    "zero_g": 0x07,
    "flat": 0x08,
    "anti_snore": 0x09,
    "yoga": 0x28,
}
# Memory slot: (save opcode, recall opcode).
MEMORY_OPCODES: Final[dict[int, tuple[int, int]]] = {
    1: (0x0A, 0x0B),
    2: (0x0C, 0x0D),
    3: (0x17, 0x18),
}
MASSAGE_OPCODES: Final[dict[MassageZone, int]] = {"back": 0x12, "legs": 0x14, "right": 0x22}
WAKE_CODES: Final[dict[Wake, int]] = {
    "flat": 0,
    "anti_snore": 1,
    "zero_g": 2,
    "memory_1": 3,
    "memory_2": 4,
    "yoga": 6,
}
_CODE_TO_WAKE: Final[dict[int, Wake]] = {code: wake for wake, code in WAKE_CODES.items()}


def motion(axis: Axis, up: bool, payload: bytes = STANDARD) -> bytes:
    return frame(AXIS_OPCODES[axis] + (0 if up else 1), payload)


def preset(name: Preset, payload: bytes = STANDARD) -> bytes:
    return frame(PRESET_OPCODES[name], payload)


def memory(slot: int, *, save: bool = False, payload: bytes = STANDARD) -> bytes:
    if slot not in MEMORY_OPCODES:
        raise ValueError(f"Unknown memory slot {slot}")
    return frame(MEMORY_OPCODES[slot][0 if save else 1], payload)


def massage(zone: MassageZone, wire_level: int, *, bilateral: bool = False) -> bytes:
    """Set one zone's intensity; ``wire_level`` is the raw byte, not a UI index."""
    _range("massage wire level", wire_level, 0, 255)
    return frame(MASSAGE_OPCODES[zone], bytes((0 if bilateral else 8, wire_level)))


def massage_start() -> bytes:
    return frame(0x10, b"\x08")


def massage_stop(*, bilateral: bool = False) -> bytes:
    return frame(0x11, BILATERAL if bilateral else b"\x08")


def massage_mode(*, bilateral: bool = False) -> bytes:
    return frame(0x16, BILATERAL if bilateral else b"\x0a")


def light_toggle(payload: bytes = b"") -> bytes:
    return frame(0x0F, payload)


def query(payload: bytes = b"") -> bytes:
    """Status and configuration queries share opcode 00; the payload selects one."""
    return frame(0, payload)


def rgb(red: int, green: int, blue: int, brightness: int, seconds: int, on: bool) -> bytes:
    for name, value in (("red", red), ("green", green), ("blue", blue)):
        _range(name, value, 0, 255)
    _range("brightness", brightness, 0, 100)
    _range("light timeout", seconds, 0, 0xFFFF)
    return frame(0x52, bytes((blue, green, red, brightness, seconds >> 8, seconds & 255, int(on))))


def alarm(
    enabled: bool,
    weekdays: tuple[bool, ...],
    hour: int,
    minute: int,
    wake: Wake,
    back_level: int,
    leg_level: int,
) -> bytes:
    """Store the bed's alarm; weekdays run Monday through Sunday."""
    if len(weekdays) != 7:
        raise ValueError("Weekdays must contain Monday through Sunday")
    _range("hour", hour, 0, 23)
    _range("minute", minute, 0, 59)
    _range("back level", back_level, 0, 3)
    _range("leg level", leg_level, 0, 3)
    mask = sum(1 << (index + 1) for index, selected in enumerate(weekdays) if selected)
    return frame(
        0x51,
        bytes(
            (
                int(enabled),
                int(any(weekdays)),
                mask,
                hour,
                minute,
                WAKE_CODES[wake],
                back_level,
                leg_level,
            )
        ),
    )


def clock(value: datetime) -> bytes:
    _range("year", value.year, 1970, 2225)
    return frame(
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


def g3_name(payload: bytes) -> bytes:
    """Wrap a device name for the G3 name characteristic. G1 takes the bare name."""
    _range("name length", len(payload), 0, 255)
    return bytes((1, 0xFC, 7, len(payload))) + payload


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
    # Raw automatic-light byte; apps disagree on which value means on.
    automatic_light: int | None = None
    massage_back: int | None = None
    massage_legs: int | None = None
    legacy_light: bool | None = None


def parse_notification(data: bytes, *, massage_levels: tuple[int, ...]) -> Notification | None:
    """Parse one callback without reading incomplete fields or trusting invalid ranges.

    No response checksum is required: the apps accept bad trailers. Status
    replies 05/06 dispatch on byte 2 under any header. Massage levels outside
    ``massage_levels`` are dropped rather than reported.
    """
    prefix = data[:3]
    if prefix == b"\xf2\xf2\x50" and len(data) >= 6:
        return Notification(clock_requested=True)
    if prefix == b"\xf2\xf2\x0e" and len(data) >= 7:
        value = data[4]
        # This unusual conversion is proven in the frozen parser vectors.
        bits = (f"{value:b}" + "00000000")[:8][::-1]
        return Notification(capabilities=Capabilities(bool(value & 2), bits[5] == "1"))
    if prefix == b"\xf2\xf2\x0f" and len(data) >= 7:
        return Notification(reapply_layout=True)
    if prefix == b"\xf2\xf2\x51" and len(data) >= 7:
        if len(data) < 14 or data[7] > 23 or data[8] > 59 or max(data[10:12]) > 3:
            return Notification(alarm_visible=True)
        return Notification(
            alarm_visible=True,
            alarm=AlarmState(
                data[4] == 1,
                tuple(bool(data[6] & (1 << bit)) for bit in range(1, 8)),
                data[7],
                data[8],
                _CODE_TO_WAKE.get(data[9]),
                data[10],
                data[11],
            ),
        )
    if prefix == b"\xf2\xf2\x53" and len(data) >= 7:
        return Notification(automatic_light=data[4])
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
            massage_back=data[4] if data[2] == 6 and data[4] in massage_levels else None,
            massage_legs=data[6] if data[2] == 6 and data[6] in massage_levels else None,
        )
    return None
