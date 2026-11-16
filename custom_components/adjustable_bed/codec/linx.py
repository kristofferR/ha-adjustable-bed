"""Linx 1.0.7 (27): JSON, AA instructions, ASCII setup and AB intervention.

The accepted unit079 literals do not match the existing Keeson JSON field
order, nor its binary carriers. Transport selection is independent of the
payload family. No catalog semantics are inferred from the AA key builder.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Transport:
    service: str
    write: str
    notify: str
    subscription: str


TRANSPORTS: Final = {
    "a00a": Transport(
        "0000a00a-0000-1000-8000-00805f9b34fb",
        "0000b002-0000-1000-8000-00805f9b34fb",
        "0000b004-0000-1000-8000-00805f9b34fb",
        "indicate",
    ),
    "uart": Transport(
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        "notify",
    ),
}


def _json(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()


def control(device: str, word: int, *, km: int = 1, held: bool = False) -> bytes:
    """DEX/Gson reflection order, including primitive zero fields."""
    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError("Linx key must be a 32-bit word")
    return _json(
        {
            "cmd": {"ctrm": 0, "key": f"{word:08x}", "keykt": int(held), "km": km},
            "code": 2,
            "dvid": device,
        }
    )


def request(device: str, code: int, fields: Mapping[str, object]) -> bytes:
    """JSONObject insertion order of queries, self-check and settings."""
    return _json({"dvid": device, "code": code, "cmd": dict(fields)})


INSTRUCTION_KEYS: Final = frozenset(
    {
        0,
        1,
        2,
        4,
        8,
        16,
        32,
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        8388608,
        16777216,
        33554432,
        134217728,
        536870912,
        1073741824,
        -2147483648,
    }
)


def instruction(key: int) -> bytes:
    """AA builder's finite switch, special high bytes and zero fallback."""
    payload = bytearray(
        (key & 0xFFFFFFFF).to_bytes(4, "little") if key in INSTRUCTION_KEYS else bytes(4)
    )
    if key in (8192, 16384):
        payload[3] = 8
    body = bytes.fromhex("aa03000a000401") + payload + b"\0"
    return body + bytes((~sum(body[5:11]) & 255, 0xF3, 0x55))


ALARM_KEY_CONVERSION: Final = {
    1000: 4096,
    2000: 8192,
    4000: 16384,
    8000: 32768,
    10000: 65536,
    40000: 262144,
    80000: 524288,
    100000: 1048576,
    4000000: 67108864,
}


def alarm_recall(device: str, position_key: str, *, uart: bool) -> bytes:
    """Known serialization only. R01 prevents exposing catalog choices to users."""
    value = int(position_key, 10)
    if uart:
        return instruction(ALARM_KEY_CONVERSION.get(value, value))
    return _json(
        {"cmd": {"ctrm": 1, "key": f"{value:08d}", "keykt": 0, "km": 1}, "code": 2, "dvid": device}
    )


def startup_query(name: str) -> bytes:
    """Preserve the decimal/hex detour and single underflow correction of P3."""
    body = ("7D0E00" + (name[-8:] if len(name) >= 8 else "") + "AB54").encode("ascii")
    decimal = "".join(str(value if value < 128 else value - 256) for value in body)
    stage = "".join(format(int(decimal[i : i + 2]), "x") for i in range(0, len(decimal) - 1, 2))
    chars = "".join(chr(int(stage[i : i + 2], 16)) for i in range(0, len(stage) - 1, 2))
    total = sum(int(chars[i : i + 2], 16) for i in range(0, len(chars) - 1, 2))
    value = 255 - total
    if value < 0:
        value = 511 - total
    return body + format(value & 0xFFFFFFFF, "x").encode("ascii")


def snore(device: str, *, uart: bool, keep: int, speed: int, lift: int) -> bytes:
    if uart:
        return bytes(
            (
                0xAB,
                3,
                0,
                11,
                keep & 255,
                7,
                1,
                0,
                0,
                128,
                0,
                0,
                speed & 255,
                lift & 255,
                122,
                243,
                85,
            )
        )
    seconds = (keep * 60 + 2**31) % 2**32 - 2**31
    return request(
        device,
        3,
        {"key": "00008000", "pwm": speed, "pwmt": lift, "pwkt": seconds, "ctrm": 0, "pwsw": 1},
    )


SNORE_STATUS: Final = bytes.fromhex("ab03020b1d0701000080000080ca55")


def snore_delay_ms(keep: int) -> int:
    """Java int multiplication passed to Handler.postDelayed, including overflow."""
    return (keep * 60000 + 2**31) % 2**32 - 2**31


def alarm_slot(
    device: str,
    slot: int,
    *,
    position_id: int | None = None,
    weekdays: Sequence[int] = (),
    seconds: int = 0,
    populated: bool = False,
) -> bytes:
    """Six resident slots. Populated row meanings await R01; clears are independent."""
    if type(slot) is not int or not 1 <= slot <= 6:
        raise ValueError("Linx alarm slot must be 1–6")
    if any(type(day) is not int or not 0 <= day <= 6 for day in weekdays):
        raise ValueError("Linx repeat days must be 0–6")
    if not 0 <= seconds < 86400:
        raise ValueError("Linx alarm seconds must be within a day")
    mode = 16 if position_id in (1, 4) else 128 if position_id == 2 else 0
    return request(
        device,
        15,
        {
            "nm": slot,
            "blmd": mode if populated else 0,
            "blpt": sum(1 << day for day in set(weekdays)) if populated else 0,
            "blat": seconds if populated else 0,
            "blsw": int(populated),
        },
    )


def bed_mode(data: bytes, previous: int | None) -> int | None:
    """This literal substring is a wire selector, including the match on 20."""
    if b'"bedmd":2' in data:
        return 2
    return 0 if b'"bedmd":' in data else previous


@dataclass(frozen=True, slots=True)
class SetupReply:
    result: str
    version: str | None = None


def setup_reply(data: bytes) -> SetupReply | None:
    """A03: exact eight-byte guard; reject the source's decimal parsing failure."""
    if len(data) != 8 or data[0] != 0x8E:
        return None
    if data[4] == 1:
        return SetupReply("connection_failed")
    if data[4] != 2:
        return None
    fields = data[5:7].hex().upper()
    if not fields[:2].isdecimal():
        return SetupReply("invalid_version")
    return SetupReply("version_received", f"{int(fields[:2])}.{fields[2]}.{fields[3]}")


def status(data: bytes) -> dict[str, object]:
    """No assembly or invented ACK/checksum. Invalid and truncated JSON is ignored."""
    try:
        result = json.loads(data)
    except ValueError, UnicodeError:
        return {}
    return result if isinstance(result, dict) else {}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    complete: bool
    head: int
    foot: int
    head_massage: bool
    foot_massage: bool
    head_ripple: int
    foot_ripple: int


def diagnostic(payload: dict[str, object]) -> Diagnostic | None:
    values = tuple(payload.get(key) for key in ("chkStatu", "headPlus", "footPlus"))
    if any(type(value) is not int for value in values):
        return None
    code, head, foot = (int(str(value)) for value in values)
    bits = format(code & 0xFFFFFFFF, "b")
    if len(bits) < 8:
        bits = "00000000"
    return Diagnostic(
        bits[:2] == "11",
        int(bits[6:8], 2),
        int(bits[4:6], 2),
        bits[3] == "0",
        bits[2] == "0",
        head,
        foot,
    )
