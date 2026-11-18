"""OrmatekTechnoSmart 1.2.0: independent wire catalog and page layout."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, Literal

from ..codec import keeson, okin_nframe
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release, encode

type Wire = Literal["okin15", "okin24"]
HOLD_INTERVAL_MS: Final = 200
RELEASE_DELAY_MS: Final = 100
STOP_INTERVAL_MS: Final = 200
MASSAGE_UI_DELAY_MS: Final = 200
MASSAGE_HELPER_DELAY_MS: Final = 100
ALARM_QUERY_DELAY_MS: Final = 100
LAYOUTS: Final = {"new": "Techno Smart New", "lite": "Techno Smart Lite"}
WIRES: Final = {"okin15": "Okin", "okin24": "SmartBed"}
WORDS: Final = {
    "stop": 0,
    "lightSwitch": 0x20000,
    "headUp": 1,
    "headDown": 2,
    "footUp": 4,
    "footDown": 8,
    "hfUp": 5,
    "hfDown": 10,
    "memoryAntiSnore": 0x8000,
    "memoryLounge": 0x2000,
    "memory1M5": 0x10000,
    "memoryTvpc": 0x4000,
    "memoryZero": 0x1000,
    "memoryFlat": 0x8000000,
    "massageSwitch": 0x100,
    "massageTimeSwitch": 0x200,
    "strengthHeadUp": 0x800,
    "strengthFootUp": 0x400,
    "massageWaveSwitch": 0x10000000,
}
PROFILES: Final = {
    wire: KeesonProfile(
        key=f"ormatek_{wire}",
        carrier="k1" if wire == "okin15" else "p2_side",
        header=0xE6,
        side=0 if wire == "okin15" else None,
        no_response=True,
        hold=(1, HOLD_INTERVAL_MS),
        refresh_ms=HOLD_INTERVAL_MS,
        execution=STREAM_HOLD,
        release=Release(steps=((RELEASE_DELAY_MS, 0), (STOP_INTERVAL_MS, 0)), after_tap=True),
        presets={
            "flat": WORDS["memoryFlat"],
            "zero_g": WORDS["memoryZero"],
            "tv": WORDS["memoryTvpc"],
            "anti_snore": WORDS["memoryAntiSnore"],
        },
        lights=None,
        massage="none",
        tilt=False,
        lumbar=False,
        keeson_motor_names=False,
    )
    for wire in WIRES
}
WAKE: Final = {
    "okin15": {
        "none": 0,
        "flat": 28,
        "memory_1": 17,
        "memory_2": 19,
        "zero_g": 13,
        "anti_snore": 16,
        "tv": 15,
        "massage": 9,
    },
    "okin24": {
        "none": 0,
        "flat": 9,
        "memory_1": 5,
        "memory_2": 6,
        "zero_g": 1,
        "anti_snore": 4,
        "tv": 3,
        "massage": 8,
    },
}
WAKE_CHOICES: Final = {"new": ("massage", "memory_1", "flat"), "lite": ("zero_g", "tv")}


def match_name(name: str) -> Wire | None:
    name = name.lower()
    return (
        "okin15" if name.startswith("okin") else "okin24" if name.startswith("smartbed") else None
    )


def normal(wire: str, action: str) -> bytes:
    return encode(PROFILES[wire], WORDS[action])


def clock(wire: str, now: datetime) -> bytes:
    if wire == "okin15":
        return keeson.clock(now)
    return okin_nframe.clock(
        (now.year - 2000, now.month, now.day, now.isoweekday(), now.hour, now.minute, now.second)
    )


def weekday(mask: int, hour: int, minute: int, now: datetime) -> int:
    """Source builder's next-day branch; the reachable UI always supplies 255."""
    if mask > 128:
        return mask
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if int((target - now).total_seconds() * 1000) < 0:
        target += timedelta(hours=24)
    return 1 << (target.isoweekday() % 7)


def alarm(
    wire: str,
    *,
    enabled: bool,
    hour: int = 0,
    minute: int = 0,
    wake: str = "none",
    week: int = 255,
    slot: int = 0,
) -> bytes:
    """Encode the app builder; public admission restricts layout, week and slot."""
    mode = WAKE[wire][wake]
    if wire == "okin15":
        return keeson.alarm_table(3, bytes((hour, minute, week if enabled else 0, mode)))
    fields = (week, mode, hour, minute, 0, 1, 0) if enabled else (0,) * 7
    return okin_nframe.alarm(fields, slot=1 if slot == 0 else 2)


def alarm_queries(wire: str, *, after_set: bool = False) -> tuple[bytes, ...]:
    if wire == "okin15":
        return (keeson.ALARM_QUERY,) if after_set else (okin_nframe.request(0xC0),)
    return (okin_nframe.request(0xC0), okin_nframe.request(0xD0))


def massage_query(wire: str) -> bytes:
    return normal(wire, "stop") if wire == "okin15" else okin_nframe.request(0xB0)
