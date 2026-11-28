"""Dynasty Base A 1.0: independent layouts and service-selected Keeson carriers."""

from typing import Final

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, encode

LAYOUTS: Final = {
    "20": ("head", "feet"),
    "30": ("head", "feet", "tilt"),
    "31": ("head", "feet", "lumbar"),
    "40": ("head", "feet", "tilt", "lumbar"),
}
CHOICES: Final = {
    "20": "Back and legs",
    "30": "Back, legs and headrest",
    "31": "Back, legs and waist",
    "40": "Back, legs, headrest and waist",
}
AXES: Final = {"head": (1, 2), "feet": (4, 8), "tilt": (16, 32), "lumbar": (64, 128)}
REFRESH_MS: Final = 100
PRESET_HOLD_MAX_MS: Final = 8000
ALARM_DELAY_S: Final = 0.1
LIGHT: Final = 0x20000
CHORD: Final = 0x08001000
WAKE: Final = {"none": 0, "memory_1": 17, "memory_2": 19, "massage": 9}
NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
PROFILES: Final = {
    route: KeesonProfile(
        key=f"dynasty_base_a_{route}",
        execution=STREAM_HOLD,
        carrier="k1" if route == "p1" else "p2",
        header=0xE6,
        side=0,
        transport="base" if route == "p1" else "dynasty_p2",
        notify="base" if route == "p1" else "dynasty_p2",
        fixed_write=True,
        hold=(10, REFRESH_MS),
        refresh_ms=REFRESH_MS,
        presets={
            "flat": 0x08000000,
            "zero_g": 0x1000,
            "tv": 0x4000,
            "lounge": 0x2000 if route == "p1" else 0x8000,
            "anti_snore": 0x8000 if route == "p1" else 0x2000,
        },
        memory={1: 0x10000, 2: 0x40000},
        memory_slots=2,
        massage="none",
    )
    for route in ("p1", "p2")
}


def actions(route: str) -> dict[str, int]:
    return {
        "head_massage": 0x800,
        "foot_massage": 0x400 if route == "p1" else 0x1000000,
        "massage_power": 0x100 if route == "p1" else 0x200000,
        "massage_timer": 0x200,
        "massage_type": 0x10000000 if route == "p1" else 0x4000000,
    }


def controls(route: str, layout: str) -> dict[str, int]:
    profile = PROFILES[route]
    return {
        **{
            f"{axis}_{direction}": word
            for axis in LAYOUTS[layout]
            for direction, word in zip(("up", "down"), AXES[axis], strict=True)
        },
        **profile.presets,
        **{f"memory_{n}": word for n, word in profile.memory.items()},
        "flat_zero_g": CHORD,
    }


def frame(route: str, word: int) -> bytes:
    return encode(PROFILES[route], word)


def alarm(hour: int, minute: int, days: int, mode: int) -> bytes:
    return codec.alarm_table(3, bytes((hour, minute, days, mode)))


class Receiver:
    """The app's ordered fragment dispatch, including its retained prefix cache."""

    def __init__(self) -> None:
        self.prefix: bytes | None = None

    def receive(self, route: str, data: bytes) -> bytes | None:
        if route == "p2" or len(data) > 20:
            return data
        if len(data) <= 3:
            return self.prefix + data if self.prefix is not None else None
        if data.startswith(b"\xf4\xfe\x16"):
            self.prefix = data
            return None
        if len(data) in (10, 16):
            return data
        return self.prefix + data if self.prefix is not None else None


def status(route: str, data: bytes) -> tuple[int, bool | None, bool | None] | None:
    """Timer minutes, proven light flag and P2 massage branch state only."""
    if route == "p2":
        if len(data) <= 10:
            return None
        return {1: 10, 2: 20, 3: 30}.get(data[10] & 15, 0), None, data[10] != 255
    timer, light = {23: (19, 18), 16: (14, 13), 10: (8, 7)}.get(len(data), (-1, -1))
    if timer == -1:
        return None
    signed_light = data[light] if data[light] < 128 else data[light] - 256
    return {1: 10, 2: 20, 3: 30}.get(data[timer] & 15, 0), signed_light >> 6 > 0, None
