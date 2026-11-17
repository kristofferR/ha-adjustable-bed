"""ORE Ultramatic 1.0.5(9), row158, over the literal-proven Keeson codec.

P1/P2 are selected from live FFF0 presence, never from an advertisement or name.
Timing, keys and alarm choices below belong only to this accepted app.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Final, Literal

from ..codec import keeson as codec
from .keeson import ORE_ULTRAMATIC, KeesonProfile

Route = Literal["P1", "P2"]
SELECTOR: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
REFRESH_MS: Final = 100
SINGLE_MS: Final = 100
QUERY_MS: Final = 200
P2_PRESETS: Final = {"tv": 0x4000, "anti_snore": 0x8000, "zero_g": 0x1000, "flat": 0x8000000}
P2_MASSAGE: Final = {
    "head": 0x800,
    "foot": 0x400,
    "timer": 0x200,
    "toggle": 0x100,
    "wave": 0x10000000,
}
LIGHT_TOGGLE: Final = 0x20000
P1_RECALL: Final = {
    "memory_1": 0x01000008,
    "memory_2": 0x01000009,
    "zero_g": 0x01000001,
    "flat": 0x01000002,
}
P1_SAVE: Final = {name: word + 0x1F000000 for name, word in P1_RECALL.items()}


def profile(route: Route) -> KeesonProfile:
    return (
        ORE_ULTRAMATIC
        if route == "P1"
        else replace(ORE_ULTRAMATIC, header=0xE6, order="little", side=0)
    )


def query(route: Route, now: datetime) -> bytes:
    return (
        codec.checked(
            bytes((0xE2, 0xFE, 0x16, now.second, now.minute, now.hour, now.isoweekday() % 7))
        )
        if route == "P1"
        else codec.ALARM_QUERY
    )


def alarm(
    route: Route, now: datetime, *, enabled: bool, hour: int, minute: int, repeat: int, kind: int
) -> bytes:
    if (
        not 0 <= hour <= 23
        or not 0 <= minute <= 59
        or not -128 <= repeat <= 255
        or kind not in range(4)
    ):
        raise ValueError("Choose hour0..23, minute0..59, repeat-128..255 and alarm type0..3")
    if repeat in (0, 128):
        repeat = 1 << ((now.isoweekday() % 7 + int((hour, minute) < (now.hour, now.minute))) % 7)
    if route == "P1":
        return codec.checked(
            bytes(
                (
                    0xEB,
                    0xFE,
                    0x16,
                    now.second,
                    now.minute,
                    now.hour,
                    minute if enabled else 255,
                    hour if enabled else 255,
                    now.isoweekday() % 7,
                    repeat & 255 if enabled else 255,
                    17 if enabled and kind == 1 else 255,
                    17 if enabled and kind == 1 else 255,
                    {2: 8, 3: 9}.get(kind, 255) if enabled else 255,
                )
            )
        )
    record = (
        bytes((hour, minute, repeat & 255, {1: 9, 3: 13}.get(kind, 15))) if enabled else bytes(4)
    )
    return codec.alarm_table(3, record)
