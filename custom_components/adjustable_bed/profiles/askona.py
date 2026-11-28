"""Askona 5.4.3's accepted P1 subset over Keeson, hardware unverified.

Source audit remains PARTIAL. Models are explicit choices, never inferred from
shared GATT roles. The notification-length fallback is parser behavior only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from ..codec import keeson
from .keeson import KeesonProfile, Release

WRITE_SERVICE: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
VERSION_UUID: Final = "00002a28-0000-1000-8000-00805f9b34fb"
MODEL_CHOICES: Final = {
    "633": "Ergomotion 633",
    "180x200": "Ergomotion 180x200",
    "element": "Ergomotion Element",
}


@dataclass(frozen=True, kw_only=True)
class AskonaProfile(KeesonProfile):
    max_head: int
    max_foot: int
    light_offset: int
    timer_offset: int
    massage_values: tuple[int, ...]
    preset_positions: tuple[tuple[int, int], ...]


PROFILES: Final = {
    key: AskonaProfile(
        key=f"askona_{key}",
        hold=None,
        release=Release(steps=(), on_stop=False),
        presets={"lounge": 0x2000, "zero_g": 0x1000, "tv": 0x4000},
        massage="none",
        tilt=False,
        lumbar=False,
        fixed_write=True,
        max_head=head,
        max_foot=foot,
        light_offset=light,
        timer_offset=timer,
        massage_values=levels,
        preset_positions=positions,
    )
    for key, head, foot, light, timer, levels, positions in (
        ("633", 68, 44, 13, 9, tuple(range(7)), ((0, 0), (46, 24), (21, 37), (60, 34))),
        ("180x200", 64, 22, 13, 9, (0, 1, 3, 6), ((0, 0), (44, 12), (21, 20), (55, 17))),
        ("element", 100, 36, 14, 10, (0, 1, 3, 6), ((0, 0), (31, 19), (13, 36), (55, 32))),
    )
}


def admitted_name(name: str | None) -> bool:
    """Kotlin Regex.matches: case sensitive, with a wildcard after i4/i5."""
    return re.fullmatch(r"(base-i[45].)[0-9]{8}", name or "") is not None


def target(head: int, foot: int) -> bytes:
    """The app places byte targets in each 16-bit field's high byte."""
    return keeson.position_target((head & 255) << 8, (foot & 255) << 8)


def parse_status(data: bytes, model: str | None = None) -> keeson.AskonaStatus | None:
    if len(data) < 16:
        return None
    profile = PROFILES[model if model is not None else "element" if len(data) == 19 else "633"]
    return keeson.parse_askona_status(
        data,
        max_head=profile.max_head,
        max_foot=profile.max_foot,
        light_offset=profile.light_offset,
        timer_offset=profile.timer_offset,
        massage_values=profile.massage_values,
    )
