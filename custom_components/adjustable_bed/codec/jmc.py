"""JMC400 wire codec: the control box the Jensen and Svane Remote apps drive.

One characteristic carries commands and reports. A frame is an opcode and its
payload, with no length or checksum:

- ``0A 00 00 00 00`` requests the config report;
- ``10 code 00 00 00 00`` moves and recalls. ``code`` combines one head bit
  (``01`` up, ``02`` down) and one foot bit (``10`` up, ``20`` down); ``00`` is
  STOP, ``81`` flat, ``40`` and ``80`` save and recall the box's memory, and
  ``FF`` asks for a position report;
- ``10 04`` + four position bytes goes to a position, as a report carries it;
- ``12 head foot wave 00 00`` sets the massage levels, with no timer;
- ``13 02 level`` + three bytes sets light output 2;
- ``14 level`` + four bytes sets the fan;
- ``1E`` + four PIN digits, one per byte, unlocks the box.

The box answers on the same characteristic: ``10 state`` + four position bytes,
``0A`` with its config and ``1E`` with the PIN result. The bytes after a light
or fan level belong to the app's profile (``profiles/jmc.py``); which commands
an app sends, its PIN and its timing belong to its controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..const import JENSEN_CHAR_UUID, JENSEN_SERVICE_UUID

SERVICE_UUID: Final = JENSEN_SERVICE_UUID
CHAR_UUID: Final = JENSEN_CHAR_UUID
"""Commands and reports."""

CONFIG: Final = 0x0A
MOTION: Final = 0x10
MASSAGE: Final = 0x12
LIGHT: Final = 0x13
FAN: Final = 0x14
PIN: Final = 0x1E

# Codes of a ``10`` frame.
STOP: Final = 0x00
HEAD_UP: Final = 0x01
HEAD_DOWN: Final = 0x02
GOTO: Final = 0x04
FOOT_UP: Final = 0x10
FOOT_DOWN: Final = 0x20
MEMORY_SAVE: Final = 0x40
MEMORY_RECALL: Final = 0x80
FLAT: Final = 0x81
"""Jensen's flat; Svane Remote sends it as its unnamed Svane position."""
POSITION_QUERY: Final = 0xFF
"""No app sends it; the box answers it with a position report (#631)."""

LIGHT_OUTPUT: Final = 0x02
"""The apps drive every light kind through output 2."""

CONFIG_REQUEST: Final = bytes((CONFIG, 0, 0, 0, 0))


def command(code: int) -> bytes:
    """A ``10`` frame: STOP, a motion mask, a preset or the position query."""
    return bytes((MOTION, code, 0, 0, 0, 0))


def motion(head: bool | None, foot: bool | None) -> bytes:
    """Held motion; an idle section is ``None``, and both idle is STOP."""
    if (head is not None and type(head) is not bool) or (
        foot is not None and type(foot) is not bool
    ):
        raise ValueError("Axis intent must be boolean or absent")
    return command(
        (0 if head is None else HEAD_UP if head else HEAD_DOWN)
        | (0 if foot is None else FOOT_UP if foot else FOOT_DOWN)
    )


def goto(position: bytes) -> bytes:
    """Go to four position bytes, as a ``10`` report carries them."""
    if len(position) != 4:
        raise ValueError("A JMC400 position is four bytes")
    return bytes((MOTION, GOTO)) + position


def position(head: int, foot: int) -> bytes:
    """Head and foot as a JMC400 reports them: unsigned 16-bit little-endian (#631).

    The apps keep the four bytes opaque; a JMC400 capture gives their order.
    """
    return head.to_bytes(2, "little") + foot.to_bytes(2, "little")


def head_foot(position: bytes) -> tuple[int, int]:
    """Read four position bytes as head and foot; see ``position()``."""
    return int.from_bytes(position[:2], "little"), int.from_bytes(position[2:4], "little")


def massage(head: int, foot: int, wave: int) -> bytes:
    """Massage levels; 0 turns that part off."""
    return bytes((MASSAGE, head, foot, wave, 0, 0))


def light(level: int, tail: bytes) -> bytes:
    """Light output 2 at ``level``, then the app's three bytes."""
    return bytes((LIGHT, LIGHT_OUTPUT, level)) + tail


def fan(level: int, tail: bytes) -> bytes:
    """The fan at ``level``, then the app's four bytes."""
    return bytes((FAN, level)) + tail


def pin(digits: str) -> bytes:
    """Unlock with decimal digits, one per byte."""
    return bytes((PIN, *(int(digit) for digit in digits)))


@dataclass(frozen=True, slots=True)
class PositionReport:
    """``10 state`` + four position bytes: state ``00`` is idle, ``FF`` a query's reply."""

    state: int
    position: bytes


def position_report(data: bytes | bytearray) -> PositionReport | None:
    """Decode a position report; anything else, or shorter than six bytes, is ``None``."""
    if len(data) >= 6 and data[0] == MOTION:
        return PositionReport(data[1], bytes(data[2:6]))
    return None
