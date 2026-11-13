"""Bedgear-specific projections and bounded, source-shaped stream framing."""

import re
from dataclasses import dataclass, field


def color_parameters(rgb: tuple[int, int, int], brightness: float = 1) -> tuple[int, int, int]:
    values = tuple(int((int(channel * brightness) & 255) / 255 * 120) for channel in rgb)
    return (
        values[0] if values[0] >= 10 else 0,
        values[1] if values[1] >= 30 else 0,
        values[2] if values[2] >= 30 else 0,
    )


@dataclass
class Receiver:
    collecting: bool = False
    buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> tuple[str, ...]:
        if not data:
            return ()
        texts = []
        if not self.collecting:
            if b"$" in data:
                self.collecting = True
                self.buffer.clear()
                self.buffer.extend(data[data.index(b"$") + 1 :])
        else:
            if b"\r" in data:
                self.buffer.extend(data[: max(0, data.index(b"\r") - 1)])
                texts.append(
                    re.sub(r"[^0-9 ]", "", self.buffer.decode("ascii", errors="ignore")).strip()
                )
                self.buffer.clear()
            elif b"$" not in data:
                self.buffer.extend(data)
            if b"$" in data:
                self.buffer.extend(data[data.index(b"$") + 1 :])
        # The Android buffer is unbounded. Reject oversized/incomplete messages in HA.
        if len(self.buffer) > 8192:
            self.buffer.clear()
            self.collecting = False
        return tuple(texts)


def token_fields(text: str) -> dict[str, object]:
    tokens = text.split(" ")
    result: dict[str, object] = {}
    count = len(tokens)
    if count == 75:
        result["rgb_timer"] = [tokens[i] for i in (28, 29, 30, 54)]
        result["alarm"] = [tokens[i] for i in (11, 12, 14)]
    elif count in (39, 44, 71):
        result["rgb_timer"] = [tokens[i] for i in (18, 19, 20, 30)]
    if count == 39:
        result["bind"] = {
            "available": tokens[27] in ("00065", "00066"),
            "active": tokens[27] == "00065",
        }
        if tokens[24].isascii() and tokens[24].isdecimal() and len(tokens[24]) <= 10:
            result["sync_type"] = int(tokens[24])
            result["event"] = "OK"
    return result
