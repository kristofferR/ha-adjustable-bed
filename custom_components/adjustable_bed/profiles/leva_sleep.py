"""Leva Sleep 1.0.2 on the Keeson E5/E6 carrier."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Final

from ..codec import keeson as codec
from .keeson import LEVA_SLEEP, KeesonProfile
from .ore_ultramatic import Route

P2_PRESETS: Final = {
    "flat": 0x08000000,
    "zero_g": 0x00001000,
    "memory_1": 0x00010000,
    "memory_2": 0x00040000,
}
_WAKE_KINDS: Final = {"none": 0, "massage": 1, "memory_1": 2, "memory_2": 3}
WAKE_KINDS: Final[dict[Route, dict[str, int]]] = {"P1": _WAKE_KINDS, "P2": _WAKE_KINDS}
P2_WAKE_CODES: Final = {1: 0x09, 2: 0x11, 3: 0x13}


def profile(route: Route) -> KeesonProfile:
    """The automatically selected P1 or P2 carrier."""
    if route == "P1":
        return LEVA_SLEEP
    return replace(LEVA_SLEEP, header=0xE6, order="little", side=0)


def alarm(
    route: Route, now: datetime, *, enabled: bool, hour: int, minute: int, repeat: int, kind: int
) -> bytes:
    """Encode the user's alarm selection. The received raw type is separate."""
    hour = max(0, int.from_bytes(bytes((hour & 255,)), signed=True))
    minute = max(0, int.from_bytes(bytes((minute & 255,)), signed=True))
    if route == "P1":
        return codec.ore_alarm_p1(
            now, enabled=enabled, hour=hour, minute=minute, repeat=repeat, kind=kind
        )
    record = bytes((hour, minute, repeat & 255, P2_WAKE_CODES.get(kind, 0))) if enabled else b""
    return codec.alarm_table(codec.ALARM_WEEKLY, record)
