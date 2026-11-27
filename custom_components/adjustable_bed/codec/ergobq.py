"""ErgoBQ 1.8.1 direct BED framing and DP payloads (not the mattress route)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Final

SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
IDENTITY_SERVICE: Final = "00005342-0000-1000-8000-00805f9b34fb"


def integer(value: int, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"Expected an integer in {low}..{high}")
    return value


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def frame(command: int, payload: bytes = b"") -> bytes:
    integer(command, 0, 255)
    if len(payload) > 512:
        raise ValueError("ErgoBQ payload exceeds 512 bytes")
    body = b"\x55\xaa\x00" + bytes([command]) + len(payload).to_bytes(2, "big") + payload
    return body + crc16(body).to_bytes(2, "big")


class Kind(IntEnum):
    RAW = 0
    BOOL = 1
    VALUE = 2
    STRING = 3
    ENUM = 4


@dataclass(frozen=True, slots=True)
class DP:
    id: int
    kind: Kind
    value: bytes

    def encode(self) -> bytes:
        integer(self.id, 0, 255)
        if len(self.value) > 65535:
            raise ValueError("DP value exceeds U16 length")
        return bytes([self.id, self.kind]) + len(self.value).to_bytes(2, "big") + self.value


def boolean(id: int, value: bool) -> DP:
    if not isinstance(value, bool):
        raise ValueError("Expected a boolean")
    return DP(id, Kind.BOOL, bytes([value]))


def number(id: int, value: int) -> DP:
    return DP(id, Kind.VALUE, integer(value, -(2**31), 2**31 - 1).to_bytes(4, "big", signed=True))


def enumeration(id: int, value: int) -> DP:
    return DP(id, Kind.ENUM, bytes([integer(value, 0, 255)]))


def raw(id: int, value: bytes) -> DP:
    return DP(id, Kind.RAW, value)


def publish(entries: Iterable[DP]) -> bytes:
    # Preserve supplied map order. The app's Java HashMap promises no order.
    payload = b"".join(entry.encode() for entry in entries)
    if not payload:
        raise ValueError("Empty DP map")
    return frame(4, payload)


def auth(stamp: str, *, phase: int = 1) -> bytes:
    integer(phase, 1, 3)
    return frame(3, bytes([1 if phase == 1 else 0, phase]) + stamp.strip().encode())


def clock(seconds: int, offset_seconds: int) -> bytes:
    return frame(
        12,
        integer(seconds, 0, 0xFFFFFFFF).to_bytes(4, "big")
        + bytes([int(offset_seconds >= 0), min(abs(offset_seconds) // 1800 * 2, 255)]),
    )


def force_sync(direction: int) -> tuple[DP, DP]:
    return enumeration(9, 2), enumeration(10, integer(direction, 0, 1))


@dataclass(frozen=True, slots=True)
class Massage:
    on: bool = False
    intensity: int = 0
    mode: int = 0
    minutes: int = 0

    def encode(self) -> bytes:
        boolean(0, self.on)
        return bytes(
            [
                self.on,
                integer(self.intensity, 0, 5),
                integer(self.mode, 0, 3),
                integer(self.minutes, 0, 60),
            ]
        )


@dataclass(frozen=True, slots=True)
class Light:
    on: bool = False
    brightness: int = 0
    red: int = 0
    green: int = 0
    blue: int = 0
    minutes: int = 0

    def encode(self) -> bytes:
        boolean(0, self.on)
        return bytes(
            [
                self.on,
                integer(self.brightness, 0, 100),
                integer(self.red, 0, 255),
                integer(self.green, 0, 255),
                integer(self.blue, 0, 255),
                integer(self.minutes, 0, 120),
            ]
        )


def schedule_header(task: int, status: int, repeat: int, hour: int, minute: int) -> bytes:
    integer(task, 1, 5)
    integer(status, 0, 2)
    integer(repeat, 0, 254)
    if repeat & 1:
        raise ValueError("Repeat bit 0 is reserved")
    return bytes([task, status, repeat, integer(hour, 0, 23), integer(minute, 0, 59)])


NO_MASSAGE: Final = Massage()
NO_LIGHT: Final = Light()


def custom_schedule(
    task: int,
    status: int,
    repeat: int,
    hour: int,
    minute: int,
    *,
    position: bool = False,
    scene: int = 0,
    massage: bool = False,
    sync: bool = False,
    head: Massage = NO_MASSAGE,
    legs: Massage = NO_MASSAGE,
    light: Light = NO_LIGHT,
) -> bytes:
    if sync and head != legs:
        raise ValueError("Synchronized massage parameters must match")
    for value in (position, massage, sync):
        boolean(0, value)
    return (
        schedule_header(task, status, repeat, hour, minute)
        + bytes([0, position, integer(scene, 0, 7), massage, sync])
        + head.encode()
        + legs.encode()
        + light.encode()
    )


def diy_length(data: bytes) -> int | None:
    """The proven fixed/TLV length recognizer, not the deferred DP41 parser."""
    if len(data) < 2:
        return None
    pos = 2
    for _ in range(data[1]):
        if pos + 4 > len(data):
            return None
        mask, count = data[pos + 2 : pos + 4]
        pos += 4
        if mask & 128:
            for _ in range(count):
                if pos + 3 > len(data):
                    return None
                pos += 3 + data[pos + 2]
                if pos > len(data):
                    return None
        else:
            pos += (8 if mask & 1 else 0) + (2 if mask & 2 else 0) + (8 if mask & 4 else 0)
        if pos > len(data):
            return None
    return pos


def diy_program(data: bytes) -> bytes:
    if diy_length(data) != len(data):
        raise ValueError("Incomplete or trailing DIY program")
    return data


@dataclass(frozen=True, slots=True)
class ProgramMotor:
    parts: int
    mode: int
    speed: int
    positions: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ProgramVibration:
    parts: int
    intensity: int
    mode: int


@dataclass(frozen=True, slots=True)
class ProgramLight:
    fade: int
    on: int
    start_brightness: int
    end_brightness: int
    rgb: tuple[int, int, int]
    seconds: int


@dataclass(frozen=True, slots=True)
class Segment:
    seconds: int
    motor: ProgramMotor | None
    vibration: ProgramVibration | None
    light: ProgramLight | None


def parse_diy(data: bytes) -> tuple[int, tuple[Segment, ...]] | None:
    """Fixed-mask DP60 model. Bit-7 TLVs only have a proven length recognizer."""
    if diy_length(data) != len(data):
        return None
    pos = 2
    segments = []
    for _ in range(data[1]):
        seconds = int.from_bytes(data[pos : pos + 2], "big")
        mask = data[pos + 2]
        pos += 4
        if mask & 128:
            return None
        fields: list[bytes | None] = []
        for bit, length in ((1, 8), (2, 2), (4, 8)):
            fields.append(data[pos : pos + length] if mask & bit else None)
            if mask & bit:
                pos += length
        motor, vibration, light = fields
        segments.append(
            Segment(
                seconds,
                ProgramMotor(motor[0], motor[1], motor[2], (motor[3], motor[4], motor[5]))
                if motor
                else None,
                ProgramVibration(vibration[0], vibration[1] >> 4, vibration[1] & 15)
                if vibration
                else None,
                ProgramLight(
                    light[0] >> 4,
                    light[0] & 15,
                    light[1],
                    light[2],
                    (light[3], light[4], light[5]),
                    int.from_bytes(light[6:8], "big"),
                )
                if light
                else None,
            )
        )
    return data[0], tuple(segments)


def diy_schedule(
    task: int,
    status: int,
    repeat: int,
    hour: int,
    minute: int,
    mode: int,
    program: bytes | None = None,
) -> bytes:
    payload = bytes([integer(mode, 11, 30)]) if program is None else diy_program(program)
    return schedule_header(task, status, repeat, hour, minute) + b"\x01" + payload


def run_diy(mode: int, program: bytes | None = None) -> tuple[DP, ...]:
    control = raw(61, bytes([integer(mode, 0, 255), 0, 0, 0]))
    return (control,) if program is None else (control, raw(60, diy_program(program)))


@dataclass(frozen=True, slots=True)
class Frame:
    command: int
    payload: bytes
    wire: bytes = field(default=b"", compare=False, repr=False)


def parse_frame(data: bytes) -> Frame | None:
    if len(data) < 8 or data[:3] != b"\x55\xaa\x00":
        return None
    size = int.from_bytes(data[4:6], "big")
    if size > 4096 or size + 8 != len(data) or crc16(data[:-2]) != int.from_bytes(data[-2:], "big"):
        return None
    return Frame(data[3], data[6:-2], data)


class Receiver:
    def __init__(self) -> None:
        self.pending = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        if not self.pending and not data.startswith(b"\x55\xaa"):
            return []
        self.pending.extend(data)
        result: list[Frame] = []
        while self.pending:
            start = self.pending.find(b"\x55\xaa")
            if start < 0:
                self.pending[:] = self.pending[-1:] if self.pending[-1] == 0x55 else b""
                break
            del self.pending[:start]
            if len(self.pending) < 6:
                break
            size = int.from_bytes(self.pending[4:6], "big")
            if size > 4096:
                del self.pending[0]
                continue
            length = size + 8
            if len(self.pending) < length:
                # Prefer a later complete valid frame to a corrupt oversized head.
                found = False
                for index in range(2, len(self.pending) - 7):
                    tail = self.pending[index:]
                    end = int.from_bytes(tail[4:6], "big") + 8
                    if parse_frame(bytes(tail[:end])) is not None:
                        del self.pending[:index]
                        found = True
                        break
                if found:
                    continue
                break
            parsed = parse_frame(bytes(self.pending[:length]))
            if parsed is None:
                del self.pending[0]
                continue
            result.append(parsed)
            del self.pending[:length]
        return result


type Value = bool | int | str | bytes


def parse_dps(data: bytes) -> dict[int, Value]:
    result: dict[int, Value] = {}
    pos = 0
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError("Truncated DP header")
        id, kind = data[pos : pos + 2]
        size = int.from_bytes(data[pos + 2 : pos + 4], "big")
        pos += 4
        if pos + size > len(data):
            raise ValueError("Truncated DP value")
        raw_value = data[pos : pos + size]
        pos += size
        value: Value = raw_value
        if kind == Kind.BOOL and size == 1:
            value = raw_value[0] != 0
        elif kind == Kind.VALUE and size == 4:
            value = int.from_bytes(raw_value, "big", signed=True)
        elif kind == Kind.ENUM and size == 1:
            value = raw_value[0]
        elif kind == Kind.STRING:
            value = raw_value.decode("utf-8", errors="replace")
        result[id] = value
    return result


def parse_info(data: bytes) -> dict[int, bytes]:
    pos = 1 if data[:1] == b"\x01" else 0
    result: dict[int, bytes] = {}
    while pos + 2 <= len(data):
        tag, size = data[pos : pos + 2]
        pos += 2
        if pos + size > len(data):
            break
        result[tag] = data[pos : pos + size]
        pos += size
    return result
