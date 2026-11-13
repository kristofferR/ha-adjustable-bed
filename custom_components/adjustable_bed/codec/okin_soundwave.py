"""Okin AA/2A records, proven by Symphony Sleep Sense 2.8.0 (194).

Each operation has its own payload. The six-byte header is marker, two zero
bytes, domain, operation and a size field. There is no checksum. App meaning,
numeric transforms, scheduling and admissible operations belong to profiles.
"""

from __future__ import annotations

from collections.abc import Sequence


def record(
    domain: int,
    operation: int,
    fields: Sequence[int],
    *,
    query: bool = False,
    size: int | None = None,
) -> bytes:
    """Encode a write (AA) or query (2A), preserving all payload bytes."""
    if len(fields) > 255:
        raise ValueError("A SoundWave record has at most 255 payload bytes")
    return bytes(
        (
            0x2A if query else 0xAA,
            0,
            0,
            domain,
            operation,
            len(fields) if size is None else size,
            *fields,
        )
    )


def movement(mask: int, second_mask: int = 0) -> bytes:
    """Four-byte motor payload; the second byte carries the fifth actuator."""
    return record(1, 1, (mask, second_mask, 0, 0))


def preset(index: int, *, save: bool = False) -> bytes:
    """Recall or program an app-selected preset index."""
    return record(1, 5 if save else 3, (index,))


def query(domain: int, fields: Sequence[int] = ()) -> bytes:
    """Read one source-defined domain."""
    return record(domain, 0x81, fields, query=True)
