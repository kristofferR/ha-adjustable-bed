"""Kaidi mesh wire codec.

The Rize, Floyd Home and ISleep apps (``com.kaidi_test4.*``) drive one PairLink
mesh-over-GATT frame set through one write and one notify characteristic.
Session frames join a room and find the bed's virtual address; every bed
command is a control frame addressed to that virtual address:

- join: ``01 16 01 room password``
- enrollment of an unprovisioned bed: ``01 03 room password 00 00 00 00``
- ping: ``03 FF FF FF FF FE own``
- control: ``03 target 20 own`` then the payload ``01 command parameter 00``

Rooms and virtual addresses are 32-bit little-endian; a negative value is sent
as a Java int's two's complement. The password is ASCII ``1122``. There is no
checksum, sequence number or fragmentation. Which commands, parameters, session
rules and timing an app uses belongs to its profile (``profiles/kaidi.py``),
never to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..const import KAIDI_MESH_SERVICE_UUID, KAIDI_NOTIFY_CHAR_UUID, KAIDI_WRITE_CHAR_UUID

SERVICE_UUID: Final = KAIDI_MESH_SERVICE_UUID
WRITE_CHAR_UUID: Final = KAIDI_WRITE_CHAR_UUID
NOTIFY_CHAR_UUID: Final = KAIDI_NOTIFY_CHAR_UUID

PASSWORD: Final = b"1122"
BROADCAST: Final = 0xFFFFFFFF
"""The all-nodes address, and the own address of a phone the bed has not named."""
CONTROL_CHANNEL: Final = 0x20
PING_CHANNEL: Final = 0xFF
_PING: Final = 0xFE


def _le32(value: int) -> bytes:
    return value.to_bytes(4, "little", signed=value < 0)


def join(room: int) -> bytes:
    """Join a provisioned bed's room."""
    return b"\x01\x16\x01" + _le32(room) + PASSWORD


def enroll(room: int) -> bytes:
    """Assign an unprovisioned bed to a room."""
    return b"\x01\x03" + _le32(room) + PASSWORD + bytes(4)


def ping(own: int) -> bytes:
    """Ask every node for its virtual address."""
    return b"\x03" + _le32(BROADCAST) + bytes((_PING,)) + _le32(own)


def payload(command: int, parameter: int = 0, parameter2: int = 0) -> bytes:
    """The four-byte command payload a control frame carries."""
    return bytes((0x01, command, parameter, parameter2))


def control(
    target: int, own: int, command: int, parameter: int = 0, parameter2: int = 0
) -> bytes:
    """Send ``command`` from ``own`` to the node at ``target``."""
    return (
        b"\x03"
        + _le32(target)
        + bytes((CONTROL_CHANNEL,))
        + _le32(own)
        + payload(command, parameter, parameter2)
    )


def node_address(data: bytes) -> str:
    """Format a six-byte node address, sent least significant byte first, as a MAC."""
    if len(data) != 6:
        raise ValueError(f"Kaidi node address must be 6 bytes, got {len(data)}")
    return ":".join(f"{byte:02X}" for byte in reversed(data))


@dataclass(frozen=True, slots=True)
class JoinReply:
    """``02 16 status``: status 0 accepts the join. ``None`` when the status byte is missing."""

    status: int | None


@dataclass(frozen=True, slots=True)
class EnrollReply:
    """``02 03 status``: status 0 accepts the enrollment."""

    status: int


@dataclass(frozen=True, slots=True)
class OwnAddress:
    """``01 0A`` + LE32: the phone's own virtual address; zero means none was assigned."""

    vaddr: int


@dataclass(frozen=True, slots=True)
class RosterChange:
    """``01 02`` with the node count at bytes 8-9 (LE): known addresses are stale."""

    count: int


@dataclass(frozen=True, slots=True)
class PingReply:
    """Channel ``FF``: a node's MAC (bytes 6-11) and virtual address (bytes 12-15)."""

    node: str
    vaddr: int

    @property
    def signed_vaddr(self) -> int:
        """The address as the apps' Java int."""
        return self.vaddr - (1 << 32) if self.vaddr & 0x80000000 else self.vaddr


@dataclass(frozen=True, slots=True)
class ControlReply:
    """Channel ``20`` from a node: the command byte (11) and its value (12)."""

    command: int
    value: int


type Notification = JoinReply | EnrollReply | OwnAddress | RosterChange | PingReply | ControlReply


def parse_notification(data: bytes) -> Notification | None:
    """Decode one notification; anything else, or too short, is ``None``."""
    head = data[:2]
    if head == b"\x02\x16":
        return JoinReply(data[2] if len(data) > 2 else None)
    if head == b"\x02\x03" and len(data) >= 3:
        return EnrollReply(data[2])
    if head == b"\x01\x0a" and len(data) >= 6:
        return OwnAddress(int.from_bytes(data[2:6], "little"))
    if head == b"\x01\x02" and len(data) >= 10:
        return RosterChange(int.from_bytes(data[8:10], "little"))
    if data[:1] == b"\x03" and len(data) >= 16 and data[5] == PING_CHANNEL:
        return PingReply(node_address(data[6:12]), int.from_bytes(data[12:16], "little"))
    if data[:1] == b"\x03" and len(data) >= 14 and data[5] == CONTROL_CHANNEL:
        return ControlReply(data[11], data[12])
    return None
