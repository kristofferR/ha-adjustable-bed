"""Typed, preflighted alarm tables for the seven explicit app profiles.

These are bed tables, not a Home Assistant alarm scheduler. A single captured
local reference time belongs to the whole service call, including every side.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal


@dataclass(frozen=True, slots=True, kw_only=True)
class WeeklyAlarmRecord:
    enabled: bool = False
    wake: bool = False
    hour: int = 0
    minute: int = 0
    weekdays: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class OneTimeAlarmRecord:
    enabled: bool = False
    wake: bool = False
    hour: int = 0
    minute: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class AlarmTableSchedule:
    weekly: tuple[WeeklyAlarmRecord, ...]
    one_time: tuple[OneTimeAlarmRecord, ...]
    dispatch: Literal["both", "weekly", "one_time"]
    reference_time: datetime


def _relative_seconds(row: OneTimeAlarmRecord, now: datetime) -> int:
    """Validate local wall time, then truncate positive milliseconds like Java.

    UTC round trips reject nonexistent times. Distinct valid fold offsets reject
    ambiguous times. Comparison/subtraction use UTC, including on DST dates.
    Convert absolute dates to Java Date millisecond precision first, then apply
    positive integer division. This differs from flooring a microsecond delta
    at the sub-millisecond boundary immediately after a whole second.
    """
    wall = now.replace(hour=row.hour, minute=row.minute, second=0, microsecond=0)
    candidates = [wall.replace(fold=fold) for fold in (0, 1)]
    valid = [
        candidate
        for candidate in candidates
        if candidate.astimezone(UTC).astimezone(now.tzinfo).replace(tzinfo=None)
        == wall.replace(tzinfo=None)
    ]
    if not valid:
        raise ValueError("One-time alarm time does not exist in the local timezone")
    if len({candidate.utcoffset() for candidate in valid}) != 1:
        raise ValueError("One-time alarm time is ambiguous in the local timezone")
    target_utc, now_utc = valid[0].astimezone(UTC), now.astimezone(UTC)
    delta = target_utc - now_utc
    if delta.total_seconds() <= 0:
        raise ValueError("Enabled one-time alarms must be later today")
    epoch = datetime(1970, 1, 1, tzinfo=UTC)

    def milliseconds(value: datetime) -> int:
        elapsed = value - epoch
        return (elapsed.days * 86400 + elapsed.seconds) * 1000 + elapsed.microseconds // 1000

    return (milliseconds(target_utc) - milliseconds(now_utc)) // 1000


@dataclass(frozen=True, slots=True)
class AlarmTableScheduleSpec:
    """Exact caller encoding; capacity applies to both tables before dispatch."""

    weekday_marker: int
    wake_byte: int
    capacity: int = 3
    dispatch_delay_ms: int = 500

    def validate(self, schedule: AlarmTableSchedule) -> None:
        """Validate every field without computing a checksum or emitting bytes."""
        if schedule.reference_time.tzinfo is None or schedule.reference_time.utcoffset() is None:
            raise ValueError("Alarm schedules require one timezone-aware local reference time")
        if schedule.dispatch not in ("both", "weekly", "one_time"):
            raise ValueError("Choose both, weekly, or one_time dispatch")
        for table in (schedule.weekly, schedule.one_time):
            if sum(row.enabled for row in table) > self.capacity:
                raise ValueError(
                    f"Each alarm table supports at most {self.capacity} enabled records"
                )
            for row in table:
                if type(row.enabled) is not bool or type(row.wake) is not bool:
                    raise ValueError("Alarm enabled and wake fields must be booleans")
                if type(row.hour) is not int or not 0 <= row.hour <= 23:
                    raise ValueError("Alarm hour must be 0 through 23")
                if type(row.minute) is not int or not 0 <= row.minute <= 59:
                    raise ValueError("Alarm minute must be 0 through 59")
        for row in schedule.weekly:
            if len(set(row.weekdays)) != len(row.weekdays) or any(
                type(day) is not int or not 0 <= day <= 6 for day in row.weekdays
            ):
                raise ValueError("Weekdays must be unique integers, Monday 0 through Sunday 6")
            if row.enabled and not row.weekdays:
                raise ValueError("Enabled weekly alarms require at least one weekday")
        for row in schedule.one_time:
            if row.enabled:
                _relative_seconds(row, schedule.reference_time)

    def encode(self, schedule: AlarmTableSchedule) -> tuple[bytes, bytes]:
        """Build both complete tables only after validation succeeds."""
        self.validate(schedule)
        weekly = bytearray(b"\xed\x80\x03" + bytes(13))
        one_time = bytearray(b"\xed\x80\x02" + bytes(13))
        index = 3
        for row in schedule.weekly:
            if not row.enabled:
                continue
            days = self.weekday_marker | sum(1 << ((day + 1) % 7) for day in row.weekdays)
            weekly[index : index + 4] = bytes(
                (row.hour, row.minute, days, self.wake_byte if row.wake else 0)
            )
            index += 4
        index = 3
        for row in schedule.one_time:
            if not row.enabled:
                continue
            seconds = _relative_seconds(row, schedule.reference_time)
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            one_time[index : index + 4] = bytes(
                (hours & 255, minutes, seconds, self.wake_byte if row.wake else 0)
            )
            index += 4
        for frame in (weekly, one_time):
            frame[-1] = ~sum(frame[:-1]) & 255
        return bytes(weekly), bytes(one_time)
