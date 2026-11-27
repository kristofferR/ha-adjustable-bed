"""The accepted ordinary dispatcher subset, without extended payload guesses."""

from typing import Final

EXACT: Final = {
    bytes.fromhex("6e09010078"): "clock_feature",
    bytes.fromhex("6e0e00037f"): "light_feature",
}


class CommonReceive:
    """Mirror the app's early dispatch and next-marker ordinary boundaries."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        out: list[bytes] = []
        while len(self.buffer) >= 3:
            try:
                start = self.buffer.index(0x6E)
            except ValueError:
                self.buffer.clear()
                break
            del self.buffer[:start]
            if len(self.buffer) < 3:
                break  # Unverified post-junk corner: retain, never infer state.
            if self.buffer[1] in (0x20, 0x21, 0x40):
                self.buffer.clear()  # Shared extended/desk/OTA semantics are unverified.
                break
            try:
                end = self.buffer.index(0x6E, 1)
            except ValueError:
                end = len(self.buffer)
            out.append(bytes(self.buffer[:end]))
            del self.buffer[:end]
        return out

    def expire(self) -> None:
        self.buffer.clear()
