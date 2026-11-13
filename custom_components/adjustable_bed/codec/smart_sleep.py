"""OKIN Smart Sleep's two bed channels, from the accepted row094 literals.

P1 motor keys reuse Keeson's proven 05 02 carrier. P1 settings and P2's
AA/2A commands are distinct formats, without a checksum or authentication.
The length-looking bytes are command-specific, not a universal envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

from .keeson import p2

Format = Literal["p1", "p2"]
SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NAME: Final = "00002a00-0000-1000-8000-00805f9b34fb"
FIRMWARE: Final = "00002a26-0000-1000-8000-00805f9b34fb"
PROTOCOL: Final = "00002a27-0000-1000-8000-00805f9b34fb"
INITIALIZE: Final = bytes.fromhex("2a000005810900ffff00002225124b")
LEGACY_KEYS: Final = {
    "stop": 0,
    "light": 0x20000,
    "massage_all": 0x100,
    "massage_off": 0x02000000,
    "wave": 0x10000000,
    "timer": 0x200,
    "foot_strength": 0x400,
    "head_strength": 0x800,
    "flat": 0x08000000,
    "zero_g": 0x1000,
    "read": 0x2000,
    "tv": 0x4000,
    "anti_snore": 0x8000,
    "memory_1": 0x10000,
    "memory_2": 0x40000,
}
PRESETS: Final = {
    "zero_g": 1,
    "read": 2,
    "tv": 3,
    "anti_snore": 4,
    "memory_1": 5,
    "memory_2": 6,
    "flat": 9,
}
CATALOGS: Final = {
    "wave": (66, 4),
    "head_strength": (80, 4),
    "foot_strength": (84, 4),
    "timer": (73, 3),
    "alarm": (1, 9),
}


def wrap(index: int, first: int, count: int) -> int:
    """The app wraps one step out of range, rather than using modulo."""
    return first + (count if index < 1 else 1 if index > count else index) - 1


def motion(fmt: Format, axis: int, up: bool) -> bytes:
    if axis not in range(1, 6):
        raise ValueError("Choose app actuator 1 through 5")
    mask = (1 if up else 2) << (2 * (axis - 1))
    if fmt == "p2":
        return bytes((0xAA, 0, 0, 1, 1, 4)) + mask.to_bytes(4, "little")
    word = ((0x40 if up else 0x80) << 24) if axis == 5 else mask
    return p2(word, "p2_side")


def stop(fmt: Format, *, motor: bool = False) -> bytes:
    if fmt == "p1":
        return p2(0, "p2_side")
    return bytes.fromhex("aa000001010400000000" if motor else "aa0000010200")


def preset(fmt: Format, name: str, *, save: bool = False) -> bytes:
    if fmt == "p1":
        if save:
            raise ValueError("Legacy SAVE is not proven")
        return bytes.fromhex("01b601") if name == "ai_zero" else p2(LEGACY_KEYS[name], "p2_side")
    value = PRESETS[name]
    if save and name == "flat":
        raise ValueError("Flat has no SAVE")
    return bytes((0xAA, 0, 0, 1, 5 if save else 3, 1, value + (32 if save else 0)))


def massage(fmt: Format, action: str, index: int = 1) -> bytes:
    if fmt == "p1":
        return p2(LEGACY_KEYS[action], "p2_side")
    value = {"massage_all": 64, "massage_off": 65}.get(action)
    if value is None:
        value = wrap(index, *CATALOGS[action])
    return bytes((0xAA, 0, 0, 2, 1, 1, value))


def wave_cycle(current: int) -> bytes:
    # Unlike gainValue, waveAdd looks up current+1 and falls back to opcode66.
    return bytes((0xAA, 0, 0, 2, 1, 1, 66 + current if 0 <= current < 4 else 66))


def light(fmt: Format, enabled: bool) -> bytes:
    return (
        p2(LEGACY_KEYS["light"], "p2_side")
        if fmt == "p1"
        else bytes((0xAA, 0, 0, 4, 1, 5, 0, int(enabled)))
    )


def query(fmt: Format, kind: str) -> bytes:
    if kind == "settings" or fmt == "p1" and kind == "massage":
        return bytes.fromhex("00b0")
    if fmt == "p1" and kind == "alarm":
        return bytes.fromhex("00c0")
    return bytes((0x2A, 0, 0, 3 if kind == "alarm" else 2, 0x81, 1, 1 if kind == "alarm" else 3))


def gain_week(mask: int, scheduled: datetime, now: datetime) -> int:
    """Source gainWeek, including equality after flooring to milliseconds."""
    epoch = datetime(1970, 1, 1, tzinfo=UTC if scheduled.tzinfo else None)
    if (mask <= 0 or mask == 128) and (scheduled - epoch) // timedelta(milliseconds=1) <= (
        now - epoch
    ) // timedelta(milliseconds=1):
        return 1 << ((scheduled.isoweekday() + 1) % 7)
    return mask


def alarm(
    fmt: Format,
    *,
    enabled: bool,
    week: int,
    action: int,
    hour: int,
    minute: int,
    flexible: bool = False,
) -> bytes:
    if not 0 <= week <= 255 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Invalid alarm fields")
    if fmt == "p1":
        if not enabled:
            return bytes((7, 5, 0, 0, 0, 0, 0, 0, 0, int(flexible)))
        return bytes((7, 5, week, action, hour, minute, 0, 1, 1, int(flexible)))
    return (
        bytes((0xAA, 0, 0, 3, 2, 7, 1, week, wrap(action, 1, 9), 1, hour, minute, 0))
        if enabled
        else bytes.fromhex("aa000003020701000000000000")
    )


def clock(fmt: Format, now: datetime) -> bytes:
    new = fmt == "p2"
    fields = (
        now.year - (2000 if new else 1900),
        now.month - (0 if new else 1),
        now.day,
        now.isoweekday() - (0 if new else 1),
        now.hour,
        now.minute,
        now.second,
    )
    return bytes((0xAA, 0, 0, 3, 1, 7, *fields) if new else (7, 4, *fields))


def privacy(enabled: bool) -> bytes:
    return bytes((1, 0xB2, int(enabled)))


def antisnore(enabled: bool, value: int, *, demo: bool = False) -> bytes:
    if value not in (0, 1, 3, 6):
        raise ValueError("Choose a proven antisnore option")
    return bytes((2, 11, 2 if demo else int(enabled), 6 if demo else value, 1))


def sensitivity(level: int) -> bytes:
    if level not in (1, 2, 3):
        raise ValueError("Choose sensitivity 1, 2 or 3")
    return bytes((1, 10, level))


@dataclass(frozen=True, slots=True)
class MassageState:
    on: bool
    wave: int
    head: int
    foot: int
    timer: int
    timer_index: int


@dataclass(frozen=True, slots=True)
class SettingsState:
    massage: MassageState
    sensitivity: int
    antisnore: bool
    antisnore_value: int
    privacy: bool


@dataclass(frozen=True, slots=True)
class AlarmState:
    enabled: bool
    week: int | None = None
    action: int | None = None
    time: tuple[int, int, int] | None = None
    flexible: bool | None = None


@dataclass(frozen=True, slots=True)
class LightState:
    state: int
    brightness: int

    @property
    def on(self) -> bool:
        return self.state != 0 and self.brightness != 0


@dataclass(frozen=True, slots=True)
class AIZeroState:
    status: int
    score: int


type State = MassageState | SettingsState | AlarmState | LightState | AIZeroState


def privacy_compat(protocol: str, firmware: str) -> bool:
    parts = firmware.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except ValueError, IndexError:
        return False
    return protocol in ("SENSOR_VOICE", "SLEEPVOICE") and (major > 1 or major == 1 and minor > 0)


def parse(data: bytes, fmt: Format, *, new_privacy: bool = False) -> State | None:
    """Complete bed replies only. No padding, analytics or log-only combined value."""
    if data[:2] == b"\xa5\x0b" and len(data) == 20:
        ticks = int.from_bytes(data[4:6], "little")
        timer = ticks // 600 + 1 if ticks else 0

        def strength(v: int) -> int:
            return v % 3 + v // 3 + int(v > 1)

        state = (
            MassageState(
                True,
                data[6] - 1,
                strength(data[7] & 15),
                strength(data[8]),
                timer,
                min(timer - 1, 2),
            )
            if timer
            else MassageState(False, 0, 0, 0, 0, 0)
        )
        return SettingsState(
            state,
            data[14],
            data[15] == 1,
            data[16],
            bool(data[19] & 2) if new_privacy else data[18] == 1,
        )
    if data[:2] == b"\xa5\x0c" and len(data) == 11:
        week, kind, hour, minute = data[4:8]
        if hour > 23 or minute > 59:
            return None
        return AlarmState(
            data[9] == 1 and any((week, kind, hour, minute)),
            0 if week < 128 else week,
            kind,
            (hour, minute, 0),
            data[10] == 1,
        )
    if data[:3] == b"\xa7\x01\x02" and len(data) == 5 and data[3] in (0, 255):
        return AIZeroState(data[3], data[4])
    if fmt != "p2" or data[:3] != b"\x2a\x00\x00":
        return None
    if len(data) == 12 and data[3:7] == bytes((4, 129, 6, 2)):
        return LightState(data[7], data[11])
    if len(data) == 11 and data[3:5] == bytes((2, 129)) and data[6] == 3:
        head = (data[7] & 15) // 3 + 1 if data[7] & 15 else 0
        foot = (data[10] & 15) // 3 + 1 if data[10] & 15 else 0
        ticks = int.from_bytes(data[8:10], "little")
        timer = ticks // 600 + 1 if ticks else 0
        return (
            MassageState(
                True, max(data[7] >> 4, data[10] >> 4), head, foot, timer, min(timer - 1, 2)
            )
            if (head or foot) and timer
            else MassageState(False, 0, 0, 0, 0, 0)
        )
    if len(data) == 13 and data[3:5] == bytes((3, 129)) and data[6] == 1:
        # All six fields are required even for disabled alarms (audit A1).
        week, action, enabled, hour, minute, second = data[7:13]
        if enabled not in (0, 1) or hour > 23 or minute > 59 or second > 59 or action > 9:
            return None
        return (
            AlarmState(True, week, action, (hour, minute, second)) if enabled else AlarmState(False)
        )
    return None


class Replies:
    """Bounded bed-only framing; history FE16 fragments never enter bed parsers.

    Fixed reply shapes come from the accepted parser, not a guessed length
    byte. A caller gives each session its own assembler and expires partials.
    """

    def __init__(self) -> None:
        self.pending = b""

    def feed(self, data: bytes, fmt: Format) -> tuple[bytes, ...]:
        if not data or len(data) > 1024:
            self.pending = b""
            return ()
        # A fresh complete header cannot be the tail of a truncated reply.
        starts = (b"\xa5\x0b", b"\xa5\x0c", b"\xa7\x01\x02", b"\x2a\x00\x00")
        if self.pending and data.startswith(starts):
            self.pending = b""
        self.pending += data
        frames: list[bytes] = []
        sizes = {b"\xa5\x0b": 20, b"\xa5\x0c": 11, b"\xa7\x01\x02": 5}
        if fmt == "p2":
            sizes.update(
                {
                    b"\x2a\x00\x00\x02\x81": 11,
                    b"\x2a\x00\x00\x03\x81": 13,
                    b"\x2a\x00\x00\x04\x81": 12,
                }
            )
        while self.pending:
            match = next(
                (
                    (prefix, size)
                    for prefix, size in sizes.items()
                    if self.pending.startswith(prefix)
                ),
                None,
            )
            if match is None:
                if any(prefix.startswith(self.pending) for prefix in sizes):
                    break
                self.pending = b""
                break
            _, size = match
            if len(self.pending) < size:
                break
            frames.append(self.pending[:size])
            self.pending = self.pending[size:]
        return tuple(frames)
