"""KONFURT 1.0: three manual layouts on the proven Keeson E6 carrier."""

from dataclasses import dataclass
from typing import Final, cast

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Preset, Release, encode

WRITE_SERVICE: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
WRITE: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
REFRESH_MS: Final = 300
RELEASE_MS: Final = (300, 600)
ALARM_DELAY_MS: Final = 200
QUERY_MS: Final = (300, 600)
WORDS: Final = {
    "back_up": 1, "back_down": 2, "feet_up": 4, "feet_down": 8,
    "head_up": 16, "head_down": 32, "lumbar_up": 64, "lumbar_down": 128,
    "stop": 0, "flat": 0x08000000, "anti_snore": 0x8000, "reading": 0x2000,
    "memory_1": 0x10000, "zero_g": 0x1000, "tv": 0x4000,
    "light": 0x20000, "massage": 0x100, "massage_head": 0x800,
    "massage_foot": 0x400, "massage_wave": 0x10000000, "massage_timer": 0x200,
}
ALARM_QUERY: Final = codec.checked(bytes((0xE1, 0x80, 3)))
ALARM_TYPES: Final = {"none": 0, "massage": 9, "memory_1": 17}


@dataclass(frozen=True, slots=True)
class Layout:
    profile: KeesonProfile
    axes: tuple[str, ...]
    controls: tuple[str, ...]


LAYOUTS: Final = {
    str(count): Layout(
        KeesonProfile(
            key=f"konfurt_{count}", header=0xE6, side=0, execution=STREAM_HOLD,
            hold=(4, REFRESH_MS), refresh_ms=REFRESH_MS,
            release=Release(steps=tuple((at, codec.frame(0, header=0xE6, side=0))
                                        for at in (300, 300))),
            presets={cast(Preset, key): WORDS[key] for key in presets if key != "reading"}, memory={1: WORDS["memory_1"]},
            memory_slots=1, lights="toggle", massage="none", tilt=count >= 3,
            lumbar=count == 4, keeson_motor_names=True,
        ),
        axes,
        tuple(f"{axis}_{direction}" for axis in axes for direction in ("up", "down"))
        + presets + ("memory_1", "light", "massage", "massage_head", "massage_foot",
                     "massage_wave", "massage_timer"),
    )
    for count, axes, presets in (
        (2, ("back", "feet"), ("flat", "anti_snore", "reading", "zero_g", "tv")),
        (3, ("back", "feet", "head"), ("flat", "zero_g", "tv")),
        (4, ("back", "feet", "head", "lumbar"), ("flat", "zero_g")),
    )
}
CHOICES: Final = {key: f"{key} motors" for key in LAYOUTS}


def frame(control: str, layout: Layout) -> bytes:
    return encode(layout.profile, WORDS[control])


def alarm(hour: int, minute: int, repeat: int, kind: int) -> bytes:
    return codec.alarm_table(3, bytes((hour, minute, repeat, kind)))
