"""SonicSleep caller domains and receive contracts over the Richmat codec.

Outbound records are 6E length 20, received records are 6E 20 length.
The app's common stream framing consumes a three-byte fragment; extended
records wait for length. HA bounds malformed frames before indexing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...codec import richmat as codec
from ...profiles.sonicsleep import PRESETS

LIST_ALARMS = codec.record(5, 1, 0, (0,))
LINK_NAME = codec.record(6, 3, 0, (0,))


@dataclass(frozen=True, slots=True)
class Alarm:
    id: int
    opaque: int
    hour: int
    minute: int
    mode: int
    repeat: int

    def packet(self) -> bytes:
        return codec.record(5, 1, 1, (self.id, self.opaque, self.hour, self.minute, self.mode, self.repeat))

    def toggle(self, enabled: bool) -> Alarm:
        return replace(self, repeat=self.repeat & 254 | int(enabled))


def form_alarm(number: int, hour: int, minute: int, mode: str, days: tuple[int, ...], enabled: bool) -> Alarm:
    """New/edit form only. Received cached toggles do not pass through this guard."""
    if not 0 <= number <= 255 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Invalid alarm form time or ID")
    if mode not in PRESETS or any(day not in range(7) for day in days):
        raise ValueError("Choose a SonicSleep preset and weekdays Monday through Sunday")
    return Alarm(number, 0, hour, minute, PRESETS[mode][0], sum(1 << (7 - day) for day in set(days)) | int(enabled))


def delete_alarm(number: int) -> bytes:
    if not 0 <= number <= 255:
        raise ValueError("Invalid received alarm ID")
    return codec.record(5, 2, 1, (number,))


def parse_alarm(packet: bytes) -> Alarm | None:
    if len(packet) >= 13 and packet[:2] == b"\x6e\x20" and packet[2] == len(packet) and codec.is_valid(packet) and packet[3:5] == b"\x05\x01" and packet[5] in (2, 3):
        return Alarm(*packet[6:12])
    return None


_LITERALS = {
    "6e09010078": "clock_capability", "6e0e00037f": "light_capability",
    "6e07010177": "alarm_add_success", "6e07010278": "alarm_cancel_success",
    "6e90c101c0": "diagnostic_capability", "6e2100008f": "snore_capability",
}


def decode(b: bytes) -> dict[str, object]:
    """Observed BED state only, without inferring setters, units or calibrated axes."""
    n = len(b)
    if n == 5:
        if event := _LITERALS.get(b.hex()):
            return {event: True}
        if b[:2] != b"\x6e\x90":
            return {}
        high, low, value = b[2] >> 4, b[2] & 15, b[3]
        if high == 0 and low == 0:
            return {"protocol_version": value}
        if high == 1:
            return {"bed_mode": low}
        if high == 3:
            return {"motor": {"no": b[2] >> 2 & 3, "status": b[2] & 3, "angle": value}}
        if high == 10:
            q = low << 8 | value
            return {"massage": {"mode": q >> 9 & 7, "zone1": q >> 6 & 7, "zone2": q >> 3 & 7, "zone3": q & 7}}
        if high == 11:
            return {"follow_shake": bool(value & 64)}
        if high == 12 and low == 2:
            return {"detection_check": {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start")}
        if high == 12 and low in (3, 4, 5):
            return {"detection": {"domain": {3: "motor", 4: "massage", 5: "underbedlight"}[low], "index": value >> 4, "status": {0: "abnormal", 1: "normal", 2: "controlBoxMalfunction", 3: "notPluggedIn"}.get(value & 15, "notPluggedIn")}}
        if high == 13 and low == 2:
            return {"follow_shake_gear": value}
        return {}
    if n < 7 or b[:2] != b"\x6e\x20" or b[2] != n or not codec.is_valid(b):
        return {}
    group, function, op = b[3:6]
    if group == 10:
        # Source function 6 is audio; function 5 is the BED C65 diagnostic.
        return {"diagnostic": {"function": function, "frame": b.hex()}} if function in (1, 2, 3, 4, 5) else {}
    if op not in (2, 3):
        return {}
    if group == 1 and function == 2 and n > 10:
        return {"motor_travel": {"height": ((b[7] << 8) | b[8]) / 10, "type": b[9], "angle": b[10] if n > 11 else -1}}
    if group == 2:
        if function == 1 and (n - 7) % 2 == 0:
            strengths = {{1: "head", 2: "foot"}[b[i]]: b[i + 1] for i in range(6, n - 1, 2) if b[i] in (1, 2)}
            return {"massage_strength": strengths} if strengths else {}
        if n > 8 and function in (2, 4, 5, 6):
            key = {2: "massage_mode", 4: "massage_frequency", 5: "follow_shake_gear", 6: "massage_power"}[function]
            return {key: b[7] == 1 if function == 6 else b[7]}
    if group == 3 and function == 1 and n > 8:
        return {"white_led": b[7] == 1}
    if group == 4:
        if function == 1 and n > 10:
            return {"rgb": [v / 255 for v in b[7:10]]}
        if function == 2 and n > 9:
            return {"rgb_timer": b[7] * 60 + b[8]}
        if function in (3, 4) and n > 8:
            return {"rgb_motion" if function == 3 else "rgb_power": b[7] == 1}
    if alarm := parse_alarm(b):
        return {"alarm": {"event": "list" if op == 2 else "escalation", "id": alarm.id, "reserved": alarm.opaque, "hour": alarm.hour, "minute": alarm.minute, "mode": alarm.mode, "repeat": alarm.repeat}}
    if group == 6 and n > 8:
        if function in (1, 2):
            return {"anti_snore_enabled" if function == 1 else "off_bed": b[7] == 1}
        if function == 3:
            return {"link_name": "".join(chr(v) for v in b[7:-1])}
    if group == 11 and n > 8:
        if function == 1:
            return {"press_mode": b[7]}
        if function == 2:
            return {"standard_split": b[7] == 2}
        if function == 4:
            return {"same_split": b[7]}
    return {}


@dataclass
class Receiver:
    pending: bytearray = field(default_factory=bytearray)

    def feed(self, chunk: bytes) -> list[bytes]:
        self.pending.extend(chunk)
        if len(self.pending) > 4096:
            self.pending.clear()
            return []
        frames: list[bytes] = []
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            extended = self.pending[1] == 0x20
            if extended:
                size = self.pending[2]
                if size < 7:
                    del self.pending[0]
                    continue
            else:
                try:
                    size = self.pending.index(0x6E, 1)
                except ValueError:
                    size = len(self.pending)
            if len(self.pending) < size:
                break
            b = bytes(self.pending[:size])
            del self.pending[:size]
            if not extended or codec.is_valid(b):
                frames.append(b)
        return frames
