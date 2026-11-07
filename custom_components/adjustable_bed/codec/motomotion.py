"""HHC ``$#`` wire codec: the MotoMotion, MotoSleep and Power Bob apps.

The forms come from the accepted MotoMotion 3.1.9 report (row113); MotoSleep
5.1.5 and Power Bob 2.0.3 send the ASCII, binary and letter forms. The apps
write six frame forms:

- ASCII command: ``$#``, then the command, the parameter and the XOR of their
  decimal digits, each as five decimal digits, then ``R\\r``.
- Binary command: ``$#``, the command and parameter as big-endian 16-bit words,
  the XOR of those four bytes, then ``A\\r``.
- Music: ``$#``, a channel letter (M, T, B or V), two decimal digits, ``\\r``.
- Position: ``AIOK``, then head, lumbar, back, base and tilt as saturating
  big-endian 16-bit words, then ``R\\r``.
- Binding: eight raw random bytes from 0 to 254, on the binding role.
- Letter: ``$`` and one command letter, or wrapped as ``$#$`` letter ``R\\r``.

Plus two fixed frames: the letter ``$z`` before the timer setting, and the
unpair command ``$#`` A(500, 12345).

Which commands a panel sends, its name flags and its timing belong to the
profiles (``profiles/motomotion.py``, ``profiles/motosleep.py``) and the
controllers, never to this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from operator import xor
from typing import Final


def ascii_command(command: int, parameter: int = 0) -> bytes:
    digits = str(command) + str(parameter)
    if not digits.isascii() or not digits.isdecimal():
        raise ValueError("MotoMotion ASCII fields must be nonnegative decimal integers")
    checksum = reduce(xor, (ord(c) - 48 for c in digits), 0)
    return f"$#{command:05d}{parameter:05d}{checksum:05d}R\r".encode("ascii")


def binary_command(command: int, parameter: int = 0) -> bytes:
    if command < 0:
        raise ValueError("Negative MotoMotion command")
    body = (command & 65535).to_bytes(2, "big") + (parameter & 65535).to_bytes(2, "big")
    return b"$#" + body + bytes((reduce(xor, body), 65, 13))


def music_command(letter: str, value: float) -> bytes:
    if letter not in ("M", "T", "B", "V"):
        raise ValueError("Unknown music channel")
    return f"$#{letter}{int(value):02d}\r".encode("ascii")


def u16(value: int) -> int:
    return min(65535, max(0, value))


@dataclass(frozen=True)
class Position:
    head: int
    base: int
    back: int
    lumbar: int
    tilt: int

    def to_bytes(self) -> bytes:
        return (
            b"AIOK"
            + b"".join(
                u16(v).to_bytes(2, "big")
                for v in (self.head, self.lumbar, self.back, self.base, self.tilt)
            )
            + b"R\r"
        )


def binding_code(draws: Iterable[int]) -> bytes:
    """The binding frame: the app's eight random draws, each 0..254, as raw bytes."""
    code = bytes(draws)
    if len(code) != 8 or max(code) > 254:
        raise ValueError("A MotoMotion binding code is eight bytes from 0 to 254")
    return code


def letter_command(letter: str, *, wrapped: bool = False) -> bytes:
    if len(letter) != 1 or not letter.isascii():
        raise ValueError("An HHC letter command is one ASCII character")
    frame = b"$" + letter.encode("ascii")
    return b"$#" + frame + b"R\r" if wrapped else frame


TIMER_PREFIX: Final = letter_command("z")
UNPAIR: Final = ascii_command(500, 12345)
