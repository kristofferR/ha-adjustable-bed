"""King Koil Bed 1.0: saved app selectors, independently proven command tables."""

from dataclasses import dataclass
from typing import Final

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

REFRESH_MS: Final = 300
POLL_S: Final = 0.5
LIGHT: Final = 0x20000
MASSAGE: Final = {
    "massage_mode": 0x04000000,
    "massage_head": 0x800,
    "massage_foot": 0x400,
    "massage_timer": 0x200,
}


@dataclass(frozen=True, slots=True)
class Layout:
    label: str
    profile: KeesonProfile
    axes: tuple[tuple[str, int, int], ...]
    massage: bool
    held_light: bool

    @property
    def actions(self) -> dict[str, int]:
        return {"light": LIGHT, **(MASSAGE if self.massage else {})}


# These are SAVED selectors, not the inverted guide-image/resource filenames.
LAYOUTS: Final = {
    selector: Layout(
        label,
        KeesonProfile(
            key=f"kingkoil_{selector}",
            execution=STREAM_HOLD,
            carrier="p2",
            transport="ksbt",
            notify="ksbt",
            fixed_write=True,
            hold=(10, REFRESH_MS),
            refresh_ms=REFRESH_MS,
            release=Release(steps=(), on_stop=False),
            presets={"flat": 0x08000000, "zero_g": 0x1000, "tv": 0x4000},
            lights=None,
            massage="none",
            tilt=False,
            lumbar=False,
            keeson_motor_names=False,
        ),
        axes,
        massage,
        massage,
    )
    for selector, label, axes, massage in (
        (
            "KSBT03CK",
            "Head / foot with massage",
            (("head", 1, 2), ("feet", 4, 8)),
            True,
        ),
        (
            "KSBT03CL",
            "Head A / head B / foot",
            (("head_a", 1, 2), ("head_b", 4, 8), ("feet", 16, 32)),
            False,
        ),
    )
}
CHOICES: Final = {key: layout.label for key, layout in LAYOUTS.items()}
TRANSPORT: Final = codec.TRANSPORTS["ksbt"]
