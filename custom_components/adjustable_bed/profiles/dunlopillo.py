"""Dunlopillo Remote 1.7 (11), four explicit BLE layouts, hardware unverified.

Hand-transcribed from the accepted package-local report, with no generator.
All frozen transmit literals reproduce through the existing Keeson codec.
"""

from dataclasses import dataclass
from typing import Final, Literal

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
REFRESH_MS: Final = 100
PULSE_RELEASE_MS: Final = 300
CHOICES: Final = {
    "b2": "A / B2 (two axes)",
    "b1": "B / B1 (two axes)",
    "c1": "C / C1 (two axes, light)",
    "d1": "D / D1 (four axes, light)",
}
AXES: Final = {
    key: ("head", "feet", "tilt", "lumbar") if key == "d1" else ("head", "feet") for key in CHOICES
}
Mode = Literal["hold", "single", "pulse"]


@dataclass(frozen=True, slots=True)
class Control:
    label: str
    word: int
    mode: Mode


_COMMON: Final = {
    "head_up": Control("Head up", 1, "hold"),
    "head_down": Control("Head down", 2, "hold"),
    "feet_up": Control("Foot up", 4, "hold"),
    "feet_down": Control("Foot down", 8, "hold"),
    "flat": Control("Flat", 0x08000000, "single"),
    "zero_g": Control("Zero gravity", 0x1000, "single"),
    "head_massage_up": Control("Head massage increase", 0x800, "pulse"),
    "foot_massage_up": Control("Foot massage increase", 0x400, "pulse"),
    "timer": Control("Massage timer / all off", 0x200, "pulse"),
    "reset": Control("Reset", 0x08001000, "hold"),
}
_WAVE: Final = Control("Massage wave", 0x100, "single")
_EXTRA: Final = {
    "head_massage_down": Control("Head massage decrease", 0x800000, "pulse"),
    "foot_massage_down": Control("Foot massage decrease", 0x1000000, "pulse"),
    "light": Control("Toggle under-bed light", 0x20000, "single"),
    "reclined": Control("Reclined position", 0x2000, "hold"),
    "raised": Control("Raised position", 0x4000, "hold"),
    "wave": _WAVE,
}
CONTROLS: Final = {
    "b1": {
        **_COMMON,
        "wave": _WAVE,
        "massage_screen": Control("Massage screen", 0x4000, "hold"),
        "massage_contour": Control("Massage contour", 0x2000, "hold"),
    },
    "b2": {
        **_COMMON,
        **{
            f"wave_{n}": Control(f"Massage {n}-wave", word, "single")
            for n, word in ((1, 0x80000), (2, 0x100000), (3, 0x200000))
        },
    },
    "c1": {**_COMMON, **_EXTRA},
    "d1": {
        **_COMMON,
        **_EXTRA,
        "tilt_up": Control("Tilt up", 0x10, "hold"),
        "tilt_down": Control("Tilt down", 0x20, "hold"),
        "lumbar_up": Control("Lumbar up", 0x40, "hold"),
        "lumbar_down": Control("Lumbar down", 0x80, "hold"),
    },
}
PROFILES: Final = {
    key: KeesonProfile(
        key=f"dunlopillo_{key}",
        execution=STREAM_HOLD,
        fixed_write=True,
        no_response=True,
        hold=(10, REFRESH_MS),
        refresh_ms=REFRESH_MS,
        release=Release(guarded=True),
        presets={"flat": 0x08000000, "zero_g": 0x1000},
        massage="none",
        lights="toggle" if key in ("c1", "d1") else None,
        tilt=key == "d1",
        lumbar=key == "d1",
        keeson_motor_names=False,
        held_controls={
            name: (row.word, True)
            for name, row in controls.items()
            if row.mode == "hold" and name != "reset"
        },
    )
    for key, controls in CONTROLS.items()
}


def timer_minutes(data: bytes) -> int | None:
    """Unknown values leave the indicator unchanged; each callback is one record."""
    if len(data) not in (16, 19, 20):
        return None
    offset = 15 if len(data) == 19 and data[0] != 0xF1 else 14
    return {255: 0, 1: 10, 2: 20, 3: 30}.get(data[offset])


def trim_name(name: str) -> str:
    return name.strip("".join(map(chr, range(33))))


def rename(name: str) -> bytes:
    """Preserve the app's UTF-16-length copy from Android's UTF-8 bytes."""
    name = trim_name(name)
    units = len(name.encode("utf-16-le")) // 2
    return codec.rename(name.encode("utf-8")[:units])
