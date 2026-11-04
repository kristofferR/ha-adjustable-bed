"""Okin N-frame wire codec.

Every command is one frame: ``N 02 <N-byte big-endian command word>``, so a
frame is ``N + 2`` bytes long. The command word is a bit mask: each set bit is
one held key, and the all-zero word releases every key (STOP). Profiles use
32-bit (``04 02``), 40-bit, 48-bit, 64-bit or 96-bit words; the word's width is
profile data, never inferred from a key.

The 96-bit (CST) routes carry two independently routed 32-bit fields and 32
zero bits. The 40-bit routes carry a 32-bit key word followed by one selector byte, which
picks a CB24 bed side (``AA``/``BB``) and is ``00`` everywhere else. Several of
them also send 64-bit ``08 02`` frames for a few lights and massage keys,
two-byte ``00 <code>`` requests, ``04 E0`` setting frames and ``03 F0`` position
targets. What a request or setting means is profile data.

Two transports carry the frame. The plain route writes it to the Okin write
characteristic. RF-Gateway receivers and revision-0 Leggett boxes take the same
32-bit word in an 8-byte envelope, ``E5 FE 16 <word> checksum``, where the
checksum is the inverted low byte of the sum of every earlier byte.

Which words an app sends, with which timing and release, belongs to its profile
(``profiles/okin_nframe.py``), never to this module.
"""

from __future__ import annotations

from typing import Final

from ..const import (
    LEGGETT_OKIN_NOTIFY_CHAR_UUID,
    LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_POSITION_NOTIFY_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
)

SERVICE_UUID: Final = OKIMAT_SERVICE_UUID
WRITE_UUID: Final = OKIMAT_WRITE_CHAR_UUID
# Okimat boxes report head and foot positions here.
POSITION_UUID: Final = OKIN_POSITION_NOTIFY_CHAR_UUID
# Leggett boxes: LED/status notifications, and the characteristic whose
# presence selects the plain (revision-1) frame over the envelope (revision 0).
STATUS_UUID: Final = LEGGETT_OKIN_NOTIFY_CHAR_UUID
REVISION_SELECTOR_UUID: Final = LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID
# Leggett settings channel and the write that opens it after subscribing.
SETTINGS_WRITE_UUID: Final = OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID
SETTINGS_NOTIFY_UUID: Final = OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID
SETTINGS_INIT: Final = b"\x01\x02"

WIDTHS: Final = frozenset({4, 5, 6, 8, 12})
GATEWAY_HEADER: Final = b"\xe5\xfe\x16"


def frame(word: int, width: int = 4) -> bytes:
    """Encode one command word as ``width 02 <word>``."""
    if width not in WIDTHS:
        raise ValueError(f"Unsupported command word width: {width} bytes")
    if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word < 1 << (8 * width):
        raise ValueError(f"Command word must be an unsigned {8 * width}-bit integer")
    return bytes((width, 0x02)) + word.to_bytes(width, "big")


def frame40(key: int, selector: int = 0) -> bytes:
    """Encode a 40-bit frame: the 32-bit key word, then the selector byte."""
    if isinstance(key, bool) or not isinstance(key, int) or not 0 <= key <= 0xFFFFFFFF:
        raise ValueError("Key word must be an unsigned 32-bit integer")
    if not 0 <= selector <= 0xFF:
        raise ValueError("Selector must be one byte")
    return frame(key << 8 | selector, 5)


def frame96(primary: int, secondary: int = 0) -> bytes:
    """Encode a 96-bit CST frame: two 32-bit fields, then 32 zero bits."""
    for value in (primary, secondary):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("CST fields must be unsigned 32-bit integers")
    return frame(primary << 64 | secondary << 32, 12)


def request(code: int) -> bytes:
    """Encode a two-byte ``00 <code>`` request."""
    return bytes((0x00, code))


def extended(parameter: int, value: int, value2: int = 0) -> bytes:
    """Encode a 6-byte ``04 E0`` setting frame: light, massage level or timer."""
    return bytes((0x04, 0xE0, parameter, value, value2, 0x00))


def position_target(axis: int, target: int) -> bytes:
    """Encode a 5-byte ``03 F0`` position target."""
    return bytes((0x03, 0xF0, axis, target, 0x00))


def word_of(data: bytes) -> int:
    """Return the 32-bit command word of a plain frame."""
    if len(data) != 6 or data[:2] != b"\x04\x02":
        raise ValueError("Expected a 6-byte 32-bit Okin frame")
    return int.from_bytes(data[2:], "big")


def gateway_frame(word: int) -> bytes:
    """Wrap a 32-bit command word in the 8-byte RF-Gateway (revision-0) envelope."""
    body = GATEWAY_HEADER + frame(word)[2:]
    return body + bytes(((~sum(body)) & 0xFF,))


STOP: Final = frame(0)


def parse_position(data: bytes) -> tuple[int, int] | None:
    """Return raw (head, foot) positions: little-endian at bytes 3-4 and 5-6."""
    if len(data) < 7:
        return None
    return data[3] | (data[4] << 8), data[5] | (data[6] << 8)


def parse_status(data: bytes) -> tuple[int, int] | None:
    """Reconstruct the Leggett Prodigy LED mask and signed status byte."""
    if len(data) < 4:
        return None

    size = data[0] & 0x0F
    if len(data) < size + 3:
        return None

    led_mask = 0
    for index in range(min(max(size - 2, 0), 4)):
        led_mask = (led_mask << 8) | data[index + 2]

    status = data[6] if size > 5 else -1
    if status >= 0x80:
        status -= 0x100

    def read_unsigned(offset: int, count: int) -> int:
        return int.from_bytes(data[offset : offset + count], "big")

    opcode = data[2]
    if opcode == 6:
        led_mask |= read_unsigned(3, size)
    elif opcode in (7, 9):
        led_mask &= ~read_unsigned(3, size)
    elif opcode == 8 and size != 6:
        led_mask ^= read_unsigned(3, size)
    elif opcode == 11:
        half = size >> 1
        offset = 3 + (size & 1)
        led_mask = (read_unsigned(offset + half, half) & read_unsigned(offset, half) & ~0x200) | (
            led_mask & 0x200
        )

    return led_mask & 0xFFFFFFFF, status


def parse_receipt(data: bytes) -> int | None:
    """Return the status mask of a CU170 ``09 0B`` receipt, which repeats it twice."""
    if len(data) != 20 or data[:2] != b"\x09\x0b" or data[2:6] != data[6:10]:
        return None
    return int.from_bytes(data[2:6], "big")
