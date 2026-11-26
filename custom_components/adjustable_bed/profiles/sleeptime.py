"""Sleeptime 1.0.1 (2) layouts, keys and timing over Okin N-frame."""

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from ..alarm import AlarmRequest
from ..codec import okin_nframe as codec
from ..const import BED_TYPE_SLEEPTIME
from ..execution import ExecutionCapabilities
from .okin_nframe import Hold, OkinNFrameProfile

REFRESH_MS: Final = 300
RELEASE_MS: Final = 100
SAVE_MS: Final = REFRESH_MS + 6000  # The local timer starts at the first repeat.
CLOCK_REPEAT_MS: Final = 500
NOTIFY_RETRY_MS: Final = 1000
MASSAGE_QUERY: Final = codec.request(0xB0)
ALARM_QUERY: Final = codec.request(0xC0)
ALARM_WRITES: Final = ((0, "set"), (300, "set"), (500, "query"), (600, "query"), (700, "query"))

MOTORS: Final = MappingProxyType(
    {
        "back": (0x01, 0x02),
        "legs": (0x04, 0x08),
        "neck": (0x10, 0x20),
        "lumbar": (0x40, 0x80),
        "head_tilt": (0x10, 0x20),
        "foot_tilt": (0x40, 0x80),
        "bed_height": (0x50, 0xA0),
    }
)
PRESETS: Final = MappingProxyType(
    {
        "tv": 0x00004000,
        "zero_g": 0x00001000,
        "reading": 0x00002000,
        "anti_snore": 0x00008000,
        "flat": 0x08000000,
        "memory_1": 0x00010000,
        "memory_2": 0x00040000,
    }
)
MASSAGE: Final = MappingProxyType(
    {
        "massage_toggle": (0x00000100, 200),
        "massage_timer": (0x00000200, 300),
        "massage_head_up": (0x00000800, 200),
        "massage_head_down": (0x00800000, 200),
        "massage_foot_up": (0x00000400, 200),
        "massage_foot_down": (0x01000000, 200),
        "massage_mode_next": (0x10000000, 200),
        "massage_mode_previous": (0x04000000, 200),
    }
)
WAKE_MODES: Final = MappingProxyType(
    {
        "massage": 8,
        "tv": 3,
        "zero_g": 1,
        "reading": 2,
        "anti_snore": 4,
        "flat": 9,
        "memory_1": 5,
        "memory_2": 6,
    }
)
LIGHT: Final = codec.frame40(0x00020000, 1)
STOP: Final = codec.frame40(0)
RESET: Final = codec.frame40(0x08001000)


@dataclass(frozen=True, slots=True)
class Layout:
    axes: tuple[str, ...]
    presets: tuple[str, ...]

    @property
    def wake_actions(self) -> tuple[str, ...]:
        return tuple(
            action
            for action in WAKE_MODES
            if action in self.presets or action in ("massage", "flat")
        )


_STANDARD = Layout(("back", "legs"), tuple(PRESETS))
_NECK_LUMBAR = Layout(("back", "legs", "neck", "lumbar"), _STANDARD.presets)
_TILT_LIFT = Layout(
    ("back", "legs", "head_tilt", "foot_tilt", "bed_height"),
    ("reading", "anti_snore", "memory_1", "memory_2"),
)

# Order is the app's selector precedence. 402 and 405 are separate selectors.
LAYOUTS: Final = MappingProxyType(
    {
        "205": _STANDARD,
        "404": _TILT_LIFT,
        "405": _NECK_LUMBAR,
        "402": _NECK_LUMBAR,
    }
)
PREFIXES: Final = tuple(f"smartbed{selector}" for selector in LAYOUTS)
SELECTORS: Final = MappingProxyType({selector: f"SmartBed{selector}" for selector in LAYOUTS})


def select(name: str) -> str | None:
    """Return the app's selector for a Bluetooth platform name."""
    return next(
        (selector for selector in LAYOUTS if name.lower().startswith(f"smartbed{selector}")), None
    )


def motor_key(axis: str, direction: str) -> str:
    return f"{axis}_{direction}"


PROFILE: Final = OkinNFrameProfile(
    key=BED_TYPE_SLEEPTIME,
    name="Sleeptime",
    bed_types=(BED_TYPE_SLEEPTIME,),
    width=5,
    write="no_response",
    envelope="plain",
    selectors=(1, 0),
    keys=MappingProxyType(
        {
            **{
                motor_key(axis, direction): value
                for axis, values in MOTORS.items()
                for direction, value in zip(("up", "down"), values, strict=True)
            },
            **PRESETS,
        }
    ),
    hold=Hold(repeat_ms=REFRESH_MS, releases=1, release_after_ms=RELEASE_MS),
    execution=ExecutionCapabilities(
        hold="stream",
        hold_controls=frozenset(
            motor_key(axis, direction) for axis in MOTORS for direction in ("up", "down")
        ),
    ),
    memory_slots=2,
)


def clock(now: datetime) -> bytes:
    return codec.clock(
        (
            (now.year - 2000) & 0xFF,
            now.month,
            now.day,
            (now.weekday() + 1) % 7,
            now.hour,
            now.minute,
            now.second,
        )
    )


def once_mask(now: datetime, hour: int, minute: int) -> int:
    day = (now.weekday() + 1) % 7
    if (hour, minute) <= (now.hour, now.minute):
        day = (day + 1) % 7
    return 1 << day


def day_mask(request: AlarmRequest) -> int:
    if not request.weekdays:
        return once_mask(request.reference_time, request.hour, request.minute)
    if len(request.weekdays) == 7:
        return 0xFF
    return sum(1 << ((day + 1) % 7) for day in request.weekdays)


def alarm(mode: int, days: int, hour: int, minute: int, enabled: bool) -> bytes:
    return codec.alarm((mode, days, hour, minute, 0, int(enabled), 0))
