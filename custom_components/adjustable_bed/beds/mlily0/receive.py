"""The accepted MLILY 3.1.1 receive subset, without a stream-parity claim."""

from collections.abc import Callable

from ...codec import richmat as codec
from ..goodvibe.receive import extended
from ..mlily_remote.receive import Receiver as ProductReceiver

ACKS = {
    bytes.fromhex("6e09010078"): "clock_available",
    bytes.fromhex("6e0e00037f"): "light_available",
    bytes.fromhex("6e1a000189"): "aroma_available",
    bytes.fromhex("6e07010177"): "alarm_added",
    bytes.fromhex("6e07010278"): "alarm_cancelled",
    bytes.fromhex("6e90c101c0"): "diagnostic_available",
    bytes.fromhex("6e2100008f"): "anti_snore_available",
}


class Receiver(ProductReceiver):
    """Decode complete known records; retain everything else only in raw diagnostics.

    Common length-7/16 and fragmented/coalesced stream parity remain unresolved
    static work. A shared library parser is not proof of those app behaviors.
    """

    def __init__(self, emit: Callable[[str, object], None]) -> None:
        self.emit = emit
        self.rejection: str | None = None

    def clear(self) -> None:
        self.rejection = None

    def feed(self, data: bytes) -> None:
        self.rejection = None
        if event := ACKS.get(data):
            self.emit(event, True)
            return
        if len(data) < 7 or data[:2] != b"\x6e\x20" or data[2] != len(data):
            return
        if not codec.is_valid(data):
            self.rejection = "Invalid notification checksum"
            return
        domain, sub, op = data[3:6]
        if op not in (2, 3):
            return
        if domain == 1 and sub == 2 and len(data) > 9:
            self.emit("motor", {
                "height": (data[7] * 256 + data[8]) / 10,
                "type": data[9],
                "angle": data[10] if len(data) > 11 else -1,
                "monitorHeight": (data[12] * 256 + data[11]) / 10 if len(data) > 13 else 0,
            })
        elif domain == 3 and sub == 1 and len(data) > 7:
            self.emit("white_led", data[7] == 1)
        elif domain in (2, 4) and not (domain == 2 and sub == 5):
            # These corroborated fields are diagnostics, not product capabilities.
            try:
                for name, value in extended(list(data)):
                    self.emit(name, value)
            except (ValueError, IndexError):
                self.rejection = "Truncated notification"
