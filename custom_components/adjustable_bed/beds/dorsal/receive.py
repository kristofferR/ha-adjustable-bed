"""Dorsal notifications. Only extended records have a length and checksum gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ...codec import richmat as codec

type Value = bool | int | float | str | tuple[Value, ...]
type Status = dict[str, Value]

_EXACT: Final = {
    bytes.fromhex(wire): (key, value)
    for wire, key, value in (
        ("6e09010078", "clock_available", True),
        ("6e0e00037f", "light_available", True),
        ("6e1a000189", "aromatherapy_available", True),
        ("6e07010177", "alarm_saved", True),
        ("6e07010278", "alarm_cancelled", True),
        ("6e90c101c0", "detection_available", True),
        ("6e23018416", "locked", True),
        ("6e23008415", "locked", False),
    )
}
_BLANKET_LENGTHS: Final = {1: 8, 2: 10, 5: 10, 6: 8, 7: 21, 8: 8, 9: 12}
_SCALAR: Final = {
    (2, 2): "massage_mode",
    (2, 4): "massage_frequency",
    (2, 5): "massage_vibration",
    (0x0B, 1): "press_mode",
    (0x0B, 4): "same_split_control",
    (0x0E, 1): "fan_level",
    (0x10, 1): "atomizer_status",
}
_BOOLEAN: Final = {
    (2, 6): "massage_on",
    (3, 1): "bed_light",
    (4, 3): "light_motion",
    (4, 4): "rgb_light",
    (6, 1): "anti_snore",
    (6, 2): "get_off_bed",
    (7, 2): "locked",
}


@dataclass(slots=True)
class Stream:
    """Retain a partial explicit record. Unsupported desk/OTA traffic is discarded."""

    pending: bytes = field(default=b"", init=False)

    def feed(self, chunk: bytes) -> list[bytes]:
        data = self.pending + chunk
        self.pending = b""
        frames: list[bytes] = []
        while (start := data.find(b"\x6e")) >= 0:
            data = data[start:]
            if len(data) < 3 or data[1] == 0x40 and len(data) < 4:
                self.pending = data
                break
            if data[1] in (0x20, 0x21, 0x40):
                length = int.from_bytes(data[2:4], "big") if data[1] == 0x40 else data[2]
                if length < (5 if data[1] == 0x40 else 7):
                    data = data[1:]
                    continue
                if len(data) < length:
                    self.pending = data
                    break
                if data[1] == 0x20:
                    frames.append(data[:length])
            else:
                length = data.find(b"\x6e", 1)
                if length < 0:
                    length = len(data)
                frames.append(data[:length])
            data = data[length:]
        return frames


@dataclass(frozen=True, slots=True)
class Alarm:
    slot: int
    kind: int
    hour: int
    minute: int
    selector: int
    repeat: int
    tail: bytes = b""

    def encode(self) -> bytes:
        return codec.record_20_len(
            5,
            1,
            1,
            (
                self.slot,
                self.kind,
                self.hour,
                self.minute,
                0 if self.kind == 1 else self.selector,
                self.repeat,
                *(self.tail if self.kind == 1 or self.kind == 0 and self.selector == 0xFF else b""),
            ),
        )


def _common(frame: bytes) -> Status:
    if match := _EXACT.get(frame):
        key, value = match
        return {key: value}
    if len(frame) != 5 or frame[1] != 0x90:
        return {}
    tag, value = frame[2:4]
    match tag >> 4:
        case 0 if tag == 0:
            return {"protocol_version": value}
        case 1:
            return {"bed_mode": value}
        case 3:
            return {"motor_status": ((tag >> 2 & 3, tag & 3, value),)}
        case 10:
            packed = (tag & 15) << 8 | value
            return dict(
                zip(
                    ("massage_mode", "massage_1", "massage_2", "massage_3"),
                    ((packed >> shift) & 7 for shift in (9, 6, 3, 0)),
                    strict=True,
                )
            )
        case 11:
            return {"massage_vibration_on": bool(value & 64)}
        case 12 if tag == 0xC2:
            return {
                "detection_status": {2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start")
            }
        case 12 if 0xC3 <= tag <= 0xC6:
            return {"detection_event": tag & 15}
        case 13 if tag == 0xD2:
            return {"massage_vibration_level": value}
    return {}


def _motor(operation: int, payload: bytes) -> Status:
    if not payload or operation not in (2, 3):
        return {}
    if operation == 2 and payload[0] == 0:
        if len(payload) < 4:
            return {}
        return {
            "motor_height": int.from_bytes(payload[1:3], "big") / 10,
            "motor_height_type": payload[3],
            "height_angle": payload[4] if len(payload) >= 5 else -1,
            "monitor_height": int.from_bytes(payload[5:7], "big") / 10
            if len(payload) >= 7
            else 0.0,
        }
    if len(payload) % 3:
        return {}
    key = "motor_travel" if operation == 2 else "motor_angle"
    return {
        key: tuple(
            (payload[i], int.from_bytes(payload[i + 1 : i + 3], "big"))
            for i in range(0, len(payload), 3)
        )
    }


def _extended(frame: bytes) -> Status | Alarm:
    if len(frame) < 7 or frame[2] != len(frame) or not codec.is_valid(frame):
        return {}
    group, operation, role = frame[3:6]
    if group == 0x0A and 1 <= operation <= 6:
        return {"check_report": frame.hex(), "check_type": operation}
    if role not in (2, 3):
        return {}
    data = frame[6:-1]
    if group == 1:
        return _motor(operation, data)
    if (group, operation) == (5, 1) and len(data) >= 6:
        slot, kind, hour, minute, selector, repeat = data[:6]
        if 1 <= slot <= 7:
            tail = data[6:] if kind == 1 or kind == 0 and selector == 0xFF else b""
            return Alarm(slot, kind, hour, minute, selector, repeat, tail)
        return {}
    if group == 0x0D and len(frame) >= _BLANKET_LENGTHS.get(operation, 256):
        return {"blanket_event": operation}  # The published object has no values.
    if (group, operation) == (2, 1):
        return {
            "head_massage_level" if zone == 1 else "foot_massage_level": value
            for zone, value in zip(data[::2], data[1::2], strict=False)
            if zone in (1, 2)
        }
    if (group, operation) == (0x0F, 1) and len(data) >= 2:
        return {
            "sleep_aid_on": tuple(
                (zone, value == 1) for zone, value in zip(data[::2], data[1::2], strict=False)
            )
        }
    if (group, operation) == (0x0F, 2) and data and len(data) % 4 == 0:
        return {
            "sleep_aid_timers": tuple(
                (data[i], int.from_bytes(data[i + 1 : i + 3], "big"))
                for i in range(0, len(data), 4)
            )
        }
    if (group, operation) == (0x11, 5) and data:
        return {"heating_pad_mode": data[0]}
    if len(data) < 2:
        return {}
    value = data[1]
    if name := _SCALAR.get((group, operation)):
        return {name: value}
    if name := _BOOLEAN.get((group, operation)):
        return {name: value == 1}
    match group, operation:
        case 4, 1 if len(data) >= 4:
            return {"rgb": tuple(component / 255 for component in data[1:4])}
        case 4, 2 if len(data) >= 3:
            return {"rgb_timer": value * 60 + data[2]}
        case 6, 3:
            return {"sleep_name": data[1:].hex()}
        case 6, 5 if len(data) >= 3 and value in (1, 2):
            return {"anti_snore_count" if value == 1 else "anti_snore_time": data[2]}
        case 0x0B, 2:
            return {"standard_split_control": value == 2}
        case 0x10, 2 if len(data) >= 3:
            return {"atomizer_time": data[2]}
        case 0x11, 2 if len(data) >= 3:
            timer = int.from_bytes(data[1:3], "big")
            return {
                "heating_timer": (
                    data[0],
                    0 if not timer else 1 if timer == 0xFFFF else 2,
                    0 if timer == 0xFFFF else timer,
                )
            }
        case 0x11, 3 if len(data) >= 3:
            return {"heating_temperature": (data[0], data[2])}
    return {}


def decode(frame: bytes) -> Status | Alarm:
    if len(frame) < 2 or frame[0] != 0x6E:
        return {}
    return _extended(frame) if frame[1] == 0x20 else _common(frame)
