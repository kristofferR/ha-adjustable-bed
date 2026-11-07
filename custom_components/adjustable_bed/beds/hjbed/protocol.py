"""HJBed 2.1.2 frames over the Richmat 6E codec; source RVAs and vectors in the row121 ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...codec import richmat as codec


def function(enum: str, code: int, side: int, single: bool) -> bytes:
    return codec.function(code, side, action=enum, single=single)


def clock(minutes: int, code: int) -> tuple[bytes, bytes]:
    return codec.countdown(minutes, code)


def light_time(seconds: int) -> bytes:
    """The app splits a 4-digit hex string; zero becomes the ``FF FF`` sentinel."""
    value = f"{seconds:x}".rjust(4, "0")
    hi, lo = int(value[:2], 16), int(value[2:4], 16)
    if hi == lo == 0:
        hi = lo = 255
    return codec.light_timer(hi, lo)


def color(rgb: tuple[int, int, int]) -> bytes:
    return codec.rgb(*rgb)


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
    data = [
        alarm.number,
        alarm.kind,
        alarm.hour,
        alarm.minute,
        0 if alarm.kind == 1 else alarm.code,
        alarm.repeat,
    ]
    if alarm.kind == 1 or (alarm.kind == 0 and alarm.code == 255):
        data.extend(alarm.data)
    return codec.record(5, 1, 1, data)


def delete_alarm(number: int) -> bytes:
    return codec.record(5, 2, 1, (number,))


def query_alarms() -> bytes:
    return codec.record(5, 1, 0, (0,))


def control_mode(mode: int | None = None) -> bytes:
    return codec.record(11, 2, 0, (0,)) if mode is None else codec.record(11, 2, 1, (0, mode))


def sync_time(now: datetime, offset_now: datetime) -> tuple[bytes, bytes]:
    """Timestamp/calendar share one snapshot; zone uses the second app snapshot."""
    return codec.time_sync(now, offset_now)
