"""Decode the ordinary Enso 2 bed notifications from its GATT stream."""

from dataclasses import dataclass, field
from typing import Final

from ...codec.richmat import is_valid

ALARM_PRESENT: Final = bytes.fromhex("6e09010078")
LIGHT_OFF: Final = bytes.fromhex("6e0e00017d")
LIGHT_ON: Final = bytes.fromhex("6e0e00037f")
AROMA_PRESENT: Final = bytes.fromhex("6e1a000189")
ALARM_SET: Final = bytes.fromhex("6e07010177")
ALARM_CANCELLED: Final = bytes.fromhex("6e07010278")
AROMA_SAVED: Final = bytes.fromhex("6e1a00028a")
AROMA_REJECTED: Final = bytes.fromhex("6e1a00038b")

# Desk notifications share the receiver, but have no bed interpretation.
_LENGTHS: Final = {0x08: 5, 0x90: 7, 0x92: 16, 0x94: 16, 0x97: 16}
_BED_FUNCTIONS: Final = frozenset({0x07, 0x09, 0x0E, 0x1A})


@dataclass(slots=True)
class Receiver:
    buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes | bytearray) -> tuple[bytes, ...]:
        """Reassemble fragmented notifications and consume checksum-valid windows."""
        self.buffer.extend(data)
        frames = []
        while self.buffer:
            try:
                start = self.buffer.index(0x6E)
            except ValueError:
                self.buffer.clear()
                break
            del self.buffer[:start]
            if len(self.buffer) < 2:
                break
            function = self.buffer[1]
            size = 5 if function in _BED_FUNCTIONS else _LENGTHS.get(function, 0)
            if size and len(self.buffer) < size:
                # A complete record following a corrupt prefix still gets a chance.
                if len(self.buffer) < 5 or 0x6E not in self.buffer[2:]:
                    break
                # This frame may simply be fragmented. Prefer a complete bed reply.
                if not any(
                    self.buffer[i] == 0x6E
                    and self.buffer[i + 1] in _BED_FUNCTIONS
                    and is_valid(bytes(self.buffer[i : i + 5]))
                    for i in range(2, len(self.buffer) - 4)
                ):
                    break
                del self.buffer[0]
                continue
            frame = bytes(self.buffer[:size])
            if size and is_valid(frame):
                del self.buffer[:size]
                if function in _BED_FUNCTIONS:
                    frames.append(frame)
            else:
                del self.buffer[0]
        return tuple(frames)
