"""Source-ordered streaming parser and callback state for cluster-018.

Malformed input raises a bounded exception instead of crashing the HA BLE
callback. The retained buffer and successful callback effects follow the app.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .codec import richmat as codec
from .richmat_classic_protocol import float32, new_height, old_height, rounded

PREFIXES = (
    "6e90", "6e08", "6e94", "6e92", "6e97", "6e070101", "6e070102",
    "6e090100", "6e0e0001", "6e0e0003", "6e1a0001", "6e1a0002", "6e1a0003",
)


class MalformedFrame(ValueError):
    """An app substring/getPack boundary that cannot produce a callback."""


@dataclass(slots=True)
class ReceiveState:
    buffer: str = ""
    old_pack: str = ""
    height_cm: float | None = None
    height_inches: float | None = None
    unit: int | None = None
    unit_event: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    modern_controls: bool = True
    error: str | None = None
    error_confirmation_pending: bool = False
    last_value: str | None = None
    value_event: str | None = None
    alarm_capable: bool = False
    light_capable: bool = False
    aroma_capable: bool = False
    alarm_enabled: bool | None = None
    # SettingsActivity reveals at most one previously hidden row per callback.
    menu: set[str] = field(default_factory=set)
    events: list[dict[str, object]] = field(default_factory=list)

    def _clear(self) -> None:
        self.buffer = "6e" if self.buffer.endswith("6e") else ""

    def _pack(self, length: int) -> str:
        original = self.buffer.lower().strip()
        remainder = original
        for prefix in PREFIXES:
            offset = 0
            while offset <= len(original):
                found = remainder.find(prefix)
                if found == -1 or found + length > len(remainder):
                    break
                candidate = remainder[found:found + length]
                raw = bytes.fromhex(candidate)
                if codec.is_valid(raw):
                    return candidate
                offset += found + 4
                if offset > len(original):
                    raise MalformedFrame("getPack substring exceeds the retained buffer")
                remainder = original[offset:]
        return ""

    def _value(self, packet: str, app: str, layout: str) -> None:
        self.last_value = packet
        self.value_event = packet
        self.events.append({"value": packet})
        if packet == "6e09010078":
            self.alarm_capable = True
        if packet in ("6e0e00017d", "6e0e00037f"):
            self.light_capable = True
        if packet == "6e1a000189":
            self.aroma_capable = True
        if packet == "6e07010177":
            self.alarm_enabled = True
        if packet == "6e07010278":
            self.alarm_enabled = False
        if self.alarm_capable and "alarm" not in self.menu:
            if app == "avocadoecobase" and layout == "URRM":
                return
            self.menu.add("alarm")
        elif self.light_capable and "light" not in self.menu:
            self.menu.add("light")
        elif self.aroma_capable and "aroma" not in self.menu:
            self.menu.add("aroma")

    def feed(self, data: bytes, *, app: str, layout: str, desk_bound: bool = True, table_controls_bound: bool = True) -> None:
        self.unit_event = None
        self.value_event = None
        self.events = []
        text = data.hex()
        if text.startswith("6e") and len(self.buffer) > 100:
            self.buffer = ""
        self.buffer += text
        if len(self.buffer) < 10:
            return
        if len(self.buffer) < 32:
            packet = self._pack(14)
            if packet:
                if packet.startswith("6e90") and desk_bound:
                    raw = bytes.fromhex(packet)
                    self.height_cm, self.height_inches = new_height(raw[3], raw[4], raw[5])
                    self.events.append({"height": {"cm": self.height_cm, "inch": self.height_inches}})
                self._clear()
                return
            packet = self._pack(10)
            if not packet:
                # Actual short-buffer branch calls substring before testing empty.
                raise MalformedFrame("No valid five-byte packet in short notification buffer")
            if packet.startswith("6e08"):
                if self.old_pack == packet:
                    self._clear()
                    return
                if not self.old_pack and table_controls_bound:
                    self.modern_controls = False
                    self.events.append({"visible": False})
                self.old_pack = packet
                if desk_bound:
                    raw = bytes.fromhex(packet)
                    self.height_cm, self.height_inches = old_height(raw[2], raw[3])
                    self.events.append({"height": {"cm": self.height_cm, "inch": self.height_inches}})
            else:
                self._value(packet, app, layout)
            self._clear()
            return
        packet = self._pack(32)
        if packet:
            raw = bytes.fromhex(packet)
            values = [rounded(float32((raw[i] * 100 + raw[i + 1]) / 10.0)) for i in (7, 9, 11, 13)]
            if raw[1] in (0x94, 0x92) and desk_bound:
                self.unit = raw[2]
                self.unit_event = raw[2]
                self.minimum, self.maximum = values[:2]
                self.height_cm, self.height_inches = values[3], values[2]
                self.events.append({"unit": self.unit, "minimum": self.minimum, "maximum": self.maximum, "initial": self.height_cm, "initial_other": self.height_inches, "reveal_modern_controls": raw[1] == 0x94})
                if raw[1] == 0x94 and table_controls_bound:
                    self.modern_controls = True
                    self.events.append({"visible": True})
            elif raw[1] == 0x97 and desk_bound:
                # The source reads the whole retained buffer, not the matched frame.
                self.error = self.buffer[6:8]
                self.error_confirmation_pending = True
            self._clear()
        packet = self._pack(10)
        if packet:
            self._value(packet, app, layout)
            self._clear()
