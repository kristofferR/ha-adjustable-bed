"""Okin ORE wire codec.

Every frame is ``A5 5A checksum 00 length command_hi command_lo``, followed by
``length`` parameter bytes. The checksum is the complement of the low byte of
the sum of every byte after it. Nerum also carries parameter bytes.

Which commands a bed sends belongs to its controller or route table, never to
this module.
"""

from __future__ import annotations


def frame(command: int, payload: bytes = b"") -> bytes:
    """Encode a 16-bit command and its parameter bytes."""
    if isinstance(command, bool) or not isinstance(command, int) or not 0 <= command <= 0xFFFF:
        raise ValueError("Command must be an unsigned 16-bit integer")
    body = bytes((0x00, len(payload) & 0xFF)) + command.to_bytes(2, "big") + payload
    return bytes((0xA5, 0x5A, ~sum(body) & 0xFF)) + body
