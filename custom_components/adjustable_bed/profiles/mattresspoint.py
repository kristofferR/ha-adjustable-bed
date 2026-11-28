"""MattressPoint 1.0.3 (5), bounded app evidence over Okin N-frame."""

from dataclasses import replace
from datetime import datetime
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..execution import ExecutionCapabilities
from .okin_nframe import Hold, OkinNFrameProfile

REFRESH_MS: Final = 300
RELEASE_MS: Final = 100
CLOCK_OFFSETS: Final = (0, 500)
ALARM_OFFSETS: Final = (0, 300, 600)
QUERY_OFFSETS: Final = (0, 200)
# These words are this app's frozen literals, expressed in codec byte order.
MOTORS: Final = MappingProxyType(
    {
        "back": (0x01, 0x02),
        "legs": (0x04, 0x08),
        "both": (0x05, 0x0A),
        "head_tilt": (0x10, 0x20),
        "lumbar": (0x40, 0x80),
    }
)
PRESETS: Final = MappingProxyType(
    {
        "flat": 0x08000000,
        "zero_g": 0x00001000,
        "tv": 0x00004000,
        "lounge": 0x00002000,
        "anti_snore": 0x00008000,
    }
)
MASSAGE: Final = MappingProxyType(
    {
        "on": 0x00000100,
        "off": 0x02000000,
        "timer": 0x00000200,
        "head_up": 0x00000800,
        "head_down": 0x00800000,
        "foot_up": 0x00000400,
        "foot_down": 0x01000000,
        "wave_up": 0x10000000,
        "wave_down": 0x04000000,
    }
)
LIGHT: Final = codec.frame40(0x00020000)
RESET: Final = codec.frame40(0x08001000)  # Encodable only; gesture matrix is unresolved.
STOP: Final = codec.frame40(0)
MASSAGE_QUERY: Final = codec.request(0xB0)
ALARM_QUERY: Final = codec.request(0xC0)
ALARM_DISABLE: Final = codec.alarm((0, 0, 0, 0, 0, 0, 0))
VARIANTS: Final = MappingProxyType({"BOX2422": "BOX2422", "BOX2442": "BOX2442"})
_BASE = OkinNFrameProfile(
    key="mattresspoint",
    name="MattressPoint",
    bed_types=("mattresspoint",),
    width=5,
    write="no_response",
    envelope="plain",
    hold=Hold(repeat_ms=REFRESH_MS, releases=1, release_after_ms=RELEASE_MS),
    keys=MappingProxyType(
        {
            **{
                f"{axis}_{direction}": word
                for axis, words in MOTORS.items()
                for direction, word in zip(("up", "down"), words, strict=True)
            },
            **PRESETS,
        }
    ),
)
PROFILES: Final = MappingProxyType(
    {
        variant: replace(
            _BASE,
            key=f"mattresspoint:{variant}",
            name=f"MattressPoint {variant}",
            axes=axes,
            execution=ExecutionCapabilities(
                hold="stream",
                hold_controls=frozenset(
                    f"{axis}_{direction}" for axis in axes for direction in ("up", "down")
                ),
            ),
        )
        for variant, axes in (
            ("BOX2422", ("back", "legs", "both")),
            ("BOX2442", ("back", "legs", "both", "head_tilt", "lumbar")),
        )
    }
)


def clock(now: datetime) -> bytes:
    return codec.clock(
        (now.year - 2000, now.month, now.day, now.isoweekday(), now.hour, now.minute, now.second)
    )


def alarm(
    *,
    repeat: int,
    position: int,
    wake: int,
    hour: int,
    minute: int,
    now_hour: int,
    now_minute: int,
    weekday: int,
) -> bytes:
    """Frozen builder grammar only. UI choices remain unavailable pending S01."""
    mode = 8 if position != 0 else (5 if wake == 0 else 1 if wake == 1 else 2 if wake == 2 else 3)
    if repeat == 128:
        today = (hour, minute) > (now_hour, now_minute)
        repeat = (
            (1 if weekday == 7 else 128 >> (7 - weekday))
            if today
            else (2 if weekday == 7 else 128 >> (6 - weekday))
        )
    return codec.alarm((repeat, mode, hour, minute, 0, 1, 0))
