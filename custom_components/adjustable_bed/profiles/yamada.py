"""アシステック 1.0.1 (6), com.okin.yamada: app data over proven codecs.

Row178's verified scope is accepted under the stall rule, with report/helper
dispatch equivalence R1 deferred. No data here relies on that disputed guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from ..codec import keeson, okin_nframe
from .keeson import YAMADA_P1, YAMADA_P2, KeesonProfile

PROFILES: Final = {"p1": YAMADA_P1, "p2": YAMADA_P2}
VERSION_CHOICES: Final = {"p1": "P1: E6 / ED", "p2": "P2: 05 / A5"}
WORDS: Final = {
    "head_up": 1,
    "head_down": 2,
    "foot_up": 4,
    "foot_down": 8,
    "anti_snore": 0x8000,
    "zero": 0x1000,
    "memory_m2": 0x2000,
    "tvpc": 0x4000,
    "light": 0x20000,
    "flat": 0x08000000,
    "stop": 0,
}
POSITIONS: Final = {
    "yamada_p1": {"memory_1": 14, "anti_snore": 16, "zero_g": 13, "tv": 15, "flat": 28},
    "yamada_p2": {"memory_1": 2, "anti_snore": 4, "zero_g": 1, "tv": 3, "flat": 9},
}
WRITE_SERVICES: Final = frozenset(
    {
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    }
)
WRITE_CHARS: Final = frozenset(
    {
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    }
)
NOTIFY_SERVICES: Final = frozenset(
    {
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    }
)
NOTIFY_CHARS: Final = frozenset(
    {
        "0000ffe4-0000-1000-8000-00805f9b34fb",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    }
)
NAME_PREFIXES: Final = ("okin-ble", "smartbed")
REFRESH_MS: Final = 300
SAVE_CONFIRMATION_MS: Final = 5200
PAGE_ROUNDS_MS: Final = (0, 300, 600)
NOTIFY_RETRY_MS: Final = 1000


def manufacturer_version(value: bytes) -> str | None:
    """The app's first VALUE selector, only when that value is reconstructible.

    HA manufacturer maps must not be concatenated to emulate Android's bridge.
    Callers must establish the value's provenance or ask the user for the route.
    """
    if len(value) < 5:
        return None
    return "p2" if (value[0], value[1], value[2], value[4]) == (89, 65, 77, 2) else "p1"


def clock(profile: KeesonProfile, now: datetime) -> bytes:
    """Raw year-1900, month0, and (P2 only) Sunday0; never BCD."""
    fields = ((now.year - 1900) & 255, now.month - 1, now.day)
    time = (now.hour, now.minute, now.second)
    return (
        keeson.clock_fields((*fields, *time))
        if profile.key == "yamada_p1"
        else okin_nframe.clock((*fields, now.isoweekday() % 7, *time))
    )


def queries(profile: KeesonProfile) -> tuple[tuple[int, bytes], ...]:
    """One manager round, distinct from the three-round page entry."""
    if profile.key == "yamada_p1":
        return ((0, keeson.checked(bytes((0xE1, 0x80, 3)))),)
    return ((0, okin_nframe.request(0xC0)), (300, okin_nframe.request(0xD0)))


def alarm_week(value: int, hour: int, minute: int, now: datetime) -> int:
    """gainWeekday passes >128; otherwise resolves the next local time's day."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError("Weekday mask must be 0..255")
    if value > 128:
        return value
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # DateTime.add uses 24 elapsed hours, including across a DST change.
    if int((target.timestamp() - now.timestamp()) * 1000) < 0:
        target = datetime.fromtimestamp(target.timestamp() + 86400, tz=now.tzinfo)
    return 1 << (target.isoweekday() % 7)


@dataclass(frozen=True, slots=True)
class Alarm:
    hour: int
    minute: int
    weekday: int | None
    position: int
    enabled: bool

    @property
    def fields(self) -> bytes:
        if self.enabled and self.weekday is None:
            raise ValueError("The enabled alarm's weekday is unknown")
        return bytes(
            (self.hour, self.minute, (self.weekday or 0) if self.enabled else 0, self.position)
        )


def alarm_frame(profile: KeesonProfile, slot: int, selected: Alarm, other: Alarm | None) -> bytes:
    """Serialize an explicit slot; P1 needs the observed other record too."""
    if isinstance(slot, bool) or slot not in (1, 2):
        raise ValueError("Choose alarm slot 1 or 2")
    if profile.key == "yamada_p1":
        if other is None:
            raise ValueError("Refresh both bed alarms on this connection before changing a P1 slot")
        records = (selected, other) if slot == 1 else (other, selected)
        return keeson.alarm_table(3, b"".join(record.fields for record in records))
    return okin_nframe.alarm(
        (
            (selected.weekday or 0) if selected.enabled else 0,
            selected.position,
            selected.hour,
            selected.minute,
            0,
            int(selected.enabled),
            0,
        ),
        slot,
    )
