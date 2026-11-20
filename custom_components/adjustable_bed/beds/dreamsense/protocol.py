"""Dream Sense special records, all carried by the Richmat wire codec."""

from __future__ import annotations

from ...codec import richmat as codec


def split_mode(mode: int) -> bytes:
    return codec.record_20_len(0x0B, 2, 1, (0, mode))


def split_query() -> bytes:
    return codec.record_20_len(0x0B, 2, 0, (0,))


def alarm_list() -> bytes:
    return codec.record_20_len(5, 1, 0, (0,))


def alarm_add(
    number: int, repeat: int, mode: int, hour: int, minute: int, second: int = 0
) -> bytes:
    return codec.record_20_len(5, 1, 1, (number, repeat, mode, hour, minute, second))


def alarm_delete(number: int) -> bytes:
    return codec.record_20_len(5, 2, 1, (number,))


def light_seconds(seconds: int) -> bytes:
    return codec.light_timer(seconds >> 8, seconds) if seconds else codec.light_timer(255, 255)
