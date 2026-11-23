"""FFFF frame wire codec (Solace/QMS, Woosa Sleep, BedSense and Motion Bed apps).

Every frame starts ``FF FF FF FF`` and the fifth byte selects one of two trailers:

- Kinds ``03``, ``05``, ``FE`` and ``FF`` end with CRC-16/MODBUS (initial value
  ``FFFF``, reflected polynomial ``A001``) over every preceding byte, low byte
  first. Kind ``05`` is the fixed 11-byte control frame
  ``05 00 group arg code``; kind ``03`` the 11-byte query
  ``03 00 register 00 count``. ``FE``/``FF`` frames carry module payloads.
- Kinds ``01`` and ``02`` end with the 16-bit little-endian sum of every
  preceding byte: ``kind 00 opcode length payload sum``, where ``length``
  counts the whole frame.

One FFE1 characteristic carries writes and notifications. Which commands an app
sends, and when, belongs to its profile (``profiles/ff_frame.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from ..const import SOLACE_CHAR_UUID, SOLACE_SERVICE_UUID

SERVICE_UUID: Final = SOLACE_SERVICE_UUID
CHARACTERISTIC_UUID: Final = SOLACE_CHAR_UUID
HEADER: Final = b"\xff\xff\xff\xff"


def bcd(value: int) -> int:
    """Encode a two-digit decimal value as one BCD byte."""
    return ((value // 10) << 4) | (value % 10)


def with_crc(body: bytes) -> bytes:
    """Append CRC-16/MODBUS over the whole body, header included."""
    crc = 0xFFFF
    for byte in body:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return body + crc.to_bytes(2, "little")


def with_sum(body: bytes) -> bytes:
    """Append the minimal little-endian byte sum; every reachable body needs two bytes."""
    total = sum(body)
    return body + total.to_bytes((total.bit_length() + 7) // 8, "little")


def control(code: int, *, arg: int = 0, group: int = 0) -> bytes:
    """Encode one kind-05 control frame (movement, preset, memory, massage, light)."""
    return with_crc(HEADER + bytes((0x05, 0, group, arg, code)))


def query(register: int, count: int) -> bytes:
    """Encode one kind-03 status query."""
    return with_crc(HEADER + bytes((0x03, 0, register, 0, count)))


def summed(kind: int, opcode: int, payload: bytes = b"") -> bytes:
    """Encode one kind-01/02 frame; its length byte counts the whole frame."""
    return with_sum(HEADER + bytes((kind, 0, opcode, len(payload) + 10)) + payload)


STOP: Final = control(0x00)


def clock(now: datetime, weekday: int) -> bytes:
    """Clock sync: BCD hour, minute, second, raw weekday 1-7, BCD year, month, day."""
    return summed(
        0x01,
        0x01,
        bytes(
            (
                bcd(now.hour),
                bcd(now.minute),
                bcd(now.second),
                weekday,
                bcd(now.year % 100),
                bcd(now.month),
                bcd(now.day),
            )
        ),
    )


def alarm(
    *,
    switch: int,
    hour: int,
    minute: int,
    weekday_mask: int,
    repeat: bool,
    mode: int,
    massage: bool,
    sound: int,
) -> bytes:
    """Alarm: switch byte, BCD hour and minute, ``00``, weekday mask, repeat, mode, massage, sound."""
    return summed(
        0x01,
        0x02,
        bytes((switch, bcd(hour), bcd(minute), 0, weekday_mask, repeat, mode, massage, sound)),
    )
