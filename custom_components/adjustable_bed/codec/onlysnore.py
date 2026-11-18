"""Snore Monitor 2.3.8's BED records, from accepted row170.

The eight-byte control declares 05 despite carrying six payload octets. It
cannot use the seven-byte N-frame or Smart Sleep carrier. Parameter records
reuse the existing encoder; no checksum, side selector or length repair is added.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from .okin_nframe import parameter_record

SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FIRMWARE: Final = "00002a26-0000-1000-8000-00805f9b34fb"
HARDWARE: Final = "00002a27-0000-1000-8000-00805f9b34fb"
ACTION_CODES: Final = (1, 9, 5, 6, 8)


def control(word: int, *, save: bool = False) -> bytes:
    """The app's four control bytes, reserved zero, then its save flag."""
    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError("Control word must be unsigned 32-bit")
    return parameter_record(2, (*word.to_bytes(4, "big"), 0, 15 if save else 0), size=5)


def query(opcode: int) -> bytes:
    return bytes((0, opcode & 255))


def setting(opcode: int, value: int) -> bytes:
    return bytes((1, opcode & 255, value & 255))


def intervention(mode: int, level: int) -> bytes:
    return bytes((2, 11, mode & 255, level & 255, 1, 0, 0))


INTERVENTION_STOP: Final = bytes((2, 11, 0, 1))


def clock(now: datetime) -> bytes:
    return parameter_record(
        4,
        tuple(
            v & 255
            for v in (
                now.year - 1900,
                now.month - 1,
                now.day,
                now.isoweekday() - 1,
                now.hour,
                now.minute,
                now.second,
            )
        ),
    )


def single_alarm(week: int, type_index: int, hour: int, minute: int) -> bytes:
    action = ACTION_CODES[type_index] if 0 <= type_index < len(ACTION_CODES) else 0
    return parameter_record(5, tuple(v & 255 for v in (week, action, hour, minute, 0, 1, 1)))


CLOSE_SINGLE: Final = parameter_record(5, (0,) * 7)


def triple_alarm(
    index: int, week: int, action_code: int, hour: int, minute: int, opened: int, soft: int
) -> bytes:
    if index not in (0, 1, 2):
        raise ValueError("Choose alarm slot 1, 2 or 3")
    return parameter_record(
        index + 5,
        tuple(
            v & 255
            for v in (
                week,
                action_code,
                hour,
                minute,
                0,
                opened,
                0,
                soft,
            )
        ),
        size=7,
    )


@dataclass(slots=True)
class AlarmModel:
    week: int
    hour: int
    minute: int
    type_index: int = 0
    index: int = 0
    opened: int = 1
    soft: int = 0


def open_single(model: AlarmModel, now: datetime) -> tuple[bytes, int]:
    """A001: retains seconds, floors subseconds, advances by elapsed 24 hours."""
    if model.week in (0, 128):
        target = now.replace(hour=model.hour, minute=model.minute, microsecond=0)
        if target < now:
            target = (
                (target.astimezone(UTC) + timedelta(hours=24)).astimezone(now.tzinfo)
                if now.tzinfo
                else target + timedelta(hours=24)
            )
        weekday = target.isoweekday()
        model.week = 1 << (0 if weekday == 7 else weekday)
    return single_alarm(model.week, model.type_index, model.hour, model.minute), model.week


def set_triple(model: AlarmModel, now: datetime, weekday_now: datetime) -> tuple[bytes, int]:
    """A001: independent weekday clock, zero seconds, local mask, no mutation."""
    week = model.week
    if week in (0, 128):
        target = now.replace(hour=model.hour, minute=model.minute, second=0, microsecond=0)
        weekday = weekday_now.isoweekday()
        exponent = (0 if weekday == 6 else weekday + 1) if target < now else weekday
        week = 1 << exponent
    action = ACTION_CODES[model.type_index] if 0 <= model.type_index < 5 else 1
    return triple_alarm(
        model.index, week, action, model.hour, model.minute, model.opened, model.soft
    ), week


@dataclass(frozen=True, slots=True)
class Status:
    privacy: bool
    snore_detection: bool
    anti_snore_enabled: bool
    anti_snore_level: int
    massage_timer_index: int
    massage_pattern_index: int
    massage_head_index: int
    massage_foot_index: int
    massage_shared_index: int


@dataclass(frozen=True, slots=True)
class Alarm:
    index: int
    week: int
    action_code: int
    hour: int
    minute: int
    opened: int
    soft: int | None


def parse(data: bytes) -> Status | Alarm | int | None:
    """One complete notification. No fragment assembly or invented checksum."""
    if data[:2] == b"\xa5\x0b" and len(data) >= 20:

        def intensity(value: int) -> int:
            return value % 3 + value // 3 + int(value > 1)

        head, foot = intensity(data[7] & 15), intensity(data[8])
        return Status(
            bool(data[19] & 2),
            bool(data[19] & 4),
            data[15] == 1,
            data[16],
            (int.from_bytes(data[4:6], "little") + 599) // 600,
            data[6] - 1,
            head,
            foot,
            max(head, foot),
        )
    if data[:3] == b"\xa5\x0a\x08" and len(data) >= 9:
        return 3 if data[8] == 3 else 1
    if len(data) >= 10 and data[0] == 165 and data[1] in (12, 13, 14):
        week, action, hour, minute = data[4:8]
        if hour > 23 or minute > 59:
            return None
        opened = 0 if not any((week, action, hour, minute)) else data[9]
        soft = data[10] if len(data) >= 11 else None
        if data[1] != 12 and soft is None:
            return None
        return Alarm(data[1] - 12, week, action, hour, minute, opened, soft)
    return None


def manufacturer(data: bytes) -> tuple[str, str]:
    """Reverse first; long payloads use reversed indices 1 through 6."""
    reversed_data = data[::-1]
    mac = (reversed_data[1:7] if len(data) >= 7 else reversed_data).hex()
    model = {
        1: "single",
        2: "double",
        3: "meise",
        4: "dormimundo",
        5: "singleOnlySound",
        6: "noBreathheart",
        10: "wifi",
    }.get(data[6] if len(data) >= 7 else -1, "unKnow")
    return mac, model
