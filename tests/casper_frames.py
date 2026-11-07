"""Rebuild a Casper Base or Hush Base frame through ``codec/richmat.py`` from its own bytes."""

from __future__ import annotations

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.casper import QUERIES, light_duration

_QUERIES = {codec.function(code, action=action)[:4]: (action, code) for action, code in QUERIES}


def rebuild(frame: bytes) -> bytes:
    """Decode one write by its form and encode it again through the builder the apps use."""
    if len(frame) == 1:
        return codec.function(frame[0], single=True)
    # The colour write carries two frames, each with its own checksum.
    if frame[0] != codec.BED or (len(frame) != 10 and not codec.is_valid(frame)):
        raise AssertionError(f"not a Casper Base frame: {frame.hex()}")
    kind = frame[1]
    if kind == 0x01:
        return codec.function(frame[3], frame[2])
    if (query := _QUERIES.get(frame[:4])) is not None:
        action, code = query
        return codec.function(code, action=action)
    if kind == 0x0B:
        high, low = frame[2], frame[3]
        return codec.light_timer(*light_duration(0 if high == low == 0xFF else high << 8 | low))
    if kind == 0x0C:
        return codec.rgb(frame[3], frame[7], frame[8])
    if kind == 0x06:
        return codec.countdown(frame[2] << 8, frame[3])[1]
    if kind == 0x05 and frame[3] == 0:
        return codec.countdown(frame[2], 0)[0]
    if kind == 0x20 and frame[2] == len(frame):
        return codec.record_20_len(frame[3], frame[4], frame[5], frame[6:-1])
    raise AssertionError(f"no Casper Base builder sends {frame.hex()}")
