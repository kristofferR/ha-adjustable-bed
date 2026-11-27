"""PowersBedding 1.1.0 (2), independently frozen command and UI semantics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from ..codec import keeson as codec
from ..codec import okin_nframe
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Preset, Release, encode

AXES: Final = {"head": (1, 2), "feet": (4, 8), "both": (5, 10)}
PRESETS: Final[dict[Preset, int]] = {"zero_g": 0x1000, "flat": 0x08000000}
MEMORY: Final = {1: 0x10000, 2: 0x40000}
P1_PRESETS: Final[dict[Preset, int]] = {"zero_g": 0x01000001, "flat": 0x01000002}
P1_MEMORY: Final = {1: 0x01000008, 2: 0x01000009}
LEVELS: Final = {"head": 0x10000010, "foot": 0x11000010, "wave": 0x10000020}
STEPS: Final = {
    "toggle": 0x100,
    "head_up": 0x800,
    "head_down": 0x800000,
    "foot_up": 0x400,
    "foot_down": 0x1000000,
    "wave": 0x10000000,
    "timer": 0x200,
}
WAKE: Final = ("none", "memory_1", "memory_2", "massage")
REFRESH_MS: Final = 100
SAVE_MS: Final = 6000
PROFILES: Final = {
    route: KeesonProfile(
        key=f"powersbedding_{route}",
        hold=None,
        refresh_ms=100,
        execution=STREAM_HOLD,
        carrier="p2_side" if route == "p3" else "k1",
        header=0xE6 if route == "p2" else 0xE5,
        order="big" if route == "p1" else "little",
        side=0 if route == "p2" else None,
        release=Release(steps=((0, 0), (100, 0))),
        presets=P1_PRESETS if route == "p1" else PRESETS,
        memory=P1_MEMORY if route == "p1" else MEMORY,
        memory_slots=2,
        lights="discrete" if route == "p1" else "toggle",
        massage="none",
        tilt=False,
        lumbar=False,
        keeson_motor_names=False,
    )
    for route in ("p1", "p2", "p3")
}


def normal(route: str, word: int) -> bytes:
    return encode(PROFILES[route], word & 0xFFFFFFFF)


def clock(route: str, now: datetime) -> bytes:
    if route == "p1":
        return codec.weekday_clock((now.second, now.minute, now.hour, now.isoweekday() % 7))
    if route == "p2":
        return codec.clock(now)
    return okin_nframe.clock(
        (
            (now.year - 2000) & 255,
            now.month,
            now.day,
            now.isoweekday() % 7,
            now.hour,
            now.minute,
            now.second,
        )
    )


def alarm_fields(
    route: str, hour: int, minute: int, week: int, massage: int, mode: int, now: datetime
) -> bytes:
    if route == "p1":
        return codec.bedding_alarm(
            (
                now.second,
                now.minute,
                now.hour,
                minute,
                hour,
                now.isoweekday() % 7,
                week & 255,
                17,
                massage & 17,
                (mode + 240) & 255,
            )
        )
    if route == "p2":
        return codec.alarm_table(3, bytes((hour, minute, week & 255, mode)))
    return okin_nframe.alarm(
        (
            0 if week == -128 else week & 255,
            mode,
            hour,
            minute,
            0,
            int(any((hour, minute, week, mode))),
            0,
        )
    )


def cancel(route: str, now: datetime) -> bytes:
    if route == "p1":
        return codec.bedding_alarm((now.second, now.minute, now.hour, *([255] * 6), 24))
    return alarm_fields(route, 0, 0, 0, 0, 0, now)


def week_mask(selected: Sequence[int], now: datetime, hour: int, minute: int) -> int:
    """Sunday-zero days; HA's Monday-zero conversion is the caller's responsibility."""
    if len(selected) == 7:
        return -1
    if set(selected) == set(range(1, 6)):
        return -66
    if not selected:
        day = now.isoweekday() % 7
        if (hour, minute) <= (now.hour, now.minute):
            day = (day + 1) % 7
        return 1 << day
    return -128 + sum(1 << day for day in selected)


def wake_mode(route: str, wake: str, massage: bool) -> tuple[int, int]:
    if route == "p1":
        return (
            17 if massage or wake == "massage" else 0,
            {"memory_1": 8, "memory_2": 9}.get(wake, 15),
        )
    return (
        0,
        (
            {"memory_1": 17, "memory_2": 19, "massage": 9}
            if route == "p2"
            else {"memory_1": 5, "memory_2": 6, "massage": 8}
        ).get(wake, 0),
    )


def alarm_query(route: str) -> bytes | None:
    return (
        None
        if route == "p1"
        else codec.checked(bytes.fromhex("e18003"))
        if route == "p2"
        else okin_nframe.request(0xC0)
    )


def signed(value: int) -> int:
    return value if value < 128 else value - 256


@dataclass(frozen=True, slots=True)
class Massage:
    arc: int
    wave: int
    head: int
    foot: int


def parse_massage(route: str, data: bytes) -> Massage | None:
    if route == "p2" and len(data) == 16:
        return Massage(
            min(data[14] & 15, 4),
            signed(data[14]) >> 4,
            ((data[7] & 15) + 1) // 2,
            ((data[8] & 15) + 1) // 2,
        )
    if route == "p3" and len(data) >= 9:
        timer = signed(data[4])
        return Massage(
            3 if timer > 4 else 2 if timer > 2 else 1 if timer > 0 else 0,
            signed(data[6]),
            int((signed(data[7]) + 1) / 2),
            int((signed(data[8]) + 1) / 2),
        )
    return None


@dataclass(frozen=True, slots=True)
class Alarm:
    hour: int
    minute: int
    week: int
    enabled: bool
    massage: bool
    memory_a: bool
    memory_b: bool


def is_alarm(route: str, data: bytes) -> bool:
    return (
        route == "p1"
        and len(data) >= 10
        or route == "p2"
        and data[:3] == b"\xed\x80\x03"
        or route == "p3"
        and data[:2] == b"\xa5\x0c"
    )


def parse_alarm(route: str, data: bytes, previous: Alarm | None = None) -> Alarm | None:
    """Bound unsafe app indexing; retain its raw time domain and mode-selection quirks."""
    if route == "p1":
        if len(data) < 10:
            return None
        minute, hour = (0 if data[i] == 255 else signed(data[i]) for i in (3, 4))
        if not 0 <= hour <= 24 or not 0 <= minute <= 60:
            return None
        week = 0 if data[6] == 255 else data[6]
        return Alarm(
            hour, minute, week, bool(week), data[7:9] == b"\x11\x11", data[9] == 248, data[9] == 249
        )
    if route == "p2" and len(data) >= 7:
        h, m, w, mode = data[3:7]
        return Alarm(
            h,
            m,
            w,
            any((h, m, w)),
            mode == 9 or bool(previous and previous.massage),
            mode == 17 or bool(previous and previous.memory_a),
            mode == 19 or bool(previous and previous.memory_b),
        )
    if route == "p3" and len(data) >= 10:
        return Alarm(
            data[6], data[7], data[4], bool(data[9]), data[5] == 8, data[5] == 5, data[5] == 6
        )
    return None
