"""ComfortBaseForBluetooth 1.1.2 (6), accepted row161 product and action data.

Product numbers select the phone layout only. Every live control uses selector zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from .keeson import Preset


@dataclass(frozen=True, slots=True)
class Product:
    name: str
    stored_value: int
    axes: tuple[str, ...]
    massage_light: bool = True


_TWO: Final = ("head", "feet")
_THREE: Final = (*_TWO, "elevate")
_FOUR: Final = (*_TWO, "both", "elevate", "tilt")
WRITE_SERVICE: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
PRODUCTS: Final = {
    "ss18x20": Product("SS18X20", 15, _THREE),
    "ss18x40": Product("SS18X40", 16, _FOUR),
    "ssx25": Product("SSX25", 17, _THREE),
    "ssx45": Product("SSX45", 18, _FOUR),
    "freestyle": Product("Freestyle 2.0", 14, _TWO, False),
    "accord": Product("Accord", 11, _THREE),
    "vesta": Product("Vesta", 12, _THREE),
    "odessa": Product("Odessa", 13, _FOUR),
    "somerston": Product("Somerston", 19, _TWO),
    "madrid": Product("Madrid", 20, (*_TWO, "tilt")),
}
AXES: Final[dict[str, tuple[str, int, int]]] = {
    "head": ("keeson_back", 0x01, 0x02),
    "feet": ("keeson_legs", 0x04, 0x08),
    "both": ("both", 0x05, 0x0A),
    "tilt": ("keeson_head", 0x10, 0x20),
    "elevate": ("bed_height", 0x40, 0x80),
}
PRESETS: Final[dict[Preset, int]] = {"zero_g": 0x1000, "flat": 0x8000000, "anti_snore": 0x8000}
MEMORY: Final = {1: 0x2000, 2: 0x4000}
MASSAGE: Final = {
    "timer": 0x200,
    "wave_next": 0x10000000,
    "wave_previous": 0x4000000,
    "intensity_up": 0xC00,
    "intensity_down": 0x1800000,
}
LIGHT_TOGGLE: Final = 0x20000
REFRESH_MS: Final = 100
SAVE_SECONDS: Final = 6
ALARM_DELAY_SECONDS: Final = 0.15
