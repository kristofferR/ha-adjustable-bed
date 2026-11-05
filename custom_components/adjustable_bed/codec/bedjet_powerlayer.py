"""BedJet PowerLayer wire codec.

Every command is two bytes, ``01 <key>``: ``01`` is the only command opcode the
frame accepts, and the second byte names a remote key. The protocol defines no
STOP frame. Status is a 20-byte frame, read or notified, whose bytes 12-13 are
the head and bytes 14-15 the foot actuator count, each big-endian.

Which keys a frame accepts, its count-to-degree calibration and its timing
belong to the profile (``profiles/bedjet_powerlayer.py``), never to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..const import (
    BEDJET_POWERLAYER_COMMAND_CHAR_UUID,
    BEDJET_POWERLAYER_NAME_CHAR_UUID,
    BEDJET_POWERLAYER_SERVICE_UUID,
    BEDJET_POWERLAYER_STATUS_CHAR_UUID,
)


@dataclass(frozen=True)
class Transport:
    """GATT roles of the frame's one service."""

    service_uuid: str
    name_uuid: str
    status_uuid: str
    command_uuid: str


TRANSPORT: Final = Transport(
    BEDJET_POWERLAYER_SERVICE_UUID,
    BEDJET_POWERLAYER_NAME_CHAR_UUID,
    BEDJET_POWERLAYER_STATUS_CHAR_UUID,
    BEDJET_POWERLAYER_COMMAND_CHAR_UUID,
)

BUTTON: Final = 0x01
STATUS_LENGTH: Final = 20
_HEAD: Final = slice(12, 14)
_FOOT: Final = slice(14, 16)


def command(key: int) -> bytes:
    """Encode one remote key as a BUTTON command."""
    if not 0 <= key <= 0xFF:
        raise ValueError(f"invalid PowerLayer key {key:#x}")
    return bytes((BUTTON, key))


def positions(frame: bytes) -> tuple[int, int] | None:
    """Return the head and foot actuator counts, or None for a short frame."""
    if len(frame) < STATUS_LENGTH:
        return None
    return int.from_bytes(frame[_HEAD], "big"), int.from_bytes(frame[_FOOT], "big")
