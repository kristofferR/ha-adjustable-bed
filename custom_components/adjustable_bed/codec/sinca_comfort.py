"""Settings and replies specific to the Sinca Comfort Bed app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Final

from .mline import Protocol

_COMPACT_LEVELS: Final = {0: 0, 1: 1, 3: 2, 6: 3}
_ANGLES: Final = {1: "low", 3: "medium", 6: "high"}
_ALARM_ACTIONS: Final = {
    "legacy": {
        1: "zero_g",
        9: "flat",
        5: "memory_1",
        6: "memory_2",
        8: "massage",
        4: "anti_snore",
        2: "reading",
        3: "tv",
    },
    "okin": {
        13: "zero_g",
        28: "flat",
        17: "memory_1",
        19: "memory_2",
        9: "massage",
        16: "anti_snore",
        14: "reading",
        15: "tv",
    },
    "smartsainuo": {1: "zero_g", 9: "flat", 2: "memory_1", 3: "memory_2"},
}


def anti_snore(position: int, angle: int) -> bytes:
    """Enable automatic anti-snore. Position precedes angle on this profile."""
    if position not in (1, 2) or angle not in _ANGLES:
        raise ValueError("Invalid anti-snore position or level")
    return bytes((4, 11, 1, position, angle))


def newer_sensor(protocol: str | None, firmware: str | None) -> bool | None:
    """Select the privacy bit from exact metadata, without guessing malformed versions."""
    if protocol != "SENSOR_VOICE":
        return False
    if firmware is None:
        return None
    major, separator, rest = firmware.partition(".")
    try:
        version = int(major)
        return version > 1 or version == 1 and bool(separator) and int(rest.split(".", 1)[0]) > 0
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class MassageState:
    wave: int
    head: int
    foot: int
    timer: int

    @property
    def intensity(self) -> int:
        return max(self.head, self.foot)


def _legacy_level(value: int) -> int:
    quotient, remainder = divmod(value, 3)
    return quotient + remainder + int(value > 1)


def massage(data: bytes, protocol: Protocol) -> MassageState | None:
    if data[:3] == b"\xed\xfe\x16":
        if len(data) < 15:
            return None
        return MassageState(
            data[14] >> 4,
            _COMPACT_LEVELS.get(data[7], 0),
            _COMPACT_LEVELS.get(data[8], 0),
            data[14] & 15,
        )
    is_full = data[:3] == b"\xf4\xfe\x16"
    if not is_full and data[:2] != b"\xa5\x0b":
        return None
    if protocol == "okin":
        if len(data) < 22:
            return None
        timer, wave = data[19] & 15, data[21]
        return MassageState(
            wave if wave <= 4 else 0,
            ((data[11] & 15) + 1) // 2,
            (data[12] + 1) // 2,
            timer if timer <= 4 else 0,
        )
    if len(data) < 9:
        return None
    timer_word = int.from_bytes(data[4:6], "little" if protocol == "sleep" else "big")
    return MassageState(
        data[6],
        _legacy_level(data[7] & 15),
        _legacy_level(data[8]),
        timer_word // 600 + 1 if timer_word else 0,
    )


def anti_snore_state(data: bytes) -> tuple[bool, str] | None:
    if len(data) < 17 or data[:2] != b"\xa5\x0b":
        return None
    enabled = data[15] == 1
    return enabled, _ANGLES.get(data[16], "low") if enabled else "low"


def privacy_state(data: bytes, newer: bool | None) -> bool | None:
    if newer is None or data[:2] != b"\xa5\x0b" or len(data) < (20 if newer else 19):
        return None
    return bool(data[19] & 2) if newer else data[18] == 1


@dataclass(frozen=True, slots=True)
class AlarmState:
    week: int = 0
    mode: int = 0
    hour: int = 0
    minute: int = 0
    enabled: int = 0

    def action(self, protocol: Protocol) -> str:
        if not self.enabled:
            return "zero_g"
        return _ALARM_ACTIONS.get(protocol, _ALARM_ACTIONS["legacy"]).get(self.mode, "zero_g")

    @property
    def repeat(self) -> int:
        return self.week if self.enabled and self.week >= 128 else 0


def alarm(data: bytes) -> AlarmState | None:
    if len(data) < 3:
        return None
    if data[:2] == b"\xa5\x0c":
        if data[2] != 0x0E:
            return AlarmState()
        if len(data) >= 10:
            week, mode, hour, minute = data[4:8]
            enabled = data[9]
            if enabled == 1 and not any((week, mode, hour, minute)):
                enabled = 0
            return AlarmState(week, mode, hour, minute, enabled)
    elif data[:3] == b"\xed\x80\x03" and len(data) >= 7:
        return AlarmState(data[5], data[6], data[3], data[4], int(data[5] != 0))
    return None


HISTORY_HEADERS: Final = (b"\xa6\x30", b"\xa6\x31")
HISTORY_RECORD_SIZE: Final = 12


def history_timestamps(data: bytes, local_zone: tzinfo) -> tuple[datetime, ...] | None:
    """Return admitted UTC instants, or an empty tuple for an aligned, filtered batch."""
    if data[:2] not in HISTORY_HEADERS or len(data) % HISTORY_RECORD_SIZE:
        return None
    timestamps = []
    for offset in range(0, len(data), HISTORY_RECORD_SIZE):
        raw = data[offset : offset + HISTORY_RECORD_SIZE]
        year = 1900 + raw[7]
        if raw[5] not in range(3, 7) or raw[6] == 0 or year <= 2023:
            continue
        year, month = divmod(year * 12 + raw[8], 12)
        # Dart DateTime normalizes out-of-range calendar fields.
        stamp = datetime(year, month + 1, 1, tzinfo=local_zone) + timedelta(
            days=raw[9] - 1, hours=raw[10], minutes=raw[11]
        )
        timestamps.append(stamp.astimezone(UTC))
    return tuple(timestamps)


def history_has_long_group(timestamps: set[datetime], local_zone: tzinfo) -> bool:
    """Whether the app would wait for a consumer to finish a report-length group."""
    first = previous = None
    for stamp in sorted(timestamps):
        local_hour = stamp.astimezone(local_zone).hour
        gap = 30 if local_hour < 6 or local_hour >= 22 else 5
        if previous is None or stamp - previous > timedelta(minutes=gap):
            first = stamp
        assert first is not None
        if stamp - first >= timedelta(minutes=10):
            return True
        previous = stamp
    return False
