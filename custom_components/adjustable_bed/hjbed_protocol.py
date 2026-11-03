"""HJBed 2.1.2 packet builders; source RVAs and vectors in the row121 ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def checked(values: list[int]) -> bytes:
    """The plugin masks each integer to uint8 after calculating the sum."""
    return bytes(v & 255 for v in (*values, sum(values) & 255))


def extended(body: list[int]) -> bytes:
    return checked([0x6E, len(body) + 3, *body])


QUERY_PREFIX = {
    "deviceFunctionItemExitLimit": [0x6E, 2, 1],
    "deviceFunctionItemCheckClock": [0x6E, 8, 1],
    "deviceFunctionItemCheckLight": [0x6E, 10, 0],
    "deviceFunctionItemCheckMusic": [0x6E, 21, 1],
}


def function(enum: str, code: int, side: int, single: bool) -> bytes:
    if single:
        return bytes((code & 255,))
    return checked([*QUERY_PREFIX.get(enum, [0x6E, 1, side]), code])


def clock(minutes: int, code: int) -> tuple[bytes, bytes]:
    return checked([0x6E, 5, minutes & 255, 0]), checked([0x6E, 6, int(minutes / 256), code])


def light_time(seconds: int) -> bytes:
    value = f"{seconds:x}".rjust(4, "0")
    hi, lo = int(value[:2], 16), int(value[2:4], 16)
    if hi == lo == 0:
        hi = lo = 255
    return checked([0x6E, 11, hi, lo])


def color(rgb: tuple[int, int, int]) -> bytes:
    red, green, blue = rgb
    return checked([0x6E, 12, 255, red]) + checked([0x6E, 13, green, blue])


@dataclass(frozen=True, slots=True)
class Alarm:
    """Full received alarm bean, including custom/imported payloads."""

    number: int
    kind: int
    hour: int
    minute: int
    code: int
    repeat: int
    data: tuple[int, ...] = ()


def add_alarm(alarm: Alarm) -> bytes:
    body = [
        0x20,
        5,
        1,
        1,
        alarm.number,
        alarm.kind,
        alarm.hour,
        alarm.minute,
        0 if alarm.kind == 1 else alarm.code,
        alarm.repeat,
    ]
    if alarm.kind == 1 or (alarm.kind == 0 and alarm.code == 255):
        body.extend(alarm.data)
    return extended(body)


def delete_alarm(number: int) -> bytes:
    return extended([0x20, 5, 2, 1, number])


def query_alarms() -> bytes:
    return extended([0x20, 5, 1, 0, 0])


def control_mode(mode: int | None = None) -> bytes:
    return extended([0x20, 11, 2, 0, 0] if mode is None else [0x20, 11, 2, 1, 0, mode])


def sync_time(now: datetime, offset_now: datetime) -> tuple[bytes, bytes]:
    """Timestamp/calendar share one snapshot; zone uses the second app snapshot."""
    offset = offset_now.utcoffset()
    if now.utcoffset() is None or offset is None:
        raise ValueError("Time synchronization requires aware datetimes")
    stamp = f"{int(now.timestamp()):X}".rjust(8, "0")
    epoch = [int(stamp[i : i + 2], 16) for i in range(0, 8, 2)]
    return (
        extended([0x20, 8, 2, 1, *epoch, int(offset.total_seconds() / 3600) & 255]),
        extended(
            [0x20, 8, 3, 1, now.year - 1970, now.month, now.day, now.hour, now.minute, now.second]
        ),
    )
