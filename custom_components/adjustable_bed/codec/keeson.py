"""Keeson E5/E6 wire codec (K1).

Every command carries one 32-bit Keeson key word, a bit mask of held keys and
actions. The zero word releases every key. The K1 frame is
``header FE 16 word [side] checksum``: header ``E5`` or ``E6``, the word in
little- or big-endian order, an optional side byte that makes the frame nine
bytes, and the complement of the byte sum.

Some ``keeson`` routes carry the same key word in other frames, listed as
carriers below. The ``p2`` frames are the Okin N-frame layout; they live here
until that family's codec exists (#759). Which carrier, header, byte order and
words an app uses belongs to its profile (``profiles/keeson.py``).

The checked setup frames (``E5 FE 17`` pulse targets, ``E7 80`` clock,
``E1 80`` alarm dismissal, ``E2 80`` alarm query, ``EF 02`` rename) end with the
same checksum.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_FALLBACK_GATT_PAIRS,
    KEESON_JSON_NOTIFY_CHAR_UUID,
    KEESON_JSON_SERVICE_UUID,
    KEESON_JSON_WRITE_CHAR_UUID,
    KEESON_KSBT_CHAR_UUID,
    KEESON_KSBT_FALLBACK_GATT_PAIRS,
    KEESON_KSBT_SERVICE_UUID,
    NORDIC_UART_READ_CHAR_UUID,
)

TransportKey = Literal["base", "ksbt", "json"]
ByteOrder = Literal["little", "big"]
Carrier = Literal["k1", "p2", "p2_side", "p2_padded", "p2_checked", "json"]


@dataclass(frozen=True)
class Transport:
    """GATT roles. ``fallbacks`` are (service, write) pairs tried when the primary is absent."""

    service_uuid: str
    write_uuid: str
    notify_uuid: str
    fallbacks: tuple[tuple[str, str], ...] = ()


TRANSPORTS: Final[dict[TransportKey, Transport]] = {
    "base": Transport(
        KEESON_BASE_SERVICE_UUID,
        KEESON_BASE_WRITE_CHAR_UUID,
        KEESON_BASE_NOTIFY_CHAR_UUID,
        tuple(KEESON_FALLBACK_GATT_PAIRS),
    ),
    "ksbt": Transport(
        KEESON_KSBT_SERVICE_UUID,
        KEESON_KSBT_CHAR_UUID,
        NORDIC_UART_READ_CHAR_UUID,
        tuple(KEESON_KSBT_FALLBACK_GATT_PAIRS),
    ),
    "json": Transport(
        KEESON_JSON_SERVICE_UUID, KEESON_JSON_WRITE_CHAR_UUID, KEESON_JSON_NOTIFY_CHAR_UUID
    ),
}

RELEASE: Final = 0
# Motor key bits; every app reads them the same way.
HEAD_UP: Final = 0x01
HEAD_DOWN: Final = 0x02
FOOT_UP: Final = 0x04
FOOT_DOWN: Final = 0x08
TILT_UP: Final = 0x10
TILT_DOWN: Final = 0x20
LUMBAR_UP: Final = 0x40
LUMBAR_DOWN: Final = 0x80


def checksum(body: bytes) -> int:
    """Complement of the byte sum, shared by every checked Keeson frame."""
    return ~sum(body) & 0xFF


def checked(body: bytes) -> bytes:
    """Append the checksum to a frame body."""
    return body + bytes((checksum(body),))


def _word(word: int) -> int:
    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError(f"Key word must be 32-bit, got {word:#x}")
    return word


def frame(
    word: int, *, header: int = 0xE5, order: ByteOrder = "little", side: int | None = None
) -> bytes:
    """Encode one K1 frame."""
    if header not in (0xE5, 0xE6):
        raise ValueError(f"K1 header must be E5 or E6, got {header:#x}")
    body = bytes((header, 0xFE, 0x16)) + _word(word).to_bytes(4, order)
    if side is not None:
        body += bytes((side,))
    return checked(body)


def p2(word: int, carrier: Carrier = "p2") -> bytes:
    """Encode a big-endian ``04 02`` or ``05 02`` frame.

    ``p2`` is ``04 02 word``; ``p2_side`` is ``05 02 word 00``; ``p2_padded``
    is ``04 02 word 00``; ``p2_checked`` is ``04 02 word checksum``.
    """
    body = bytes((0x05 if carrier == "p2_side" else 0x04, 0x02)) + _word(word).to_bytes(4, "big")
    if carrier in ("p2_side", "p2_padded"):
        return body + b"\x00"
    if carrier == "p2_checked":
        return checked(body)
    if carrier != "p2":
        raise ValueError(f"{carrier} is not a P2 carrier")
    return body


def json_command(word: int, device_id: str, *, ctrm: int, km: int, keykt: int) -> bytes:
    """Encode one JSON/A00A command for the Juna and Linx remotes."""
    payload = {
        "code": 2,
        "dvid": device_id,
        "cmd": {"key": f"{_word(word):08x}", "ctrm": ctrm, "km": km, "keykt": keykt},
    }
    return json.dumps(payload, separators=(",", ":")).encode()


# Two-byte status request of the direct P2 remotes; not a STOP.
STATUS_QUERY: Final = b"\x00\xb0"


def rename(raw_name: bytes) -> bytes:
    """Encode the 18-byte ``EF 02`` rename frame: name zero-filled to 15 bytes, checksum last.

    Each app limits the name itself; the frame holds at most 15 bytes.
    """
    if len(raw_name) > 15:
        raise ValueError("Rename payload must be at most 15 bytes")
    return checked(b"\xef\x02" + raw_name.ljust(15, b"\x00"))


def position_target(head: int, foot: int) -> bytes:
    """Encode the ``E5 FE 17`` pulse-target frame: two little-endian 16-bit pulse counts."""
    return checked(
        b"\xe5\xfe\x17"
        + (head & 0xFFFF).to_bytes(2, "little")
        + (foot & 0xFFFF).to_bytes(2, "little")
    )


def clock_fields(fields: Sequence[int]) -> bytes:
    """Encode the ``E7 80 01`` clock frame from six date and time bytes.

    Apps differ in how they derive the bytes (month and day bases, hour offset).
    """
    if len(fields) != 6:
        raise ValueError("The clock frame carries six date and time bytes")
    return checked(bytes((0xE7, 0x80, 0x01, *fields)))


def clock(now: datetime) -> bytes:
    """Clock frame with year minus 1900, zero-based month, then day and time as they are."""
    year = (now.year - 1900) & 0xFF
    return clock_fields((year, now.month - 1, now.day, now.hour, now.minute, now.second))


# Dismisses a ringing wake alarm.
ALARM_DISMISS: Final = checked(b"\xe1\x80\x04")
# Ask for the stored alarm records: E2 80 (Glideaway Motion, AdjustaMattress P1)
# and E1 80 03 (SIMMONS OKIN, both records at once).
ALARM_QUERY: Final = checked(b"\xe2\x80\x03\x00")
ALARM_RECORDS_QUERY: Final = checked(b"\xe1\x80\x03")


@dataclass(frozen=True)
class PositionStatus:
    """An ``ED``/``F0``/``F1`` status notification; positions are percentages."""

    head_position: int
    foot_position: int
    head_massage: int
    foot_massage: int
    head_moving: bool
    foot_moving: bool
    led_on: bool
    timer_minutes: str | None


_STATUS_LENGTHS: Final = {0xED: 16, 0xF0: 19, 0xF1: 20}


def parse_position_status(data: bytes) -> PositionStatus | None:
    """Parse a status notification; ``FFFF`` positions read as zero."""
    length = _STATUS_LENGTHS.get(data[0]) if data else None
    if length is None or len(data) < length:
        return None
    head = int.from_bytes(data[1:3], "little")
    foot = int.from_bytes(data[3:5], "little")
    moving = data[13] & 0xF
    timer = data[14]
    return PositionStatus(
        head_position=0 if head == 0xFFFF else head,
        foot_position=0 if foot == 0xFFFF else foot,
        head_massage=data[5],
        foot_massage=data[6],
        head_moving=moving != 0xF and bool(moving & 1),
        foot_moving=moving != 0xF and bool(moving & 2),
        led_on=bool(data[13] & 0x40),
        timer_minutes=("10", "20", "30")[timer - 1] if 1 <= timer <= 3 else None,
    )
