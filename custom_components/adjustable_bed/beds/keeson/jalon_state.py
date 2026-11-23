"""Jalon's notification rules, independent of the other Keeson app parsers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MassageStatus:
    section: Literal["massage", "massage_motion4"]
    time: int
    wave: int
    headStrength: int
    footStrength: int


@dataclass(frozen=True)
class AlarmStatus:
    section: Literal["alarm"]
    week: int
    type: int
    hour: int
    minute: int
    isOpen: int
    isFirst: int


def parse_notification(profile: str, data: bytes) -> MassageStatus | AlarmStatus | None:
    """Consume one complete notification. Reject truncation rather than invent zero state.

    The app ignores the asset length/offset fields and does not validate checksums
    or assemble fragments. P1's long-massage declaration has no live consumer.
    """
    if len(data) < 3:
        return None
    if profile in ("jalon_13", "jalon_15") and data[:2] == b"\xed\xfe":
        if len(data) < 15:
            return None
        return MassageStatus(
            "massage", data[14] & 15, data[14] >> 4, _strength(data[7]), _strength(data[8])
        )
    if profile == "jalon_15" and data[:2] == b"\xf4\xfe":
        if len(data) < 22:
            return None
        return MassageStatus(
            "massage_motion4", data[19] & 15, data[21], _strength(data[11]), _strength(data[12])
        )
    if profile == "jalon_24" and data[:2] == b"\xa5\x0b":
        if len(data) < 9:
            return None
        ticks = (data[4] << 8) + data[5]
        return MassageStatus(
            "massage",
            (ticks + 599) // 600,
            data[6],
            _star_strength(data[7]),
            _star_strength(data[8]),
        )
    # Header dispatch is hardcoded, not the selected asset's alarm handle.
    if data[:2] in (b"\xa5\x0c", b"\xa5\x0d") or data[:3] == b"\xed\x80\x03":
        if profile == "jalon_24":
            if len(data) < 10:
                return None
            return AlarmStatus(
                "alarm", data[4], data[5], data[6], data[7], data[9], 0 if data[1] == 12 else 1
            )
        if len(data) < 7:
            return None
        return AlarmStatus(
            "alarm", data[5], data[6], data[3], data[4], 0 if data[5] in (0, 128) else 1, 0
        )
    return None


def _strength(value: int) -> int:
    nibble = value & 15
    return 1 if nibble <= 2 else 2 if nibble <= 4 else 3


def _star_strength(value: int) -> int:
    return 0 if value == 0 else value // 3 + 1
