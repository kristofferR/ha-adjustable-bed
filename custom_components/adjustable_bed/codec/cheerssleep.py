"""CheersSleep 2.7.0 serial/PID and EE key/setting formats.

P1 is extracted from Remacro's proven serial/PID encoder; P2 adds EE
key/settings/query frames. Values truncate like Java byte/short/int stores.
Neither format adds a checksum or authentication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Format = Literal["p1", "p2"]
SERVICE: Final = "6e403587-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e403588-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e403589-b5a3-f393-e0a9-e50e24dcca9e"


def p1(serial: int, pid: int, command: int, parameter: int = 0) -> bytes:
    return (
        bytes((serial & 255, pid & 255))
        + (command & 65535).to_bytes(2, "little")
        + (parameter & 0xFFFFFFFF).to_bytes(4, "little")
    )


def side(selected: int) -> int:
    return {1: 0xAA, 2: 0xBB}.get(selected, selected & 255)


def normal(key: int, selected: int = 0) -> bytes:
    return (
        bytes((0xEE, 1, 5)) + (key & 0xFFFFFFFF).to_bytes(4, "big") + bytes((side(selected), 0xC0))
    )


def setting(opcode: int, a: int = 0, b: int = 0, c: int = 0, selected: int = 0) -> bytes:
    return bytes((0xEE, 2, 5, opcode & 255, a & 255, b & 255, c & 255, side(selected), 0xC0))


def query(music: bool = False, selected: int = 0) -> bytes:
    return bytes((0xEE, 0xD0 if music else 0xB0, 1, side(selected), 0xC0))


@dataclass(slots=True)
class Counters:
    command: int = 1
    cached: int = 0
    settings: int = 1

    def control(self, command: int, parameter: int = 0, *, held: bool = False) -> bytes:
        if not held or command != self.cached:
            self.command += 1
        if held:
            self.cached = command
        return p1(self.command, 1, command, parameter)

    def configure(self, command: int, parameter: int) -> bytes:
        frame = p1(self.settings, 3, command, parameter)
        self.settings += 1
        return frame

    def mac_query(self) -> bytes:
        frame = p1(self.command, 7, 0)
        self.command += 1
        return frame


def signed(value: int) -> int:
    return value - 256 if value >= 128 else value


@dataclass(frozen=True, slots=True)
class SleepState:
    side: str
    snore: int
    on_bed: bool
    asleep: bool
    heart: int
    breath: int
    gatem: int
    gateo: int
    snore_count: int
    snore_power: int


def sleep_state(data: bytes) -> SleepState | None:
    if len(data) < 9 or data[1] not in (0x87, 0x88):
        return None
    occupied = bool(data[2] & 4)
    return SleepState(
        "left" if data[1] == 0x87 else "right",
        data[2] & 3,
        occupied,
        bool(data[2] & 8),
        signed(data[3]) if occupied else 0,
        signed(data[4]) if occupied else 0,
        *(signed(v) for v in data[5:9]),
    )


def sleep_mac(data: bytes) -> str | None:
    return data[2:8].hex() if len(data) >= 8 and data[1] == 0x89 else None


@dataclass(frozen=True, slots=True)
class BasicState:
    light: bool
    mode: int | None
    head: int | None
    foot: int | None


def basic_state(data: bytes, *, massage: bool, selected: int = 0) -> BasicState | None:
    if len(data) < 10 or data[:2] != b"\xee\xb0":
        return None
    mode = signed(data[6]) - 1
    valid = massage and mode in range(3) and (not selected or data[3] == side(selected))
    return BasicState(
        data[9] == 1,
        mode if valid else None,
        signed(data[7]) if valid else None,
        signed(data[8]) if valid else None,
    )


@dataclass(frozen=True, slots=True)
class SharedState:
    rgb: tuple[int, int, int]
    brightness: int
    light: bool
    music: bool
    mode: int
    level: int


def shared_state(data: bytes, *, as_layout: bool = False, selected: int = 0) -> SharedState | None:
    if len(data) < 17 or data[:2] != b"\xee\xd0":
        return None
    mode = signed(data[12])
    if selected:
        mode = data[12] & 15 if selected == 1 else data[12] >> 4
    return SharedState(
        (data[4], data[5], data[6]),
        signed(data[7]),
        data[8 if as_layout else 16] == 1,
        bool(data[8] & 1),
        mode,
        min(100, max(0, signed(data[11]))),
    )


@dataclass(slots=True)
class Burst:
    """The shipped runnable retains its count across interrupted invocations."""

    count: int = 0

    def step(self) -> tuple[bool, bool]:
        """Return (command, final duplicate release). Six callbacks per fresh burst."""
        self.count += 1
        if self.count < 4:
            return True, False
        if self.count >= 6:
            self.count = 0
            return False, True
        return False, False


def rgb_parameter(red: int, green: int, blue: int, brightness: int) -> int:
    return ((red << 24) + (green << 16) + (blue << 8) + brightness) & 0xFFFFFFFF
