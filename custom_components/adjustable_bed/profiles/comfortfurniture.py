"""ComfortFurniture 2.3 (10): fixed bedding profile over Keeson K1.

No name/service selector, model query or seating/accessory capability is proven.
Words, labels and cadence come from this app.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from .keeson import COMFORTFURNITURE, KeesonProfile

MassageSlider = Literal["wave", "intensity"]
PRESET_NAMES: Final = MappingProxyType(
    {
        "zero_g": "Zero G",
        "flat": "Flat",
        "anti_snore": "AS",
        "reading": "Reading",
        "memory": "Memory",
    }
)


@dataclass(frozen=True)
class ComfortFurnitureProfile:
    """App controls and local slider preferences; bins have no measured unit."""

    wire: KeesonProfile = COMFORTFURNITURE
    axes: Mapping[str, tuple[int, int]] = field(
        default_factory=lambda: MappingProxyType(
            {
                "back": (1, 2),
                "feet": (4, 8),
                "both": (5, 10),
                "head": (0x10, 0x20),
                "waist": (0x40, 0x80),
            }
        )
    )
    recalls: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType(
            {
                "zero_g": 0x21000001,
                "flat": 0x21000002,
                "anti_snore": 0x21000003,
                "reading": 0x21000004,
                "memory": 0x21000006,
            }
        )
    )
    saves: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType(
            {
                "zero_g": 0x21000011,
                "flat": 0x21000012,
                "anti_snore": 0x21000013,
                "reading": 0x21000014,
                "memory": 0x21000016,
            }
        )
    )
    preset_stop: int = 0x21000000
    reset_label: int = 0xFFFFFFFF
    massage_start: int = 0x10000011
    massage_stop: int = 0x10000010
    slider_bases: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType(
            {
                "wave": 0x10000021,
                "intensity": 0x10000011,
            }
        )
    )
    slider_max: int = 29
    slider_default: int = 10
    timers: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType(
            {
                "10": 0x10000030,
                "20": 0x10000031,
                "30": 0x10000032,
            }
        )
    )

    def slider_word(self, slider: str, progress: int) -> int:
        """Shipped SeekBar progress, quantized in three bins without physical names."""
        if (
            slider not in self.slider_bases
            or type(progress) is not int
            or not 0 <= progress <= self.slider_max
        ):
            raise ValueError("ComfortFurniture slider must be wave/intensity progress 0..29")
        return self.slider_bases[slider] + progress // 10

    @property
    def words(self) -> frozenset[int]:
        """Every proven command word, for codec coverage and generated reference."""
        return frozenset(
            {
                0,
                *(word for pair in self.axes.values() for word in pair),
                *self.recalls.values(),
                *self.saves.values(),
                self.preset_stop,
                self.reset_label,
                self.massage_start,
                self.massage_stop,
                *self.timers.values(),
                0x31000000,
                0x31000001,
                *(self.slider_word(slider, p) for slider in self.slider_bases for p in (0, 10, 20)),
            }
        )


PROFILE: Final = ComfortFurnitureProfile()
