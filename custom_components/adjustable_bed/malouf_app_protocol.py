"""Frozen Malouf Base 2.4.3 / Lucid Base 1.3.3 app protocol tables.

Models describe the shipped controls, independently of the five GATT transports.
Only reachable command endpoints are included. Android write type 2 is an
acknowledged write, despite the original reports' incorrect descriptive label.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final


@dataclass(frozen=True, slots=True)
class MaloufAppModel:
    """Explicit app model capabilities, including persisted-only profiles."""

    name: str
    memory_slots: int
    manual: tuple[str, ...]
    presets: tuple[str, ...]
    functions: tuple[str, ...]


_BASIC = ("back", "legs")
_PRESETS = ("zero_g", "anti_snore")
_FULL_PRESETS = ("zero_g", "tv", "anti_snore", "lounge")
_MASSAGE = ("massage", "massage_head", "massage_foot", "massage_wave")
_RICHMAT = (*_MASSAGE, "massage_off", "massage_timer_set", "light")
_OKIN = (*_MASSAGE, "massage_timer_step", "alarm", "light")

MALOUF_APP_MODELS: Final[dict[str, MaloufAppModel]] = {
    "Altitude": MaloufAppModel(
        "Altitude",
        0,
        (*_BASIC, "dual", "tilt_head", "full_tilt"),
        _PRESETS,
        (*_MASSAGE, "massage_off", "light"),
    ),
    "E450": MaloufAppModel("E450", 0, _BASIC, _PRESETS, ()),
    "E455": MaloufAppModel("E455", 0, _BASIC, _PRESETS, ()),
    "Forte": MaloufAppModel(
        "Forte", 0, _BASIC, ("zero_g",), ("massage", "massage_head", "massage_wave", "massage_off")
    ),
    "GoodLifeBase": MaloufAppModel("Good Life Base", 0, (*_BASIC, "dual"), _FULL_PRESETS, ()),
    "GoodLifePremierBase": MaloufAppModel(
        "Good Life Premier Base", 0, (*_BASIC, "dual", "tilt", "lumbar"), _FULL_PRESETS, _RICHMAT
    ),
    "GoodLifeProBase": MaloufAppModel(
        "Good Life Pro Base", 0, (*_BASIC, "dual"), _FULL_PRESETS, _RICHMAT
    ),
    "L300": MaloufAppModel("L300", 0, _BASIC, _PRESETS, ()),
    "L600": MaloufAppModel("L600", 1, _BASIC, ("zero_g", "anti_snore", "lounge", "tv"), _OKIN),
    "M455": MaloufAppModel(
        "M455",
        0,
        _BASIC,
        _PRESETS,
        ("massage", "massage_head", "massage_wave", "massage_off", "massage_timer_set"),
    ),
    "M550": MaloufAppModel("M550", 1, _BASIC, ("zero_g", "anti_snore", "lounge", "tv"), _OKIN),
    "M555": MaloufAppModel("M555", 1, (*_BASIC, "dual"), _FULL_PRESETS, _RICHMAT),
    # Malouf's uppercase READ has no writable endpoint. Lucid lowercases it
    # to an Okin-only endpoint, exposed separately as an app-labelled action.
    "Premium": MaloufAppModel(
        "Premium", 2, (*_BASIC, "dual"), ("zero_g", "anti_snore", "tv"), _OKIN
    ),
    "S655": MaloufAppModel("S655", 2, (*_BASIC, "dual", "tilt"), _FULL_PRESETS, _RICHMAT),
    "S750": MaloufAppModel("S750", 2, (*_BASIC, "tilt", "lumbar"), _FULL_PRESETS, _OKIN),
    "S755": MaloufAppModel("S755", 2, (*_BASIC, "dual", "tilt", "lumbar"), _FULL_PRESETS, _RICHMAT),
}

APP_MODEL_OPTIONS: Final[dict[str, tuple[str, ...]]] = {
    "malouf": (
        "E450",
        "E455",
        "M455",
        "M555",
        "S655",
        "S755",
        "Forte",
        "Altitude",
        "GoodLifeBase",
        "GoodLifePremierBase",
        "GoodLifeProBase",
        "L600",
        "M550",
        "S750",
    ),
    "lucid": ("L300", "L600", "Premium"),
}


@dataclass(frozen=True, slots=True)
class MaloufAppTransport:
    """A complete, coherent GATT role set, never a service-order hybrid."""

    family: str
    command_service: str
    command_characteristic: str
    notify_service: str | None = None
    notify_characteristic: str | None = None


_UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
_UART_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
_UART_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
TRANSPORTS: Final[dict[str, MaloufAppTransport]] = {
    "richmat_single": MaloufAppTransport("richmat", _UART_SERVICE, _UART_WRITE),
    "richmat_framed": MaloufAppTransport(
        "richmat", "0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600"
    ),
    "okin_legacy": MaloufAppTransport(
        "okin",
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    "okin_custom": MaloufAppTransport(
        "okin",
        "62741523-52f9-8864-b1ab-3b3a8d65950b",
        "62741525-52f9-8864-b1ab-3b3a8d65950b",
        "62741523-52f9-8864-b1ab-3b3a8d65950b",
        "62741625-52f9-8864-b1ab-3b3a8d65950b",
    ),
    "okin_new": MaloufAppTransport("okin", _UART_SERVICE, _UART_WRITE, _UART_SERVICE, _UART_NOTIFY),
}

RICHMAT_COMMANDS: Final[dict[str, int]] = {
    "head_up": 0x24,
    "head_down": 0x25,
    "foot_up": 0x26,
    "foot_down": 0x27,
    "dual_up": 0x29,
    "dual_down": 0x2A,
    "save_1": 0x2B,
    "save_2": 0x2C,
    "memory_1": 0x2E,
    "memory_2": 0x2F,
    "flat": 0x31,
    "light": 0x3C,
    "tilt_up": 0x3F,
    "tilt_down": 0x40,
    "full_tilt_up": 0x3F,
    "full_tilt_down": 0x40,
    "tilt_head_up": 0x41,
    "tilt_head_down": 0x42,
    "lumbar_up": 0x41,
    "lumbar_down": 0x42,
    "zero_g": 0x45,
    "anti_snore": 0x46,
    "massage_off": 0x47,
    "massage_wave": 0x48,
    "massage_head": 0x4C,
    "massage_foot": 0x4E,
    "tv": 0x58,
    "lounge": 0x59,
    "massage_10": 0x5F,
    "massage_30": 0x61,
    "massage_20": 0x63,
    "stop": 0x6E,
}
OKIN_COMMANDS: Final[dict[str, int]] = {
    "stop": 0,
    "head_up": 1,
    "head_down": 2,
    "foot_up": 4,
    "foot_down": 8,
    "dual_up": 5,
    "dual_down": 10,
    "tilt_up": 0x10,
    "tilt_down": 0x20,
    "lumbar_up": 0x40,
    "lumbar_down": 0x80,
    "massage_timer_step": 0x200,
    "massage_foot": 0x400,
    "massage_head": 0x800,
    "zero_g": 0x1000,
    "lounge": 0x2000,
    "tv": 0x4000,
    "anti_snore": 0x8000,
    "memory_1": 0x10000,
    "light": 0x20000,
    "memory_2": 0x40000,
    "flat": 0x08000000,
    "massage_wave": 0x10000000,
}
SELECTOR_ACTIONS: Final = frozenset(
    {"head_up", "head_down", "massage_head", "flat", "zero_g", "anti_snore"}
)
ALARM_TYPES: Final[dict[str, int]] = {
    "zero_g": 13,
    "lounge": 14,
    "tv": 15,
    "anti_snore": 16,
    "memory_1": 17,
    "memory_2": 18,
}


def command_frame(transport: str, command: int, *, selector: int = 0) -> bytes:
    """Encode a resolved command; selector is meaningful only for P1 framing."""
    if transport == "richmat_single":
        return bytes((command,))
    if transport == "richmat_framed":
        return bytes((0x6E, 1, selector, command, (0x6F + selector + command) & 0xFF))
    if transport == "okin_legacy":
        data = b"\xe6\xfe\x16" + command.to_bytes(4, "little") + b"\x00"
        return data + bytes((~sum(data) & 0xFF,))
    if transport == "okin_custom":
        return b"\x04\x02" + command.to_bytes(4, "big") + bytes(4)
    if transport == "okin_new":
        return b"\x05\x02" + command.to_bytes(4, "big") + bytes(2)
    raise ValueError(f"Unknown Malouf/Lucid app transport: {transport}")


def clock_frame(transport: str, now: datetime) -> bytes:
    """Encode Java Calendar's local time and Sunday-zero weekday conventions."""
    if transport == "okin_new":
        return bytes(
            (
                7,
                4,
                now.year & 0xFF,
                now.month,
                now.day,
                (now.weekday() + 1) % 7,
                now.hour,
                now.minute,
                now.second,
            )
        )
    if transport not in {"okin_legacy", "okin_custom"}:
        raise ValueError("This app transport has no clock")
    data = bytes(
        (
            0xE7,
            0x80,
            1,
            (now.year - 1900) & 0xFF,
            now.month - 1,
            now.day,
            now.hour,
            now.minute,
            now.second,
        )
    )
    return data + bytes((~sum(data) & 0xFF,))


def alarm_frame(transport: str, hour: int, minute: int, alarm_type: int, repeats: int) -> bytes:
    """Encode app alarm data, including the exact zero-type clear packet."""
    if transport == "okin_new":
        days = (repeats & 0x7E) | int(bool(repeats & 0x80))
        return bytes((7, 5, days, (alarm_type - 12) & 0xFF, hour, minute, 0, int(days > 0), 0))
    if transport not in {"okin_legacy", "okin_custom"}:
        raise ValueError("This app transport has no alarm")
    data = bytes((0xED, 0x80, 3, hour, minute, repeats, alarm_type)) + bytes(8)
    return data + bytes((~sum(data) & 0xFF,))


@dataclass(frozen=True, slots=True)
class MaloufAppNotification:
    """The two actual app notification values, without inferred motor state."""

    massage_remaining_minutes: int
    light_status: int


def parse_notification(transport: str, data: bytes) -> MaloufAppNotification | None:
    """Preserve the artifact's guards, optional offsets, and signed-byte values."""
    if transport == "okin_legacy":
        offsets = {10: (7, 8), 16: (13, 14), 20: (18, 19)}
        if len(data) not in offsets:
            return None
        light_offset, massage_offset = offsets[len(data)]
        timer = data[massage_offset] & 0xF
        light = int.from_bytes(data[light_offset : light_offset + 1], signed=True) >> 6
        return MaloufAppNotification(timer * 10 if 1 <= timer <= 3 else 0, light)
    if transport == "okin_custom":
        timer = int.from_bytes(data[10:11], signed=True) if len(data) > 10 else 0
        return MaloufAppNotification(timer * 10, 0)
    if transport == "okin_new":
        if len(data) < 2 or data[1] != 11:
            return None
        timer = int.from_bytes(data[4:5], signed=True) if len(data) > 4 else 0
        minutes = 30 if timer > 4 else 20 if timer > 2 else 10 if timer > 0 else 0
        light = any(len(data) > offset and data[offset] == 1 for offset in (9, 13))
        return MaloufAppNotification(minutes, int(light))
    return None
