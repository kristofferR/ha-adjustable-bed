"""Simmons Blue layouts and records carried by the Okin N-frame codec."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..const import BED_TYPE_SIMMONS_BLUE
from ..execution import STREAM_HOLD
from .okin_nframe import Hold, OkinNFrameProfile

NAME_PREFIX: Final = "smartbed"
REFRESH_MS: Final = 200
SAVE_HOLD_MS: Final = 5500
SLOTS: Final = (1, 2, 3)
WAKE_MODES: Final = MappingProxyType(
    {"flat": 9, "lounge": 2, "tv": 3, "anti_snore": 4, "memory_1": 5, "memory_2": 6}
)
WAKE_LABELS: Final = MappingProxyType(
    {
        "flat": "Flat",
        "lounge": "Relax",
        "tv": "TV",
        "anti_snore": "Anti-snore",
        "memory_1": "Memory 1",
        "memory_2": "Memory 2",
    }
)

PROFILE: Final = OkinNFrameProfile(
    key=BED_TYPE_SIMMONS_BLUE,
    name="Simmons Blue",
    bed_types=(BED_TYPE_SIMMONS_BLUE,),
    width=5,
    write="response",
    envelope="plain",
    keys=MappingProxyType(
        {
            "stop": 0,
            "first_up": 0x01,
            "first_down": 0x02,
            "second_up": 0x04,
            "second_down": 0x08,
            "incline": 0x10,
            "combined_up": 0x50,
            "combined_down": 0xA0,
            "memory_1": 0x00010000,
            "memory_2": 0x00040000,
            "anti_snore": 0x00008000,
            "tv": 0x00004000,
            "relax": 0x00001000,
            "flat": 0x08000000,
            "light": 0x00020000,
        }
    ),
    hold=Hold(repeat_ms=REFRESH_MS, releases=1),
    execution=STREAM_HOLD,
    memory_slots=2,
)


@dataclass(frozen=True, slots=True)
class Layout:
    label: str
    held: tuple[str, ...]


_BALANCE: Final = ("first_up", "first_down")
_MOTION: Final = (*_BALANCE, "second_up", "second_down", "flat", "relax", "tv", "anti_snore")
_COMBINED: Final = (*_MOTION, "combined_up", "combined_down")
DEFAULT_LAYOUT: Final = "balance"
LAYOUTS: Final = MappingProxyType(
    {
        DEFAULT_LAYOUT: Layout("Simmons E Balance", _BALANCE),
        "motion2": Layout("iD Motion 2 motors", _MOTION),
        "motion3": Layout("iD Motion 3 motors", _COMBINED),
        "motion4": Layout("iD Motion 4 motors", (*_COMBINED, "incline")),
    }
)


def control(action: str) -> bytes:
    return codec.frame40(PROFILE.keys[action])


def query_alarm(slot: int) -> bytes:
    return codec.request({2: 0xD0, 3: 0xE0}.get(slot, 0xC0))


def alarm_frame(slot: int, week: int, mode: int, hour: int, minute: int, enabled: int) -> bytes:
    """Program one alarm slot, including the reserved trailing bytes."""
    opcode = {2: 6, 3: 7}.get(slot, 5)
    return codec.parameter_record(
        2, (7, opcode, week, mode, hour, minute, 0, enabled, 0, 0), size=5
    )


def clock_frame(now: datetime) -> bytes:
    """Encode local date and time, with Monday as weekday 1."""
    return codec.parameter_record(
        2,
        (
            7,
            4,
            (now.year - 2000) & 0xFF,
            now.month,
            now.day,
            now.isoweekday(),
            now.hour,
            now.minute,
            now.second,
            0,
        ),
        size=5,
    )


def alarm_week(weekdays: Sequence[int]) -> int:
    """Encode weekdays using the bed's Sunday-first recurring mask."""
    return 0 if not weekdays else 0x80 | sum(1 << ((day + 1) % 7) for day in set(weekdays))


@dataclass(frozen=True, slots=True)
class AlarmRecord:
    slot: int
    week: int
    mode: int
    hour: int
    minute: int
    enabled: int


def parse_alarm(data: bytes) -> AlarmRecord | None:
    """Decode a complete alarm report. The massage-shaped reply carries no state."""
    if len(data) < 10 or data[0] != 0xA5 or data[1] not in (0x0C, 0x0D, 0x0E):
        return None
    week, mode, hour, minute = data[4:8]
    enabled = data[9]
    if enabled == 1 and not any((week, mode, hour, minute)):
        enabled = 0
    if enabled and week < 0x80:
        week = 0
    return AlarmRecord(data[1] - 0x0B, week, mode if enabled else 9, hour, minute, enabled)
