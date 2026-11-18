"""Ormatek notification decoding, scoped to one BLE connection."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Massage:
    timer: int
    head: int
    foot: int
    wave: int


@dataclass(frozen=True, slots=True)
class Alarm:
    enabled: bool
    hour: int
    minute: int
    slot: int = 1


def value(data: bytes, index: int, way: int) -> int:
    """The app's indexed rules, including zero defaults and fixed reads."""
    if index >= len(data):
        return 0
    if way == 1000 or index < 0 and way in (1001, 1521, 2422):
        return 0
    if index < 0:
        raise IndexError(index)
    n = data[index]
    if way == 1001:
        return n
    if way == 1521:
        return int(n not in (0, 128))
    if way == 2422:
        # The source performs these reads before returning the unchanged byte.
        for fixed in (6, 7, 4, 5):
            _ = data[fixed]
        return n
    if way == 1002:
        return int(n != 12)
    if way == 1511:
        return 3 if n & 15 > 4 else 2 if n & 15 > 2 else 1
    if way == 1512:
        return n & 15 if n & 15 <= 3 else 0
    if way == 1513:
        return n >> 4 if n >> 4 <= 4 else 0
    if way == 2411:
        return n // 3 + 1 if n else 0
    if way == 2412:
        raw = n * 256 + (data[index + 1] if index + 1 < len(data) else 0)
        return (raw + 599) // 600
    return n if way == 2413 else 0


class Parser:
    """Consumed 20-byte fragment and current-chunk dedup; no process-global cache."""

    def __init__(self, wire: str) -> None:
        self.wire = wire
        self.pending = b""
        self.last = b""

    def feed(self, chunk: bytes) -> Massage | Alarm | None:
        if len(chunk) < 3:
            return None
        packet, self.pending = self.pending + chunk, b""
        if len(chunk) == 20:
            self.pending = chunk
            return None
        if chunk == self.last:
            return None
        self.last = chunk
        if chunk[:2] == (b"\xed\xfe" if self.wire == "okin15" else b"\xa5\x0b"):
            timer = value(packet, 14, 1512) if self.wire == "okin15" else value(packet, 4, 2412)
            head = value(packet, 7, 1511 if self.wire == "okin15" else 2411)
            foot = value(packet, 8, 1511 if self.wire == "okin15" else 2411)
            wave = value(packet, 14, 1513) if self.wire == "okin15" else value(packet, 6, 2413)
            return Massage(timer, head if timer else 0, foot if timer else 0, wave if timer else 0)
        if self.wire == "okin15" and chunk[:2] == b"\xed\x80":
            return Alarm(
                value(packet, 5, 1521) == 1, value(packet, 3, 1001), value(packet, 4, 1001)
            )
        if self.wire == "okin24" and chunk[:2] in (b"\xa5\x0c", b"\xa5\x0d"):
            return Alarm(
                value(packet, 9, 2422) == 1,
                value(packet, 6, 1001),
                value(packet, 7, 1001),
                value(packet, 1, 1002) + 1,
            )
        return None
