"""Rebuild a Casper 6E frame through ``codec/casper.py`` from its own bytes."""

from __future__ import annotations

from custom_components.adjustable_bed.codec import casper as codec

_QUERIES = {bytes(values[:4]): name for name, values in codec.SPECIAL.items()}


def rebuild(frame: bytes) -> bytes:
    """Decode one write by its form and encode it again through the codec."""
    if len(frame) == 1:
        return codec.control(frame[0], single=True)
    # The colour write carries two frames, each with its own checksum.
    if frame[0] != 0x6E or (len(frame) != 10 and codec.frame(frame[:-1]) != frame):
        raise AssertionError(f"not a Casper frame: {frame.hex()}")
    kind = frame[1]
    if kind == 0x01:
        return codec.control(frame[3], side=frame[2])
    if (name := _QUERIES.get(frame[:4])) is not None:
        return codec.special(name)
    if kind == 0x0B:
        high, low = frame[2], frame[3]
        return codec.light_seconds(0 if high == low == 0xFF else high << 8 | low)
    if kind == 0x0C:
        return codec.light_rgb((frame[3], frame[7], frame[8]))
    if kind == 0x06:
        return codec.alarm_pair(frame[2] << 8, frame[3])[0]
    if kind == 0x05 and frame[3] == 0:
        return codec.alarm_pair(frame[2], 0)[1]
    if kind == 0x20 and frame[2] == len(frame):
        return codec.extra(frame[3], frame[4], frame[6:-1], operation=frame[5])
    raise AssertionError(f"no Casper builder sends {frame.hex()}")
