"""P1 framing for the Langjue Comfort Smart Bed."""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Final


class Op(IntEnum):
    MOTION = 0x01
    PRESET = 0x02
    SAVE = 0x04
    LIGHT = 0x10
    READ_LIGHT = 0x18
    MASSAGE_LEVEL = 0x20
    MASSAGE_PATTERN = 0x21
    MASSAGE_TIMER = 0x22
    READ_MASSAGE_LEVEL = 0x28
    READ_MASSAGE_TIME = 0x29
    READ_MASSAGE_STATE = 0x2A
    CLOCK = 0x30
    WRITE_ALARM = 0x31
    READ_ALARM = 0x32
    HANDSHAKE = 0x81
    VERSION = 0x82
    RELEASE_DATE = 0x83


NEUTRAL: Final = 0x83


def frame(op: Op, argument: int = 0, payload: bytes = b"", *, vector_size: int = 0) -> bytes:
    """Encode the P1 payload sum and the caller's two explicit header fields."""
    return bytes((0x55, sum(payload) & 0xFF, vector_size, 0, op, argument)) + payload


def handshake() -> bytes:
    return frame(Op.HANDSHAKE, 8, bytes.fromhex("000200007efa1cf7"))


def motion(count: int, axis: int | None = None, *, up: bool = False) -> bytes:
    if not 1 <= count <= 99 or axis is not None and not 0 <= axis < count:
        raise ValueError("Invalid Langjue motion vector")
    payload = bytearray([NEUTRAL] * count)
    if axis is not None:
        payload[axis] = 0x85 if up else 0x68
    return frame(Op.MOTION, 1, bytes(payload), vector_size=count)


def preset(mode: int, *, save: bool = False) -> bytes:
    return frame(Op.SAVE if save else Op.PRESET, 1, bytes((mode,)))


def light(enabled: bool) -> bytes:
    return frame(Op.LIGHT, 1, bytes((1 if enabled else 2,)))


def massage_level(zone: int, level: int) -> bytes:
    if zone not in (1, 2) or level not in range(4):
        raise ValueError("Choose head or foot and a level from 0 to 3")
    return frame(Op.MASSAGE_LEVEL, 2, bytes((zone, level)))


def clock(now: datetime) -> bytes:
    return frame(Op.CLOCK, 4, bytes((now.weekday(), now.hour, now.minute, now.second)))


def alarm(action: int, weekdays: tuple[int, ...], hour: int, minute: int) -> bytes:
    if (
        action not in range(3, 13)
        or any(day not in range(7) for day in weekdays)
        or len(set(weekdays)) != len(weekdays)
        or hour not in range(24)
        or minute not in range(60)
    ):
        raise ValueError("Invalid Langjue alarm")
    return frame(
        Op.WRITE_ALARM,
        8,
        bytes(
            (0, 1, 2 if weekdays else 1, action, sum(1 << day for day in weekdays), hour, minute, 0)
        ),
    )


def alarm_enabled(payload: bytes, enabled: bool) -> bytes:
    """Edit the live reply without reconstructing its other fields."""
    if len(payload) != 8 or payload[1] not in (0, 1):
        raise ValueError("The bed did not report a recognized alarm record")
    return frame(Op.WRITE_ALARM, 8, payload[:1] + bytes((int(enabled),)) + payload[2:])


@dataclass(frozen=True, slots=True)
class Notification:
    op: Op
    payload: bytes

    @property
    def decimal_value(self) -> int | None:
        """The app parses these hex-formatted tokens as decimal digits."""
        token = f"{self.payload[0]:02x}" if self.payload else ""
        return int(token) if token.isdecimal() else None

    @property
    def massage_level(self) -> tuple[str, int] | None:
        if self.op is not Op.READ_MASSAGE_LEVEL or len(self.payload) < 2:
            return None
        return ("head" if self.payload[0] == 1 else "foot", self.payload[1])


def notification(data: bytes) -> Notification | None:
    """Dispatch by opcode without applying the outbound checksum to replies."""
    if len(data) < 6 or data[0] != 0x55:
        return None
    try:
        op = Op(data[4])
    except ValueError:
        return None
    return Notification(op, data[6:])
