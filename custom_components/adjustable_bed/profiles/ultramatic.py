"""Ultramatic Smart Bed 1.1.2 app data.

This is the Nordic UART app, separate from the Ultramatic ORE route.
Source labels POSTURE/LUMBAR disagree with LUMBAR/HIPS enum identifiers;
neither establishes physical actuator anatomy.
"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..execution import STREAM_HOLD
from .okin_nframe import Hold, OkinNFrameProfile

SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SELECTORS: Final = MappingProxyType({"A": 1, "AB": 0, "B": 2})
HEADERS: Final = frozenset({b"\xa5\x0b\x0e", b"\xed\x80\x03", b"\xa5\x0c\x0e"})
QUERY_MASSAGE: Final = codec.request(0xB0)
QUERY_ALARM: Final = codec.request(0xC0)
SAVE_HOLD_MS: Final = 6000
NOTIFY_RETRY_MS: Final = 1000
STARTUP: Final = ((0, "clock"), (200, "massage"), (500, "massage"))
CLOCK_SYNC: Final = ((0, "clock"), (500, "clock"))
MASSAGE_QUERIES: Final = (300, 600, 900)
ALARM_QUERY: Final = ((0, "query"), (200, "query"))
ALARM_SET: Final = ((0, "alarm"), (300, "alarm"), (500, "query"), (600, "query"), (700, "query"))

# Words are in the shared codec's big-endian frame order, not native masks.
PROFILE: Final = OkinNFrameProfile(
    key="ultramatic_smart_bed",
    name="Ultramatic Smart Bed",
    bed_types=("ultramatic_smart_bed",),
    width=5,
    write="no_response",
    envelope="plain",
    selectors=(1, 0, 2),
    axes=("head", "foot", "headtilt", "lumbar", "hips"),
    keys=MappingProxyType(
        {
            "HEADUP": 0x00000001,
            "HEADDOWN": 0x00000002,
            "FOOTUP": 0x00000004,
            "FOOTDOWN": 0x00000008,
            "HEADTILTUP": 0x00000010,
            "HEADTILTDOWN": 0x00000020,
            "LUMBARUP": 0x00000040,
            "LUMBARDOWN": 0x00000080,
            "HIPSUP": 0x40000000,
            "HIPSDOWN": 0x80000000,
            "ZG": 0x00001000,
            "ANTI": 0x00008000,
            "FLAT": 0x08000000,
            "M1": 0x00010000,
            "M2": 0x00040000,
            "LIGHT": 0x00020000,
            "timerSwitch": 0x00000200,
            "headStrengthAdd": 0x00000800,
            "headStrengthReduce": 0x00800000,
            "footStrengthAdd": 0x00000400,
            "footStrengthReduce": 0x01000000,
            "waveAdd": 0x10000000,
            "waveReduce": 0x04000000,
            "massageOnOff": 0x00000100,
            "reset_memory": 0x08001000,
            "STOP": 0,
        }
    ),
    hold=Hold(repeat_ms=300, releases=1, release_after_ms=100),
    execution=STREAM_HOLD,
    memory_slots=2,
)


def control(action: str, side: str = "AB") -> bytes:
    """Encode the app's literal key and independent A/AB/B selector."""
    return codec.frame40(PROFILE.keys[action], 0 if action == "STOP" else SELECTORS[side])


def bcd(value: int) -> int:
    """App builder's two decimal digits, bounded before transmission."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 99:
        raise ValueError("BCD value must be an integer from 0 to 99")
    return value // 10 * 16 + value % 10


def clock(now: datetime) -> bytes:
    return codec.clock(
        tuple(
            bcd(v)
            for v in (
                now.year - 2000,
                now.month,
                now.day,
                (now.weekday() + 1) % 7,
                now.hour,
                now.minute,
                now.second,
            )
        )
    )


# set_alarm wake actions to the app's alarm types (Vibrate, ZG, M1).
WAKE_TYPES: Final = MappingProxyType({"massage": 1, "zero_g": 2, "memory_1": 3})


def alarm_days(weekdays: tuple[int, ...]) -> int:
    """Return the app's Sunday-bit-0 day mask; no weekdays is its once mask, 128."""
    return sum(1 << ((day + 1) % 7) for day in weekdays) if weekdays else 128


def alarm(
    hour: int,
    minute: int,
    days: int,
    type_code: int,
    enabled: bool,
    side: str = "AB",
    *,
    now: datetime | None = None,
) -> bytes:
    """Outbound TYPE byte3 and SIDE byte8, unlike the receive record layout."""
    for name, value, upper in (("hour", hour, 23), ("minute", minute, 59), ("days", days, 255)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= upper:
            raise ValueError(f"Invalid alarm {name}")
    if isinstance(type_code, bool) or type_code not in (1, 2, 3) or not isinstance(enabled, bool):
        raise ValueError("Alarm requires Vibrate, ZG or M1 and a boolean enabled flag")
    if days == 128:
        if now is None:
            raise ValueError("One-shot alarm requires local current time")
        weekday = (now.weekday() + 1) % 7
        if now.replace(hour=hour, minute=minute, second=0, microsecond=0) <= now:
            weekday = (weekday + 1) % 7
        days = 1 << weekday
    return codec.alarm((days, type_code, bcd(hour), bcd(minute), 0, int(enabled), SELECTORS[side]))


def timer_bucket(value: int) -> int:
    return (value - 1) // 600 + 1 if 1 <= value <= 1800 else 0


def equivalent(first: bytes, second: bytes, *, massage: bool) -> bool:
    if len(first) != 7 or len(second) != 7:
        return False
    if not massage:
        return first[1:] == second[1:]
    return (
        first[1] == second[1]
        and first[3:] == second[3:]
        and timer_bucket(int.from_bytes(first[1:3], "big"))
        == timer_bucket(int.from_bytes(second[1:3], "big"))
    )


def state(
    records: tuple[bytes, bytes, bytes],
    side: str,
    now: datetime,
) -> dict[str, str | int | bool]:
    """Normalize each accepted raw receive layout with the app's selection rules."""
    header, first, second = records
    massage = header == b"\xa5\x0b\x0e"
    standalone = first[0] == 0 or second[0] == 0
    selected = None
    if standalone:
        selected = first  # Even when only the SECOND record carries zero.
    elif side == "AB":
        if {first[0], second[0]} == {1, 2} and equivalent(first, second, massage=massage):
            selected = first
    else:
        selected = next((r for r in (first, second) if r[0] == SELECTORS[side]), None)
    result: dict[str, str | int | bool] = {
        "kind": "massage" if massage else "alarm",
        "standalone": standalone,
    }
    if massage:
        r = selected if selected is not None else bytes(7)
        result.update(
            timer_bucket=timer_bucket(int.from_bytes(r[1:3], "big")),
            wave=r[3],
            head=r[4],
            foot=r[5],
        )
    elif selected is None or selected[1] == 0:
        result.update(
            days=255, wake_type="Vibrate", hour=now.hour, minute=now.minute, enabled=False
        )
    else:
        result.update(
            days=selected[1],
            wake_type="Vibrate" if selected[2] == 1 else "Position",
            hour=(selected[3] >> 4) * 10 + (selected[3] & 15),
            minute=(selected[4] >> 4) * 10 + (selected[4] & 15),
            enabled=selected[6] == 1,
        )
        if selected[2] != 1:
            result["position_index"] = selected[2] - 2
    return result
