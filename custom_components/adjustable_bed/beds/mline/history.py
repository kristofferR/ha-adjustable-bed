"""Bounded raw 12-byte history projection, without phone reports or scoring."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.util.json import JsonValueType


@dataclass(frozen=True)
class Record:
    raw: bytes
    time: datetime

    def as_dict(self) -> dict[str, JsonValueType]:
        return {
            "raw": self.raw.hex(),
            "time": self.time.isoformat(),
            "heart": self.raw[3],
            "breath": self.raw[4],
            "state": self.raw[5],
            "field37": self.raw[6] & 15 if self.raw[6] & 15 in (1, 2, 3, 4) else 0,
        }


def records(payload: bytes, now: datetime) -> list[Record]:
    result: list[Record] = []
    for index in range(0, len(payload) - 11, 12):
        raw = payload[index : index + 12]
        if not raw[6] or raw[5] not in range(3, 7):
            continue
        # Dart DateTime normalizes date fields. Keep that behavior, but fence overflow.
        try:
            year, month = divmod((raw[7] + 1900) * 12 + raw[8], 12)
            stamp = datetime(year, month + 1, 1, tzinfo=now.tzinfo) + timedelta(
                days=raw[9] - 1, hours=raw[10], minutes=raw[11]
            )
        except ValueError, OverflowError:
            continue
        if stamp >= now - timedelta(milliseconds=31536000000):
            result.append(Record(raw, stamp))
    return result


def grouped(items: list[Record]) -> list[list[Record]]:
    # Stable sort keeps the first occurrence at an equal timestamp.
    unique: dict[datetime, Record] = {}
    for row in items:
        unique.setdefault(row.time, row)
    groups: list[list[Record]] = [[]]
    for stamp in sorted(unique):
        record = unique[stamp]
        previous = groups[-1][-1] if groups[-1] else None
        limit = 30 if record.time.hour < 6 or record.time.hour >= 22 else 5
        if previous and (record.time - previous.time).total_seconds() > limit * 60:
            groups.append([])
        groups[-1].append(record)
    return groups
