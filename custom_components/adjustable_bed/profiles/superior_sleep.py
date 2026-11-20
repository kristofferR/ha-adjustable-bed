"""Superior sleep 1.0.0 (2): explicit products over the Okin N-frame codec.

The name chooses only the GATT route. Both products use the same 40-bit
controls and binary clock/alarm records. Hardware effects remain unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from ..alarm import AlarmRequest
from ..codec import okin_nframe as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities

REFRESH_MS: Final = 100
ONCE_COUNT: Final = 2
SAVE_MS: Final = 6000
MOTION_MS: Final = 5000
QUERY_DELAY_MS: Final = 500
MASSAGE_RELEASE_MS: Final = 100


@dataclass(frozen=True, slots=True)
class Transport:
    service: str
    write: str
    notify: str


TRANSPORTS: Final = MappingProxyType(
    {
        "nordic": Transport(
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        ),
        "ble": Transport(
            "00001000-0000-1000-8000-00805f9b34fb",
            "00001001-0000-1000-8000-00805f9b34fb",
            "00001002-0000-1000-8000-00805f9b34fb",
        ),
    }
)


def transport_for_name(name: str) -> Transport:
    return TRANSPORTS["ble" if name.startswith("BLE") else "nordic"]


# Literal 32-bit keys, followed by the app's constant zero selector byte.
KEYS: Final = MappingProxyType(
    {
        "head_up": 0x00000001,
        "head_down": 0x00000002,
        "foot_up": 0x00000004,
        "foot_down": 0x00000008,
        "lumbar_up": 0x00000010,
        "lumbar_down": 0x00000020,
        "back_up": 0x00000040,
        "back_down": 0x00000080,
        "flat": 0x08000000,
        "zero_g": 0x00001000,
        "anti_snore": 0x00008000,
        "lounge": 0x00002000,
        "memory_1": 0x00010000,
        "memory_2": 0x00040000,
        "reset_memories": 0x08001000,
        "light": 0x00020000,
        "motion_on": 0x00021000,
        "motion_off": 0x00028000,
        "massage_on": 0x00080000,
        "massage_off": 0x02000000,
        "massage_head_up": 0x00000800,
        "massage_head_down": 0x00800000,
        "massage_foot_up": 0x00000400,
        "massage_foot_down": 0x01000000,
        "massage_up": 0x00000C00,
        "massage_down": 0x01800000,
        "massage_mode": 0x10000000,
        "wave_up": 0x10000000,
        "wave_down": 0x04000000,
        "massage_timer": 0x00000200,
        "stop": 0,
        "speech_stop": 0x00000003,
    }
)
FRAMES: Final = MappingProxyType(
    {
        **{key: codec.frame40(word) for key, word in KEYS.items()},
        "query_massage": codec.request(0xB0),
        "query_alarm": codec.request(0xC0),
    }
)
MOTORS: Final = tuple(
    f"{a}_{d}" for a in ("head", "foot", "back", "lumbar") for d in ("up", "down")
)
SPEECH_ACTIONS: Final = (
    *MOTORS,
    "speech_stop",
    "lounge",
    "zero_g",
    "anti_snore",
    "flat",
    "memory_1",
    "memory_2",
    "massage_on",
    "massage_off",
    "light",
    "motion_on",
    "motion_off",
)
LABELS: Final = MappingProxyType(
    {
        "flat": "Flat",
        "zero_g": "Zero gravity",
        "anti_snore": "Anti-snore",
        "lounge": "Lounge",
        "memory_1": "Memory 1",
        "memory_2": "Memory 2",
        "massage_on": "Massage on",
        "massage_off": "Massage off",
        "massage_up": "Massage intensity up",
        "massage_down": "Massage intensity down",
        "massage_head_up": "Head massage up",
        "massage_head_down": "Head massage down",
        "massage_foot_up": "Foot massage up",
        "massage_foot_down": "Foot massage down",
        "massage_mode": "Cycle massage mode",
        "massage_timer": "Cycle massage timer",
        "wave_up": "Wave increase",
        "wave_down": "Wave decrease",
        "light": "Toggle under-bed light",
        "speech_stop": "Speech stop",
        "query_massage": "Refresh massage state",
        "query_alarm": "Refresh alarm state",
        "reset_memories": "Reset saved presets",
    }
)


@dataclass(frozen=True, slots=True)
class SuperiorSleepProfile:
    key: str
    name: str
    axes: tuple[str, ...]
    presets: tuple[str, ...]
    adjustments: tuple[str, ...]
    programmable: tuple[str, ...]
    execution: ExecutionCapabilities = STREAM_HOLD


PROFILES: Final = MappingProxyType(
    {
        "ss350": SuperiorSleepProfile(
            "superior_sleep_ss350",
            "SS350",
            ("head", "foot"),
            ("flat", "zero_g", "anti_snore", "lounge", "memory_1", "memory_2"),
            ("massage_up", "massage_down", "wave_up", "wave_down", "massage_timer"),
            ("memory_1", "memory_2", "lounge", "zero_g"),
        ),
        "ss650": SuperiorSleepProfile(
            "superior_sleep_ss650",
            "SS650",
            ("head", "foot", "back", "lumbar"),
            ("flat", "zero_g", "anti_snore"),
            (
                "massage_head_up",
                "massage_head_down",
                "massage_foot_up",
                "massage_foot_down",
                "massage_mode",
                "massage_timer",
            ),
            ("zero_g",),
        ),
    }
)


def clock(now: datetime) -> bytes:
    return codec.clock(
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


def alarm_fields(mask: int, mode: int, hour: int, minute: int) -> bytes:
    """Keep the compiled selector transform, independently of RX display order."""
    return codec.alarm((mask, 5 if mode == 17 else 8 if mode == 9 else 6, hour, minute, 0, 1, 1))


def alarm(request: AlarmRequest) -> bytes:
    mask = 0x80 | sum(1 << ((day + 1) % 7) for day in request.weekdays)
    return alarm_fields(
        mask if request.enabled else 0,
        5 if request.wake_action == "wake_mode_1" else 6,
        request.hour if request.enabled else 0,
        request.minute if request.enabled else 0,
    )


@dataclass(frozen=True, slots=True)
class MassageState:
    timer_seconds: int
    timer_minutes: int
    mode: int
    head_level: int
    foot_level: int


def level(value: int) -> int:
    return value // 3 + value % 3 + int(value > 1)


def parse_massage(data: bytes) -> MassageState | None:
    if len(data) < 9 or data[:3] != b"\xa5\x0b\x0e":
        return None
    seconds = (data[4] << 8) | data[5]
    minutes = (seconds + 599) // 600 * 10 if 0 < seconds <= 1800 else 0
    return MassageState(seconds, minutes, data[6] - 1, level(data[7] & 15), level(data[8]))


def alarm_selector(mode: int) -> int:
    return 17 if mode == 5 else 19 if mode == 6 else 9


def alarm_display_days(mask: int) -> str:
    """App's independent RX display, without claiming physical weekday semantics."""
    return ", ".join(
        day
        for bit, day in zip(
            (6, 5, 4, 3, 2, 1, 0), ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), strict=True
        )
        if mask & (1 << bit)
    )


@dataclass(frozen=True, slots=True)
class AlarmState:
    alarm_hour: int
    alarm_minute: int
    alarm_mask: int
    alarm_selector: int
    alarm_enabled: bool
    display_days: str


def parse_alarm(data: bytes) -> AlarmState | None:
    """App display fields, independent of outbound schedule packing."""
    if len(data) < 8 or data[:2] != b"\xa5\x0c":
        return None
    return AlarmState(
        data[6],
        data[7],
        data[4],
        alarm_selector(data[5]),
        data[4] != 0,
        alarm_display_days(data[4]),
    )
