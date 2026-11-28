"""AMADA whole-list replies, with bounds-safe seven-byte marker records.

No invented buffering, CRC or position data. Missing-side fallback and AB's
active-side choice are source behavior, not independent-side HA telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Massage:
    time: int
    head: int
    foot: int
    mode: int
    on: bool
    light: bool


@dataclass(frozen=True)
class Alarm:
    repeat: int
    kind: int
    hour: int
    minute: int
    enabled: bool


def bucket(remaining: int) -> int:
    return 0 if remaining <= 0 or remaining > 1800 else (remaining - 1) // 600 + 1


def _blocks(data: bytes) -> dict[int, bytes]:
    return {data[start]: data[start:start + 7] for start in (3, 10)
            if len(data) >= start + 7 and data[start] in (0xAA, 0xBB)}


def _choose(blocks: dict[int, bytes], selector: int, active_offset: int) -> bytes | None:
    a, b = blocks.get(0xAA), blocks.get(0xBB)
    if selector:
        return blocks.get(selector, b if selector == 0xAA else a)
    if a is None or b is None:
        return a if a is not None else b
    active_a = int.from_bytes(a[1:3], "big") > 0 if active_offset == 1 else a[6] == 1
    active_b = int.from_bytes(b[1:3], "big") > 0 if active_offset == 1 else b[6] == 1
    return b if active_b and not active_a else a


def parse(data: bytes, selector: int) -> Massage | Alarm | None:
    if len(data) < 10 or data[:3] not in (b"\xa5\x0b\x0e", b"\xa5\x0c\x0e"):
        return None
    # Reject a partial second record, rather than silently ignoring its marker.
    if 10 < len(data) < 17:
        return None
    blocks = _blocks(data)
    if data[1] == 0x0C:
        block = _choose(blocks, selector, 6)
        return Alarm(block[1], block[2], block[3], block[4], block[6] == 1) if block else Alarm(0, 0, 0, 0, False)
    massage, light = _choose(blocks, selector, 1), _choose(blocks, selector, 6)
    time = bucket(int.from_bytes(massage[1:3], "big")) if massage else 0
    return Massage(time, (massage[4] + 1) // 2 if massage and time else 0,
                   (massage[5] + 1) // 2 if massage and time else 0,
                   massage[3] if massage and time else 0, time > 0,
                   light is not None and light[6] == 1)
