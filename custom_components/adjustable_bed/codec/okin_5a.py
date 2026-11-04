"""Okin 5A wire codec.

Every command is one 7-byte key frame: ``5A 01 03 10 page key A5``. There is no
checksum. Page ``30`` holds the normal keys; page ``40`` repeats some of them for
an alternate use (Mattress Firm massage intensity). A STOP is the page-30 key
``0F``. Two connection frames do not follow the key frame: the 4-byte wake
``5A 0B 00 A5`` and the Mattress Firm handshake ``09 05 0A 23 05 00 00``.

Which keys, transport, write mode and timing a bed uses belongs to its profile
(``profiles/okin_5a.py``), never to this module.
"""

from __future__ import annotations

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


def command(key: int, page: int = NORMAL) -> bytes:
    """Encode one key frame."""
    if not 0 <= key <= 0xFF or page not in (NORMAL, ALTERNATE):
        raise ValueError(f"invalid key {key:#x} on page {page:#x}")
    return bytes((0x5A, 0x01, 0x03, 0x10, page, key, 0xA5))


STOP: Final = command(0x0F)
WAKE: Final = bytes.fromhex("5A0B00A5")
MATTRESSFIRM_HANDSHAKE: Final = bytes.fromhex("09050A23050000")
CONNECTION_FRAMES: Final = frozenset({WAKE, MATTRESSFIRM_HANDSHAKE})
