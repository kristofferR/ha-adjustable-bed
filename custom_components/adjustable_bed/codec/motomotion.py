"""MotoMotion wire codec, from the accepted MotoMotion 3.1.9 report (row113).

The app writes five frame forms:

- ASCII command: ``$#``, then the command, the parameter and the XOR of their
  decimal digits, each as five decimal digits, then ``R\\r``.
- Binary command: ``$#``, the command and parameter as big-endian 16-bit words,
  the XOR of those four bytes, then ``A\\r``.
- Music: ``$#``, a channel letter (M, T, B or V), two decimal digits, ``\\r``.
- Position: ``AIOK``, then head, lumbar, back, base and tilt as saturating
  big-endian 16-bit words, then ``R\\r``.
- Binding: eight raw random bytes from 0 to 254, on the binding role.

Plus two fixed frames: ``$z`` (no terminator) before the timer setting, and the
unpair command ``$#`` A(500, 12345).

Which commands a panel sends, its name flags and its timing belong to the
profile (``profiles/motomotion.py``) and the controller, never to this module.
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


TIMER_PREFIX: Final = b"$z"
UNPAIR: Final = ascii_command(500, 12345)
