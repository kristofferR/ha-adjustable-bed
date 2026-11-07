"""Adjustable Comfort M1X12 StarCode packets and notification values.

This codec follows the accepted M1X12 artifact report. It deliberately keeps
raw Part numbers instead of assigning physical names to unverified actuators.
Control frames for both dialects come from ``starcode_dialect.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from ..codec import okin_5a
from .starcode_dialect import is_star
from .starcode_feedback import (
    PALETTE,
    AlarmOffsets,
    StateValue,
    advanced_alarm,
    basic_alarm,
    closest_color,
    eq,
    kneading,
    motor,
)

PROFILES: Final = ("cb25", "f23", "kneading")
_MOTOR_NAMES: Final = (
    "part_1_position",
    "part_2_position",
    "part_4_position",
    "part_8_position",
    "part_16_position",
    "part_32_position",
)
_ALARM_SLOTS: Final[tuple[AlarmOffsets, ...]] = (
    (3, 4, 5, 6, 7, 8, 9, 10, 11, 13),
    (14, 15, 16, 17, 18, 19, 20, 21, 22, 24),
)


def profile_from_name(name: str) -> str | None:
    """Normalize app-name prefixes with the accepted specific-before-generic order."""
    normalized = name.upper()
    if normalized.startswith(("STAR254205", "STAR255401")):
        return "f23"
    if normalized.startswith(("STAR255402", "STAR255403")):
        return "kneading"
    if normalized.startswith("STAR25"):
        return "cb25"
    return None


def time_packet(
    year_argument: int,
    month: int,
    day: int,
    weekday: int,
    hour: int,
    minute: int,
    second: int,
) -> bytes:
    """Match the builder's year subtraction and weekday-before-time field order."""
    values = (year_argument - 2000, month, day, weekday, hour, minute, second)
    return okin_5a.clock(tuple(value & 0xFF for value in values))


def clock_packet(local_time: datetime) -> bytes:
    """Match the shipped caller, including its second subtraction of 2000."""
    return time_packet(
        local_time.year - 2000,
        local_time.month,
        local_time.day,
        local_time.isoweekday(),
        local_time.hour,
        local_time.minute,
        local_time.second,
    )


def _normal_rgb(data: bytes) -> dict[str, StateValue]:
    raw_head, raw_foot = data[7] & 0x0F, data[7] >> 4
    color_code = data[14] & 0x0F
    direct_rgb = color_code > 7
    rgb = int.from_bytes(data[16:19], "big") if direct_rgb else PALETTE[max(color_code - 1, 0)]
    return {
        "massage_time_raw": int.from_bytes(data[4:6], "big"),
        "massage_mode": data[6] & 0x0F,
        "massage_head_level": max(raw_head - 1, 0),
        "massage_foot_level": max(raw_foot - 1, 0),
        "massage_active": raw_head > 0 or raw_foot > 0,
        "light_mode": data[14] >> 4,
        "light_brightness": data[15] >> 4,
        "light_on": color_code > 0,
        "light_color_index": closest_color(rgb) if direct_rgb else color_code,
        "light_rgb": rgb,
        "light_rgb_mode": int(direct_rgb),
    }


def _sonic(data: bytes) -> dict[str, StateValue]:
    head, foot = data[11] & 0x0F, data[11] >> 4
    any_active = head > 0 or foot > 0
    return {
        "sonic_head_level": head,
        "sonic_foot_level": foot,
        "sonic_active": head > 0 and foot > 0,
        "sonic_frequency": (30 if data[12] == 5 else 40 if data[12] == 9 else 50)
        if any_active
        else 0,
        "sonic_time_raw": int.from_bytes(data[9:11], "big") if any_active else 0,
        "sonic_mode": data[6] >> 4,
        "sonic_massage_type": int((data[8] & 0x0F) > 0),
    }


def parse_notification(
    data: bytes,
    *,
    profile: str,
    dialect: str,
    previous: Mapping[str, StateValue] | None = None,
) -> dict[str, StateValue]:
    """Return a safe state delta for supported M1X12 notification types."""
    del previous  # Consumers merge deltas so untouched domains retain their prior values.
    if profile not in PROFILES:
        raise ValueError(f"Unknown Adjustable Comfort M1X12 profile: {profile}")
    is_star(dialect)  # Rejects unknown dialects.
    if len(data) < 2 or data[0] != 0xA5:
        return {}
    match data[1]:
        case 0x0D if len(data) >= 18:
            return motor(data, _MOTOR_NAMES)
        case 0x0B if len(data) >= 20:
            return {**_normal_rgb(data), **_sonic(data)}
        case 0x0C if profile == "cb25" and len(data) >= 17:
            return basic_alarm(data, (4, 11))
        case 0x0C if profile in ("f23", "kneading") and len(data) >= 25:
            return advanced_alarm(data, _ALARM_SLOTS)
        case 0x0E if profile in ("f23", "kneading") and len(data) >= 22:
            return eq(data)
        case 0x0F if profile == "kneading" and len(data) >= 8:
            return kneading(data)
        case _:
            return {}
