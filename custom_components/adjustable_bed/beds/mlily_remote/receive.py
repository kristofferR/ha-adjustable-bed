"""MLILY Remote BED receive branches, without promoting shared parsers to features."""

from collections.abc import Callable

from ...codec import richmat as codec
from ..goodvibe.receive import common, extended


class Receiver:
    """Bounded session buffer; complete common frames and guarded extended fields."""

    def __init__(self, emit: Callable[[str, object], None]) -> None:
        self.emit = emit
        self.buffer = bytearray()
        self.rejection: str | None = None

    def clear(self) -> None:
        self.buffer.clear()

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)
        self.rejection = None
        while len(self.buffer) >= 3:
            try:
                start = self.buffer.index(0x6E)
            except ValueError:
                self.clear()
                return
            del self.buffer[:start]
            if len(self.buffer) < 3:
                return
            framed = self.buffer[1] == 0x20
            size = self.buffer[2] if framed else 5
            if size < 7 and framed:
                self.rejection = "Invalid extended notification length"
                del self.buffer[0]
                continue
            if len(self.buffer) < size:
                return
            b = list(self.buffer[:size])
            del self.buffer[:size]
            try:
                if framed:
                    if not codec.is_valid(bytes(b)) or b[3] not in (1, 2, 3, 4, 5, 6, 10):
                        continue
                    if b[3] == 10 and b[4] not in (1, 2, 3, 4):
                        continue  # Music/vibrator diagnostics are outside BED scope.
                    if b[3] == 6 and b[4] not in (1, 2, 3):
                        continue
                    if b[3] == 5 and b[4] == 1 and len(b) < 13:
                        raise ValueError("Truncated alarm record")
                    events = extended(b, mlily=True)
                else:
                    if b[1] == 0x90 and b[2] >> 4 in (11, 13):
                        continue  # Audio/USB control state, not product capability.
                    if bytes(b).hex() in ("6e1a000189", "6e16010186"):
                        continue
                    events = common(b)
                for name, value in events:
                    self.emit(name, value)
            except (ValueError, IndexError) as error:
                self.rejection = str(error)
