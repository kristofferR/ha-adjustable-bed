"""Verified extended, mattress, calendar and sleep frames for the explicit app profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ...codec import richmat as codec
from ..richmat_mh.protocol import mattress_frame

NORMAL_SETTINGS = {
    "pressure": (1, {"low": 1, "medium": 2, "high": 3}),
    "heat_level": (2, {"off": 0, "low": 1, "medium": 2, "high": 3}),
    "heat_duration": (3, {"2_hours": 1, "4_hours": 2, "6_hours": 3, "8_hours": 4}),
    "heat_area": (4, {"off": 0, "back": 1, "legs": 2, "both": 3}),
    "mode": (5, {"off": 0, "sleep": 1, "wake": 2, "decompress": 3, "leg": 4}),
    "pillow_duration": (7, {"20_minutes": 1, "40_minutes": 2, "60_minutes": 3}),
    "sleep_duration": (9, {"15_minutes": 1, "20_minutes": 2, "30_minutes": 3}),
}


@dataclass(frozen=True)
class AlarmRequest:
    family: Literal["mattress", "calendar"]
    enabled: bool
    delete: bool = False
    hour: int = 0
    minute: int = 0
    mattress_side: Literal["left", "right"] = "left"
    repeat: Literal["once", "daily"] = "once"
    intensity: int = 1
    slot: int = 1
    mode: int = 0
    weekdays: tuple[int, ...] = ()  # Monday=0 through Sunday=6
    bed: int = 0

    def validate(self) -> None:
        if not 0 <= self.hour <= 23 or not 0 <= self.minute <= 59:
            raise ValueError("Choose a valid local alarm time")
        if self.family == "mattress":
            if self.delete:
                raise ValueError("Delete is only for calendar alarms; disable a mattress alarm to cancel it")
            if (
                self.mattress_side not in ("left", "right")
                or self.repeat not in ("once", "daily")
                or not 1 <= self.intensity <= 3
            ):
                raise ValueError("Choose a mattress side, once/daily and intensity 1-3")
        elif self.family == "calendar":
            if not 1 <= self.slot <= 7 or not 0 <= self.mode <= 255 or not 0 <= self.bed <= 255:
                raise ValueError("Choose alarm slot 1-7 and byte-sized bed/mode values")
            if len(set(self.weekdays)) != len(self.weekdays) or any(
                not 0 <= x <= 6 for x in self.weekdays
            ):
                raise ValueError("Weekdays must be distinct values from Monday (0) to Sunday (6)")
        else:
            raise ValueError("Unknown alarm family")


def alarm_frame(request: AlarmRequest, now: datetime) -> bytes:
    request.validate()
    if request.family == "mattress":
        side = 1 if request.mattress_side == "left" else 2
        if not request.enabled:
            return mattress_frame(side, 0x0B, 0x10)
        return mattress_frame(
            side,
            0x0B,
            1 if request.repeat == "once" else 2,
            request.intensity,
            request.hour,
            request.minute,
            now.hour,
            now.minute,
        )
    if request.delete:
        return codec.record_20_len(5, 2, 1, bytes((request.slot,)))
    week = int(request.enabled) | sum(1 << (7 - day) for day in request.weekdays)
    record = bytes((request.slot, request.bed, request.hour, request.minute, request.mode, week))
    return codec.record_20_len(5, 1, 1, record)


def calendar_clock(now: datetime) -> tuple[bytes, bytes]:
    offset = now.utcoffset()
    dst = now.dst()
    if offset is not None and dst is not None:
        offset -= dst
    hours = int(offset.total_seconds() / 3600) if offset is not None else 0
    epoch = int(now.timestamp()).to_bytes(4, "big")
    return (
        codec.record_20_len(8, 2, 1, epoch + bytes((hours & 255,))),
        codec.record_20_len(
            8,
            3,
            1,
            bytes((now.year - 1970, now.month, now.day, now.hour, now.minute, now.second)),
        ),
    )


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8C if crc & 1 else 0)
    return crc


def sleep_frame(kind: int, payload: bytes = b"") -> bytes:
    body = bytes([kind]) + payload
    return bytes([0xFA, (len(payload) + 2) & 255, crc8(body)]) + body
