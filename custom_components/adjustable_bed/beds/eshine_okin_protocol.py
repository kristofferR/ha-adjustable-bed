"""com.okin.eshine 1.1.8 wire values, independent of the E6000 app.

Accepted row122 evidence and deliberate malformed-input corrections are recorded
in docs/apk-analysis/dispositions/row122-eshine.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
REFRESH_MS: Final = 300
RELEASE_MS: Final = 200
COMMANDS: Final = {
    "query_alarm": bytes.fromhex("00 c0"),
    "query_state": bytes.fromhex("00 b0"),
    "disable_alarm": bytes.fromhex("07 05 00 00 00 00 00 00 00"),
    "massage_wave": bytes.fromhex("05 02 10 00 00 00 00"),
    "stop": bytes.fromhex("05 02 00 00 00 00 00"),
    "tv": bytes.fromhex("05 02 00 00 40 00 00"),
    "anti_snore": bytes.fromhex("05 02 00 00 80 00 00"),
    "zero_g": bytes.fromhex("05 02 00 00 10 00 00"),
    "feet_down": bytes.fromhex("05 02 00 00 00 08 00"),
    "feet_up": bytes.fromhex("05 02 00 00 00 04 00"),
    "head_down": bytes.fromhex("05 02 00 00 00 02 00"),
    "head_up": bytes.fromhex("05 02 00 00 00 01 00"),
    "pillow_down": bytes.fromhex("05 02 00 00 00 20 00"),
    "pillow_up": bytes.fromhex("05 02 00 00 00 10 00"),
    "light": bytes.fromhex("05 02 00 02 00 00 00"),
    "flat": bytes.fromhex("05 02 08 00 00 00 00"),
    "reading": bytes.fromhex("05 02 00 00 20 00 00"),
    "massage_foot_strength": bytes.fromhex("05 02 00 00 04 00 00"),
    "massage_head_strength": bytes.fromhex("05 02 00 00 08 00 00"),
    "massage_timer": bytes.fromhex("05 02 00 00 02 00 00"),
    "massage_off": bytes.fromhex("05 02 02 00 00 00 00"),
    "massage_on": bytes.fromhex("05 02 00 00 01 00 00"),
    "flat_zero_g": bytes.fromhex("05 02 08 00 10 00 00"),
}
HELD: Final = frozenset(
    {
        "head_up",
        "head_down",
        "feet_up",
        "feet_down",
        "pillow_up",
        "pillow_down",
        "flat",
        "zero_g",
        "reading",
        "tv",
        "anti_snore",
        "flat_zero_g",
        "light",
    }
)
ALARM_TYPES: Final = {"zero_g": 1, "flat": 9, "massage": 8}
type StateValue = int | bool | str


def clock_frame(now: datetime) -> bytes:
    """Local civil time, Monday=1; low eight bits match the app encoder."""
    return bytes(
        v & 255
        for v in (
            7,
            4,
            now.year - 2000,
            now.month,
            now.day,
            now.isoweekday(),
            now.hour,
            now.minute,
            now.second,
        )
    )


def alarm_frame(now: datetime, hour: int, minute: int, action: str) -> bytes:
    """Time-only picker selects one next-occurrence day, Sunday at bit zero."""
    selected = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    day = selected.isoweekday() % 7
    if selected <= now:
        day = (day + 1) % 7
    return bytes((7, 5, 1 << day, ALARM_TYPES[action], hour, minute, 0, 1, 1))


def parse_notification(data: bytes, now: datetime) -> tuple[str, dict[str, StateValue]] | None:
    """Parse complete recognized deliveries, retaining unusual reported values.

    The app's fe/16 pending buffer corrupts the next independent notification.
    HA ignores that unknown header rather than inventing a fragmentation format.
    A truncated message cannot partly update HA state or throw from a BLE callback.
    """
    if data[:3] == b"\xa5\x0b\x0e" and len(data) >= 14:
        seconds = int.from_bytes(data[4:6], "big")
        timer = (seconds + 599) // 600
        head, foot = data[7] & 15, data[8]
        head = head % 3 + head // 3 + (1 if head > 1 else 0)
        foot = foot % 3 + foot // 3 + (1 if foot > 1 else 0)
        enabled = timer > 0
        return "massage", {
            "seconds": seconds,
            "timer_index": timer,
            "enabled": enabled,
            "wave": data[6] - 1 if enabled else 0,
            "head": head if enabled else 0,
            "foot": foot if enabled else 0,
            "combined": max(head, foot),
            "light": data[13] == 1,
            "raw_wave": data[6] - 1,
            "raw_head": head,
            "raw_foot": foot,
        }
    if data[:3] == b"\xa5\x0c\x0e" and len(data) >= 10:
        day, action, hour, minute, enabled = (data[i] for i in (4, 5, 6, 7, 9))
        on = enabled != 0 and not (enabled == 1 and day == action == hour == minute == 0)
        # As in the app DateTime consumer, overflow is normalized, not clamped.
        normalized = now.replace(hour=0, minute=0, microsecond=0) + timedelta(
            hours=hour if on else now.hour,
            minutes=minute if on else now.minute,
        )
        return "alarm", {
            "enabled": on,
            "selection": {1: 1, 9: 2, 8: 3}.get(action, 0) if on else 1,
            "action": next((k for k, v in ALARM_TYPES.items() if v == action), "unknown")
            if on
            else "zero_g",
            "date": normalized.isoformat(),
            "weekday_mask": day,
            "raw_type": action,
            "raw_hour": hour,
            "raw_minute": minute,
            "raw_enabled": enabled,
        }
    return None
