"""AW MOTION's common and length-framed notifications, without axis guesses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ...codec import richmat as codec
from .receive import Receive

SIGNALS: Final = {
    "6e09010078": "clock",
    "6e0e00037f": "light",
    "6e1a000189": "aroma (no current control caller)",
    "6e07010177": "alarm_added",
    "6e07010278": "alarm_cancelled",
    "6e90c101c0": "diagnostics",
    "6e2100008f": "anti_snore_intervention",
}


def common(data: bytes) -> dict[str, object] | None:
    if len(data) != 5:
        return None
    if event := SIGNALS.get(data.hex()):
        return {"event": event}
    if data[:2] != b"\x6e\x90":
        return None
    selector, value = data[2:4]
    if selector == 0:
        return {"event": "version", "value": value}
    match selector >> 4:
        case 1:
            return {"event": "bed_mode", "value": selector & 15}
        case 3:
            return {
                "event": "motor",
                "no": (selector >> 2) & 3,
                "status": selector & 3,
                "angle": value,
            }
        case 10:
            packed = ((selector & 15) << 8) | value
            return {
                "event": "massage",
                "mode": (packed >> 9) & 7,
                "massage1": (packed >> 6) & 7,
                "massage2": (packed >> 3) & 7,
                "massage3": packed & 7,
            }
    if selector == 0xC2:
        return {"event": "detection_status", "value": {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start")}
    if selector in (0xC3, 0xC4, 0xC5, 0xC6):
        # This delivery's optimized diagnostic object retains no fields.
        return {"event": "detection_message", "details": {}}
    return None


def extra(data: bytes) -> dict[str, object] | None:
    if (
        len(data) < 7
        or data[:2] != b"\x6e\x20"
        or data[2] != len(data)
        or not codec.is_valid(data)
        or data[5] not in (2, 3)
    ):
        return None
    domain, subtype = data[3:5]
    size = len(data)
    if domain == 1 and subtype == 2 and size >= 10:
        return {
            "height": int.from_bytes(data[7:9], "big") / 10,
            "type": data[9],
            "angle": data[10] if size > 11 else -1,
        }
    if domain == 2:
        if subtype == 1:
            return {
                "event": "massage_intensities",
                "zones": [
                    [data[i], data[i + 1]] for i in range(6, size - 2, 2) if data[i] in (1, 2)
                ],
            }
        if size > 7 and subtype in (2, 4, 6):
            return {
                "event": {2: "massage_mode", 4: "massage_frequency", 6: "massage_switch"}[subtype],
                "value": data[7] == 1 if subtype == 6 else data[7],
            }
    if domain == 3 and subtype == 1 and size > 7:
        return {"event": "white_light", "value": data[7] == 1}
    if domain == 4:
        if subtype == 1 and size > 9:
            return {"event": "color", "rgb": list(data[7:10])}
        if subtype == 2 and size > 8:
            return {"event": "light_timer", "seconds": int.from_bytes(data[7:9], "big") * 60}
    if domain == 6:
        if subtype in (1, 2) and size > 7:
            return {
                "event": {1: "snore_detection", 2: "off_bed_detection"}[subtype],
                "value": data[7] == 1,
            }
        if subtype == 3:
            return {"event": "sleep_band_adv_name", "raw": list(data[7:-1])}
    if domain == 10 and subtype in range(1, 6):
        return {"event": "diagnostics", "subtype": subtype, "raw": data.hex()}
    if domain == 11 and size > 7:
        if subtype == 1:
            return {"event": "press_mode", "value": data[7]}
        if subtype == 2:
            return {"event": "same_control", "value": data[7] == 2}
    return None


@dataclass(slots=True)
class AwMotionReceive(Receive):
    _extended_types = (0x20,)
    values: dict[str, object] = field(default_factory=dict)
    last_event: str | None = None

    def feed(self, data: bytes) -> None:
        self.pending.extend(data)
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                return
            del self.pending[:start]
            if len(self.pending) < 3:
                return
            if self.pending[1] == 0x20:
                size = self.pending[2]
                if size < 7:
                    # Bound malformed input, including the app's zero-length loop.
                    self.pending.clear()
                    return
                if len(self.pending) < size:
                    return
                frame = bytes(self.pending[:size])
                del self.pending[:size]
                self._record(frame)
            else:
                end = self.pending.find(0x6E, 1)
                end = len(self.pending) if end < 0 else end
                frame = bytes(self.pending[:end])
                del self.pending[:end]
                self._common(frame)

    def _accept(self, event: dict[str, object] | None) -> None:
        if event is None:
            return
        name = str(event.get("event", "motor_extended"))
        self.last_event = name
        # Motor identifiers remain raw app fields, never cover positions.
        key = f"motor_{event['no']}" if name == "motor" else name
        self.values[key] = event
        if name in ("clock", "light"):
            self.capabilities.add(name)
        elif name in ("alarm_added", "alarm_cancelled"):
            self.last_ack = name

    def _common(self, frame: bytes) -> None:
        self._accept(common(frame))

    def _record(self, frame: bytes) -> None:
        self._accept(extra(frame))
