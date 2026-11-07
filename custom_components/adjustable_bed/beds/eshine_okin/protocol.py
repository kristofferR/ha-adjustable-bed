"""com.okin.eshine 1.1.8 clock, alarm and reply rules, independent of the E6000 app.

Key words and hold timing are the ``ESHINE_PROFILES`` data; every frame is an
Okin N-frame (``codec/okin_nframe.py``). Evidence: APK Protocol Audit row122,
with deliberate malformed-input corrections.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from ...codec import okin_nframe
from ...profiles.okin_nframe import ESHINE_KEYS

SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
COMMANDS: Final = {
    "query_alarm": okin_nframe.request(0xC0),
    "query_state": okin_nframe.request(0xB0),
    "disable_alarm": okin_nframe.alarm(bytes(7)),
    **{action: okin_nframe.frame40(word) for action, word in ESHINE_KEYS.items()},
}
# Every key but STOP and the massage keys streams while held.
HELD: Final = frozenset(
    action for action in ESHINE_KEYS if action != "stop" and not action.startswith("massage_")
)
ALARM_TYPES: Final = {"zero_g": 1, "flat": 9, "massage": 8}
type StateValue = int | bool | str


def clock_frame(now: datetime) -> bytes:
    """Local civil time, Monday=1; the year's low eight bits match the app encoder."""
    return okin_nframe.clock(
        (
            (now.year - 2000) & 255,
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
    return okin_nframe.alarm((1 << day, ALARM_TYPES[action], hour, minute, 0, 1, 1))


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
