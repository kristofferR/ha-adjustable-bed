"""Sealy Posturematic's three layouts over the Okin 5A codec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..codec import okin_5a as codec
from ..execution import ExecutionCapabilities
from .okin_5a import Action, Okin5AProfile, Tap

REFRESH_MS: Final = 300
QUERY_DELAY_MS: Final = 100
PROGRAM_MS: Final = 6000
LAYOUTS: Final = {"0": "Element", "1": "Ascent", "2": "Apex"}

# Every live accessor is retained, including one-shot voice routes. Layouts
# change screen visibility and reset gestures, never these command bytes.
KEYS: Final = {
    "stop": 0x0F,
    "head_up": 0x00,
    "head_down": 0x01,
    "feet_up": 0x02,
    "feet_down": 0x03,
    "both_up": 0x0C,
    "both_down": 0x0D,
    "flat": 0x10,
    "tv": 0x11,
    "zero_g": 0x13,
    "anti_snore": 0x16,
    "memory_1": 0x1A,
    "memory_2": 0x1B,
    "light_toggle": 0x71,
    "light_on": 0x73,
    "light_off": 0x74,
    "massage_toggle": 0x5A,
    "massage_on": 0x52,
    "massage_off": 0x6F,
    "massage_timer": 0x6D,
    "massage_head_up": 0x60,
    "massage_head_down": 0x61,
    "massage_foot_up": 0x62,
    "massage_foot_down": 0x63,
    "wave_up": 0x58,
    "mode_0": 0x52,
    "mode_1": 0x53,
    "mode_2": 0x54,
    "save_zero_g": 0x90,
    "save_tv": 0x92,
    "save_memory_1": 0x94,
    "save_memory_2": 0x95,
    "reset": 0x96,
    "reset_element": 0x37,
    "force_flat": 0x7E,
    "voice_stop": 0x1F,
}
FRAMES: Final = (
    {key: codec.command(value) for key, value in KEYS.items()}
    | {
        f"voice_{key}": codec.command(value, codec.ALTERNATE)
        for key, value in {"head_up": 0, "head_down": 1, "feet_up": 2, "feet_down": 3}.items()
    }
    | {
        "initialize": codec.request(0x0B),
        "query_massage": codec.request(0xB0),
        "query_anti_pinch": codec.request(0xE0),
    }
)


@dataclass(frozen=True, kw_only=True)
class SealyProfile(Okin5AProfile):
    """An explicitly selected product; names do not distinguish the layouts."""

    layout: str


_BASE_KEYS: Final[dict[Action, int]] = {
    "stop": 0x0F,
    "head_up": 0,
    "head_down": 1,
    "feet_up": 2,
    "feet_down": 3,
    "both_up": 0x0C,
    "both_down": 0x0D,
    "flat": 0x10,
    "tv": 0x11,
    "zero_g": 0x13,
    "anti_snore": 0x16,
    "memory_1": 0x1A,
    "memory_2": 0x1B,
    "light_toggle": 0x71,
    "light_on": 0x73,
    "light_off": 0x74,
    "massage_toggle": 0x5A,
    "massage_on": 0x52,
    "massage_off": 0x6F,
    "massage_head_up": 0x60,
    "massage_head_down": 0x61,
    "massage_foot_up": 0x62,
    "massage_foot_down": 0x63,
}
PROFILES: Final = {
    layout: SealyProfile(
        key=layout,
        layout=layout,
        transport="nus",
        write_with_response=False,
        wake=(FRAMES["initialize"],),
        wake_with_response=True,
        frames={key: codec.command(value) for key, value in _BASE_KEYS.items()},
        execution=ExecutionCapabilities(hold="stream"),
        recall=Tap(repeats=2, repeat_ms=REFRESH_MS),
        stop=Tap(repeats=2, repeat_ms=REFRESH_MS),
        hold_refresh_ms=REFRESH_MS,
    )
    for layout in LAYOUTS
}


@dataclass(frozen=True, slots=True)
class MassageStatus:
    minutes: int
    wave: int
    head: int
    foot: int


def parse_massage(data: bytes) -> MassageStatus | None:
    """Packets are independent; absent fields default to zero, without suffix checks."""
    if len(data) < 3 or data[:2] != b"\xa5\x0b":
        return None
    time = (data[4] << 8 if len(data) > 4 else 0) + (data[5] if len(data) > 5 else 0)
    levels = data[7] if len(data) > 7 else 0
    return MassageStatus(
        (time + 599) // 600, data[6] & 15 if len(data) > 6 else 0, levels & 15, (levels & 240) >> 4
    )


def parse_anti_pinch(data: bytes) -> int | None:
    """Forward the raw value only; the app's shared dialog is not bed state."""
    if len(data) < 3 or data[:2] != b"\xa5\x0e":
        return None
    return data[10] if len(data) > 10 else 0


def matches_name(name: str) -> bool:
    """The enabled app selector lowercases the nonempty platform name, without trimming."""
    return bool(name) and name.lower().startswith("star")
