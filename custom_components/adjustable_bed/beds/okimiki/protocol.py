"""Okimiki's countdown, alarm records and exact within-session receive rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import ceil, floor, trunc
from typing import Final

from ...codec import richmat as codec
from ..goodvibe.receive import Notifications

EVENTS: Final = {
    "6e09010078": "alarm",
    "6e0e00037f": "light",
    "6e07010177": "alarm_add_success",
    "6e07010278": "alarm_cancel_success",
    # Passive shared BED effects, never promoted to capabilities or controls.
    "6e2100008f": "anti_snore",
    "6e23018416": "control_box_lock",
    "6e23008415": "control_box_unlock",
    "6e23a06e9f": "anti_snore_stop_music",
}


@dataclass(frozen=True, slots=True)
class Alarm:
    id: int
    reserved: int
    hour: int
    minute: int
    opcode: int
    mask: int

    def frame(self) -> bytes:
        return codec.record(
            5, 1, 1, (self.id, self.reserved, self.hour, self.minute, self.opcode, self.mask)
        )


def light_seconds(seconds: int) -> bytes:
    """First four padded hex digits, with zero mapped to always-on FFFF."""
    digits = f"{seconds:04x}"
    return codec.light_timer(
        *((255, 255) if seconds == 0 else (int(digits[:2], 16), int(digits[2:4], 16)))
    )


def color_byte(component: float) -> int:
    return (floor(component * 255 + 0.5) if component >= 0 else ceil(component * 255 - 0.5)) & 255


def sync_time(now: datetime, zone: datetime) -> tuple[bytes, bytes]:
    """The source takes the first eight padded epoch hex digits, including overflow."""
    offset = zone.utcoffset()
    if now.utcoffset() is None or offset is None:
        raise ValueError("Clock synchronization requires local aware datetimes")
    digits = f"{int(now.timestamp()):08x}"
    epoch = bytes.fromhex(digits[:8])
    return codec.record(8, 2, 1, (*epoch, trunc(offset.total_seconds() / 3600))), codec.calendar(
        now
    )


def countdown_minutes(now: datetime, when: datetime) -> int:
    delta = when.timestamp() - now.timestamp()
    if trunc(delta / 60) <= 0:
        delta += 86400
    return trunc(delta / 60)


def countdown(minutes: int, opcode: int) -> tuple[bytes, bytes]:
    return codec.frame(0x6E, 5, minutes & 255, 0), codec.frame(
        0x6E, 6, trunc(minutes / 256), opcode
    )


def next_alarm_id(records: tuple[Alarm, ...]) -> int:
    """The app's allocator, including its serialized FF exhaustion quirk."""
    return next((n for n in range(1, 8) if all(row.id != n for row in records)), -1)


def repeat_mask(days: tuple[int, ...], enabled: bool) -> int:
    return sum(1 << (7 - day) for day in set(days)) | int(enabled)


class Receiver(Notifications):
    """Common consumes the entire current buffer; only 6E20 is length framed.

    No repaired five-byte common assembly, splitting on a second header or
    expiry timer. Bounds/zero-progress failures are rejected at the HA boundary.
    """

    def __init__(self, emit: Callable[[str, object], None]) -> None:
        super().__init__(emit)

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)
        try:
            while len(self.buffer) >= 3:
                try:
                    start = self.buffer.index(0x6E)
                except ValueError:
                    self.clear()
                    break
                del self.buffer[:start]
                if len(self.buffer) < 3:
                    break
                if self.buffer[1] != 0x20:
                    packet = bytes(self.buffer)
                    self.clear()
                    if event := EVENTS.get(packet.hex()):
                        self.emit(event, None)
                    continue
                length = self.buffer[2]
                if length < 4:
                    raise ValueError("Invalid extended notification length")
                if len(self.buffer) < length:
                    break
                packet = bytes(self.buffer[:length])
                del self.buffer[:length]
                if not codec.is_valid(packet):
                    continue
                if packet[3:5] == bytes((5, 1)) and len(packet) > 5 and packet[5] in (2, 3):
                    if len(packet) < 13:
                        raise ValueError("Incomplete recurring alarm fields")
                    self.emit(
                        "alarm_list" if packet[5] == 2 else "alarm_update", Alarm(*packet[6:12])
                    )
            self.rejection = None
        except ValueError as err:
            self.rejection = str(err)
            self.clear()
