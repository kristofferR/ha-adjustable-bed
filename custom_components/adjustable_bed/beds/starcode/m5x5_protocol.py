"""AdjustableM5X5 packet and feedback fields from the accepted 1.2.3 artifact.

Feedback is a delta: callers retain fields from other domains. Short frames are
ignored safely instead of reproducing the application's out-of-bounds errors.
Control frames for both dialects come from ``dialect.py``.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from ...codec import okin_5a
from .dialect import is_star
from .feedback import (
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

# AdjustableM5X5 bed classes.
PROFILES: Final = ("cb25", "f23", "kneading")
_MOTOR_NAMES: Final = ("back", "legs", "lumbar", "motor_part4", "motor_part5", "motor_part6")
_ALARM_SLOTS: Final[tuple[AlarmOffsets, ...]] = (
    (3, 4, 5, 6, 7, 8, 9, 11, 12, 13),
    (14, 15, 16, 17, 18, 19, 20, 21, 22, 24),
)


def clock_packet(local_time: datetime) -> bytes:
    """Encode the supplied local clock, with Dart's Monday=1 weekday convention."""
    return okin_5a.clock(
        (
            local_time.year - 2000,
            local_time.month,
            local_time.day,
            local_time.hour,
            local_time.minute,
            local_time.second,
            local_time.isoweekday(),
        )
    )


def _normal_and_sonic(data: bytes) -> dict[str, StateValue]:
    head, foot = data[7] & 0xF, data[7] >> 4
    color = data[14] & 0xF
    direct = color > 7
    rgb = int.from_bytes(data[16:19], "big") if direct else PALETTE[max(color - 1, 0)]
    sonic_head, sonic_foot = data[11] & 0xF, data[11] >> 4
    sonic_any = sonic_head > 0 or sonic_foot > 0
    return {
        "massage_time_raw": int.from_bytes(data[4:6], "big"),
        "massage_mode": data[6] & 0xF,
        "massage_head_level": max(head - 1, 0),
        "massage_foot_level": max(foot - 1, 0),
        "massage_active": head > 0 or foot > 0,
        "light_mode": data[15] >> 4,
        "light_brightness": data[14] >> 4,
        "light_on": color > 0,
        # Report direct RGB in the wire numbering the palette select uses
        # (0 = off, 1 = white): palette position p is wire index p + 1.
        "light_color_index": closest_color(rgb) + 1 if direct else color,
        "light_rgb": rgb,
        "light_rgb_mode": int(direct),
        "sonic_head_level": sonic_head,
        "sonic_foot_level": sonic_foot,
        "sonic_active": sonic_head > 0 and sonic_foot > 0,
        "sonic_frequency": (30 if data[12] == 5 else 40 if data[12] == 9 else 50)
        if sonic_any
        else 0,
        "sonic_time_raw": int.from_bytes(data[9:11], "big") if sonic_any else 0,
        "sonic_mode": int((data[8] & 0xF) > 0),
        "sonic_massage_type": data[6] >> 4,
    }


def parse_notification(
    data: bytes,
    *,
    profile: str,
    dialect: str,
    previous: Mapping[str, StateValue] | None = None,
) -> dict[str, StateValue]:
    """Return only delivered fields, without mutating previous or inventing ACKs.

    Delta application preserves prior alarm slots and sonic fields, including on
    EQ's USB-only sonic update. ELEVATE lifts use the separate star_elevate type.
    No app debounce suppression is carried into Home Assistant.
    """
    star = is_star(dialect)
    if profile not in ("cb25", "f23", "kneading"):
        raise ValueError(f"Unknown AdjustableM5X5 profile: {profile}")
    if len(data) < 2 or data[0] != 0xA5:
        return {}
    match data[1]:
        case 0x0D if len(data) >= 18:
            return motor(data, _MOTOR_NAMES)
        case 0x0B if len(data) >= 20:
            return _normal_and_sonic(data)
        case 0x0C if profile == "cb25" and len(data) >= 17:
            return basic_alarm(data, (4, 11) if star else (4,))
        case 0x0C if profile in ("f23", "kneading") and len(data) >= 25:
            return advanced_alarm(data, _ALARM_SLOTS)
        case 0x0E if profile in ("f23", "kneading") and len(data) >= 22:
            return eq(data)
        case 0x0F if profile == "kneading" and len(data) >= 8:
            return kneading(data)
        case _:
            return {}
