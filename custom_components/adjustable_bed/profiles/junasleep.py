"""JunaSleep 1.0.3 (20), accepted static A/B remote tables, hardware unverified.

Hand-transcribed from the accepted package-local report. All 35 outgoing
literals reproduce through the existing Keeson encoders. No catalog generator.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

CHOICES: Final = {"a": "Remote A (two axes)", "b": "Remote B (four axes)"}
MASSAGE: Final = {
    "foot_massage_down": 0x1000000,
    "foot_massage_up": 0x400,
    "head_massage_down": 0x800000,
    "head_massage_up": 0x800,
    "massage_timer_button": 0x200,
}
AXES: Final = {
    "a": (("head", 1, 2), ("feet", 4, 8)),
    "b": (("head", 1, 2), ("feet", 4, 8), ("tilt", 32, 16), ("lumbar", 128, 64)),
}
PROFILES: Final = {
    key: KeesonProfile(
        key=f"junasleep_{key}",
        execution=STREAM_HOLD,
        carrier="p2" if key == "a" else "k1",
        transport="ksbt" if key == "a" else "base",
        notify="ksbt" if key == "a" else "base",
        fixed_write=True,
        hold=(10, refresh),
        refresh_ms=refresh,
        release=Release(steps=(), on_stop=False),
        presets={"flat": 0x08000000, "zero_g": 0x1000},
        memory={1: 0x2000, 2: 0x4000},
        memory_slots=2,
        massage="none",
        lights="toggle",
        tilt=key == "b",
        lumbar=key == "b",
        held_controls={
            f"{axis}_{direction}": (word, True)
            for axis, up, down in AXES[key]
            for direction, word in (("up", up), ("down", down))
        },
    )
    for key, refresh in (("a", 300), ("b", 80))
}
QUERY: Final = {"a": codec.STATUS_QUERY, "b": codec.frame(0)}
QUERY_PERIOD_S: Final = 3.0
POST_TAP_QUERY_S: Final = 0.2


@dataclass(frozen=True, slots=True)
class Status:
    light: bool | None
    seconds: int | None
    indicator: int | None


def parse_status(remote: str, data: bytes) -> Status | None:
    """Retain unpadded A hex, B nibble reversal/Java overflow and unchanged gates."""
    if remote == "a":
        if len(data) != 16:
            return None
        light = {0: False, 1: True}.get(data[12])
        seconds = int(f"{data[3]:x}{data[4]:x}", 16)
        indicator = (
            0
            if seconds == 0
            else 10
            if seconds <= 600
            else 20
            if seconds <= 1200
            else 30
            if seconds <= 1800
            else None
        )
    else:
        if len(data) != 20:
            return None
        light = {0: False, 1: True}.get((data[14] & 240) >> 6)
        raw = int(data[9:13].hex()[::-1], 16)
        if raw > 0x7FFFFFFF:
            # The app updates the light before Integer.parseInt throws.
            return Status(light, None, None)
        seconds = raw // 1000
        indicator = 0 if seconds == 0 else 10 if seconds <= 600 else 20 if seconds <= 1200 else 30
    return Status(light, seconds, indicator)


def actions(remote: str) -> dict[str, int]:
    return {**MASSAGE, **({"total_massage_button": 0x100} if remote == "a" else {})}


def scan_matches(name: str) -> bool:
    """App fuzzy discovery; these shared names never choose an A/B remote."""
    return "KSBT02C" in name or "base" in name.lower()
