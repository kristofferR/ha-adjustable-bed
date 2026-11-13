"""Rize Home 1.1.2 (12), com.okin.rize: two explicit product layouts.

Unit163's 34 frozen literals reproduce with the existing Okin prefixed-record
and request builders. The 05 prefix is fixed, including on four-field records.
These are not the Kaidi Rize Beds or CST Rize product profiles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from ..codec import okin_nframe as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities

SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
REFRESH_MS: Final = 200
ONCE_OFFSETS_MS: Final = (0, 200, 400)
SAVE_MS: Final = 6000
POLL_MS: Final = 1500
RELEASE_STOP_MS: Final = 200
RELEASE_QUERY_MS: Final = 300
MTU_SETTLE_MS: Final = 350
NOTIFY_RETRY_MS: Final = 1000
Source = Literal["button", "speak"]

# The app's literal payload parameters, in transport order. No length,
# checksum, zero padding or command-word width is inferred from them.
FIELDS: Final = MappingProxyType(
    {
        "head_tilt_up": (0x40, 0, 0, 0),
        "head_tilt_down": (0x80, 0, 0, 0),
        "head_up": (0, 0, 0, 1),
        "head_down": (0, 0, 0, 2),
        "foot_up": (0, 0, 0, 4),
        "foot_down": (0, 0, 0, 8),
        "lumbar_up": (0, 0, 0, 0x10),
        "lumbar_down": (0, 0, 0, 0x20),
        "elevate_up": (0, 0, 0, 0x40),
        "elevate_down": (0, 0, 0, 0x80),
        "leisure": (0, 0, 0x40, 0),
        "zero_g": (0, 0, 0x10, 0),
        "anti_snore": (0, 0, 0x80, 0),
        "flat": (8, 0, 0, 0),
        "memory": (0, 1, 0, 0),
        "reading": (0, 0, 0x20, 0),
        "light": (0, 2, 0, 0),
        "massage_on": (0, 8, 0, 0, 0),
        "massage_off": (2, 0, 0, 0, 0),
        "massage_head_up": (0, 0, 8, 0, 0),
        "massage_head_down": (0, 0x80, 0, 0, 0),
        "massage_foot_up": (0, 0, 4, 0, 0),
        "massage_foot_down": (1, 0, 0, 0, 0),
        "massage_up": (0, 0, 0x0C, 0, 0),
        "massage_down": (1, 0x80, 0, 0, 0),
        "massage_toggle": (0, 0, 1, 0, 0),
        "massage_mode": (0x10, 0, 0, 0, 0),
        "massage_timer": (0, 0, 2, 0, 0),
        "motion_on": (0, 2, 0x10, 0, 0),
        "motion_off": (0, 2, 0x80, 0, 0),
        "reset_memories": (8, 0, 0x10, 0),
        "stop": (0, 0, 0, 0),
        "voice_stop": (0, 0, 0, 3, 0),
    }
)
FRAMES: Final = MappingProxyType(
    {
        **{key: codec.prefixed_query(fields, width=5) for key, fields in FIELDS.items()},
        "query": codec.request(0xB0),
    }
)
MOTOR_ACTIONS: Final = tuple(
    f"{axis}_{direction}"
    for axis in ("head_tilt", "head", "foot", "lumbar", "elevate")
    for direction in ("up", "down")
)
VOICE_ACTIONS: Final = (
    *MOTOR_ACTIONS,
    "stop",
    "leisure",
    "zero_g",
    "anti_snore",
    "flat",
    "reading",
    "memory",
    "massage_on",
    "massage_off",
    "massage_head_up",
    "massage_head_down",
    "massage_foot_up",
    "massage_foot_down",
    "massage_up",
    "massage_down",
    "light",
    "motion_on",
    "motion_off",
)
INTENSITY_ACTIONS: Final = frozenset(
    {
        "massage_head_up",
        "massage_head_down",
        "massage_foot_up",
        "massage_foot_down",
        "massage_up",
        "massage_down",
    }
)


@dataclass(frozen=True, kw_only=True)
class RizeHomeProfile:
    key: str
    name: str
    axes: tuple[str, ...]
    presets: tuple[str, ...]
    programmable: tuple[str, ...]
    combined_massage: bool
    poll_query_offsets_ms: tuple[int, ...]
    execution: ExecutionCapabilities = STREAM_HOLD
    frames: Mapping[str, bytes] = field(default_factory=lambda: FRAMES)


PROFILES: Final = MappingProxyType(
    {
        "remedy_iii": RizeHomeProfile(
            key="rize_home_remedy_iii",
            name="Remedy III",
            axes=("head", "foot", "lumbar", "elevate"),
            presets=("reading", "memory", "anti_snore", "leisure", "flat", "zero_g"),
            programmable=("reading", "memory", "anti_snore", "leisure", "zero_g"),
            combined_massage=True,
            poll_query_offsets_ms=(0, 100),
        ),
        "contempo_iv": RizeHomeProfile(
            key="rize_home_contempo_iv",
            name="Contempo IV",
            axes=("head_tilt", "head", "foot", "lumbar", "elevate"),
            presets=("anti_snore", "leisure", "flat", "zero_g"),
            programmable=("anti_snore", "leisure", "zero_g"),
            combined_massage=False,
            poll_query_offsets_ms=(0,),
        ),
    }
)


@dataclass(frozen=True)
class MassageState:
    timer_index: int
    active: bool
    combined_intensity: int | None = None
    head: int | None = None
    foot: int | None = None
    mode: int | None = None


def parse_massage(profile: RizeHomeProfile, data: bytes) -> MassageState | None:
    """Reject truncated packets safely; only project state the app persists.

    Remedy computes b8 for logging, but persists only the b7-derived combined
    intensity. Neither product's response reports motor positions or identity.
    """
    if len(data) < 9 or data[:3] != b"\xa5\x0b\x0e":
        return None
    if profile.combined_massage:
        timer = ((data[4] << 8) + data[5] + 599) // 600
        return MassageState(timer, timer != 0, combined_intensity=(data[7] + 1) // 2)
    timer = data[4] // 2
    return MassageState(timer, timer != 0, head=data[7], foot=data[8], mode=data[6])
