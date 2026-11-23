"""N32's live alarm callback and app-owned per-physical-bed records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, NamedTuple

from ...codec.okin_nframe import AlarmReport
from ...controller_state import StateKey


class AlarmRow(NamedTuple):
    hour: int
    minute: int
    week: int
    mode: int
    enabled: int


def callback_row(report: AlarmReport, old: AlarmRow | None) -> AlarmRow | None:
    """Deletion precedes old-field preservation; phone music has no wire field."""
    enabled = report.enabled
    if enabled == 1 and not any((report.week, report.mode, report.hour, report.minute)):
        enabled = 0
    week = 0 if enabled and report.week < 128 else report.week
    row = AlarmRow(report.hour, report.minute, week, report.mode, enabled)
    # The source constructs music=0, then tests all six fields before looking
    # up the old row. Excluded phone music cannot turn a cleared reply into a row.
    if not any(row):
        return None
    if not enabled and old is not None:
        row = row._replace(mode=old.mode, week=old.week)
    return row


@dataclass(frozen=True)
class AlarmKeys:
    time: StateKey[str | None]
    enabled: StateKey[bool | None]
    mode: StateKey[str | None]
    week: StateKey[int | None]
    ab: StateKey[int | None]
    soft: StateKey[int | None]
    fresh: StateKey[bool]
    record: StateKey[tuple[int, int, int, int, int] | None]

    @classmethod
    def for_slot(cls, slot: int) -> AlarmKeys:
        prefix = f"n32_alarm_{slot}"
        return cls(
            StateKey[str | None](prefix),
            StateKey[bool | None](prefix + "_enabled"),
            StateKey[str | None](prefix + "_mode"),
            StateKey[int | None](prefix + "_week"),
            StateKey[int | None](prefix + "_ab"),
            StateKey[int | None](prefix + "_soft"),
            StateKey[bool](prefix + "_fresh"),
            StateKey[tuple[int, int, int, int, int] | None](prefix + "_record"),
        )


ALARM_KEYS: Final = {slot: AlarmKeys.for_slot(slot) for slot in (1, 2, 3)}
