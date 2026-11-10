"""OkinComfortBed II's app-owned layouts, keys and setup choices (unit132)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from ..codec import keeson, okin_nframe
from .keeson import JALON_13, JALON_15, JALON_24, KeesonProfile

PROFILES: Final = {"P1": JALON_13, "P2": JALON_15, "P3": JALON_24}
LAYOUTS: Final = {
    "0": ("head", "feet"),
    "10": ("head", "feet", "tilt"),
    "11": ("head", "feet", "lumbar"),
    "2": ("head", "feet", "tilt", "lumbar"),
}
COMMANDS: Final = {
    "stopCommand": 0,
    "headUp": 1,
    "headDown": 2,
    "footUp": 4,
    "footDown": 8,
    "neckUp": 0x10,
    "neckDown": 0x20,
    "lumbarUp": 0x40,
    "lumbarDown": 0x80,
    "memoryFlat": 0x08000000,
    "memoryZero": 0x1000,
    "memoryLounge": 0x2000,
    "memoryTvpc": 0x4000,
    "memoryAntiSnore": 0x8000,
    "memory1M5": 0x10000,
    "memory2M6": 0x40000,
    "lightSwitch": 0x20000,
    "massageSwitch": 0x100,
    "massageTimeSwitch": 0x200,
    "strengthHeadUp": 0x800,
    "strengthFootUp": 0x400,
    "massageWaveSwitch": 0x10000000,
}
WAKE_TYPES: Final = {
    "jalon_15": {
        "flat": 28,
        "memory_1": 17,
        "memory_2": 19,
        "zero_g": 13,
        "anti_snore": 16,
        "tv": 15,
        "massage": 9,
    },
    "jalon_24": {
        "flat": 9,
        "memory_1": 5,
        "memory_2": 6,
        "zero_g": 1,
        "anti_snore": 4,
        "tv": 3,
        "massage": 8,
    },
}
REFRESH_MS: Final = 300
PRESET_MS: Final = 100
MEMORY_SAVE_MS: Final = 6000
QUERY_DELAY_MS: Final = 100
ALARM_FOLLOWUP_MS: Final = 350


def clock(profile: KeesonProfile, now: datetime) -> bytes:
    """P1 deliberately uses the same non-P2 fallback as P3."""
    if profile.key == "jalon_15":
        return keeson.clock(now)
    return okin_nframe.clock(
        (now.year - 2000, now.month, now.day, now.isoweekday(), now.hour, now.minute, now.second)
    )


def alarm(
    profile: KeesonProfile, *, hour: int, minute: int, week: int, wake_type: int, enabled: bool
) -> bytes:
    """Bed-local alarm; no side selector is populated by this app."""
    if profile.key not in WAKE_TYPES:
        raise ValueError("This app's P1 route has no alarm setter")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= week <= 255:
        raise ValueError("Invalid alarm time or weekday mask")
    if wake_type not in WAKE_TYPES[profile.key].values():
        raise ValueError("Unknown app wake type")
    if profile.key == "jalon_15":
        fields = bytes((hour, minute, week, wake_type)) if enabled else bytes(4)
        return keeson.alarm_table(3, fields)
    return okin_nframe.alarm((week, wake_type, hour, minute, 0, int(enabled), 0))


def massage_query(profile: KeesonProfile) -> bytes:
    return keeson.STATUS_QUERY if profile.key == "jalon_24" else bytes(4)


def alarm_query(profile: KeesonProfile) -> bytes:
    if profile.key == "jalon_13":
        raise ValueError("This app's P1 route has no alarm query")
    return b"\x00\xc0" if profile.key == "jalon_24" else keeson.ALARM_QUERY


def alarm_week(week: int, hour: int, minute: int, now: datetime) -> int:
    """The app resolves Once (0/128) to today's or tomorrow's weekday bit."""
    if week not in (0, 128):
        return week
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if int((target.timestamp() - now.timestamp()) * 1000) < 0:
        target = (
            datetime.fromtimestamp(target.timestamp() + 86400, tz=now.tzinfo)
            if now.tzinfo is not None
            else target + timedelta(days=1)
        )
    return 1 << (target.isoweekday() % 7)
