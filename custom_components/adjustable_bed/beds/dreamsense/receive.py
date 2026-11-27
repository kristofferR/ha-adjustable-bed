"""The app's receive framing and bed-consumed events, with bounded malformed input."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Final

from ...codec import richmat as codec

SIGNALS: Final = {
    bytes.fromhex("6e09010078"): "clock",
    bytes.fromhex("6e0e00037f"): "light",
    bytes.fromhex("6e16010186"): "music",
    bytes.fromhex("6e07010177"): "alarm_added",
    bytes.fromhex("6e07010278"): "alarm_cancelled",
}


@dataclass(frozen=True, slots=True)
class Alarm:
    number: int
    repeat: int
    mode: int
    hour: int
    minute: int
    second: int


@dataclass(slots=True)
class Receive:
    _extended_types: ClassVar[tuple[int, ...]] = (0x20, 0x21, 0x40)
    pending: bytearray = field(default_factory=bytearray)
    capabilities: set[str] = field(default_factory=set)
    alarms: dict[int, Alarm] = field(default_factory=dict)
    alarm_revision: int = 0
    alarm_record_revisions: dict[int, int] = field(default_factory=dict)
    split: bool | None = None
    last_ack: str | None = None

    def expire(self) -> None:
        self.pending.clear()

    def feed(self, data: bytes) -> None:
        self.pending.extend(data)
        while self.pending:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                return
            del self.pending[:start]
            if len(self.pending) < 3:
                return
            kind = self.pending[1]
            if kind in self._extended_types:
                if kind == 0x40 and len(self.pending) < 4:
                    return
                size = int.from_bytes(self.pending[2:4], "big") if kind == 0x40 else self.pending[2]
                if size < (6 if kind == 0x40 else 7):
                    # Reject the source's non-advancing zero-length loop.
                    self.pending.clear()
                    return
                if len(self.pending) < size:
                    return
                frame = bytes(self.pending[:size])
                del self.pending[:size]
                if kind == 0x20 and codec.is_valid(frame):
                    self._record(frame)
            else:
                end = self.pending.find(0x6E, 1)
                end = len(self.pending) if end < 0 else end
                frame = bytes(self.pending[:end])
                del self.pending[:end]
                self._common(frame)

    def _common(self, frame: bytes) -> None:
        if signal := SIGNALS.get(frame):
            if signal in ("clock", "light", "music"):
                self.capabilities.add(signal)
            else:
                self.last_ack = signal

    def _record(self, frame: bytes) -> None:
        domain, operation, sub = frame[3:6]
        if domain == 5 and sub == 1 and operation in (2, 3):
            # Each source event reads one record at bytes 6..11. A list may
            # arrive as several notifications; it is not a packed record array.
            if len(frame) < 13:
                return
            record = Alarm(*frame[6:12])
            self.alarm_revision += 1
            if self.alarms.get(record.number) != record:
                self.alarms[record.number] = record
                self.alarm_record_revisions[record.number] = self.alarm_revision
        elif domain == 0x0B and operation in (2, 3) and sub == 2 and len(frame) > 8:
            self.split = frame[7] != 2
