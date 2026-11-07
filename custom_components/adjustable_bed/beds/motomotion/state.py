"""Ordered singleton stores and asynchronous event consumers for MotoMotion."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .motomotion_protocol import decimal
from .profiles.motomotion import name_character


@dataclass(frozen=True)
class Comfort:
    flag: bool = False
    heat: int = 0
    massage: int = 0
    field_1b: int = 0
    calibrated: bool = False


class State:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.token_count = 0
        self.rgb = ("0", "0", "0")
        self.d: tuple[str, str] | None = None
        self.cm: Comfort | None = None
        self.left: Comfort | None = None
        self.right: Comfort | None = None
        self.hsw: tuple[bool, int] | None = None

    def feed(self, data: bytes, name: str, emit: Callable[[str], None]) -> None:
        self.buffer.extend(data)
        try:
            start = self.buffer.index(36)
        except ValueError:
            self.buffer.clear()
            return
        del self.buffer[:start]
        try:
            end = self.buffer.index(13, 1)
        except ValueError:
            return
        body = bytes(self.buffer[1:end])
        self.buffer.clear()  # Source discards coalesced suffix, before parsing.
        self.parse(body, name, emit)

    def parse(self, body: bytes, name: str, emit: Callable[[str], None]) -> None:
        tokens = re.sub("[^0-9 ]", "", body.decode("latin1")).strip().split(" ")
        n = self.token_count = len(tokens)

        def number(index: int) -> int:
            return decimal(tokens[index])

        def rgb(a: int, b: int, c: int) -> None:
            self.rgb = (tokens[a], tokens[b], tokens[c])

        if n == 24:
            rgb(11, 12, 13)
            emit("OK")
        if n in (11, 16):
            if name_character(name, 10) == "M":
                rgb(0, 1, 2)
                self.cm = Comfort(False, number(3) // 30, number(4))
                emit("OK")
            else:
                self.left = Comfort(False, number(3) // 30, number(4))
                self.right = Comfort(False, number(8) // 30, number(9))
                emit("LR")
        if n in (38, 43):
            self.d = (tokens[1], tokens[0])
            rgb(11, 12, 13)
            emit("OK")
        if n == 31:
            self.d = (tokens[1], tokens[0])
            rgb(27, 28, 29)
            emit("OK")
        if n == 43:
            self.d = (tokens[1], tokens[0])
            rgb(11, 12, 13)
            emit("OK")
        if n in (37, 42):
            self.d = ("0", tokens[35])
            heat, massage, other = number(26) // 30, number(35), number(23)
            self.cm = Comfort(False, heat, massage, other)
            rgb(11, 12, 13)
            emit("OK")
        if n == 50:
            flag = number(11) > 925
            a, b, c = number(12), number(13), number(14)
            if a == b == c:
                self.hsw = (flag, 0 if a == 0 else a - 1)
            rgb(12, 13, 14)
            emit("OK")
        if n == 62:
            a, heat, massage = number(14), number(25) // 40, number(28)
            calibration = [number(i) for i in range(19, 25)]
            comparison, other = number(48), number(30)
            self.cm = Comfort(
                a >= comparison, heat, massage, other, all(v == 0 for v in calibration)
            )
            emit("OK")
        if n in (71, 39):
            a, heat, massage, other = number(4), number(33) // 30, number(16), number(30)
            self.cm = Comfort(a >= 500, heat, massage, other, True)
            rgb(18, 19, 20)
            emit("OK")
