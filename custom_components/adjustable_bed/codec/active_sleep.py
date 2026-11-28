"""Active Sleep 1.3.5 direct BLE frames (distinct from Bed Operation)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from operator import xor
from typing import Final

SERVICE_UUID: Final = "bc2f4cc6-aaef-4351-9034-d66268e328f0"
CHAR_UUID: Final = "06d1e5e7-79ad-4a71-8faa-373789f7d93c"
OPERATIONS: Final = {
    "stop": 0,
    "multi_button": 1,
    "head_up": 2,
    "head_down": 3,
    "legs_up": 4,
    "legs_down": 5,
    "height_up": 6,
    "height_down": 7,
    "combination_up": 8,
    "combination_down": 9,
    "tilt_down": 16,
    "tilt_up": 17,
}
AXES: Final = ("head", "legs", "height", "tilt")
LOCKS: Final = {"head": 1, "legs": 2, "height": 4, "combination": 8, "tilt": 16}
MODELS: Final = {
    0: "Unknown",
    1: "INTIME",
    2: "ACTIVE_SLEEP",
    3: "INTIME_COMFORT",
    4: "INTIME_1000",
    5: "ACTIVE_SLEEP_BED_FMC",
}
ZONES: Final = ("head", "shoulder", "hip", "thigh", "calf", "feet")
type Posture = tuple[int, int, int, int]


def frame(op: int, payload: bytes = b"", declared_length: int | None = None) -> bytes:
    body = bytes((op, len(payload) if declared_length is None else declared_length)) + payload
    return body + bytes((reduce(xor, body, 0),))


def arrow(button: int) -> bytes:
    return frame(0xB4, bytes((button, 127, 127, 127, 127)))


def preset(head: int, leg: int, height: int, tilt: int, current_height: int = 0) -> bytes:
    return frame(
        0xB4,
        bytes(
            v & 255 for v in (0x16, head, leg, current_height if height == 254 else height, tilt)
        ),
    )


def settings(
    head: bool = False,
    leg: bool = False,
    height: bool = False,
    combi: bool = False,
    tilt: bool = False,
    fast: bool = False,
) -> bytes:
    mask = sum(int(v) << i for i, v in enumerate((head, leg, height, combi, tilt)))
    return frame(0xB3, bytes((mask, 0, int(fast))))


def mattress(
    head: int,
    shoulder: int,
    hip: int,
    thigh: int,
    calf: int,
    feet: int,
    mode: int = 0,
    sound: int = 0,
    dehumidifier: int = 0,
    fukatto: bool = False,
) -> bytes:
    return frame(
        0xC2,
        bytes(
            (
                ((shoulder & 15) << 4) | (head & 15),
                ((thigh & 15) << 4) | (hip & 15),
                ((feet & 15) << 4) | (calf & 15),
                (sound << 7) | (dehumidifier << 6) | (int(fukatto) << 4) | (mode & 15),
            )
        ),
    )


def authentication(token: str) -> bytes:
    """Only an existing ID; the synthetic vector is never a credential default."""
    return frame(0x84, token.encode("ascii"), 16)


def fragments(raw: bytes, split: bool = False) -> tuple[bytes, ...]:
    return (
        (raw[:20], *(b"\x8f" + raw[i : i + 19] for i in range(20, len(raw), 19)))
        if split and len(raw) > 19
        else (raw,)
    )


def signed(value: int) -> int:
    return value if value < 128 else value - 256


@dataclass(frozen=True, slots=True)
class Spec:
    analyzer: bool
    bed: bool
    mattress: bool
    model: int
    mode: int

    @classmethod
    def parse(cls, payload: bytes) -> Spec:
        return cls(
            payload[0] >> 4 == 3,
            payload[3] >> 4 == 1,
            payload[6] >> 4 == 2,
            payload[3] & 15,
            payload[2] >> 4,
        )


@dataclass(frozen=True, slots=True)
class BedSpec:
    bounds: tuple[tuple[int, int], ...]
    locks: int

    @classmethod
    def parse(cls, payload: bytes) -> BedSpec:
        return cls(
            tuple((signed(payload[i]), signed(payload[i + 1])) for i in range(0, 8, 2)),
            payload[8] & 31,
        )


@dataclass(frozen=True, slots=True)
class Position:
    posture: Posture
    locks: int
    fast: bool
    fail: int

    @classmethod
    def parse(cls, payload: bytes) -> Position:
        return cls(
            (signed(payload[0]), signed(payload[1]), signed(payload[2]), signed(payload[3])),
            payload[4] & 31,
            payload[6] == 1,
            signed(payload[7]),
        )


@dataclass(frozen=True, slots=True)
class Mattress:
    zones: tuple[int, ...]
    sound: int
    ventilation: int
    fukatto: bool
    mode: int
    remaining: int
    busy: int
    fail: int

    @classmethod
    def parse(cls, payload: bytes) -> Mattress:
        return cls(
            tuple(v for b in payload[:3] for v in (b & 15, b >> 4)),
            payload[3] >> 7,
            (payload[3] >> 6) & 1,
            bool(payload[3] & 0x30),
            payload[3] & 15,
            signed(payload[4]),
            payload[6] & 127,
            signed(payload[15]),
        )

    def encode(self) -> bytes:
        return mattress(
            *self.zones,
            mode=self.mode,
            sound=self.sound,
            dehumidifier=self.ventilation,
            fukatto=self.fukatto,
        )


def sensor_value(raw: int, *, respiration: bool = False) -> int | None:
    return (int(raw * 0.2) if respiration else raw) if 0 < raw <= 251 else None


@dataclass(frozen=True, slots=True)
class Reply:
    opcode: int
    payload: bytes


class Receiver:
    """Bounded assembly with the app's rolling-XOR continuation termination.

    Unfragmented notifications have no proven checksum validation. Never let
    malformed/foreign traffic complete a query or carry state across links.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> Reply | None:
        if not data:
            return None
        if data[0] == 0x8F:
            if not self.buffer or len(data) < 2:
                return None
            self.buffer.extend(data[1:])
            if len(self.buffer) > 258:
                self.buffer.clear()
                return None
            if reduce(xor, self.buffer, 0):
                return None
            data = bytes(self.buffer[:-1])
            self.buffer.clear()
        else:
            self.buffer.clear()
            if len(data) < 2:
                return None
            if data[1] > len(data):
                self.buffer.extend(data)
                return None
        size = {
            1: 8,
            2: 9,
            4: 1,
            0x31: 9,
            0x32: 8,
            0x33: 0,
            0x34: 6,
            0x41: 16,
            0x42: 0,
            0x22: 12,
        }.get(data[0])
        if size is None or data[1] < size or len(data) < size + 2:
            return None
        return Reply(data[0], data[2 : 2 + size])
