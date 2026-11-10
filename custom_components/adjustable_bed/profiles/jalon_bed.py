"""OkinComfortBed Ⅱ 1.4 (com.ore.jalon.neworebeding_android), row135.

Physical layouts change UI axes only. The wire model remains zero. No data
here is inferred from other ORE apps, even where the Keeson codec matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .keeson import JALON_BED as PROFILE


@dataclass(frozen=True, slots=True)
class Layout:
    label: str
    axes: tuple[str, ...]


LAYOUTS: Final = {
    "20": Layout("2 motors: back and feet", ("back", "feet")),
    "30": Layout("3 motors: headrest, back and feet", ("head", "back", "feet")),
    "31": Layout("3 motors: waist, back and feet", ("lumbar", "back", "feet")),
    "40": Layout("4 motors: headrest, back, feet and waist", ("head", "back", "feet", "lumbar")),
}
MOTORS: Final = {"back": (1, 2), "feet": (4, 8), "head": (16, 32), "lumbar": (64, 128)}
AXIS_LABELS: Final = {"back": "back", "feet": "feet", "head": "head", "lumbar": "waist"}
PRESETS: Final = {
    "flat": 0x08000000,
    "zero_g": 0x1000,
    "lounge": 0x2000,
    "tv": 0x4000,
    "anti_snore": 0x8000,
    "memory_1": 0x10000,
    "memory_2": 0x40000,
}
# The overlapping Flat/Zero G press flags produce this held word. Its physical
# reset/save effect is unverified, so it is exposed as a held app gesture.
HELD: Final = {**PRESETS, "flat_zero_g": 0x08001000}
MASSAGE: Final = {"head": 0x800, "feet": 0x400, "all": 0x100, "timer": 0x200, "type": 0x10000000}
LIGHT: Final = 0x20000
WAKE_MODES: Final = {"none": 0, "memory_1": 0x11, "memory_2": 0x13, "massage": 9}
REFRESH_MS: Final = 100
HOLD_LIMIT_MS: Final = 8000
MOTOR_RELEASES: Final = 3
PRESET_REPEATS: Final = 3
POSITION_FLAT_REPEATS: Final = 2
UTILITY_REPEATS: Final = 3
UTILITY_RELEASES: Final = 2
ALARM_DELAY_MS: Final = 100
DISABLE_REPEATS: Final = 2

__all__ = ["PROFILE"]
