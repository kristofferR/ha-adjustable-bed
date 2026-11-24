"""Receive-only fields whose physical meanings trueMotion does not establish."""

from dataclasses import dataclass, field
from typing import Final

MAX_BUFFER: Final = 8192


@dataclass(slots=True)
class Observations:
    """Address-local state that survives unsolicited link loss."""

    version: str | None = None
    gd: str | None = None
    ga: dict[str, set[str]] = field(default_factory=dict)

    def observe_chunk(self, chunk: str) -> None:
        if not chunk.startswith(("+OK:GA=", "+OK:GD=")):
            return
        # Dart slices in UTF-16 units, even when the chunk lacks a CRLF.
        encoded = chunk.encode("utf-16-le")
        if len(encoded) < 18:
            return
        value = encoded[14:-4]
        if chunk.startswith("+OK:GD="):
            self.gd = value.decode("utf-16-le", errors="surrogatepass")
        elif len(value) == 20 and value[-4:] != b"0\x002\x00" and len(self.ga) < MAX_BUFFER:
            key = value[4:].decode("utf-16-le", errors="surrogatepass")
            member = value[2:4].decode("utf-16-le", errors="surrogatepass")
            members = self.ga.setdefault(key, set())
            if len(members) < 256:
                members.add(member)


class Receiver:
    def __init__(self, observations: Observations) -> None:
        self.observations = observations
        self.pending = ""

    def feed(self, data: bytes) -> str | None:
        """Version uses the completed buffer. GA/GD use the individual chunk."""
        try:
            chunk = data.decode("utf-8")
        except UnicodeDecodeError:
            self.pending = ""
            return None
        self.observations.observe_chunk(chunk)
        self.pending += chunk
        if len(self.pending) > MAX_BUFFER:
            self.pending = ""
        if not self.pending.endswith("\r\n"):
            return None
        message, self.pending = self.pending, ""
        if message.startswith("+OK:Version="):
            self.observations.version = message[12:-2]
            return self.observations.version
        return None
