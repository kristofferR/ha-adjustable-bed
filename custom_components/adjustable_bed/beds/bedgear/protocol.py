"""Letter-family projections and bounded, source-shaped stream framing."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field


def color_parameters(rgb: tuple[int, int, int], brightness: float = 1) -> tuple[int, int, int]:
    values = tuple(int((int(channel * brightness) & 255) / 255 * 120) for channel in rgb)
    return (
        values[0] if values[0] >= 10 else 0,
        values[1] if values[1] >= 30 else 0,
        values[2] if values[2] >= 30 else 0,
    )


def reported_color(red: int, green: int, blue: int) -> tuple[int, int, int]:
    return (
        min(255, int(red * 2.125)),
        min(255, int(green * 2.125)),
        min(255, int(blue * 2.125)),
    )


@dataclass
class Receiver:
    collecting: bool = False
    buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> tuple[str, ...]:
        if not data:
            return ()
        texts = []

        def append(fragment: bytes) -> bool:
            if len(self.buffer) + len(fragment) > 8192:
                self.buffer.clear()
                self.collecting = False
                return False
            self.buffer.extend(fragment)
            return True

        if not self.collecting:
            if b"$" in data:
                self.collecting = True
                self.buffer.clear()
                if not append(data[data.index(b"$") + 1 :]):
                    return ()
        else:
            if b"\r" in data:
                if not append(data[: max(0, data.index(b"\r") - 1)]):
                    return ()
                texts.append(
                    re.sub(r"[^0-9 ]", "", self.buffer.decode("ascii", errors="ignore")).strip()
                )
                self.buffer.clear()
            elif b"$" not in data:
                if not append(data):
                    return ()
            if b"$" in data:
                if not append(data[data.index(b"$") + 1 :]):
                    return tuple(texts)
        return tuple(texts)


class ErgoBedReceiver(Receiver):
    """Collect the app's fragmented status record, with a bounded buffer."""

    def feed(self, data: bytes) -> tuple[str, ...]:
        if not data:
            return ()
        texts = ()
        if self.collecting:
            end = data.find(b"\r")
            fragment = data if end == -1 else data[:end]
            if len(self.buffer) + len(fragment) > 8192:
                self.collecting = False
                self.buffer.clear()
            else:
                self.buffer.extend(fragment)
                if end != -1:
                    text = self.buffer.decode("latin-1").strip()
                    self.buffer.clear()
                    if len(text.split(" ")) == 75:
                        texts = (text,)

        # The app processes CR before it looks for a new dollar in this fragment.
        start = data.find(b"$")
        if start != -1:
            tail = data[start + 1 :]
            if len(self.buffer) + len(tail) <= 8192:
                self.collecting = True
                self.buffer.extend(tail)
            else:
                self.collecting = False
                self.buffer.clear()
        return texts


def token_fields(
    text: str,
    *,
    alarm_indices: tuple[int, int, int] = (11, 12, 14),
    parse_sync: Callable[[str], int | None] | None = None,
) -> dict[str, object]:
    tokens = text.split(" ")
    result: dict[str, object] = {}
    count = len(tokens)
    if count == 75:
        result["rgb_timer"] = [tokens[i] for i in (28, 29, 30, 54)]
        result["alarm"] = [tokens[i] for i in alarm_indices]
    elif count in (39, 44, 71):
        result["rgb_timer"] = [tokens[i] for i in (18, 19, 20, 30)]
    if count == 39:
        result["bind"] = {
            "available": tokens[27] in ("00065", "00066"),
            "active": tokens[27] == "00065",
        }
        raw = tokens[24]
        sync_type = (
            parse_sync(raw)
            if parse_sync is not None
            else int(raw)
            if raw.isascii() and raw.isdecimal() and len(raw) <= 10
            else None
        )
        if sync_type is not None:
            result["sync_type"] = sync_type
            result["event"] = "OK"
    return result
