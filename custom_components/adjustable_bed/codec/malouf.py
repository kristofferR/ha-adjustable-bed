"""Malouf wire codec.

The Malouf Base and Lucid Base apps reach five GATT transports. The Okin
transports carry one 32-bit key word, a bit mask of held keys whose zero word
releases every key; the Richmat transports carry one opcode byte. Each
transport fixes its frame:

- ``okin_legacy``: the Keeson E6 frame ``E6 FE 16 word(LE) 00 checksum``,
  built by ``codec/keeson.py``.
- ``okin_custom``: ``04 02 word(BE) 00 00 00 00``.
- ``okin_new``: ``05 02 word(BE) 00 00``.
- ``richmat_single``: the bare opcode, and ``richmat_framed``:
  ``6E 01 selector opcode sum8``, both built by ``codec/richmat.py``.

The two Okin-like frames open like an Okin N-frame but carry more bytes than
their first byte counts, so neither the N-frame nor the 5A codec reproduces
them. The Okin transports also set the bed clock and alarm and report massage
and light state. Which transports, words, opcodes and timing an app or route
uses belongs to its profile (``profiles/malouf.py``), never to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from . import keeson, richmat

TransportKey = Literal["richmat_single", "richmat_framed", "okin_legacy", "okin_custom", "okin_new"]
Family = Literal["richmat", "okin"]


@dataclass(frozen=True, slots=True)
class Transport:
    """A complete, coherent GATT role set, never a service-order hybrid."""

    family: Family
    command_service: str
    command_characteristic: str
    notify_service: str | None = None
    notify_characteristic: str | None = None


_UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
_UART_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
_UART_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
TRANSPORTS: Final[dict[TransportKey, Transport]] = {
    "richmat_single": Transport("richmat", _UART_SERVICE, _UART_WRITE),
    "richmat_framed": Transport(
        "richmat", "0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600"
    ),
    "okin_legacy": Transport(
        "okin",
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    "okin_custom": Transport(
        "okin",
        "62741523-52f9-8864-b1ab-3b3a8d65950b",
        "62741525-52f9-8864-b1ab-3b3a8d65950b",
        "62741523-52f9-8864-b1ab-3b3a8d65950b",
        "62741625-52f9-8864-b1ab-3b3a8d65950b",
    ),
    "okin_new": Transport("okin", _UART_SERVICE, _UART_WRITE, _UART_SERVICE, _UART_NOTIFY),
}

STOP_WORD: Final = 0
STOP_OPCODE: Final = richmat.STOP
# ``00 B0``: the new transport's light and massage status request.
STATUS_QUERY: Final = keeson.STATUS_QUERY
# Alarm type per preset.
ALARM_TYPES: Final[dict[str, int]] = {
    "zero_g": 13,
    "lounge": 14,
    "tv": 15,
    "anti_snore": 16,
    "memory_1": 17,
    "memory_2": 18,
}


def command(transport: TransportKey, value: int, *, selector: int = 0) -> bytes:
    """Encode a key word (Okin) or opcode (Richmat); ``selector`` is the framed role byte."""
    if transport == "richmat_single":
        return richmat.encode("nordic", value)
    if transport == "richmat_framed":
        return richmat.command(value, selector)
    word = value.to_bytes(4, "big")
    if transport == "okin_legacy":
        return keeson.frame(value, header=0xE6, side=0)
    if transport == "okin_custom":
        return b"\x04\x02" + word + bytes(4)
    if transport == "okin_new":
        return b"\x05\x02" + word + bytes(2)
    raise ValueError(f"Unknown Malouf transport: {transport}")


def _checked(body: bytes) -> bytes:
    return body + bytes((keeson.checksum(body),))


def clock(transport: TransportKey, now: datetime) -> bytes:
    """Set the bed clock in Java Calendar's local time and Sunday-zero weekday."""
    if transport == "okin_new":
        weekday = (now.weekday() + 1) % 7
        return bytes(
            (7, 4, now.year & 0xFF, now.month, now.day, weekday, now.hour, now.minute, now.second)
        )
    if transport not in ("okin_legacy", "okin_custom"):
        raise ValueError("This transport has no clock")
    fields = (now.year - 1900) & 0xFF, now.month - 1, now.day, now.hour, now.minute, now.second
    return _checked(bytes((0xE7, 0x80, 1, *fields)))


def alarm(transport: TransportKey, hour: int, minute: int, alarm_type: int, repeats: int) -> bytes:
    """Set an alarm; all-zero arguments encode the clear frame."""
    if transport == "okin_new":
        days = (repeats & 0x7E) | int(bool(repeats & 0x80))
        return bytes((7, 5, days, (alarm_type - 12) & 0xFF, hour, minute, 0, int(days > 0), 0))
    if transport not in ("okin_legacy", "okin_custom"):
        raise ValueError("This transport has no alarm")
    return _checked(bytes((0xED, 0x80, 3, hour, minute, repeats, alarm_type)) + bytes(8))


@dataclass(frozen=True, slots=True)
class Notification:
    """Massage time left and the raw light status; no motor state is inferred."""

    massage_remaining_minutes: int
    light_status: int


_LEGACY_OFFSETS: Final = {10: (7, 8), 16: (13, 14), 20: (18, 19)}


def parse_notification(transport: TransportKey, data: bytes) -> Notification | None:
    """Keep each transport's length guards, optional offsets and signed bytes."""
    if transport == "okin_legacy":
        if (offsets := _LEGACY_OFFSETS.get(len(data))) is None:
            return None
        light_offset, massage_offset = offsets
        timer = data[massage_offset] & 0xF
        light = int.from_bytes(data[light_offset : light_offset + 1], signed=True) >> 6
        return Notification(timer * 10 if 1 <= timer <= 3 else 0, light)
    if transport == "okin_custom":
        timer = int.from_bytes(data[10:11], signed=True) if len(data) > 10 else 0
        return Notification(timer * 10, 0)
    if transport == "okin_new":
        if len(data) < 2 or data[1] != 11:
            return None
        timer = int.from_bytes(data[4:5], signed=True) if len(data) > 4 else 0
        minutes = 30 if timer > 4 else 20 if timer > 2 else 10 if timer > 0 else 0
        light = any(len(data) > offset and data[offset] == 1 for offset in (9, 13))
        return Notification(minutes, int(light))
    return None
