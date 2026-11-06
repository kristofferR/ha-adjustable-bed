"""Casper 6E wire codec: the Casper Base and Hush Base apps' frames.

Both apps ship the same Richmat library builders (Casper Base 1.0.8, row101;
Hush Base 1.0.5, row126). Every frame ends in the low byte of the sum of the
bytes before it:

- Command: ``6E 01 side opcode sum``, or the bare opcode on Nordic UART.
  The library's fixed commands are STOP ``6E``, light off ``75``, the
  anti-snore preset ``46`` and the music Bluetooth switch ``D8``.
- Query: ``6E 02 01 00`` (exit limit), ``6E 08 01 01`` (clock),
  ``6E 0A 00 01`` (light) and ``6E 15 01 01`` (music).
- Extended record: ``6E 20 len category subtype operation values sum``, where
  ``len`` counts the whole frame. The Richmat 6E codec builds ``6E len 20``
  records instead, so these apps have their own codec.
- Light timer ``6E 0B high low``, colour ``6E 0C FF R`` then ``6E 0D G B``,
  and the single alarm ``6E 06 high mode`` with ``6E 05 low 00``.
- Clock: the extended record 8/3 with the local calendar.

Which opcodes a product's controls send, its pages and gestures belong to its
profile (``profiles/casper.py`` or ``profiles/hush.py``), never to this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

GATT: Final = (
    ("6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e"),
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600"),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622"),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe2-0000-1000-8000-00805f9b34fb"),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb"),
    ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "00000002-3c17-d293-8e48-14fe2e4da212"),
)
STOP: Final = 0x6E
LIGHT_OFF: Final = 0x75
# Sent on the default side when an external detector reports snoring.
ANTI_SNORE: Final = 0x46
MUSIC_BLUETOOTH: Final = 0xD8
SPECIAL: Final = {
    "exit_limit": (0x6E, 2, 1, 0),
    "clock": (0x6E, 8, 1, 1),
    "light": (0x6E, 10, 0, 1),
    "music": (0x6E, 21, 1, 1),
}


def frame(values: Sequence[int]) -> bytes:
    return bytes((*[value & 255 for value in values], sum(values) & 255))


def control(opcode: int, *, single: bool = False, side: int = 0) -> bytes:
    return bytes((opcode,)) if single else frame((0x6E, 1, side, opcode))


def special(name: str, *, single: bool = False) -> bytes:
    values = SPECIAL[name]
    return bytes((values[-1],)) if single else frame(values)


def extra(category: int, subtype: int, values: Sequence[int], operation: int = 1) -> bytes:
    return frame((0x6E, 0x20, 7 + len(values), category, subtype, operation, *values))


def light_seconds(seconds: int) -> bytes:
    # The app slices a padded hexadecimal string, including its zero sentinel.
    text = format(seconds, "x").rjust(4, "0")
    high, low = int(text[:2], 16), int(text[2:4], 16)
    if high == low == 0:
        high = low = 255
    return frame((0x6E, 11, high, low))


def light_rgb(rgb: tuple[int, int, int]) -> bytes:
    red, green, blue = rgb
    return frame((0x6E, 12, 255, red)) + frame((0x6E, 13, green, blue))


def alarm_pair(minutes: int, mode: int) -> tuple[bytes, bytes]:
    return frame((0x6E, 6, minutes // 256, mode)), frame((0x6E, 5, minutes & 255, 0))


def time_sync(now: datetime) -> bytes:
    return extra(8, 3, (now.year - 1970, now.month, now.day, now.hour, now.minute, now.second))
