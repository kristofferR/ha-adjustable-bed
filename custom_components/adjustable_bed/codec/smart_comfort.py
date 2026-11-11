"""Smart Comfort seat frames, from the two accepted cluster-024 app reports.

Unlike Keeson key words, these frames have separate seat, accessory and RGB
fields, plus A0/B1 queries and three notification layouts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SERVICE_UUID: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
NAME_SERVICE_UUID: Final = "0000ff90-0000-1000-8000-00805f9b34fb"
NAME_UUID: Final = "0000ff91-0000-1000-8000-00805f9b34fb"
MOTORS: Final = {
    "head_up": 1,
    "head_down": 2,
    "reclining_up": 4,
    "reclining_down": 8,
    "lumbar_up": 0x40,
    "lumbar_down": 0x80,
    "home": 0x3001,
    "stop": 0,
    "memory_prepare": 0x4000,
    "recall_1": 0x2001,
    "recall_2": 0x2002,
    "save_1": 0x1001,
    "save_2": 0x1002,
}
# code -> (layout, reported motors, stored addresses, selectable addresses).
MODELS: Final = {
    0x02: ("Single", 2, (0,), (0,)),
    0x03: ("Single", 3, (0,), (0,)),
    0x04: ("LoveSeat", 2, (2, 0), (2, 0)),
    0x06: ("LoveSeat", 3, (2, 0), (2, 0)),
    0x84: ("ThreeSeatNoMid", 2, (2, 1, 0), (2, 0)),
    0x86: ("ThreeSeatNoMid", 3, (2, 1, 0), (2, 0)),
    0x89: ("TurnSeat", 3, (2, 1, 0), (2, 1, 0)),
}
ACCESSORIES: Final = {
    "base_on": (0, 1, 0x10),
    "base_off": (1, 1, 0x10),
    "cup_on": (0, 0, 8),
    "cup_off": (1, 0, 8),
    "read_on": (1, 1, 4),
    "read_off": (2, 1, 4),
}


def checked(body: bytes) -> bytes:
    """Append the complement sum over all preceding bytes."""
    return body + bytes((~sum(body) & 255,))


def seat_mask(address: int) -> int:
    """Encode one exact logical seat, never a broadcast or UI side."""
    if isinstance(address, bool) or address not in (0, 1, 2):
        raise ValueError("Seat address must be 0, 1 or 2")
    return 1 << address


def command(
    action: str, address: int = 0, *, value: int = 30, rgb: tuple[int, int, int] = (18, 52, 86)
) -> bytes:
    """Encode each framed action; brightness uses the app's 4..100 domain."""
    mask = seat_mask(address)
    if action in MOTORS:
        return checked(b"\xe5\xfe\x16" + MOTORS[action].to_bytes(2, "little") + bytes((mask, 1)))
    if action in ACCESSORIES:
        first, second, group = ACCESSORIES[action]
        return checked(bytes((0xE5, 0xFE, 0x16, first, second, mask, group)))
    if action in ("base_brightness", "read_brightness"):
        if isinstance(value, bool) or not 4 <= value <= 100:
            raise ValueError("Brightness must be 4..100")
        return checked(
            bytes((0xE5, 0xFE, 0x16, value, 0, mask, 0x10 if action == "base_brightness" else 4))
        )
    if action == "color":
        red, green, blue = rgb
        return checked(bytes((0xE5, 0xFE, 0x16, blue, green, red, mask | 0x10)))
    if action == "query_system":
        return checked(bytes((0xA0, 0xB1, 0x56, 0, 0, 0, 0)))
    if action == "query_device":
        return checked(bytes((0xA0, 0xB1, 0x55, 0, 0, 0, mask)))
    raise ValueError(f"Unknown Smart Comfort action: {action}")


def rename(name: str) -> bytes:
    """Portable subset of Java's unspecified default charset: ASCII, 1..16 bytes."""
    try:
        data = name.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError("Smart Comfort names must use ASCII") from err
    if not 1 <= len(data) <= 16:
        raise ValueError("Smart Comfort names must be 1..16 ASCII bytes")
    return data


def matches_scan_record(raw: bytes) -> bool:
    """Preserve the app predicate; HA's parsed advertisements cannot reconstruct it."""
    return len(raw) >= 9 and (raw[7] == 0xB0 or raw[8] == 0xFF) and raw[6] in (0xB0, 0xFF)


@dataclass(frozen=True)
class SystemState:
    code: int
    flags: tuple[int, int, int]


@dataclass(frozen=True)
class DeviceState:
    read_brightness: int
    read_on: bool
    cup_on: bool
    rgb: tuple[int, int, int]
    base_brightness: int
    base_on: bool


@dataclass(frozen=True)
class RippleState:
    # Frame/display order, not the app callback's reordered arguments.
    counters: tuple[int, int, int]


def parse_notification(data: bytes) -> SystemState | DeviceState | RippleState | None:
    """Parse one checksum-valid callback, rejecting overlapping checksum/data.

    The apps accept 13-byte device and 15-byte ripple frames with overlapping
    fields. HA deliberately requires disjoint fields, not a claimed HW minimum.
    """
    if len(data) < 4 or sum(data) & 255 != 255:
        return None
    if data[:3] == b"\xa0\xb1\x56":
        return SystemState(data[3], (data[4], data[5], data[6])) if len(data) >= 8 else None
    if data[:2] == b"\xa0\xb1" and len(data) >= 14:

        def signed(value: int) -> int:
            return value if value < 128 else value - 256

        return DeviceState(
            signed(data[4]),
            data[5] == 0,
            data[7] == 0,
            (data[8], data[9], data[10]),
            signed(data[11]),
            data[12] == 0,
        )
    if data[:3] == b"\xb0\xb1\xb2" and len(data) >= 16:
        return RippleState(
            (
                int.from_bytes(data[3:7], "little"),
                int.from_bytes(data[7:11], "little"),
                int.from_bytes(data[11:15], "little"),
            )
        )
    return None
