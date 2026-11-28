"""Amada Smart 1.0.0 (1), accepted bounded PARTIAL app profile, hardware unverified.

All transmit literals reproduce through the unchanged Okin N-frame codec.
Selectors name the app's A/AB/B targets, not physical Left/Right bed sides.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..execution import ExecutionCapabilities
from .okin_nframe import Hold, OkinNFrameProfile, Tap

SELECTORS: Final = MappingProxyType({"a": 0xAA, "ab": 0, "b": 0xBB})
SELECTOR_CHOICES: Final = MappingProxyType({"a": "A", "ab": "AB (both app targets)", "b": "B"})
SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NAME_PREFIX: Final = "smartbed4"
REFRESH_MS: Final = 100
SAVE_MS: Final = 6000
RECALL_MS: Final = 400  # HA finite press, not an unconditional source minimum.
MOTOR_KEYS: Final = ("head_up", "head_down", "foot_up", "foot_down", "tilt_up", "tilt_down", "combined_up", "combined_down")
PRESETS: Final = ("zero_g", "anti_snore", "tv_pc", "lounge", "flat", "memory_1")
SAVES: Final = tuple(k for k in PRESETS if k != "flat")
UTILITY_TAILS: Final = MappingProxyType({
    "massage_switch": 4, "timer_step": 4, "wave_mode": 4,
    "foot_strength_up": 4, "foot_strength_down": 2,
    "strength_up": 4, "strength_down": 4, "light_toggle": 4,
})
ALARM_MODES: Final = MappingProxyType({
    "none": 0, "zero_g": 1, "lounge": 2, "tv": 3, "anti_snore": 4,
    "memory_1": 5, "light": 7, "massage": 8, "flat": 9,
})
AMADA: Final = OkinNFrameProfile(
    key="amada", name="Amada Smart", bed_types=("amada",), width=5,
    write="no_response", envelope="plain", axes=("back", "legs", "head"),
    selectors=tuple(SELECTORS.values()),
    execution=ExecutionCapabilities(hold="stream", hold_controls=frozenset(MOTOR_KEYS)),
    keys=MappingProxyType({
        "head_up": 1, "head_down": 2, "foot_up": 4, "foot_down": 8,
        "combined_up": 5, "combined_down": 10, "tilt_up": 16, "tilt_down": 32,
        "tv_pc": 0x4000, "zero_g": 0x1000, "lounge": 0x2000, "anti_snore": 0x8000,
        "flat": 0x08000000, "memory_1": 0x10000, "reset_memory": 0x08001000,
        "massage_switch": 0x100, "timer_step": 0x200, "wave_mode": 0x10000000,
        "foot_strength_up": 0x400, "foot_strength_down": 0x01000000,
        "strength_up": 0x800, "strength_down": 0x00800000, "light_toggle": 0x20000,
        "stop": 0,
    }),
    hold=Hold(repeat_ms=REFRESH_MS, releases=1),
    recall=Tap(repeats=4, repeat_ms=REFRESH_MS, releases=1), memory_slots=1,
    tap=Tap(repeats=4, repeat_ms=REFRESH_MS),
)


def clock_frame(now: datetime) -> bytes:
    """One coherent local timestamp; app month precedes year offset, Sunday=0."""
    return codec.clock((now.month, now.year - 2000, now.day, now.isoweekday() % 7,
                        now.hour, now.minute, now.second))


def alarm_week(days: tuple[int, ...], hour: int, minute: int, now: datetime) -> int:
    """HA Monday0..Sunday6; equality selects tomorrow for a once alarm."""
    if any(type(day) is not int or day not in range(7) for day in days):
        raise ValueError("Invalid weekday")
    if days:
        return 0x80 | sum(1 << ((day + 1) % 7) for day in set(days))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return 1 << (target.isoweekday() % 7)


def alarm_frame(hour: int, minute: int, repeat: int, kind: int, enabled: bool, selector: int) -> bytes:
    return codec.alarm((repeat, kind, hour, minute, 0, int(enabled), selector))
