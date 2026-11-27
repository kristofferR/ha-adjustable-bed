"""마이저모벨 1.2.8: two explicit routes over Keeson and Okin N-frame codecs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final, Literal

from ..alarm import AlarmRequest
from ..codec import keeson, okin_nframe
from ..execution import STREAM_HOLD
from .okin_nframe import Hold, OkinNFrameProfile

type Route = Literal["15_22_15a", "24_xx_xx"]
REFRESH_MS: Final = 300
STOP_MS: Final = 100
SAVE_MS: Final = 5000
RESET_COPIES: Final = 31
RESET_MS: Final = 200
WAKE_ACTIONS: Final = ("flat", "memory_1", "memory_2", "zero_g", "anti_snore", "tv")
ALARM_TYPES: Final = {"15_22_15a": (28, 17, 19, 13, 16, 15), "24_xx_xx": (9, 5, 6, 1, 4, 3)}


@dataclass(frozen=True, slots=True)
class Transport:
    service: str
    write: str
    notify_service: str
    notify: str


TRANSPORTS: Final[dict[Route, Transport]] = {
    "15_22_15a": Transport(
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    "24_xx_xx": Transport(
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
}
_KEYS: Final = {
    "stop": 0,
    "head_up": 1,
    "head_down": 2,
    "foot_up": 4,
    "foot_down": 8,
    "anti_snore": 0x8000,
    "memory_1": 0x10000,
    "memory_2": 0x40000,
    "tv": 0x4000,
    "zero_g": 0x1000,
    "flat": 0x08000000,
    "light": 0x20000,
    "reset_memories": 0x08001000,
}
PROFILES: Final[dict[Route, OkinNFrameProfile]] = {
    route: OkinNFrameProfile(
        key=f"meisemobell_{route}",
        name=f"Meisemobell {route}",
        bed_types=("meisemobell",),
        width=5,
        write="no_response",
        envelope="keeson_e6" if route == "15_22_15a" else "plain",
        axes=("back", "legs"),
        keys=MappingProxyType(_KEYS),
        hold=Hold(repeat_ms=REFRESH_MS, releases=2, release_ms=STOP_MS),
        execution=STREAM_HOLD,
        memory_slots=2,
    )
    for route in TRANSPORTS
}


def control(route: Route, action: str) -> bytes:
    word = PROFILES[route].keys[action]
    return (
        keeson.frame(word, header=0xE6, side=0)
        if route == "15_22_15a"
        else okin_nframe.frame40(word)
    )


def clock(route: Route, now: datetime) -> bytes:
    if route == "15_22_15a":
        return keeson.clock_fields(
            (now.year - 1900, now.month - 1, now.day, now.hour, now.minute, now.second)
        )
    return okin_nframe.clock(
        (now.year - 2000, now.month, now.day, now.isoweekday(), now.hour, now.minute, now.second)
    )


def queries(route: Route) -> tuple[bytes, ...]:
    if route == "15_22_15a":
        return (keeson.checked(bytes((0xE1, 0x80, 3))),)
    return (okin_nframe.request(0xC0), okin_nframe.request(0xD0))


@dataclass(frozen=True, slots=True)
class Alarm:
    hour: int = 0
    minute: int = 0
    week: int = 0
    kind: int = 0
    enabled: bool = False

    def fields(self) -> tuple[int, int, int, int]:
        return self.hour, self.minute, self.week if self.enabled else 0, self.kind


def alarm_pair(first: Alarm, second: Alarm) -> bytes:
    return keeson.alarm_table(keeson.ALARM_WEEKLY, bytes((*first.fields(), *second.fields())))


def alarm_slot(slot: int, alarm: Alarm) -> bytes:
    if slot not in (1, 2):
        raise ValueError("Alarm slot must be 1 or 2")
    fields = (
        (alarm.week, alarm.kind, alarm.hour, alarm.minute, 0, 1, 0) if alarm.enabled else (0,) * 7
    )
    return okin_nframe.alarm(fields, slot)


def alarm_request(route: Route, request: AlarmRequest) -> Alarm:
    if not request.enabled:
        return Alarm()
    now = request.reference_time
    week = sum(1 << ((day + 1) % 7) for day in set(request.weekdays))
    if week:
        week |= 128
    else:
        target = now.replace(hour=request.hour, minute=request.minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        week = 1 << (target.isoweekday() % 7)
    return Alarm(
        request.hour,
        request.minute,
        week,
        ALARM_TYPES[route][WAKE_ACTIONS.index(request.wake_action)],
        True,
    )


def parse_alarms(route: Route, data: bytes) -> tuple[tuple[int, Alarm], ...]:
    """Only complete, unfragmented chunks; never infer the unresolved List dispatch."""
    if len(data) >= 11 and data[:3] == b"\xed\x80\x03":
        return tuple(
            (
                slot,
                Alarm(
                    data[offset],
                    data[offset + 1],
                    data[offset + 2],
                    data[offset + 3],
                    data[offset + 2] not in (0, 128),
                ),
            )
            for slot, offset in ((1, 3), (2, 7))
        )
    if len(data) >= 10 and data[:2] in (b"\xa5\x0c", b"\xa5\x0d"):
        week, kind, hour, minute = data[4:8]
        opened = data[9] >= 1 and not (data[9] == 1 and not any((week, kind, hour, minute)))
        return ((data[1] - 11, Alarm(hour, minute, week, kind, opened)),)
    return ()


def parse_massage(route: Route, data: bytes) -> tuple[int, int, int, int] | None:
    if route != "24_xx_xx" or len(data) < 9 or data[:2] != b"\xa5\x0b":
        return None
    return (
        (int.from_bytes(data[4:6], "big") + 599) // 600,
        data[6],
        0 if data[7] == 0 else data[7] // 3 + 1,
        0 if data[8] == 0 else data[8] // 3 + 1,
    )
