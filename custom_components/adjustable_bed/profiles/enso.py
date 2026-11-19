"""Enso Remote 2.3 layouts and actions over the Keeson codec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..codec import keeson
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
REFRESH_MS: Final = 100


@dataclass(frozen=True, kw_only=True)
class EnsoProfile(KeesonProfile):
    """A manual layout, never inferred from advertisements or status bytes."""

    motors: tuple[str, ...]


PROFILES: Final = {
    str(count): EnsoProfile(
        key=str(count),
        execution=STREAM_HOLD,
        hold=(10, REFRESH_MS),
        refresh_ms=REFRESH_MS,
        release=Release(after_tap=True),
        presets={"flat": 0x08000000, "zero_g": 0x1000},
        memory={1: 0x2000, 2: 0x4000},
        memory_slots=2,
        lights="toggle",
        massage="none",
        tilt=count == 4,
        lumbar=count >= 3,
        motors=(
            "back",
            "foot",
            *(("waist",) if count == 4 else ()),
            *(("lumbar",) if count >= 3 else ()),
            *(("combined",) if count == 2 else ()),
        ),
    )
    for count in (2, 3, 4)
}
MOTOR_WORDS: Final = {
    "head": (1, 2),
    "feet": (4, 8),
    "tilt": (0x10, 0x20),
    "lumbar": (0x40, 0x80),
    "both": (5, 10),
}
# These are single presses, without the movement page's zero release.
MASSAGE_WORDS: Final = {
    "head_massage_increase": 0x800,
    "head_massage_decrease": 0x800000,
    "foot_massage_increase": 0x400,
    "foot_massage_decrease": 0x1000000,
    "massage_level": 0x100,
    "timer_massage_page": 0x200,
}
HELD_WORDS: Final = {
    "memory_A": 0x2000,
    "memory_B": 0x4000,
    "timer_memory_page": 0x200,
    "massage_mode": 0x4000000,
}


def trim_name(name: str) -> str:
    """Java String.trim removes only leading/trailing characters at or below U+0020."""
    return name.strip("".join(chr(value) for value in range(33)))


def rename(name: str) -> bytes:
    """Android UTF-8 bytes copied using the Java UTF-16 length, including its quirk."""
    name = trim_name(name)
    units = len(name.encode("utf-16-le")) // 2
    return keeson.rename(name.encode("utf-8")[:units])


@dataclass(frozen=True, slots=True)
class Status:
    light: bool
    timer_minutes: int | None


def parse_status(data: bytes) -> Status | None:
    """Independent light/timer page projections; unknown timers retain prior state."""
    offset = {16: 13, 19: 14}.get(len(data))
    if offset is None or data[offset] & 0x20:
        return None
    timer = data[offset + 1]
    return Status(
        bool(data[offset] & 0x40), 0 if timer == 255 else timer * 10 if timer in (1, 2, 3) else None
    )
