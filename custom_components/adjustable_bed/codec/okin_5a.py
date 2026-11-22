"""Okin 5A (StarCode) wire codec.

Every frame starts with ``5A`` and ends with ``A5``. There is no checksum.

- Normal: ``5A 01 <32-bit big-endian word> A5``. Bed keys use the word
  ``03 10 page key``: page ``30`` holds the normal keys; page ``40`` repeats some
  of them for an alternate use (Mattress Firm massage intensity). A STOP is the
  page-30 key ``0F``.
- Setting: ``5A E0 04 parameter value value2 value3 A5``.
- Position target: ``5A F0 03 axis target 00 A5``.
- Request: ``5A code 00 A5``, including the wake ``5A 0B 00 A5``.
- Clock: ``5A 14 07 <seven field bytes> A5``.

One connection frame is not a 5A frame: the Mattress Firm handshake
``09 05 0A 23 05 00 00``.

Which words, parameters, request codes, clock field order, transport, write mode
and timing a bed uses belongs to its profile (``profiles/okin_5a.py``) or its
controller, never to this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from ..const import (
    NECTAR_NOTIFY_CHAR_UUID,
    NECTAR_SERVICE_UUID,
    NECTAR_WRITE_CHAR_UUID,
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)

TransportKey = Literal["okin", "nus"]


@dataclass(frozen=True)
class Transport:
    """GATT roles of one transport."""

    service_uuid: str
    write_uuid: str
    notify_uuid: str


TRANSPORTS: Final[dict[TransportKey, Transport]] = {
    "okin": Transport(NECTAR_SERVICE_UUID, NECTAR_WRITE_CHAR_UUID, NECTAR_NOTIFY_CHAR_UUID),
    "nus": Transport(
        NORDIC_UART_SERVICE_UUID, NORDIC_UART_WRITE_CHAR_UUID, NORDIC_UART_READ_CHAR_UUID
    ),
}

NORMAL: Final = 0x30
ALTERNATE: Final = 0x40


def normal(word: int) -> bytes:
    """Encode a 32-bit command word as ``5A 01 <word> A5``."""
    if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word <= 0xFFFFFFFF:
        raise ValueError("Command word must be an unsigned 32-bit integer")
    return b"\x5a\x01" + word.to_bytes(4, "big") + b"\xa5"


def command(key: int, page: int = NORMAL) -> bytes:
    """Encode one key frame: the normal frame of word ``03 10 page key``."""
    if not 0 <= key <= 0xFF or page not in (NORMAL, ALTERNATE):
        raise ValueError(f"invalid key {key:#x} on page {page:#x}")
    return normal(0x03100000 | page << 8 | key)


def extended(parameter: int, value: int, value2: int = 0, value3: int = 0) -> bytes:
    """Encode an 8-byte ``5A E0 04`` setting frame."""
    return bytes((0x5A, 0xE0, 0x04, parameter, value, value2, value3, 0xA5))


def position_target(axis: int, target: int) -> bytes:
    """Encode a 7-byte ``5A F0 03`` position target."""
    return bytes((0x5A, 0xF0, 0x03, axis, target, 0x00, 0xA5))


def request(code: int) -> bytes:
    """Encode a 4-byte ``5A code 00 A5`` request."""
    return bytes((0x5A, code, 0x00, 0xA5))


def clock(fields: Sequence[int]) -> bytes:
    """Encode an 11-byte ``5A 14 07`` clock frame from seven field bytes, in profile order."""
    if len(fields) != 7:
        raise ValueError("A clock frame carries exactly seven fields")
    return bytes((0x5A, 0x14, 0x07, *fields, 0xA5))


STOP: Final = command(0x0F)
WAKE: Final = request(0x0B)
MATTRESSFIRM_HANDSHAKE: Final = bytes.fromhex("09050A23050000")
CONNECTION_FRAMES: Final = frozenset({WAKE, MATTRESSFIRM_HANDSHAKE})
