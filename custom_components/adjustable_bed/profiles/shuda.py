"""The single reachable Shuda app profile over Okin N-frame."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..const import BED_TYPE_SHUDA, MANUFACTURER_ID_OKIN
from ..execution import ExecutionCapabilities
from .okin_nframe import Hold, OkinNFrameProfile, Tap

REFRESH_MS: Final = 200
SAVE_HOLD_MS: Final = 5500
# The app's help starts calling it a save at five seconds.
RECALL_LIMIT_MS: Final = 5000
ORDINARY_SLOTS: Final = (1, 2)
ALARM_MODES: Final = MappingProxyType({"memory_1": 5, "flat": 9, "zero_g": 1})
SAVE_KEYS: Final = frozenset({"memory_1", "zero_g", "tv"})

KEYS: Final = MappingProxyType(
    {
        "head_up": 0x00000001,
        "head_down": 0x00000002,
        "feet_up": 0x00000004,
        "feet_down": 0x00000008,
        "flat": 0x08000000,
        "zero_g": 0x00001000,
        "memory_1": 0x00010000,
        "tv": 0x00004000,
        "light": 0x00020000,
    }
)

SHUDA: Final = OkinNFrameProfile(
    key="shuda",
    name="Shuda",
    bed_types=(BED_TYPE_SHUDA,),
    width=5,
    write="response",
    envelope="plain",
    axes=("back", "legs"),
    keys=KEYS,
    execution=ExecutionCapabilities(hold="stream", hold_controls=frozenset(KEYS) - SAVE_KEYS),
    hold=Hold(repeat_ms=REFRESH_MS, releases=1),
    recall=Tap(releases=1),
    memory_slots=1,
    memory_save=Tap(
        repeats=(SAVE_HOLD_MS + REFRESH_MS - 1) // REFRESH_MS, repeat_ms=REFRESH_MS, releases=1
    ),
    tap=Tap(releases=1),
)


def clock_frame(now: datetime) -> bytes:
    """Encode local time with an ISO weekday and the year offset from 2000."""
    return codec.wrapped_setting(
        codec.clock(
            (
                (now.year - 2000) & 0xFF,
                now.month,
                now.day,
                now.isoweekday(),
                now.hour,
                now.minute,
                now.second,
            )
        )
    )


def edited_week(days: Iterable[int]) -> int:
    """Encode an edited selection. Raw alarm models bypass this transform."""
    mask = sum(1 << ((day + 1) % 7) for day in set(days))
    return mask | 0x80 if mask else 0


def alarm_frame(row: codec.ShortAlarmReport) -> bytes:
    """Serialize the model's actual week byte without modifying it."""
    slot = row.slot if row.slot in (2, 3) else 1
    return codec.wrapped_setting(
        codec.alarm((row.week, row.mode, row.hour, row.minute, 0, row.enabled, 0), slot)
    )


def query_frame(slot: int) -> bytes:
    return codec.request({2: 0xD0, 3: 0xE0}.get(slot, 0xC0))


def alarm_model(data: bytes) -> codec.ShortAlarmReport | None:
    """Apply the alarm callback's model normalization to the wire fields."""
    row = codec.parse_short_alarm(data)
    if row is None:
        return None
    enabled = row.enabled
    if enabled == 1 and not (row.week or row.mode or row.hour or row.minute):
        enabled = 0
    return replace(
        row,
        enabled=enabled,
        week=0 if enabled and row.week < 128 else row.week,
        mode=row.mode if enabled else ALARM_MODES["flat"],
    )


def manufacturer_identity(data: Mapping[int, bytes]) -> str | None:
    """The app's optional identity, independent of the Bluetooth address."""
    value = data.get(MANUFACTURER_ID_OKIN, b"")
    return value[-2:-8:-1].hex() if len(value) >= 7 else None
