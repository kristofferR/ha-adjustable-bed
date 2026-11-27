"""M3 Ambient P2 additive-checksum climate commands and reports."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

from .ambient import signed

_HEADER: Final = bytes.fromhex("51 9F")

type Zones = tuple[int, int, int, int, int, int]


class Query(IntEnum):
    HEAT_ZONES = 3
    POWER_SUPPLY = 4
    LEFT_FAN = 8
    RIGHT_FAN = 9
    FIRMWARE = 34


@dataclass(frozen=True, slots=True)
class Heat:
    zones: Zones


@dataclass(frozen=True, slots=True)
class Fan:
    code: Query
    raw: int

    @property
    def level(self) -> int:
        return int(self.raw / 5)


@dataclass(frozen=True, slots=True)
class Supply:
    source: str


@dataclass(frozen=True, slots=True)
class Firmware:
    version: int


def _frame(*body: int) -> bytes:
    packet = _HEADER + bytes(body)
    return packet + bytes((sum(packet) & 0xFF,))


def query(code: int) -> bytes:
    return _frame(3, 1, code)


def heat(zones: Zones) -> bytes:
    return _frame(1, 8, Query.HEAT_ZONES, 6, *zones)


def fan(code: Query, level: int) -> bytes:
    if code not in (Query.LEFT_FAN, Query.RIGHT_FAN) or not 0 <= level <= 10:
        raise ValueError("Expected a ventilation channel and a level from 0 to 10")
    return _frame(1, 3, code, 1, 5 * level)


def heat_timer(hours: int) -> bytes:
    return _frame(0x55, 3, 0xAA, 1, hours)


def parse(data: bytes) -> Heat | Fan | Supply | Firmware | None:
    if not data.startswith(_HEADER) or len(data) < 8:
        return None
    if data[2] == 6 and len(data) in (8, 10):
        components = data[-5:-1]
        return Firmware(
            sum(
                signed(value) * weight
                for value, weight in zip(components, (1_000_000, 10_000, 100, 1), strict=True)
            )
        )
    # The typed climate path checks the sum. Require the complete reply shape
    # before accepting six zones as a snapshot to preserve in a later write.
    if data[-1] != sum(data[:-1]) & 0xFF or data[2] != 2:
        return None
    if len(data) == 13 and data[3:6] == bytes((8, Query.HEAT_ZONES, 6)):
        a, b, c, d, e, f = data[6:12]
        return Heat((a, b, c, d, e, f))
    if len(data) == 8 and data[3] == 3 and data[5] == 1:
        code, value = data[4], data[6]
        if code == Query.POWER_SUPPLY and value in (0, 1):
            return Supply(("AC", "DC")[value])
        if code in (Query.LEFT_FAN, Query.RIGHT_FAN):
            return Fan(Query(code), signed(value))
    return None
