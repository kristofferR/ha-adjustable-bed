"""Accepted Majestic Home E14 receive semantics, including common-frame quirks.

Bounds reject only malformed/nonprogress input that would hang or index outside
the app buffer. Common frames deliberately have no checksum gate or assembly.
"""

from dataclasses import dataclass, field, replace

from ...codec import richmat as codec

LIST_ALARMS = codec.record(5, 1, 0, (0,))
LITERALS = {
    "6e09010078": "clock_available",
    "6e0e00037f": "light_available",
    "6e07010177": "alarm_saved",
    "6e07010278": "alarm_cancelled",
    "6e90c101c0": "detection_available",
    "6e2100008f": "snore_available",
    "6e23018416": "locked",
    "6e23008415": "unlocked",
}


@dataclass(frozen=True, slots=True)
class Alarm:
    number: int
    reserved: int
    hour: int
    minute: int
    preset: int
    repeat: int

    def packet(self) -> bytes:
        return codec.record(
            5, 1, 1, (self.number, self.reserved, self.hour, self.minute, self.preset, self.repeat)
        )

    def toggle(self, enabled: bool) -> Alarm:
        return replace(self, repeat=self.repeat & 254 | int(enabled))


def decode(b: bytes) -> dict[str, object]:
    if event := LITERALS.get(b.hex()):
        return {event: True}
    n = len(b)
    if n == 5 and b[:2] == b"\x6e\x90":
        high, low, value = b[2] >> 4, b[2] & 15, b[3]
        if high == 0 and low == 0:
            return {"version": value}
        if high == 1:
            return {"bed_mode": low}
        if high == 3:
            return {"motor_no": low >> 2, "status": low & 3, "angle": value}
        if high == 10:
            packed = low << 8 | value
            return {
                key: packed >> shift & 7
                for key, shift in zip(
                    ("mode", "massage1", "massage2", "massage3"), (9, 6, 3, 0), strict=True
                )
            }
        if high == 12:
            if low == 2:
                return {
                    "detection_check_status": {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(
                        value >> 4, "start"
                    )
                }
            if low in (3, 4, 5):
                return {
                    "diagnostic_component": {3: "motor", 4: "massage", 5: "under_bed_light"}[low],
                    "no": value >> 4,
                    "status": {0: "abnormal", 1: "normal", 2: "controlBoxMalfunction"}.get(
                        value & 15, "notPluggedIn"
                    ),
                    "app_event_payload": "empty RMDeviceDetectionDataDetails",
                }
        return {}  # Audio/accessory common branches are excluded.
    if n < 7 or b[:2] != b"\x6e\x20" or b[2] != n or not codec.is_valid(b):
        return {}
    domain, operation, direction = b[3:6]
    if domain == 10 and operation in (1, 2, 3, 4, 5):
        return {"check_type": operation, "data": list(b)}
    if direction not in (2, 3):
        return {}
    if domain == 1 and operation == 2 and n > 9:
        return {
            "height": ((b[7] << 8) | b[8]) / 10,
            "type": b[9],
            "angle": b[10] if n > 11 else -1,
            "monitorHeight": ((b[11] << 8) | b[12]) / 10 if n > 13 else 0,
        }
    if domain == 2:
        if operation == 1 and (n - 7) % 2 == 0:
            return {
                {1: "head_intensity", 2: "foot_intensity"}[b[i]]: b[i + 1]
                for i in range(6, n - 1, 2)
                if b[i] in (1, 2)
            }
        if n > 7 and operation in (2, 4, 5, 6):
            return {
                {
                    2: "massage_mode",
                    4: "massage_frequency",
                    5: "massage_sync_strength",
                    6: "massage_switch",
                }[operation]: b[7] == 1 if operation == 6 else b[7]
            }
    if domain == 3 and operation == 1 and n > 7:
        return {"white_light": b[7] == 1}
    if domain == 4:
        if operation == 1 and n > 9:
            return {"rgb": list(b[7:10])}
        if operation == 2 and n > 8:
            return {"rgb_timer_seconds": b[7] * 60 + b[8]}
        if operation in (3, 4) and n > 7:
            return {"rgb_sensing" if operation == 3 else "rgb_switch": b[7] == 1}
    if domain == 5 and operation == 1 and n >= 12:
        return {
            **dict(
                zip(
                    ("alarm_number", "reserved", "hour", "minute", "preset", "repeat"),
                    b[6:12],
                    strict=True,
                )
            ),
            "event": "list" if direction == 2 else "report",
        }
    if domain == 6:
        if operation in (1, 2) and n > 7:
            return {"snore_detection" if operation == 1 else "out_of_bed": b[7] == 1}
        if operation == 4 and n > 8 and b[7] == b[8] == 1:
            return {"stop_music_bed_effect": True}
        if operation == 5 and n > 8 and b[7] in (1, 2):
            return {"snore_count" if b[7] == 1 else "snore_time": b[8]}
    if domain == 7 and operation == 2 and n > 7:
        return {"box_locked": b[7] == 1}
    if domain == 11 and n > 7:
        if operation == 1:
            return {"press_mode": b[7]}
        if operation == 2:
            return {"coupled": b[7] == 2}
        if operation == 4:
            return {"sync_movement": b[7]}
    return {}  # OTA, network, desk, accessories and audio have no BED consumer.


@dataclass(slots=True)
class Receiver:
    pending: bytearray = field(default_factory=bytearray)

    def feed(self, chunk: bytes) -> list[bytes]:
        self.pending.extend(chunk)
        frames = []
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            kind = self.pending[1]
            if kind == 0x20:
                size = self.pending[2]
                if size == 0:
                    self.pending.clear()
                    break  # HA guard: app would fail to make progress.
            elif kind == 0x40:
                if len(self.pending) < 4:
                    break  # HA guard: app can index an absent fourth byte.
                size = int.from_bytes(self.pending[2:4], "big")
                if size < 4:
                    self.pending.clear()
                    break
            else:
                try:
                    size = self.pending.index(0x6E, 1)
                except ValueError:
                    size = len(self.pending)
            if len(self.pending) < size:
                break
            b = bytes(self.pending[:size])
            del self.pending[:size]
            if kind == 0x40:
                continue  # Excluded OTA framing is consumed, never acted on.
            if kind != 0x20 or codec.is_valid(b):
                frames.append(b)
        return frames
