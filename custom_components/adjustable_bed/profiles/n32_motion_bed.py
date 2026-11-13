"""N32 Motion Bed 1.1.14 (38), com.okin.simmonskorea, accepted row080.

Only startup enum2 is live. All held, clock, query and alarm literals reproduce
through the Okin N-frame codec; no alternate models or individual upper motors
are inferred. Hardware remains unverified.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..execution import STREAM_HOLD
from .okin_nframe import Hold, OkinNFrameProfile, Tap

REFRESH_MS: Final = 200
FRAME_HOLD_MS: Final = 5300
CLOCK_DELAY_S: Final = 0.5
SLOTS: Final = (1, 2, 3)
ALARM_MODES: Final = MappingProxyType({"none": 0, "m1": 5, "m2": 6, "m3": 4, "flat": 9})
PRESET_LABELS: Final = MappingProxyType(
    {
        "memory_1": "M1",
        "memory_2": "M2",
        "memory_3": "M3",
        "lounge": "Relax",
        "tv_pc": "TV",
        "zero_g": "Zero-G",
        "flat": "Flat",
    }
)
N32: Final = OkinNFrameProfile(
    key="n32_motion_bed",
    name="N32 Motion Bed",
    bed_types=("n32_motion_bed",),
    width=5,
    write="response",
    envelope="plain",
    axes=("back", "legs", "head"),
    keys=MappingProxyType(
        {
            "stop": 0,
            "head_up": 0x05,
            "head_down": 0x0A,
            "foot_up": 0x40,
            "foot_down": 0x80,
            "cervical_up": 0x10,
            "cervical_down": 0x20,
            "memory_1": 0x00010000,
            "memory_2": 0x00040000,
            "memory_3": 0x00008000,
            "lounge": 0x00002000,
            "tv_pc": 0x00004000,
            "zero_g": 0x00001000,
            "flat": 0x08000000,
        }
    ),
    hold=Hold(repeat_ms=REFRESH_MS, releases=1),
    execution=STREAM_HOLD,
    recall=Tap(repeats=1, releases=1),
    memory_slots=3,
)


def alarm_week(weekdays: Sequence[int]) -> int:
    """HA Monday0..Sunday6 to the app's recurring UI mask; empty means once."""
    if any(type(day) is not int or day not in range(7) for day in weekdays):
        raise ValueError("Weekdays must be Monday 0 through Sunday 6")
    return 0 if not weekdays else 0x80 | sum(1 << ((day + 1) % 7) for day in set(weekdays))


def effective_week(week: int, hour: int, minute: int, now: datetime) -> int:
    """setAlarm's separate once-date transform, including Sunday -> 128."""
    if week not in (0, 128):
        return week
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    return 1 << target.isoweekday()


def alarm_frame(slot: int, hour: int, minute: int, week: int, mode: int, enabled: int) -> bytes:
    """Raw builder after caller validation; native Uint8List narrows mod256."""
    return codec.alarm(
        tuple(v & 255 for v in (week, mode, hour, minute, 0, enabled, 1)), slot, reserved=0
    )


def query_frame(slot: int) -> bytes:
    if slot not in SLOTS:
        raise ValueError("N32 has app alarm slots 1, 2 and 3")
    return codec.request(0xB0 + slot * 0x10)


def clock_frame(now: datetime) -> bytes:
    return codec.clock(
        tuple(
            v & 255
            for v in (
                now.year - 2000,
                now.month,
                now.day,
                now.isoweekday(),
                now.hour,
                now.minute,
                now.second,
            )
        )
    )


def manufacturer_identity(data: Mapping[int, bytes | None]) -> str | None:
    """Optional identity aid, never admission, a control address or a side."""
    payload = data.get(89)
    return payload[::-1][1:7].hex() if payload is not None and len(payload) >= 7 else None
