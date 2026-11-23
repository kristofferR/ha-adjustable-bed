"""Relax Motion's serial/PID and new-box frames, including its literal release.

P1 uses the proven CheersSleep serial/PID carrier. P2 has an unaddressed
parameter byte and a five-zero release, unlike CheersSleep's side controls.
"""

from __future__ import annotations

from typing import Final

from .cheerssleep import p1 as p1

SERVICE: Final = "6e403587-b5a3-f393-e0a9-e50e24dcca9e"
P2_RELEASE: Final = bytes(5)


def normal(mask: int, parameter: int = 0) -> bytes:
    return (
        bytes((0xEE, 1, 5))
        + (mask & 0xFFFFFFFF).to_bytes(4, "big")
        + bytes((parameter & 255, 0xC0))
    )


def extra(command: int, tag: int, value: int = 0) -> bytes:
    return (
        bytes((0xEE, 2, 5, command & 255))
        + (tag & 0xFFFFFF).to_bytes(3, "big")
        + bytes((value & 255, 0xC0))
    )


def sleep_state(data: bytes) -> bool | None:
    """Only CID 1201 is consumed; short unrelated notifications are ignored."""
    if len(data) < 4 or int.from_bytes(data[2:4], "little") != 0x1201:
        return None
    return len(data) >= 8 and data[1] == 0x82 and 0 < int.from_bytes(data[4:8], "little") < 4
