"""Adjustable bed 1.2.1 (33), accepted queue unit087.

The 80 frozen rows reproduce Okin N-frame and Okin 5A byte for byte.
The app route stays distinct from Lumbar and the legacy 64-bit receiver.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from ..codec import okin_5a, okin_nframe
from ..execution import STREAM_HOLD, ExecutionCapabilities
from .okin_nframe import ADJUSTABLE_LUMBAR_KEYS


@dataclass(frozen=True, kw_only=True)
class AdjustableAppProfile:
    key: str
    table: str
    frames: Mapping[str, bytes]
    execution: ExecutionCapabilities


# Literal parameters independently matched to unit087's frozen command rows.
STAR_KEYS: Final = MappingProxyType(
    {
        "head_up": (0x30, 0x00),
        "head_down": (0x30, 0x01),
        "feet_up": (0x30, 0x02),
        "feet_down": (0x30, 0x03),
        "stop": (0x30, 0x0F),
        "flat": (0x30, 0x10),
        "anti_snore": (0x30, 0x16),
        "lounge": (0x30, 0x12),
        "incline": (0x30, 0x11),
        "zero_g": (0x30, 0x13),
        "save_anti_snore": (0x30, 0x93),
        "save_lounge": (0x30, 0x91),
        "save_incline": (0x30, 0x92),
        "save_zero_g": (0x30, 0x90),
        "light": (0x30, 0x71),
        "wave_1": (0x30, 0x52),
        "wave_2": (0x30, 0x53),
        "wave_3": (0x30, 0x54),
        "massage_stop": (0x30, 0x6F),
        "massage_on": (0x30, 0x52),
        "massage_up": (0x40, 0x60),
        "massage_down": (0x40, 0x61),
        "voice_stop": (0x30, 0x1F),
        **{
            f"voice_{axis}_{direction}": (0x40, key + offset)
            for axis, key in (("head", 0x00), ("feet", 0x02), ("lumbar", 0x06))
            for direction, offset in (("up", 0), ("down", 1))
        },
    }
)


def _frames(table: str) -> Mapping[str, bytes]:
    if table == "35_22_01":
        return MappingProxyType(
            {
                **{action: okin_5a.command(key, page) for action, (page, key) in STAR_KEYS.items()},
                "check_massage": okin_5a.request(0xB0),
            }
        )
    return MappingProxyType(
        {
            **{
                action: okin_nframe.frame(word, 8)
                for action, word in ADJUSTABLE_LUMBAR_KEYS.items()
            },
            "check_massage": bytes((2, 4)),  # Raw query, outside the N-frame envelope.
        }
    )


PROFILES: Final = MappingProxyType(
    {
        table: AdjustableAppProfile(
            key=key,
            table=table,
            frames=_frames(table),
            # P2 includes a single-start lumbar route, so its entire profile
            # uses the conservative latched ceiling, including touch motors.
            execution=ExecutionCapabilities(hold="latched") if table == "35_22_01" else STREAM_HOLD,
        )
        for table, key in (
            ("25_42_02", "adjustable_bed_star"),
            ("35_22_01", "adjustable_bed_star_5a"),
            ("36_33_04a", "adjustable_bed_okin"),
        )
    }
)
VOICE_MOTORS: Final = tuple(
    f"voice_{axis}_{direction}"
    for axis in ("head", "feet", "lumbar")
    for direction in ("up", "down")
)
VOICE_PRESETS: Final = (
    "flat",
    "zero_g",
    "anti_snore",
    "lounge",
    "incline",
)
VOICE_FINITE: Final = (
    *VOICE_PRESETS,
    "light",
    "wave_1",
    "wave_2",
    "wave_3",
    "massage_on",
    "massage_stop",
)
