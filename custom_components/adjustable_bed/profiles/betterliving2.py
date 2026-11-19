"""BetterLiving2 1.3.0 (16): app-owned packet fields and controls.

The accepted report proves three wire routes and two selected layouts. Neither
the zero model byte nor the three-motor screen establishes side addressing or a
separately controllable third axis. Hardware remains unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from ..codec import keeson, okin_nframe

type Protocol = Literal["P1", "P2", "P3"]
type AlarmAction = Literal["memory_1", "memory_2", "massage"]


@dataclass(frozen=True, slots=True)
class Calendar:
    """The app's local calendar, with Sunday numbered zero."""

    year: int
    month: int
    day: int
    weekday: int
    hour: int
    minute: int
    second: int

    @classmethod
    def from_datetime(cls, now: datetime) -> Calendar:
        return cls(
            now.year,
            now.month,
            now.day,
            now.isoweekday() % 7,
            now.hour,
            now.minute,
            now.second,
        )


@dataclass(frozen=True, slots=True)
class Layout:
    """A user-selected screen, independent of the wire route."""

    label: str
    combined_up: int
    combined_down: int
    refresh_ms: int


LAYOUTS: Final = {
    "2": Layout("2 motors: back and feet", 5, 10, 100),
    "3": Layout("3 motors: back, feet and all sections", 16, 32, 200),
}
NAME_PREFIXES: Final = ("okin", "smartbed")
GATT: Final = {
    "P1": (
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    "P2": (
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    "P3": (
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
}
MANUFACTURER_MARKERS: Final = ("BLE-4.0 Module", "DewertOKIN")
MANUFACTURER_SERVICE: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_CHARACTERISTIC: Final = "00002a29-0000-1000-8000-00805f9b34fb"


def manufacturer_route(value: bytes | None) -> Protocol | None:
    """The accepted case-sensitive selector, advisory after an explicit choice."""
    if value is None:
        return None
    text = value.decode("utf-8", errors="replace").replace("\0", "").strip()
    return "P2" if any(marker in text for marker in MANUFACTURER_MARKERS) else "P1"


MOTORS: Final = {"back": (1, 2), "feet": (4, 8)}
PRESETS: Final = {
    "P1": {
        "zero_g": 0x01000001,
        "flat": 0x01000002,
        "memory_1": 0x01000008,
        "memory_2": 0x01000009,
    },
    "P2": {"zero_g": 0x1000, "flat": 0x08000000, "memory_1": 0x10000, "memory_2": 0x40000},
    "P3": {"zero_g": 0x1000, "flat": 0x08000000, "memory_1": 0x10000, "memory_2": 0x40000},
}
PROGRAM: Final = {
    "P1": {"zero_g": 0x20000001, "memory_1": 0x20000008, "memory_2": 0x20000009},
    "P2": {"zero_g": 0x1000, "memory_1": 0x10000, "memory_2": 0x40000},
    "P3": {"zero_g": 0x1000, "memory_1": 0x10000, "memory_2": 0x40000},
}
P1_PRESET_STOP: Final = 0x01000000
P1_MASSAGE_BASES: Final = {"head": 0x10000010, "feet": 0x11000010, "wave": 0x10000020}
P1_TIMER_INPUTS: Final = (-1, 0, 1, 2)
P1_TIMER_BASE: Final = 0x10000030
P1_LIGHT: Final = {False: 0x31000000, True: 0x31000001}
STEP_MASSAGE: Final = {
    "toggle": 0x100,
    "timer": 0x200,
    "feet_up": 0x400,
    "head_up": 0x800,
    "feet_down": 0x01000000,
    "head_down": 0x00800000,
    "wave": 0x10000000,
}
STEP_LIGHT: Final = 0x20000
MASSAGE_LABELS: Final = {
    "toggle": "Toggle massage",
    "timer": "Cycle massage timer",
    "feet_up": "Increase foot massage",
    "head_up": "Increase head massage",
    "feet_down": "Decrease foot massage",
    "head_down": "Decrease head massage",
    "wave": "Cycle massage wave",
}
ALARM_KINDS: Final = {
    "P1": {"memory_1": 8, "memory_2": 9, "massage": 15},
    "P2": {"memory_1": 17, "memory_2": 19, "massage": 9},
    "P3": {"memory_1": 5, "memory_2": 6, "massage": 8},
}
MOVEMENT_LIMIT_MS: Final = 1_000_000
RELEASE_MS: Final = 100
RELEASE_COUNT: Final = 2
RECALL_RELEASE_MS: Final = 100
PROGRAM_DURATION_MS: Final = 6000
PROGRAM_REFRESH_MS: Final = {"P1": 5000, "P2": 100, "P3": 100}
MASSAGE_ZONE_GAP_MS: Final = 100
P3_MASSAGE_QUERY_MS: Final = 150
ALARM_REPEAT_COUNT: Final = 2
ALARM_SYNC_DELAY_MS: Final = 100
ALARM_QUERY_DELAY_MS: Final = 400
SETUP_QUERY_DELAY_MS: Final = 300


def command(protocol: Protocol, opcode: int) -> bytes:
    """Encode the app's low 32-bit word; its model/selector is always zero."""
    word = opcode & 0xFFFFFFFF
    if protocol == "P1":
        return keeson.frame(word, header=0xE5, order="big")
    if protocol == "P2":
        return keeson.frame(word, header=0xE6, order="little", side=0)
    if protocol == "P3":
        return keeson.p2(word, "p2_side")
    raise ValueError("Unknown BetterLiving2 wire route")


def current_time(protocol: Protocol, now: Calendar) -> bytes:
    """Encode the route's own calendar offsets, truncating Java byte fields."""
    if protocol == "P1":
        return keeson.checked(
            bytes(
                (
                    0xE2,
                    0xFE,
                    0x16,
                    now.second & 255,
                    now.minute & 255,
                    now.hour & 255,
                    now.weekday & 255,
                )
            )
        )
    if protocol == "P2":
        return keeson.clock_fields(
            tuple(
                value & 255
                for value in (
                    now.year - 1900,
                    now.month - 1,
                    now.day,
                    now.hour,
                    now.minute,
                    now.second,
                )
            )
        )
    if protocol == "P3":
        return okin_nframe.clock(
            tuple(
                value & 255
                for value in (
                    now.year - 2000,
                    now.month,
                    now.day,
                    now.weekday,
                    now.hour,
                    now.minute,
                    now.second,
                )
            )
        )
    raise ValueError("Unknown BetterLiving2 wire route")


def alarm(
    protocol: Protocol,
    *,
    hour: int,
    minute: int,
    week: int,
    massage: int,
    kind: int,
    now: Calendar,
    enabled: bool = True,
) -> bytes:
    """Encode raw app fields; service admission validates user-facing values.

    P3 compares the signed sentinel before byte truncation. P1's massage mask
    is bitwise 0x11, not a boolean. Disabling P3 retains the selected fields.
    """
    if protocol == "P1":
        fields = (
            (minute, hour, now.weekday, week, 0x11, massage & 0x11, 0xF0 + kind)
            if enabled
            else (255, 255, 255, 255, 255, 255, 0x18)
        )
        return keeson.checked(
            bytes(
                (
                    0xEB,
                    0xFE,
                    0x16,
                    now.second & 255,
                    now.minute & 255,
                    now.hour & 255,
                    *(value & 255 for value in fields),
                )
            )
        )
    if protocol == "P2":
        record = bytes(value & 255 for value in (hour, minute, week, kind)) if enabled else bytes(4)
        return keeson.alarm_table(3, record)
    if protocol == "P3":
        return okin_nframe.alarm(
            tuple(
                value & 255
                for value in (
                    0 if week == -128 else week,
                    kind,
                    hour,
                    minute,
                    0,
                    int(enabled),
                    0,
                )
            )
        )
    raise ValueError("Unknown BetterLiving2 wire route")


def alarm_query(protocol: Protocol, now: Calendar) -> bytes:
    """P1's read path synchronizes time rather than sending a query opcode."""
    if protocol == "P1":
        return current_time(protocol, now)
    if protocol == "P2":
        return keeson.checked(bytes((0xE1, 0x80, 0x03)))
    if protocol == "P3":
        return okin_nframe.request(0xC0)
    raise ValueError("Unknown BetterLiving2 wire route")


def massage_query(protocol: Protocol) -> bytes:
    if protocol == "P2":
        return command(protocol, 12)
    if protocol == "P3":
        return okin_nframe.request(0xB0)
    raise ValueError("BetterLiving2 P1 has no massage query")


def weekday_mask(days: frozenset[int], hour: int, minute: int, now: datetime) -> int:
    """Sunday-zero days; no selection resolves to the strictly next alarm day."""
    if any(isinstance(day, bool) or day not in range(7) for day in days):
        raise ValueError("Weekdays must be Sunday zero through Saturday six")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Invalid alarm time")
    if days:
        return 0x80 | sum(1 << day for day in days)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return 1 << (target.isoweekday() % 7)
