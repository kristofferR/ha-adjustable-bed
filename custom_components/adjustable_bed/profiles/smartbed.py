"""SmartBed 2.4.2's ten profiles over literal-proven existing wire encoders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Final, Literal

from ..codec import keeson, okin_nframe, okin_ore, okin_soundwave
from ..execution import STREAM_HOLD, ExecutionCapabilities

Protocol = Literal[1, 2, 3, 4, 5]


class Function(IntEnum):
    HEAD = 1
    FOOT = 2
    BOTH = 3
    TILT = 4
    LUMBAR = 5
    STOP = 6
    FLAT = 7
    ANTI_SNORE = 8
    LOUNGE = 9
    MEMORY_1 = 10
    ZERO_G = 11
    TV = 12
    ALARM = 13
    LIGHT = 14
    HEAD_MASSAGE = 15
    FOOT_MASSAGE = 16
    WAVE = 17
    MASSAGE = 18
    TIMER = 19
    INTENSITY = 20
    CLOCK = 21
    HIPS = 22
    MEMORY_2 = 23
    CONFIGURATION = 24
    SONIC_INTENSITY = 25
    MUSIC = 26
    SONIC_MODE = 27
    SONIC = 28
    SONIC_TIMER = 29
    SONIC_WAVE = 30
    VOLUME = 31


ARROW_RANGES: Final = {
    Function.HEAD_MASSAGE: (0, 3),
    Function.FOOT_MASSAGE: (0, 3),
    Function.WAVE: (1, 4),
}


PRESETS: Final = {
    "flat": Function.FLAT,
    "anti_snore": Function.ANTI_SNORE,
    "lounge": Function.LOUNGE,
    "memory_1": Function.MEMORY_1,
    "zero_g": Function.ZERO_G,
    "tv": Function.TV,
    "memory_2": Function.MEMORY_2,
}
SLOTS: Final = {7: 9, 8: 4, 9: 2, 10: 5, 11: 1, 12: 3, 23: 6}
WORDS: Final = {
    7: 0x08000000,
    8: 0x8000,
    9: 0x2000,
    10: 0x10000,
    11: 0x1000,
    12: 0x4000,
    23: 0x40000,
}
ALARM_TYPES: Final = {9: 8, 13: 1, 14: 2, 15: 3, 16: 4, 17: 5, 18: 7, 19: 6, 20: 5, 21: 9}
WAKE_ACTIONS: Final = {
    "zero_g": 13,
    "lounge": 14,
    "tv": 15,
    "anti_snore": 16,
    "memory_1": 20,
    "memory_2": 19,
    "light": 18,
    "massage": 9,
    "flat": 21,
}
# P4's alarm choices are distinct from the profile named Dacheng (which sends P2).
P4_WAKE_ACTIONS: Final = {"massage": 9, "zero_g": 13, "memory_1": 20}
NORDIC: Final = (
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
)
STANDARD: Final = tuple(
    f"0000{v}-0000-1000-8000-00805f9b34fb" for v in ("1000", "1001", "1000", "1002")
)
CB: Final = tuple(f"0000{v}-0000-1000-8000-00805f9b34fb" for v in ("ffe5", "ffe9", "ffe0", "ffe4"))


def byte(value: int) -> int:
    return value & 255


def signed(value: int) -> int:
    return value if value < 128 else value - 256


def bcd(value: int) -> int:
    return int(str(value), 16)


def packet(
    protocol: Protocol,
    function: int,
    subfunction: int = 0,
    data: bytes | None = None,
    *,
    side: int = 0,
    ab: bool = False,
    clock: tuple[int, ...] = (2026, 11, 19, 4, 7, 30, 15),
) -> bytes:
    """App dispatch and transforms; every envelope is built by a shared codec.

    Empty output is an unsupported source action, never a GATT write. Numeric
    inputs retain Java byte casts for the frozen builder comparison.
    """
    p, f, s = protocol, function, subfunction
    if p == 1:
        op, payload = 0x2000, data or b""
        if f in (1, 2, 3, 4, 5):
            op = {1: 0x2001, 2: 0x2003, 3: 0x200B, 4: 0x2005, 5: 0x2007}[f] + (s != 1)
        elif f in (6, 7, 8, 9, 10, 11, 12, 14):
            op = {
                6: 0x2000,
                7: 0x2066,
                8: 0x2063,
                9: 0x2061,
                10: 0x2064,
                11: 0x2060,
                12: 0x2062,
                14: 0x2080,
            }[f]
        elif f in (15, 16, 17, 20):
            if s in (8, 9):
                op = {15: 0x2020, 16: 0x2030, 17: 0x2070, 20: 0x2096}[f] + (s == 9)
            elif s in ((10, 11, 12, 13) if f == 17 else (10, 11, 12)):
                op, payload = {15: 0x2084, 16: 0x2085, 17: 0x2083, 20: 0x2086}[f], bytes((s - 9,))
        elif f == 18:
            if s in (3, 4):
                op, payload = 0x2081, bytes((s == 3,))
            elif s == 5:
                op = 0x2050
        elif f == 19:
            if s in (10, 11, 12):
                op, payload = 0x2082, bytes((10 * (s - 9),))
        else:
            return b""
        return okin_ore.frame(op, payload)

    nside = {1: 0xAA, 2: 0xBB}.get(side, side) if ab else 0

    def normal(mask: int, extra: int = 0) -> bytes:
        return (
            keeson.frame(mask, header=0xE6, side=byte(extra))
            if p == 2
            else okin_nframe.frame40(mask, byte(side if p == 4 else nside))
        )

    def new(
        domain: int,
        operation: int,
        fields: tuple[int, ...] = (),
        *,
        query: bool = False,
        size: int | None = None,
    ) -> bytes:
        return okin_soundwave.record(
            domain, operation, tuple(byte(v) for v in fields), query=query, size=size
        )

    if f in (1, 2, 3, 4, 5, 22):
        if f == 22 and p == 2:
            return b""
        up, down = {
            1: (1, 2),
            2: (4, 8),
            3: (5, 10),
            4: (16, 32),
            5: (64, 128),
            22: (0x40000000, 0x80000000) if p == 4 else (256, 512),
        }[f]
        mask = up if s == 1 else down
        return new(1, 1, tuple(mask.to_bytes(4, "little")), query=True) if p == 5 else normal(mask)
    if f == 6:
        return new(1, 2) if p == 5 else normal(0)
    if f in WORDS:
        if p == 2 and f == 23:
            return b""
        if p == 5:
            save = s == 7 and f != 7
            return new(1, 5 if save else 3, (SLOTS[f] + (32 if save else 0),), query=not save)
        return normal(WORDS[f])
    if f == 13:
        if s not in (3, 4):
            return (
                keeson.ALARM_QUERY
                if p == 2
                else new(3, 0x81, (1,), query=True)
                if p == 5
                else okin_nframe.request(0xC0)
            )
        hour, minute, repeat, kind = (
            tuple(signed(v) for v in (data or b"")[:4]) if s == 3 else (0, 0, 0, 0)
        )
        if p == 2:
            return keeson.alarm_table(3, bytes(byte(v) for v in (hour, minute, repeat, kind)))
        if p == 5:
            return new(
                3,
                2,
                (
                    1,
                    0 if repeat == -128 else repeat,
                    ALARM_TYPES.get(kind, 0),
                    int(repeat != 0),
                    hour,
                    minute,
                    0,
                ),
            )
        if p == 3:
            return okin_nframe.alarm(
                tuple(
                    byte(v)
                    for v in (
                        0 if repeat == -128 else repeat,
                        ALARM_TYPES.get(kind, 0),
                        hour,
                        minute,
                        0,
                        int(any((hour, minute, repeat, kind))),
                        nside if ab else side,
                    )
                )
            )
        return okin_nframe.alarm(
            tuple(
                byte(v)
                for v in (
                    repeat,
                    bcd({9: 1, 13: 2, 20: 3}.get(kind, 0)),
                    bcd(hour),
                    bcd(minute),
                    0,
                    int(any((hour, minute, repeat, kind))),
                    bcd(side),
                )
            )
        )
    if f == 14:
        if p != 5:
            return normal(0x20000)
        if s == 5:
            return new(4, 0x81, query=True)
        if s == 6:
            if data is None or len(data) < 2:
                return b""
            return new(4, 1, (*(data + bytes(6))[:5], 255), size=5)
        return new(4, 1, (0, int(s == 3), 0, 0, 0, 0), size=5)
    if f in (15, 16, 17, 19, 20):
        plus = {15: 0x800, 16: 0x400, 17: 0x10000000, 19: 0x200, 20: 0xC00}
        minus = {15: 0x800000, 16: 0x1000000, 17: 0x4000000, 19: 0x100000, 20: 0x1800000}
        levels = {10: 0x80000, 11: 0x100000, 12: 0x200000}
        if p == 5:
            if s in (8, 9):
                return normal(plus[f] if s == 8 else minus[f])
            if f in (15, 16) and s == 4:
                return new(2, 1, (83 if f == 15 else 87,), query=True)
            if s in (10, 11, 12) or f == 17 and s == 13:
                if f == 20:
                    return normal(levels[s])
                return new(2, 1, ({15: 80, 16: 84, 17: 66, 19: 73}[f] + s - 10,), query=True)
            return normal(0)
        if p == 2:
            if f in (15, 16, 20):
                return normal(plus[f] if s == 8 else minus[f] if s == 9 else levels.get(s, 0))
            if f == 17:
                return normal(
                    plus[f] if s in (8, 10, 11, 12) else minus[f] if s == 9 else 0,
                    {10: 64, 11: 128, 12: 192}.get(s, 0),
                )
            return normal(0x200 if s in (10, 11, 12) else 0, {10: 64, 11: 128, 12: 192}.get(s, 0))
        if s in (8, 9):
            return normal(plus[f] if s == 8 else minus[f])
        if f == 20:
            return normal(levels.get(s, 0))
        if s in (10, 11, 12) or f == 17 and s == 13:
            return okin_nframe.parameter_record(
                3, ({15: 2, 16: 3, 17: 4, 19: 1}[f], s - 9, byte(side if p == 4 else nside))
            )
        return normal(0)
    if f == 18:
        if p == 2:
            return normal(3 if s == 5 else 256)
        if p == 5:
            return (
                new(2, 0x81, (255,), query=True)
                if s == 5
                else new(2, 1, (64 if s == 3 else 65,), query=True)
            )
        return okin_nframe.request(0xB0) if s == 5 else normal(256)
    if f == 21:
        year, month, day, dow, hour, minute, second = clock
        if p == 2:
            return keeson.clock_fields(
                tuple(byte(v) for v in (year - 1900, month - 1, day, hour, minute, second))
            )
        fields = (year - 2000, month, day, dow, hour, minute, second)
        if p == 5:
            return new(3, 1, fields)
        return okin_nframe.clock(tuple(byte(bcd(v) if p == 4 else v) for v in fields))
    if p != 5:
        return b""
    if f == 24:
        page = signed((data or b"\0")[0])
        return new(5, 0x81, (1 << max(0, min(page, 7)), 255, 255, 0, 0, 34, 37, 18, 75), query=True)
    if f in (25, 26, 30, 31):
        size = 2 if f == 25 else 1
        if data is None or len(data) != size:
            return b""
        return new(6, {25: 2, 26: 10, 30: 3, 31: 4}[f], ((0, 3) if f == 25 else (0,)) + tuple(data))
    if f == 27:
        return new(6, 5, (0, data[0] if data else 0)) if s == 6 else b""
    if f == 28:
        return new(6, 12, (0, int(s == 3))) if s in (3, 4) else new(6, 0x81, query=True)
    if f == 29:
        seconds = {10: 600, 11: 1200, 12: 1800}.get(s, 0)
        low, high = seconds & 255, seconds >> 8
        return new(6, 11, (0, 255, low, high, low, high), size=2)
    return b""


@dataclass(frozen=True, slots=True)
class SmartBedProfile:
    key: str
    base_protocol: Protocol
    transport: tuple[str, ...] = NORDIC
    refresh_ms: int = 300
    release_ms: int = 100
    save_ms: int = 5200
    preset_names: tuple[str, ...] = tuple(PRESETS)
    has_light: bool = True
    has_massage: bool = True
    massage_timer: bool = True
    wave_max: int = 4
    execution: ExecutionCapabilities = STREAM_HOLD

    def protocol(self, motors: int) -> Protocol:
        return 4 if self.key == "cb24" and motors == 5 else self.base_protocol

    def encode(
        self,
        function: int,
        subfunction: int = 0,
        data: bytes | None = None,
        *,
        motors: int = 2,
        side: int = 0,
        now: datetime | None = None,
    ) -> bytes:
        fields = (
            (now.year, now.month, now.day, now.isoweekday() % 7, now.hour, now.minute, now.second)
            if now
            else (2026, 11, 19, 4, 7, 30, 15)
        )
        return packet(
            self.protocol(motors),
            function,
            subfunction,
            data,
            side=side,
            ab=self.key == "cb24_ab",
            clock=fields,
        )


PROFILES: Final = {
    "standard": SmartBedProfile(
        "standard", 1, STANDARD, preset_names=tuple(n for n in PRESETS if n != "memory_2")
    ),
    "dacheng": SmartBedProfile(
        "dacheng", 2, preset_names=tuple(n for n in PRESETS if n != "memory_2")
    ),
    "cb24": SmartBedProfile("cb24", 3),
    "cb27": SmartBedProfile("cb27", 3),
    "cb24_ab": SmartBedProfile("cb24_ab", 3),
    "cb1221": SmartBedProfile("cb1221", 3),
    "cb27new": SmartBedProfile("cb27new", 5),
    "headboard126": SmartBedProfile(
        "headboard126",
        3,
        preset_names=("flat", "memory_1", "memory_2"),
        has_light=False,
        has_massage=False,
        massage_timer=False,
    ),
    "headboard265": SmartBedProfile(
        "headboard265",
        3,
        preset_names=("flat", "memory_1", "memory_2"),
        has_light=False,
        massage_timer=False,
        wave_max=2,
    ),
    "cb": SmartBedProfile("cb", 2, CB, preset_names=tuple(n for n in PRESETS if n != "memory_2")),
}
