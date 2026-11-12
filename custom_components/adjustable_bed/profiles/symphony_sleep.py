"""Symphony Sleep 1.1.0 (14), row078: independent UI models and BLE routes.

The normal literals reproduce Keeson K1/P2 and Okin frame40. Alarm and clock
fields below belong to this app, including P2's Sunday-zero weekday.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from ..codec import keeson as codec
from ..codec import okin_nframe
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Preset, Release, encode


@dataclass(frozen=True, slots=True)
class Model:
    label: str
    axes: tuple[str, ...]
    accessories: bool = True


MODELS: Final = {
    "400E": Model("400E, Premier Series 400", ("head", "feet", "bed_height"), False),
    "500E": Model("500E, Premier Series 500", ("head", "feet", "both", "bed_height")),
    "600E": Model("600E, Premier Series 600", ("head", "feet", "tilt", "bed_height")),
    "SS300": Model("SS300, Superior Sleep 300", ("head", "feet", "both", "bed_height")),
    "SS600": Model("SS600, Superior Sleep 600", ("head", "feet", "lumbar", "bed_height")),
}
TRANSPORT_CHOICES: Final = {
    "box1": "Box 1: P1, FFE9 / FFE4",
    "box2": "Box 2: P2, Nordic UART",
    "fallback": "Unrecognized selector: P1 output, notifications ignored",
}
AXES: Final[dict[str, tuple[str, int, int]]] = {
    "head": ("head", 1, 2), "feet": ("feet", 4, 8), "both": ("both", 5, 10),
    "tilt": ("neck", 16, 32), "lumbar": ("lumbar", 16, 32),
    "bed_height": ("bed_height", 64, 128),
}
PRESETS: Final[dict[Preset, int]] = {"flat": 0x08000000, "zero_g": 0x1000, "anti_snore": 0x8000}
MEMORY: Final = {1: 0x2000, 2: 0x4000}
MASSAGE: Final = {
    "massage_wave_next": 0x10000000, "massage_wave_previous": 0x04000000,
    "massage_intensity_up": 0xC00, "massage_intensity_down": 0x01800000,
    "massage_off": 0x02000000, "massage_timer": 0x200,
}
LIGHT: Final = 0x20000
HELD: Final = {
    **{f"{axis}_{direction}": values[i + 1] for axis, values in AXES.items()
       for i, direction in enumerate(("up", "down"))},
    **PRESETS, "memory_1": MEMORY[1], "memory_2": MEMORY[2], "light_toggle": LIGHT,
    **MASSAGE,
}
WAKE: Final = {"none": 0, "memory_1": 0x11, "memory_2": 0x13}
REFRESH_MS: Final = 300
SAVE_MS: Final = 5200  # App-local success timer, never a hardware acknowledgement.
PROFILES: Final = {
    route: KeesonProfile(
        key=f"symphony_sleep_{route}", carrier="p2_side" if route == "box2" else "k1",
        header=0xE6, side=None if route == "box2" else 0,
        transport="ksbt" if route == "box2" else "base", fixed_write=True,
        hold=None, refresh_ms=REFRESH_MS, execution=STREAM_HOLD,
        release=Release(steps=((0, 0), (300, 0), (300, 0)), after_tap=True),
        presets=PRESETS, memory=MEMORY, memory_slots=2,
        lights="toggle", massage="step", massage_off=MASSAGE["massage_off"],
        tilt=False, lumbar=False, keeson_motor_names=False,
    ) for route in TRANSPORT_CHOICES
}


def normal(route: str, word: int) -> bytes:
    return encode(PROFILES[route], word)


def bcd(value: int) -> int:
    """The app's decimal-string to hex-byte conversion, including byte truncation."""
    return int(str(value), 16) & 255


def clock(route: str, now: datetime) -> bytes:
    if route != "box2":
        return codec.clock(now)
    return okin_nframe.clock(tuple(map(bcd, (
        now.year - 2000, now.month, now.day, (now.weekday() + 1) % 7,
        now.hour, now.minute, now.second,
    ))))


def alarm(route: str, *, enabled: bool, hour: int, minute: int, wake: str) -> bytes:
    if type(enabled) is not bool or type(hour) is not int or type(minute) is not int:
        raise ValueError("Alarm enabled, hour and minute must be boolean/integer values")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or wake not in WAKE:
        raise ValueError("Choose an hour 0–23, minute 0–59 and none, memory_1 or memory_2")
    fields = (hour, minute, 255, WAKE[wake]) if enabled else (0, 0, 0, 0)
    if route != "box2":
        return codec.alarm_table(3, bytes(fields))
    h, m, day, w = fields
    return okin_nframe.alarm((day, {0x11: 2, 0x13: 3}.get(w, 0), bcd(h), bcd(m), 0, int(enabled), 0))


def alarm_query(route: str) -> bytes:
    return okin_nframe.request(0xC0) if route == "box2" else codec.ALARM_QUERY


def validate_alarm(*, weekdays: Sequence[int], head_level: int, foot_level: int) -> None:
    if weekdays or head_level or foot_level:
        raise ValueError("Symphony Sleep has one daily alarm and no alarm massage levels")
