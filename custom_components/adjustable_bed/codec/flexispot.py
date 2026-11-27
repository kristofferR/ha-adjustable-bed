"""Flexispot 1.1: 20-byte 9B/9D records, CRC16 over offsets 2 through 16.

No existing carrier reproduces this frame, including the unprotected alarm
slot byte. Incoming frames deliberately use the app's length/header/footer
guard, not an invented CRC or acknowledgment check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

SERVICE: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE: Final = "0000fff2-0000-1000-8000-00805f9b34fb"
NOTIFY: Final = "0000fff1-0000-1000-8000-00805f9b34fb"


def frame(opcode: int, key: int = 0, extra: Mapping[int, int] | None = None, num: int = 0) -> bytes:
    packet = bytearray(20)
    packet[0], packet[1], packet[2], packet[3], packet[19] = 0x9B, num, opcode, key, 0x9D
    for offset, value in (extra or {}).items():
        if not 4 <= offset <= 16:
            raise ValueError("Payload offsets must be 4 through 16")
        packet[offset] = value
    crc = 0xFFFF
    for value in packet[2:17]:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    packet[17:19] = crc.to_bytes(2, "little")
    return bytes(packet)


# Requests use Monday=0; wire puts Sunday at bit6 and Monday at bit0.
def flags(enabled: bool, weekdays: Sequence[int]) -> int:
    if any(type(day) is not int or day not in range(7) for day in weekdays):
        raise ValueError("Weekdays must be Monday 0 through Sunday 6")
    return (0x80 if enabled else 0) | sum(1 << day for day in set(weekdays))


@dataclass(frozen=True, slots=True)
class Alarm:
    hour: int
    minute: int
    flags: int
    pattern: int

    @property
    def valid(self) -> bool:
        return (
            0 <= self.hour <= 23
            and 0 <= self.minute <= 59
            and self.pattern in (1, 2)
            and bool(self.flags & 0x7F)
        )

    @property
    def enabled(self) -> bool:
        return bool(self.flags & 0x80)

    def fields(self) -> tuple[int, int, int, int]:
        return self.hour, self.minute, self.flags, self.pattern


def alarm(slots: tuple[Alarm, Alarm], selected: int, key: int) -> bytes:
    return frame(0x34, key, dict(enumerate((*slots[0].fields(), *slots[1].fields()), 4)), selected)


def pair(left: int, right: int) -> int:
    if left not in range(3) or right not in range(3):
        raise ValueError("Pair values must be 0, 1 or 2")
    return 1 + 3 * left + right


def unpair(value: int) -> tuple[int, int] | None:
    return divmod(value - 1, 3) if 1 <= value <= 9 else None


def snore(mask: int, angle_pair: int, sensitivity_pair: int) -> bytes:
    return frame(0x35, mask, {4: (angle_pair * 16 + sensitivity_pair) & 255})


def _signed(value: int) -> int:
    return value if value < 128 else value - 256


def _div(value: int) -> int:
    return value // 16 if value >= 0 else -(-value // 16)


@dataclass(frozen=True, slots=True)
class Status:
    light: int
    upper: int | None = None
    feet: int | None = None
    minutes: int | None = None
    mode: int | None = None
    right: int | None = None
    snore_mask: int | None = None
    angles: int | None = None
    sensitivities: int | None = None
    alarms: tuple[Alarm, Alarm] | None = None


def parse(data: bytes) -> Status | None:
    if len(data) != 20 or data[0] != 0x9B or data[-1] != 0x9D:
        return None
    if data[2] == 4:
        return Status(_signed(data[3]))
    if data[2] not in (0x26, 0x27):
        return None
    upper, right = _signed(data[4]), _signed(data[15])
    return Status(
        _signed(data[3]),
        _div(upper),
        upper - 16 * _div(upper),
        data[5],
        _signed(data[6]),
        _div(right),
        right - 16 * _div(right),
        data[16] >> 4,
        data[16] & 15,
        (Alarm(*data[7:11]), Alarm(*data[11:15])),
    )
