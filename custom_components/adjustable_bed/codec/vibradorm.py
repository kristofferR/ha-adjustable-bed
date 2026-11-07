"""Vibradorm VMAT wire codec.

Every Vibradorm app drives one GATT layout: the control service ``1525`` and the
status service ``1527`` under the vendor base ``-9f03-0de5-96c5-b8f4f3081186``.

- motor frame (``1526``): one command byte; ``FF`` is STOP.
- light frame (``1529``): ``level minutes_hi minutes_lo``.
- command frame (``1550``): a big-endian 16-bit command word, then its
  parameter bytes. Bit 15 is a toggle some apps alternate between frames.
- motor status reply (``1551``): ``20 3F flags`` or ``3F flags``, then
  big-endian 16-bit motor counts.

Text replies and Device Information strings decode as Java's UTF-8 decoder does.
Which commands, parameters, toggle rules and timing an app uses belongs to its
profile (``profiles/vibradorm.py``), never to this module.
"""

from __future__ import annotations

from typing import Final

from ..const import (
    VIBRADORM_CBI_CHAR_UUID,
    VIBRADORM_COMMAND_CHAR_UUID,
    VIBRADORM_LIGHT_CHAR_UUID,
    VIBRADORM_NOTIFY_CHAR_UUID,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
)

VENDOR_SUFFIX: Final = "-9f03-0de5-96c5-b8f4f3081186"
SERVICE_UUID: Final = VIBRADORM_SERVICE_UUID
STATUS_SERVICE_UUID: Final = VIBRADORM_SECONDARY_SERVICE_UUID
MOTOR_CHAR_UUID: Final = VIBRADORM_COMMAND_CHAR_UUID
LIGHT_CHAR_UUID: Final = VIBRADORM_LIGHT_CHAR_UUID
CBI_CHAR_UUID: Final = VIBRADORM_CBI_CHAR_UUID
RESPONSE_CHAR_UUID: Final = VIBRADORM_NOTIFY_CHAR_UUID
ED_CHAR_UUID: Final = "00001531" + VENDOR_SUFFIX
TEMPERATURE_CHAR_UUID: Final = "00001532" + VENDOR_SUFFIX
MANAGEMENT_CHAR_UUID: Final = "00001533" + VENDOR_SUFFIX

STOP: Final = 0xFF
TOGGLE: Final = 0x8000


def motor(command: int) -> bytes:
    """One motor command byte."""
    return bytes((command,))


def light(level: int, minutes: int) -> bytes:
    """A light level and its 16-bit timer minutes."""
    return bytes((level,)) + minutes.to_bytes(2, "big")


def command(word: int, parameters: bytes = b"", toggle: int = 0) -> bytes:
    """A command word, ORed with ``toggle`` (0 or ``TOGGLE``), then its parameters."""
    return (word | toggle).to_bytes(2, "big") + parameters


def parse_light(data: bytes) -> tuple[int, int]:
    """The level and timer minutes of a light frame."""
    if len(data) < 3:
        raise ValueError("Floor status requires three bytes")
    return data[0], int.from_bytes(data[1:3], "big")


def status_reply(data: bytes) -> tuple[int, bytes] | None:
    """Split a motor status reply into its flags byte and motor counts."""
    if data[:2] == b"\x20\x3f" and len(data) > 2:
        return data[2], data[3:]
    if data[:1] == b"\x3f" and len(data) > 1:
        return data[1], data[2:]
    return None


def decode_text(data: bytes) -> str:
    """Java UTF-8 decoding, whose replacement lengths include encoded surrogates."""
    parts: list[str] = []
    offset = 0
    while offset < len(data):
        remaining = data[offset:]
        try:
            parts.append(remaining.decode("utf-8"))
            break
        except UnicodeDecodeError as error:
            parts.append(remaining[: error.start].decode("utf-8"))
            consumed = error.end
            start = error.start
            if (
                remaining[start] == 0xED
                and start + 1 < len(remaining)
                and 0xA0 <= remaining[start + 1] <= 0xBF
            ):
                # Java's malformed surrogate sequence includes its valid
                # continuation bytes; CPython instead rejects the lead byte.
                consumed = start + 2
                if consumed < len(remaining) and 0x80 <= remaining[consumed] <= 0xBF:
                    consumed += 1
            parts.append("\ufffd")
            offset += consumed
    return "".join(parts)
