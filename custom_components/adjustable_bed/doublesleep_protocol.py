"""OKIN SleepEase 1.2.24 BLE formats, from the accepted row107 artifact.

P1, P2 and P3 are independent driver paths. They share GATT roles, not commands.
See docs/apk-analysis/dispositions/row107-doublesleep.md for safety corrections.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from .codec import okin_nframe
from .profiles.okin_nframe import DOUBLESLEEP

type Json = None | bool | int | float | str | Sequence[Json] | Mapping[str, Json]
type Protocol = Literal["p1", "p2", "p3"]
SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FIRMWARE_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
MODELS = {
    0: "Unknown",
    2: "Single",
    3: "Double",
    4: "Meise",
    5: "Dormimundo",
    10135: "Sleep XiaoBao",
    10137: "Sleep XiaoBao Single",
    67: "Milliwave Double",
    11135: "Sleep XiaoBao Only",
    11136: "Sleep XiaoBao Only Single",
}
DOUBLE_MODELS = frozenset((3, 10135, 11135))
P2_MODELS = frozenset((10135, 10137))
P3_MODELS = frozenset((11135, 11136))
PRESETS = {
    "memory_1": 14,
    "memory_2": 15,
    "anti_snore": 16,
    "lounge": 17,
    "tv": 18,
    "zero_g": 19,
    "flat": 26,
}
SAVE = {14: 20, 15: 21, 16: 22, 17: 23, 18: 24, 19: 25}
# Getter-only indices (6,7,30,33,34,39,42..46,61,65,70) have no shipped action.
DEAD = frozenset((0, 6, 7, 30, 33, 34, 39, 42, 43, 44, 45, 46, 61, 65, 70))
OTA = frozenset((74, 75, 76))
CHILD_BLOCKED = frozenset((*range(2, 20), 26, *range(28, 50), 58))
# P1 key frames are 40-bit Okin N-frames of the ``DOUBLESLEEP`` profile's words;
# these are its other static frames. Index 27 is the app's 3-byte all-stop.
P1_STATIC = {
    27: "050200",
    48: "07050000000000000000",
    50: "00b0",
    52: "00c0",
    53: "00b0",
    59: "01b201",
    60: "01b200",
    63: "020b000001",
    64: "01b301",
    66: "01b102",
} | {int(index): okin_nframe.frame40(word).hex() for index, word in DOUBLESLEEP.keys.items()}

P2_STATIC = {
    1: "aa000001010400000000",
    2: "aa000001010401000000",
    3: "aa000001010402000000",
    4: "aa000001010404000000",
    5: "aa000001010408000000",
    8: "aa000001010410000000",
    9: "aa000001010420000000",
    10: "aa000001010440000000",
    11: "aa000001010480000000",
    12: "aa000001010400010000",
    13: "aa000001010400020000",
    14: "aa000001030105",
    15: "aa000001030106",
    16: "aa000001030104",
    17: "aa000001030102",
    18: "aa000001030103",
    19: "aa000001030101",
    20: "aa000001050125",
    21: "aa000001050126",
    22: "aa000001050124",
    23: "aa000001050122",
    24: "aa000001050123",
    25: "aa000001050121",
    26: "aa000001030109",
    27: "aa0000010200",
    28: "aa000002010140",
    29: "aa000002010141",
    48: "aa00000302080100000000000000",
    50: "2a000002810103",
    51: "2a0000068100",
    52: "2a000003810101",
    53: "2a0000078100",
    54: "2a0000048100",
    59: "aa000007020101",
    60: "aa000007020100",
    63: "aa00000701080002010100000000",
    64: "01b301",
    66: "01b102",
    73: "2a0000088100",
    87: "aa00000605020000",
    88: "aa00000605020001",
    89: "aa0000060c020001",
    90: "aa0000060c020000",
}
RELATIVE = {
    31: ("time", 1),
    32: ("time", -1),
    35: ("head", 1),
    36: ("head", -1),
    37: ("foot", 1),
    38: ("foot", -1),
    40: ("mode", 1),
    41: ("mode", -1),
    79: ("head", 1),
    80: ("head", -1),
    81: ("foot", 1),
    82: ("foot", -1),
    83: ("mode", 1),
    84: ("mode", -1),
    85: ("time", 1),
    86: ("time", -1),
}
P1_SUPPORTED = frozenset(P1_STATIC) | {32, 47, 49, 62}
P2_SUPPORTED = frozenset(P2_STATIC) | frozenset(RELATIVE) | {47, 49, 57, 58, 62, 67, 72}
P3_SUPPORTED = frozenset((47, 53, 55, 59, 60, 68, 69, 71, 72, 73, 77, 78))


def select_protocol(name: str, manufacturer: Mapping[int, bytes]) -> Protocol:
    if name.lower().startswith("osleepbt"):
        return "p3"
    data = manufacturer.get(89, b"")
    return "p2" if len(data) >= 7 and data[6] + 1 in (135, 137) else "p1"


def real_mac(name: str, manufacturer: Mapping[int, bytes]) -> str | None:
    data = manufacturer.get(89)
    if data is None:
        return None
    if "osleep" in name.lower():
        parts = name.split("-")
        return parts[1] if len(parts) > 1 else name
    return bytes(reversed(data))[1:7].hex() if len(data) >= 7 else None


def discover(
    name: str, manufacturer: Mapping[int, bytes], advertisement_name: str | None = None
) -> bool:
    return bool(
        name
        and name.lower().startswith(("sleepbt", "osleepbt", "osleepbts"))
        and real_mac(advertisement_name if advertisement_name is not None else name, manufacturer)
        is not None
    )


def select_model(platform_name: str, manufacturer: Mapping[int, bytes]) -> int:
    data = manufacturer.get(89)
    if data is None:
        return 0
    if "osleepbt" in platform_name.lower():
        return 11136 if "osleepbts" in platform_name.lower() else 11135
    if len(data) < 7:
        return 0
    return next((code for code in MODELS if code % 10000 == data[6] + 1), 3)


def u8(values: Sequence[int]) -> bytes:
    """Dart Uint8List coercion, including the signed UTC offset."""
    return bytes(v & 255 for v in values)


def cycle(value: int, low: int, high: int, delta: int) -> int:
    result = value + delta
    return low if delta > 0 and result > high else high if delta < 0 and result < low else result


@dataclass
class Cache:
    """Notification-owned builder inputs, isolated by physical device in HA."""

    regular: dict[str, int] = field(
        default_factory=lambda: {"running": 0, "mode": 0, "head": 0, "foot": 0, "time": 0}
    )
    sonic: dict[str, int] = field(
        default_factory=lambda: {
            "source": 1,
            "mode": 1,
            "head": 0,
            "foot": 0,
            "time": 0,
        }
    )
    light: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])


@dataclass
class UIState:
    """App-view selections/capabilities, separate from numeric driver statics."""

    sonic_ui: bool = False
    slow: bool = False
    pwm: int = 0
    timer: int = 10


def relative(index: int, cache: Cache) -> bytes:
    domain, delta = RELATIVE[index]
    sonic = index >= 79
    value = (cache.sonic if sonic else cache.regular)[domain]
    upper = 3 if domain == "time" or sonic and domain in ("head", "foot") else 6 if sonic else 4
    low = 0 if domain in ("head", "foot") else 1
    result = (
        (4 if value == 1 else 3 if value < 1 else value - 1)
        if (not sonic and domain in ("head", "foot") and delta < 0)
        else cycle(value, low, upper, delta)
    )
    if not sonic:
        return u8(
            [170, 0, 0, 2, 1, 1, {"time": 72, "head": 79, "foot": 83, "mode": 65}[domain] + result]
        )
    if domain == "mode":
        return u8([170, 0, 0, 6, 3, 2, 0, result])
    if domain in ("head", "foot"):
        return u8(
            [
                170,
                0,
                0,
                6,
                2,
                3,
                0,
                1 if domain == "head" else 2,
                0 if result == 0 else 2 * (result + 1),
            ]
        )
    time = 600 * result - 1
    hi = time // 256 if time >= 0 else -(abs(time) // 256)
    return u8([170, 0, 0, 6, 11, 6, 0, 3, time & 255, hi, time & 255, hi])


def binary_command(
    protocol: Protocol, index: int, values: Sequence[int], cache: Cache, now: datetime
) -> bytes:
    """Build only reachable, non-OTA commands; no raw packet service."""
    if protocol == "p3" or index not in (P1_SUPPORTED if protocol == "p1" else P2_SUPPORTED):
        raise ValueError("Command is unavailable for the selected SleepEase driver")
    static = P1_STATIC if protocol == "p1" else P2_STATIC
    if index in static:
        return bytes.fromhex(static[index])
    if protocol == "p1":
        if index == 32:
            return b""  # Shipped timeDown has an empty builder.
        if index == 47:
            return u8(
                [
                    7,
                    4,
                    now.year - 1900,
                    now.month - 1,
                    now.day,
                    now.isoweekday() - 1,
                    now.hour,
                    now.minute,
                    now.second,
                ]
            )
        if index == 49:
            hour, minute, days, preset, massage = values
            return u8([7, 5, massage, preset, hour, minute, 0, 1, 1, days])
        amount, mode = values[:2]
        return u8([2, 11, amount, 3 if mode == 2 else 6 if mode == 3 else 1, 1])
    if index in RELATIVE:
        return relative(index, cache)
    if index == 47:
        offset = now.utcoffset()
        return u8(
            [
                170,
                0,
                0,
                3,
                1,
                8,
                now.year - 2000,
                now.month,
                now.day,
                now.isoweekday(),
                now.hour,
                now.minute,
                now.second,
                int(offset.total_seconds() / 3600) if offset else 0,
            ]
        )
    if index == 49:
        hour, minute, days, preset, massage = values
        return u8([170, 0, 0, 3, 2, 8, 1, days, preset, 1, hour, minute, 0, massage])
    if index == 57:
        return u8([42, 0, 0, 5, 129, 9, values[0], 255, 255, 0, 0, 34, 37, 18, 75])
    if index == 58:
        mode, on, *settings = cache.light
        return u8([170, 0, 0, 4, 1, 6, mode, int(on == 0), *settings])
    if index == 62:
        amount, mode, pwm, timer = values
        return u8([170, 0, 0, 7, 1, 8, amount, 2, mode, 1, pwm, timer, 0, 0])
    if index == 67:
        side, left, right = values
        return u8([170, 0, 0, 7, 4, 3, side, left, right])
    side, kind, year, month, day = values
    return u8(
        [
            42,
            0,
            0,
            7,
            (132 if side == 0 else 133) if kind == 0 else (134 if side == 0 else 135),
            3 if kind == 0 else 2,
            year % 2000,
            month,
            *([day] if kind == 0 else []),
        ]
    )


@dataclass
class JsonWriter:
    """Per-device sequence, shared across JSON IDs and outer fragments."""

    sequence: int = 0

    def packets(self, command: str, value: Json, mtu: int, *, send: bool = False) -> list[bytes]:
        # The artifact builds packets of MTU bytes, which Android rejects (MTU-3).
        # Retain framing but fit negotiated ATT capacity and the one-byte body length.
        capacity = min(mtu - 3, 497, 262)
        size = capacity - 14
        if size <= 0:
            raise ValueError("Negotiated MTU cannot carry SleepEase JSON framing")
        self.sequence = (self.sequence + 1) & 255
        payload = json.dumps(
            {"id": self.sequence, "cmd": command, "val": value},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        chunks = [payload[i : i + size] for i in range(0, len(payload), size)]
        if len(chunks) > 255:
            raise ValueError("SleepEase JSON command exceeds fragment-count capacity")
        packets = []
        for index, chunk in enumerate(chunks):
            self.sequence = (self.sequence + 1) & 255
            body = u8([17, 3, 89, 68, 89, len(chunk) & 255, len(chunk) >> 8]) + chunk
            packets.append(
                u8([2 if send else 0, self.sequence, len(chunks), index, len(body), 0, 0]) + body
            )
        return packets

    def command(self, index: int, values: Sequence[int], now: datetime, mtu: int) -> list[bytes]:
        if index not in P3_SUPPORTED:
            raise ValueError("Command is unavailable for the selected SleepEase driver")
        commands: dict[int, tuple[str, Json, bool]] = {
            53: ("q_antiSnore", {}, False),
            55: ("q_time", {}, False),
            59: ("q_realtime", {"time": 1}, False),
            60: ("q_realtime", {"time": 65535}, False),
            69: ("q_sens", {}, False),
            71: ("q_part", {}, False),
            73: ("s_init", 0, True),
            77: ("q_realtime", {"time": 65535}, False),
            78: ("q_report", {"allow": 1}, False),
        }
        value: Json
        if index == 47:
            offset = now.utcoffset()
            command, value, send = (
                "s_time",
                {
                    "ts": int(now.timestamp()),
                    "utc": int(offset.total_seconds() / 3600) if offset else 0,
                },
                True,
            )
        elif index == 68:
            command, value, send = "s_sens", {"L": [values[0]], "R": [values[1]], "ret": 0}, True
        elif index == 72:
            side, kind, year, month, day = values
            command, value, send = (
                "q_report",
                {"part": side + 1, "type": kind + 1, "y": year, "m": month, "d": day},
                False,
            )
        else:
            command, value, send = commands[index]
        return self.packets(command, value, mtu, send=send)


WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
ALARM_PRESETS = {"zero_g": 1, "flat": 9, "memory_1": 5, "memory_2": 6, "vibration": 8}


def alarm_days(now: datetime, hour: int, minute: int, weekdays: Sequence[str]) -> int:
    """Repeat bits follow the artifact's Su..Sa order; bit7 enables repetition.

    Fix the one-shot Sunday overflow using that same proven day-bit layout.
    """
    if weekdays:
        if any(day not in WEEKDAYS for day in weekdays):
            raise ValueError("Choose alarm weekdays from sun through sat")
        return 128 | sum(1 << WEEKDAYS.index(day) for day in set(weekdays))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    return 1 << (target.isoweekday() % 7)
