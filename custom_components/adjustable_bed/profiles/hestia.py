"""Hestia Motion 1.2 (3), accepted static app evidence, over Keeson K1.

The app accepts any scanned address; service UUIDs and write properties are
not identity rules. No position parser, initialization or authentication exists.
"""

from datetime import datetime, time
from types import MappingProxyType
from typing import Final

from ..codec import keeson
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, MemorySave, Release

PROFILE: Final = KeesonProfile(
    key="hestia_motion",
    execution=STREAM_HOLD,
    order="big",
    hold=(10, 100),
    refresh_ms=100,
    release=Release(steps=((100, 0),)),
    tap_wait_ms=100,
    presets=MappingProxyType({"zero_g": 0x21000001, "flat": 0x21000002, "anti_snore": 0x21000003}),
    memory=MappingProxyType({1: 0x21000004, 2: 0x21000006}),
    memory_slots=2,
    memory_save=MemorySave(words=MappingProxyType({1: 0x21000014, 2: 0x21000016})),
    lights="discrete",
    massage="none",
    tilt=False,
    lumbar=False,
)
AXES: Final = MappingProxyType({"back": (1, 2), "legs": (4, 8), "both": (5, 10)})
PRESET_CANCEL: Final = 0x21000000
INTENSITY: Final = 0x10000010
WAVE: Final = 0x10000020
TIMERS: Final = MappingProxyType({10: 0x10000030, 20: 0x10000031, 30: 0x10000032})
LIGHTS: Final = {False: 0x31000000, True: 0x31000001}
DEFAULTS: Final = MappingProxyType(
    {
        "intensity": "0",
        "wave": "0",
        "timer": "10",
        "hour": "0",
        "minute": "0",
        "enhancement": "off",
        "memory": "none",
    }
)
CHOICES: Final = MappingProxyType(
    {
        "intensity": tuple(map(str, range(4))),
        "wave": tuple(map(str, range(4))),
        "timer": ("10", "20", "30"),
        "hour": tuple(map(str, range(24))),
        "minute": tuple(map(str, range(60))),
        "memory": ("none", "memory_1", "memory_2"),
    }
)


def alarm(
    now: datetime,
    target: time | None,
    *,
    enhancement: bool = False,
    intensity: int = 0,
    wave: int = 0,
    timer: int = 10,
    memory: str = "none",
) -> bytes:
    """RTC enhancement and memory are independent; disabling retains the current clock."""
    if intensity not in range(4) or wave not in range(4) or timer not in TIMERS:
        raise ValueError("Choose Hestia intensity/wave 0..3 and timer 10, 20 or 30")
    if memory not in CHOICES["memory"]:
        raise ValueError("Choose no wake position, Memory A or Memory B")
    options = (
        INTENSITY + intensity & 255 if intensity else 255,
        WAVE + wave & 255,
        TIMERS[timer] & 255,
        {"none": 255, "memory_1": 4, "memory_2": 6}[memory],
    )
    if not enhancement:
        options = (255, 255, 255, options[3])
    if target is None:
        options = (255, 255, 255, 255)
    return keeson.ea_clock(now, target, options)


def words() -> frozenset[int]:
    """Every reachable key, independent of transport and host write mode."""
    assert PROFILE.memory_save is not None
    return frozenset(
        {
            0,
            PRESET_CANCEL,
            *(w for pair in AXES.values() for w in pair),
            *PROFILE.presets.values(),
            *PROFILE.memory.values(),
            *PROFILE.memory_save.words.values(),
            *LIGHTS.values(),
            *TIMERS.values(),
            *(base + level for base in (INTENSITY, WAVE) for level in range(4)),
        }
    )
