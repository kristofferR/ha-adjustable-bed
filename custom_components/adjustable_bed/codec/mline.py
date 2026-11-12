"""M Line 1.2.2 direct BED codecs; proven carriers delegate to their existing encoders.

P1 is raw 05/02, P2 reverses its four control bytes in E6/FE/16 with a
complement checksum. Auxiliary commands and replies have independent formats.
The accepted row147 literals, not the Okin name, establish these relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from . import keeson, okin_nframe

Protocol = Literal["sleep", "smart", "smartsainuo", "okin", "unknown"]
PROTOCOLS: Final[tuple[Protocol, ...]] = ("sleep", "smart", "smartsainuo", "okin", "unknown")
MODES: Final = ("zg", "flat", "m1", "m2", "vibration", "antisnore")
WORDS: Final = {
    "massageAll": 0x00000100,
    "massageStopAll": 0x02000000,
    "waveAdd": 0x10000000,
    "meanwhileStrengthAdd": 0x00000C00,
    "timerSwitch": 0x00000200,
    "stopCommand": 0,
    "machinery4Down": 0x80,
    "machinery4Up": 0x40,
    "machinery3Down": 0x20,
    "machinery3Up": 0x10,
    "hfDown": 0x0A,
    "hfUp": 0x05,
    "footDown": 8,
    "footUp": 4,
    "headDown": 2,
    "headUp": 1,
    "light": 0x00020000,
    "memory6_M2": 0x00040000,
    "memory5_M1": 0x00010000,
    "flatPosition": 0x08000000,
    "antiSnore": 0x00008000,
    "zeroGravity": 0x00001000,
}
AUXILIARY: Final = {
    "checkState": bytes((0, 0xB0)),
    "gainNewHistoricalData": bytes((1, 0xB1, 2)),
    "gainAllHistoricalData": bytes((1, 0xB1, 1)),
    "confirmGainHistoryData": bytes((1, 0xB3, 1)),
    "checkOpenBlemanage": bytes((1, 0xB4, 1)),
    "openPrivacyMode": bytes((1, 0xB2, 1)),
    "closePrivacyMode": bytes((1, 0xB2, 0)),
    "checkAlarm.P1": bytes((0, 0xC0)),
    "checkAlarm.P2": keeson.checked(bytes((0xE1, 0x80, 3))),
    "closeAlarm.P1": okin_nframe.alarm((0, 0, 0, 0, 0, 0, 0)),
    "closeAlarm.P2": keeson.alarm_table(3, bytes(4)),
}
NORDIC_SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NORDIC_WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NORDIC_NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FFE_SERVICE: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
FFE_WRITE: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
FFE_NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE_NOTIFY: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
INFO_SERVICE: Final = "0000180a-0000-1000-8000-00805f9b34fb"
FIRMWARE: Final = "00002a26-0000-1000-8000-00805f9b34fb"
PROTOCOL_STRING: Final = "00002a27-0000-1000-8000-00805f9b34fb"


def control(action: str, protocol: Protocol) -> bytes:
    word = WORDS[action]
    if protocol == "okin":
        return keeson.frame(word, header=0xE6, order="little", side=0)
    return okin_nframe.frame40(word)


def bcd(value: int) -> int:
    return value // 10 * 16 + value % 10


def clock(protocol: Protocol, now: datetime) -> bytes:
    if protocol == "okin":
        return keeson.clock(now)
    if protocol == "smartsainuo":
        fields = (
            bcd(now.year - 2000),
            bcd(now.month),
            bcd(now.day),
            now.isoweekday() % 7,
            bcd(now.hour),
            bcd(now.minute),
            bcd(now.second),
        )
    else:
        fields = (
            now.year - (1900 if protocol == "sleep" else 2000),
            now.month - 1,
            now.day,
            now.weekday() if protocol == "sleep" else now.isoweekday(),
            now.hour,
            now.minute,
            now.second,
        )
    return okin_nframe.clock(fields)


def alarm(protocol: Protocol, hour: int, minute: int, wake_type: int, mode: str) -> bytes:
    if (
        mode not in MODES
        or not 0 <= hour <= 23
        or not 0 <= minute <= 59
        or not 0 <= wake_type <= 255
    ):
        raise ValueError("Invalid M Line alarm fields")
    modes = (
        {"m1": 17, "m2": 19}
        if protocol == "okin"
        else {"m1": 2, "m2": 3}
        if protocol == "smartsainuo"
        else dict(zip(MODES, (1, 9, 5, 6, 8, 4), strict=True))
    )
    value = modes.get(mode, 0)
    if protocol == "okin":
        return keeson.alarm_table(3, bytes((hour, minute, wake_type, value)))
    return okin_nframe.alarm(
        (wake_type, value, hour, bcd(minute) if protocol == "smartsainuo" else minute, 0, 1, 1)
    )


def wake_mask(weekdays: tuple[int, ...], hour: int, minute: int, now: datetime) -> int:
    """Public Monday=0 days; source wire Sunday=0, high bit means recurrence."""
    if any(type(day) is not int or day not in range(7) for day in weekdays) or len(
        set(weekdays)
    ) != len(weekdays):
        raise ValueError("Weekdays must be unique, Monday 0 through Sunday 6")
    if weekdays:
        return 128 | sum(1 << ((day + 1) % 7) for day in weekdays)
    target = now.replace(hour=hour, minute=minute)
    if target <= now:
        target += timedelta(days=1)
    return 1 << ((target.weekday() + 1) % 7)


def anti_snore(enabled: bool, angle: int, position: int, *, demo: bool = False) -> bytes:
    if demo:
        if position not in (1, 2):
            raise ValueError("Choose head (1) or elevation (2)")
        return bytes((4, 11, 2, 1, position))
    if not enabled:
        return bytes((4, 11, 0, 0, 0))
    if angle not in (1, 3, 6) or position not in (1, 2):
        raise ValueError("Choose angle 1, 3 or 6 and position 1 or 2")
    return bytes((4, 11, 1, angle, position))


def new_sensor_protocol(protocol_string: str | None, firmware: str | None) -> bool | None:
    """Only observed valid values choose a privacy offset, never cached defaults."""
    if protocol_string is None or firmware is None:
        return None
    parts = firmware.split(".")
    if not all(part.isascii() and part.isdecimal() for part in parts):
        return None
    major, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    return protocol_string == "SENSOR_VOICE" and (major > 1 or major == 1 and minor > 0)


class Assembler:
    """Original-fragment predicate, bounded and fenced by the controller session."""

    def __init__(self) -> None:
        self.pending: bytes | None = None

    def feed(self, incoming: bytes) -> bytes | None:
        if len(incoming) < 3:
            return None
        previous, self.pending = self.pending, None
        if len(incoming) == 20 and incoming[1:3] == b"\xfe\x16":
            self.pending = incoming
            return None
        working = (previous or b"") + incoming
        return working if len(working) <= 512 else None


@dataclass(frozen=True)
class Live:
    heart: int
    breath: int
    state: int

    @property
    def moving(self) -> bool:
        return self.state == 6

    @property
    def projection(self) -> bool:
        return self.state not in (3, 5, 6)


def live(data: bytes) -> Live | None:
    # Safe adaptation of F1: validate before committing the controller's throttle.
    return Live(*data[3:6]) if len(data) >= 6 and data[:3] == b"\xa6\x10\x03" else None


@dataclass(frozen=True)
class AlarmState:
    wake: int
    mode: int
    hour: int
    minute: int
    enabled: bool


def alarm_state(data: bytes) -> AlarmState | None:
    if len(data) < 10 or data[:3] != b"\xa5\x0c\x0e":
        return None
    wake, mode, hour, minute, enabled = data[4], data[5], data[6], data[7], data[9]
    if hour > 23 or minute > 59:
        return None
    return AlarmState(
        wake if wake >= 128 else 0,
        mode,
        hour,
        minute,
        bool(enabled) and not (enabled == 1 and not any((wake, mode, hour, minute))),
    )


def alarm_mode(protocol: Protocol, value: int) -> str:
    """Response lookup is deliberately asymmetric with setAlarm's mode domain."""
    modes = (
        {2: "m1", 3: "m2", 1: "zg", 9: "flat", 4: "antisnore"}
        if protocol == "smartsainuo"
        else {17: "m1", 19: "m2", 13: "zg", 28: "flat", 16: "antisnore"}
        if protocol == "okin"
        else {1: "zg", 9: "flat", 5: "m1", 6: "m2", 8: "vibration", 4: "antisnore"}
    )
    return modes.get(value, "zg")
