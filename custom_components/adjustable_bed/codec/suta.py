"""SUTA P1 text and P2 additive-sum frames, accepted unit128."""

from __future__ import annotations


def text(command: str) -> bytes:
    """Encode a complete application command, without escaping or segmentation."""
    return (command + "\r\n").encode("utf-8")


def binary(group: int, operation: int, payload: bytes) -> bytes:
    """Build the proven 53 59 / length / payload / sum8 / 54 43 format."""
    if len(payload) > 255:
        raise ValueError("SUTA's accepted payload length is one byte")
    prefix = bytes((0x53, 0x59, group, operation, 0, len(payload))) + payload
    return prefix + bytes((sum(prefix) & 255, 0x54, 0x43))


def from_prefix(prefix: bytes) -> bytes:
    """Encode a frozen constructor prefix through the common builder."""
    if len(prefix) < 6 or prefix[:2] != b"\x53\x59" or prefix[4:6] != bytes((0, len(prefix) - 6)):
        raise ValueError("Invalid SUTA constructor prefix")
    return binary(prefix[2], prefix[3], prefix[6:])
