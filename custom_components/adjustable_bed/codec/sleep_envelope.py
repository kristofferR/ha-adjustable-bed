"""Sleep-sensor JSON envelope codec.

The Casper Base, Hush Base, GM Control and Good Vibe Sleep sensors send UTF-8
JSON behind one 14-byte header, with no checksum:

``00 request_id total sequence (length+7) 00 00 11 03 43 55 44 length_lo length_hi``

Every header byte keeps only its low eight bits. Receivers size a response from
its first notification's low length byte alone, so a body over 255 bytes
completes early, and strip ``HEADER_SIZE`` bytes from every SXB report chunk.
The JSON body, request numbering, length limits and report transfer belong to
each app's module, never to this one.
"""

from __future__ import annotations

from typing import Final

HEADER_SIZE: Final = 14
LENGTH_OFFSET: Final = 12
"""Where the little-endian body length starts: the header's last two bytes."""


def frame(body: bytes, request_id: int, *, total: int = 1, sequence: int = 0) -> bytes:
    """Frame a JSON body; an empty body frames to nothing (GM Control's source)."""
    if not body:
        return b""
    size = len(body)
    header = (0, request_id, total, sequence, size + 7, 0, 0, 0x11, 0x03, 0x43, 0x55, 0x44)
    return bytes(value & 0xFF for value in (*header, size, size >> 8)) + body


def response_size(first: bytes) -> int | None:
    """Return a response's whole size from its first chunk, or None before the length byte."""
    return first[LENGTH_OFFSET] + HEADER_SIZE if len(first) > LENGTH_OFFSET else None
