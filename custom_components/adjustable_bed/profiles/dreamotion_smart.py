"""Dreamotion Smart 1.1.8 (com.sendinfo.dreammotionpro), verified local P1.

All 35 frozen builder literals matched Jiecang's frame encoder before reuse.
These settings belong only to this app, independently of the other Dream apps.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal

from ..codec import jiecang as codec
from ..execution import STREAM_HOLD
from .jiecang import Hold, JiecangProfile, Tap

SERVICE: Final = "6e40fe60-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e40fe61-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e40fe62-b5a3-f393-e0a9-e50e24dcca9e"
AXES: Final = ("head", "back", "lumbar", "legs")
DURATIONS: Final = (0, 60, 120, 180, 240, 300, 600, 900, 1200, 1500, 1800)
PROFILE: Final = JiecangProfile(
    key="dreamotion_smart",
    execution=STREAM_HOLD,
    layouts={},
    transports=(),
    hold=Hold(repeat_ms=300, releases=((300, codec.LONG_RELEASE),)),
    recall=Tap(),
    memory_save=Tap(),
    memory_slots=2,
    memory_payload=codec.BILATERAL,
    massage_levels=(0, 1, 2, 3),
)


def query(opcode: int) -> bytes:
    size = {0: 2, 0x40: 2, 0x43: 2, 0x80: 2, 0x81: 5, 0x45: 7, 0x44: 13}[opcode]
    return codec.frame(opcode, b"\x00\x00" if opcode == 0 else bytes((0xA2,)) + bytes(size - 1))


MAIN_QUERIES: Final = tuple(
    (offset, query(op)) for offset, op in ((300, 0x43), (600, 0x40), (900, 0x80), (1200, 0x81))
)
MASSAGE_QUERIES: Final = ((0, query(0x80)), (250, query(0x81)))


def setting(opcode: int, value: int) -> bytes:
    return codec.frame(opcode, bytes((0xA1, value)))


@dataclass(frozen=True)
class Massage:
    back: int = 0
    foot: int = 0
    pattern: int = 0
    duration: int = 0
    hz: int = 0

    def frame(self) -> bytes:
        return codec.frame(0x81, bytes((0xA1, self.back, self.foot, self.pattern, self.duration)))

    def cycle(self, action: str) -> tuple[Massage, Massage | None]:
        """Return local state and the wire state, preserving notify-only fields."""
        state = self
        if action in ("back", "foot", "pattern"):
            value = getattr(self, action)
            if value not in range(4):
                return self, None
            if action == "pattern" and self.back == self.foot == 0:
                state = replace(state, back=1, foot=1)
            if value == 0 and self.hz != 0 and self.duration == 0:
                state = replace(state, duration=3)
            next_value = (value + 1) % 4 if action != "pattern" else (value % 3) + 1
            return state, replace(state, **{action: next_value})
        value = {"timer10": 1, "timer20": 2, "timer30": 3}[action]
        state = replace(state, duration=0 if self.duration == value else value)
        return state, state


@dataclass(frozen=True)
class Color:
    brightness: int
    red: int
    green: int
    blue: int

    def payload(self) -> bytes:
        if not 0 <= self.brightness <= 100:
            raise ValueError("Brightness must be 0–100 percent")
        return bytes((self.brightness, self.red, self.green, self.blue))


def timed(color: Color, seconds: int) -> bytes:
    if not 0 <= seconds <= 65535:
        raise ValueError("Choose a supported light duration")
    return codec.frame(0x45, b"\xa1" + color.payload() + seconds.to_bytes(2, "big"))


def slots(colors: tuple[Color, Color, Color]) -> bytes:
    return codec.frame(0x44, b"\xa1" + b"".join(c.payload() for c in colors))


def preview(color: Color) -> bytes:
    return codec.frame(0x4C, b"\xa1" + color.payload())


def destinations(address: str, origin: Literal["main", "control"]) -> tuple[str, ...]:
    """The app's Main query train only targets the first selected address."""
    return tuple(address.split("#")[: 1 if origin == "main" else 2])
