"""Richmat 4.2.0's named builders over the literal-verified Richmat codec."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ...codec import richmat as codec

QUERY = {
    "alarms": codec.record_20_len(5, 1, 0, (0,)),
    "snore": codec.record_20_len(6, 0, 0, (0,)),
    "blanket": codec.record_20_len(13, 0, 0, ()),
    "blanket_power": codec.record_20_len(13, 1, 0, (0, 0)),
    "blanket_settings": codec.record_20_len(13, 8, 0, (0, 0)),
    "sleep_name": codec.record_20_len(6, 3, 0, (0,)),
}


def extended(group: int, operation: int, *values: int) -> bytes:
    return codec.record_20_len(group, operation, 1, (0, *values))


def function(enum: str, code: int, side: int, single: bool) -> bytes:
    return codec.function(code, side, action=enum, single=single)


def light_timer(seconds: int) -> bytes:
    digits = format(seconds, "x").rjust(4, "0")
    high, low = int(digits[:2], 16), int(digits[2:4], 16)
    return codec.light_timer(*((255, 255) if high == low == 0 else (high, low)))


def countdown(minutes: int, code: int) -> tuple[bytes, bytes]:
    return codec.frame(110, 5, minutes & 255, 0), codec.frame(
        110, 6, math.trunc(minutes / 256), code
    )


def repeat_alarm(number: int, kind: int, hour: int, minute: int, code: int, repeat: int) -> bytes:
    return codec.record_20_len(5, 1, 1, (number, kind, hour, minute, code, repeat))


def delete_alarm(number: int) -> bytes:
    return codec.record_20_len(5, 2, 1, (number,))


def music_source(source: int, mode: int) -> bytes:
    values = (source,) if source in (0, 1) else (source, mode) if source in (2, 3) else ()
    return extended(9, 4, *values)


def sync_time(now: datetime, zone: datetime | None = None) -> tuple[bytes, bytes]:
    return codec.time_sync(now, zone, build=codec.record_20_len)


def repeat_mask(days: tuple[int, ...], enabled: bool = True) -> int:
    return int(enabled) | (0 if 7 in days else sum(1 << (7 - day) for day in set(days)))


@dataclass(frozen=True, slots=True)
class BlanketSleep:
    enabled: bool = False
    mode: int = 2
    start_hour: int = 23
    start_minute: int = 0
    end_hour: int = 7
    end_minute: int = 0
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    after_mode: int = 1
    delay: int = 5
    temperatures: tuple[int, int, int, int] = (38, 36, 35, 37)
    automatic: bool = False

    def frame(self, zone: int) -> bytes:
        return codec.record_20_len(
            13,
            7,
            1,
            (
                zone,
                int(self.enabled),
                self.mode,
                self.start_hour,
                self.start_minute,
                self.end_hour,
                self.end_minute,
                repeat_mask(self.days),
                self.after_mode,
                self.delay,
                *self.temperatures,
                int(self.automatic),
            ),
        )


def blanket_delay(enabled: bool, value: int) -> bytes:
    """UI says hours; the artifact builder multiplies its raw value by sixty."""
    seconds = max(value, 0) * 60
    return extended(13, 2, int(enabled), math.trunc(seconds / 256), seconds & 255)


def valid_sleep_duration(start: tuple[int, int], end: tuple[int, int]) -> bool:
    minutes = (end[0] * 60 + end[1] - start[0] * 60 - start[1]) % 1440 or 1440
    return 5 <= math.trunc(minutes / 60) <= 15


def opacity(rgb: tuple[int, int, int], percent: int) -> tuple[int, int, int]:
    factor = max(0, min(100, percent)) / 100
    red, green, blue = (math.floor(c * factor + 0.5) for c in rgb)
    return red, green, blue


STARTUP = tuple(
    "deviceFunctionItem" + name
    for name in (
        "CheckClock",
        "CheckLight",
        "CheckAroma",
        "CheckMattress",
        "CheckLumbarMattress",
        "CheckSnore",
        "CheckSpeech",
        "CheckDetection",
        "QueryVersion",
    )
)
VERSION_ONE = tuple(
    "deviceFunctionVersionOne" + name
    for name in (
        "BedCurrentMode",
        "Motor1CurrentAngle",
        "Motor2CurrentAngle",
        "Motor3CurrentAngle",
        "Motor4CurrentAngle",
        "CurrentMassageMode",
        "CurrentBedLightStatus",
    )
)
