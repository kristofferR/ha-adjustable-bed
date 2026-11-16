"""Nerum 1.0.8 (12): three independently proven carriers, no inferred firmware.

All literals are checked against the accepted row103 builder corpus. Dormant
builder branches remain encodable for that contract but are never HA actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from ..codec import keeson, okin_nframe, okin_ore
from ..execution import STREAM_HOLD, ExecutionCapabilities

Protocol = Literal["p1", "p2", "p3"]
PROTOCOLS: Final[tuple[Protocol, ...]] = ("p1", "p2", "p3")
AXES: Final = {"back": 1, "legs": 2, "both": 3, "head": 4, "lumbar": 5}
LAYOUTS: Final = {
    "nerum": ("back", "legs"),
    "2": ("back", "legs", "both"),
    "3": ("back", "legs", "both", "head"),
    "4": ("back", "legs", "both", "head", "lumbar"),
}
PRESETS: Final = {
    "flat": 7,
    "anti_snore": 8,
    "lounge": 9,
    "memory_1": 10,
    "zero_g": 11,
    "tv": 12,
    "memory_2": 22,
}
WAKE: Final = {"none": 0, "memory_1": 17, "memory_2": 19, "light": 18}
WAKE_CODES: Final = {17: 5, 19: 6, 18: 7, 9: 8}


@dataclass(frozen=True, slots=True)
class NerumProfile:
    key: Protocol
    service: str
    write: str
    notify_service: str
    notify: str
    refresh_ms: int = 300
    release_ms: tuple[int, ...] = (300, 600)
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def frames(self) -> dict[str, bytes]:
        return {
            **{
                f"{axis}_{direction}": build(self.key, index, 1 if direction == "up" else 2)
                for axis, index in AXES.items()
                for direction in ("up", "down")
            },
            **{
                name: build(self.key, index)
                for name, index in PRESETS.items()
                if self.key != "p1" or name != "memory_2"
            },
            "stop": build(self.key, 6),
            "light": build(self.key, 14),
        }


PROFILES: Final = {
    "p1": NerumProfile(
        "p1",
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001001-0000-1000-8000-00805f9b34fb",
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001002-0000-1000-8000-00805f9b34fb",
    ),
    "p2": NerumProfile(
        "p2",
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    "p3": NerumProfile(
        "p3",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
}


def clock(protocol: Protocol, now: datetime) -> bytes:
    if protocol == "p1":
        return b""
    if protocol == "p2":
        return keeson.clock(now)
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


def build(
    protocol: Protocol,
    function: int,
    subfunction: int = 0,
    payload: bytes | None = None,
    *,
    now: datetime | None = None,
) -> bytes:
    """Accepted builder grammar, encoded exclusively by existing production codecs."""
    if function == 21:
        return clock(protocol, now or datetime.now())
    if function == 13:
        if protocol == "p1":
            return b""
        if subfunction not in (3, 4):
            return query(
                protocol,
                payload[0] + 1 if protocol == "p3" and payload and payload[0] in (0, 1, 2) else 1,
            )
        if subfunction == 3 and (payload is None or len(payload) < 4):
            raise ValueError("Factory alarm requires four bytes")
        hour, minute, repeat, kind = payload[:4] if subfunction == 3 and payload else bytes(4)
        if protocol == "p2":
            return keeson.alarm_table(3, bytes((hour, minute, repeat, kind)))
        return okin_nframe.alarm(
            (
                0 if repeat == 128 else repeat,
                WAKE_CODES.get(kind, 0),
                hour,
                minute,
                0,
                int(any((hour, minute, repeat, kind))),
                0,
            )
        )
    if protocol == "p1":
        if not 1 <= function <= 20:
            return b""
        opcode = 0x2000
        data = payload or b""
        if function <= 5:
            opcode = (0x2001, 0x2003, 0x200B, 0x2005, 0x2007)[function - 1] + (subfunction != 1)
        elif 7 <= function <= 12:
            opcode = (0x2066, 0x2063, 0x2061, 0x2064, 0x2060, 0x2062)[function - 7]
        elif function == 14:
            opcode = 0x2080
        elif function in (15, 16, 17, 20):
            if subfunction in (8, 9):
                opcode = {15: 0x2020, 16: 0x2030, 17: 0x2070, 20: 0x2096}[function] + (
                    subfunction == 9
                )
            elif subfunction in (10, 11, 12):
                opcode = {15: 0x2084, 16: 0x2085, 17: 0x2083, 20: 0x2086}[function]
                data = bytes((subfunction - 9,))
        elif function == 18:
            if subfunction in (3, 4):
                opcode, data = 0x2081, bytes((int(subfunction == 3),))
            elif subfunction == 5:
                opcode = 0x2050
        elif function == 19 and subfunction in (10, 11, 12):
            opcode, data = 0x2082, bytes(((subfunction - 9) * 10,))
        return okin_ore.frame(opcode, data)
    word = parameter = 0
    if function <= 0 or function > 22:
        return b""
    if function <= 5:
        word = (1, 4, 5, 16, 64)[function - 1] * (1 if subfunction == 1 else 2)
    elif 7 <= function <= 12:
        word = (0x08000000, 0x8000, 0x2000, 0x10000, 0x1000, 0x4000)[function - 7]
    elif function == 14:
        word = 0x20000
    elif function == 22:
        word = 0x40000
    elif function == 18:
        if subfunction == 5:
            return (
                keeson.checked(bytes((0xE6, 0xFE, 0x16, 3, 0, 0, 0, 0)))
                if protocol == "p2"
                else okin_nframe.request(0xB0)
            )
        word = 0x100
    elif function in (15, 16, 17, 19, 20):
        steps = {
            15: (0x800, 0x800000),
            16: (0x400, 0x1000000),
            17: (0x10000000, 0x4000000),
            19: (0x200, 0x100000),
            20: (0xC00, 0x1800000),
        }
        if subfunction in (8, 9) and (function != 19 or protocol == "p3"):
            word = steps[function][subfunction - 8]
        elif subfunction in (10, 11, 12):
            level = subfunction - 9
            if protocol == "p3" and function != 20:
                selector = {15: 2, 16: 3, 17: 4, 19: 1}[function]
                return okin_nframe.parameter_record(3, (selector, level, 0))
            if function in (15, 16, 20):
                word = 0x80000 << (level - 1)
            else:
                word, parameter = (0x10000000 if function == 17 else 0x200), level * 64
    return (
        keeson.frame(word, header=0xE6, side=parameter)
        if protocol == "p2"
        else okin_nframe.frame40(word, parameter)
    )


@dataclass(frozen=True, slots=True)
class Alarm:
    hour: int = 0
    minute: int = 0
    repeat: int = 0
    kind: int = 0
    on: bool = False


def alarms(protocol: Protocol, bank: tuple[Alarm, Alarm, Alarm]) -> tuple[bytes, ...]:
    if protocol == "p1":
        raise ValueError("Nerum P1 has no alarm output")
    if protocol == "p2":
        return (
            keeson.alarm_table(
                3,
                bytes(v for a in bank for v in (a.hour, a.minute, a.repeat if a.on else 0, a.kind)),
            ),
        )
    return tuple(
        okin_nframe.alarm(
            (a.repeat, WAKE_CODES.get(a.kind, 0), a.hour, a.minute, 0, int(a.on), 0), slot
        )
        for slot, a in enumerate(bank, 1)
    )


def query(protocol: Protocol, slot: int) -> bytes:
    if protocol == "p1" or slot not in (1, 2, 3):
        raise ValueError("Choose a Nerum P2/P3 alarm slot")
    return keeson.ALARM_QUERY if protocol == "p2" else okin_nframe.request(0xB0 + 0x10 * slot)


@dataclass(frozen=True, slots=True)
class Advertisement:
    protocol: Protocol
    identifier: str
    motors: int
    massage: bool


def advertisement(name: str | None, raw: bytes | None = None) -> Advertisement | None:
    if not name or not name.lower().startswith(("okin", "smartbed")):
        return None
    protocol: Protocol = "p3" if name.lower().startswith("smartbed") else "p2"
    identifier = "0" * 16
    if raw is not None and len(raw) > 13 and raw[9:11] == b"OK":
        if len(raw) < 27:
            return None  # Android throws; never fabricate a truncated identity.
        protocol, identifier = "p1", raw[11:27].decode("utf-8", errors="replace")
    units = identifier.encode("utf-16-le", errors="surrogatepass")
    digit = units[2:4].decode("utf-16-le", errors="surrogatepass")
    feature = units[8:12].decode("utf-16-le", errors="surrogatepass")
    try:
        motors = int(digit)
    except ValueError:
        return Advertisement(protocol, identifier, 2, True)
    return Advertisement(protocol, identifier, motors, feature != "00")
