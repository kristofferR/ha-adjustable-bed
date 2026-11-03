"""Casper Base 1.0.8 direct BLE frames, independently accepted row101 evidence.

These specifications belong to this package. Shared UUIDs do not identify an app.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

GATT: Final = (
    ("6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e"),
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600"),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622"),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe2-0000-1000-8000-00805f9b34fb"),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb"),
    ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "00000002-3c17-d293-8e48-14fe2e4da212"),
)
SPECIAL: Final = {
    "exit_limit": (0x6E, 2, 1, 0),
    "clock": (0x6E, 8, 1, 1),
    "light": (0x6E, 10, 0, 1),
    "music": (0x6E, 21, 1, 1),
}
RGB_TIMERS: Final = (5, 8, 10, 13, 15, 18, 21, 24, 27, 30, 120, 210, 300, 390, 480)
ALARM_MODES: Final = {
    "tv": "TVPosition",
    "zero_g": "ZeroGravity",
    "anti_snore": "AntiSnoring",
    "lounge": "LoungePosition",
    "memory_1": "MemoryPosition1",
    "memory_2": "MemoryPosition2",
    "memory_3": "MemoryPosition3",
}
SensorKind = Literal["mm", "sxb"]


@dataclass(frozen=True, slots=True)
class Request:
    """Finite named configuration action, never arbitrary command bytes."""

    operation: str
    value: int = 0
    rgb: tuple[int, int, int] = (0, 0, 0)
    enabled: bool = True
    hour: int = 0
    minute: int = 0
    mode: str = ""
    slot: int = 1
    days: tuple[int, ...] = ()
    part: int = 1
    report_type: int = 1
    year: int = 2026
    month: int = 1
    day: int = 1
    source: str = ""


def frame(values: Sequence[int]) -> bytes:
    return bytes((*[value & 255 for value in values], sum(values) & 255))


def control(opcode: int, *, single: bool = False, side: int = 0) -> bytes:
    return bytes((opcode,)) if single else frame((0x6E, 1, side, opcode))


def special(name: str, *, single: bool = False) -> bytes:
    values = SPECIAL[name]
    return bytes((values[-1],)) if single else frame(values)


def extra(category: int, subtype: int, values: Sequence[int], operation: int = 1) -> bytes:
    return frame((0x6E, 0x20, 7 + len(values), category, subtype, operation, *values))


def light_seconds(seconds: int) -> bytes:
    # The app slices a padded hexadecimal string, including its zero sentinel.
    text = format(seconds, "x").rjust(4, "0")
    high, low = int(text[:2], 16), int(text[2:4], 16)
    if high == low == 0:
        high = low = 255
    return frame((0x6E, 11, high, low))


def light_rgb(rgb: tuple[int, int, int]) -> bytes:
    red, green, blue = rgb
    return frame((0x6E, 12, 255, red)) + frame((0x6E, 13, green, blue))


def alarm_pair(minutes: int, mode: int) -> tuple[bytes, bytes]:
    return frame((0x6E, 6, minutes // 256, mode)), frame((0x6E, 5, minutes & 255, 0))


def alarm_countdown(hour: int, minute: int, now: datetime) -> int:
    """App DateTime epoch difference, including local offset transitions."""
    current = now.replace(second=0, microsecond=0)
    target = current.replace(hour=hour, minute=minute)
    seconds = int(target.timestamp()) - int(current.timestamp())
    return int((seconds + 86400 if seconds <= 0 else seconds) / 60)


def time_sync(now: datetime) -> bytes:
    return extra(8, 3, (now.year - 1970, now.month, now.day, now.hour, now.minute, now.second))


class MainReceive:
    """Preserve supported ordinary lengths and validate extended framing."""

    def __init__(self) -> None:
        self.pending = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self.pending.extend(chunk)
        out: list[bytes] = []
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            if self.pending[1] == 0x20:
                size = self.pending[2]
                if size < 7:
                    self.pending.clear()
                    raise ValueError("Invalid extended frame length")
                if len(self.pending) < size:
                    break
            else:
                # Ordinary formats have no length byte. Keep complete 5/7/16-byte
                # notifications intact, including marker-valued data/checksums.
                size = len(self.pending)
                if size not in (5, 7, 16):
                    size = next(
                        (n for n in (5, 7, 16) if len(self.pending) > n and self.pending[n] == 0x6E),
                        0,
                    )
                    if not size:
                        if len(self.pending) < 16:
                            break
                        self.pending.clear()
                        raise ValueError("Unsupported ordinary frame boundary")
            packet = bytes(self.pending[:size])
            del self.pending[:size]
            if packet[1:2] != b"\x20" or sum(packet[:-1]) & 255 == packet[-1]:
                out.append(packet)
        return out


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    values: dict[str, object]


_EXACT: Final = {
    "6e09010078": "clock_available",
    "6e0e00037f": "light_available",
    "6e1a000189": "aroma_available",
    "6e07010177": "clock_add_ok",
    "6e07010278": "clock_cancel_ok",
    "6e16010186": "music_available",
    "6e90c101c0": "detection_available",
    "6e2100008f": "snore_available",
}


def decode_main(b: bytes) -> Event | None:
    """Decode all ordinary and extended branches, retaining uncalibrated data."""
    if name := _EXACT.get(b.hex()):
        return Event(name, {})
    if b[1:2] == b"\x20":
        return decode_extra(b)
    if len(b) == 7 and b[1] == 0x90:
        return Event(
            "desk",
            {"current_inch": (100 * b[4] + b[5]) / 10, "current_cm": (100 * b[4] + b[5]) / 10},
        )
    if len(b) == 16:
        return Event(
            "desk",
            dict(
                zip(
                    ("min_inch", "max_inch", "min_cm", "max_cm", "current_inch", "current_cm"),
                    ((100 * b[i] + b[i + 1]) / 10 for i in range(3, 15, 2)),
                    strict=True,
                )
            ),
        )
    if len(b) != 5 or b[:2] != b"\x6e\x90":
        return None
    high, low = b[2] >> 4, b[2] & 15
    if b[2] == 0:
        return Event("protocol_version", {"value": b[3]})
    if high == 1:
        return Event("bed_mode", {"value": low})
    if high == 3:
        return Event("motor", {"index": (b[2] >> 2) & 3, "status": b[2] & 3, "angle": b[3]})
    if high == 10:
        x = (low << 8) | b[3]
        return Event(
            "massage",
            {"mode": (x >> 9) & 7, "zone1": x & 7, "zone2": (x >> 3) & 7, "zone3": (x >> 6) & 7},
        )
    if high == 11:
        return Event(
            "accessories",
            {
                "usb": bool(b[2] & 1),
                "play": bool(b[3] & 128),
                "music_follow": bool(b[3] & 64),
                "bluetooth": bool(b[3] & 32),
            },
        )
    if high == 12 and low == 2:
        return Event(
            "detection_status",
            {"value": {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(b[3] >> 4, "start")},
        )
    if high == 12 and low in (3, 4, 5, 6):
        return Event(
            "detection_details",
            {
                "details": {},
                "logged_status": {
                    0: "abnormal",
                    1: "normal",
                    2: "control_box_malfunction",
                    3: "not_plugged_in",
                }.get(b[3] & 15, "not_plugged_in"),
            },
        )
    if high == 13 and low in (1, 2):
        return Event("music_volume" if low == 1 else "shake_gear", {"value": b[3]})
    return None


def decode_extra(b: bytes) -> Event | None:
    if len(b) < 7 or len(b) != b[2] or sum(b[:-1]) & 255 != b[-1]:
        return None
    category, subtype, op = b[3:6]
    if category == 10 and 1 <= subtype <= 6:
        return Event("check", {"subtype": subtype, "raw": b.hex()})
    if category == 5 and subtype == 1:
        if len(b) < 13:
            raise ValueError("Truncated alarm response")
        if op in (2, 3):
            return Event(
                "alarm_list" if op == 2 else "alarm_update",
                dict(
                    zip(("id", "reserved", "hour", "minute", "mode", "mask"), b[6:12], strict=True)
                ),
            )
    if op not in (2, 3):
        return None
    if category == 1 and subtype == 2 and len(b) > 9:
        return Event(
            "motor_extra",
            {
                "height": ((b[7] << 8) + b[8]) / 10,
                "type": b[9],
                "angle": b[10] if len(b) > 11 else -1,
            },
        )
    if category == 2:
        if subtype == 1 and (len(b) - 7) % 2 == 0:
            return Event(
                "massage_pairs",
                {"values": [[b[i], b[i + 1]] for i in range(6, len(b) - 1, 2) if b[i] in (1, 2)]},
            )
        if subtype in (2, 4, 5, 6) and len(b) > 7:
            return Event(
                {
                    2: "massage_mode",
                    4: "massage_frequency",
                    5: "music_follow_intensity",
                    6: "music_follow_power",
                }[subtype],
                {"value": b[7] == 1 if subtype == 6 else b[7]},
            )
    if category == 3 and subtype == 1 and len(b) > 7:
        return Event("white_led_power", {"value": b[7] == 1})
    if category == 4:
        if subtype == 1 and len(b) > 9:
            return Event("rgb_color", {"rgb": list(b[7:10])})
        if subtype == 2 and len(b) > 8:
            return Event("rgb_timer", {"minutes": b[7] * 60 + b[8]})
        if subtype in (3, 4) and len(b) > 7:
            return Event("rgb_sensor" if subtype == 3 else "rgb_power", {"value": b[7] == 1})
    if category == 6:
        if subtype in (1, 2) and len(b) > 7:
            return Event("snore_detection" if subtype == 1 else "bed_exit", {"value": b[7] == 1})
        if subtype == 3:
            if len(b) < 8:
                raise ValueError("Truncated sleep name")
            return Event("sleep_name", {"value": b[7:-1].decode("latin1")})
    if category == 9 and subtype in (1, 3) and len(b) > 7:
        return Event("music_play" if subtype == 1 else "music_bluetooth", {"value": b[7] == 1})
    if category == 11 and subtype in (1, 2):
        if len(b) < 9:
            raise ValueError("Truncated press mode")
        return Event(
            "press_mode" if subtype == 1 else "same_control",
            {"value": b[7] if subtype == 1 else b[7] == 2},
        )
    if category == 15 and len(b) >= 20:
        values: dict[str, object] = dict(
            zip(
                ("min_inch", "max_inch", "min_cm", "max_cm", "current_inch", "current_cm"),
                ((100 * b[i] + b[i + 1]) / 10 for i in range(7, 19, 2)),
                strict=True,
            )
        )
        values.update(
            long_press=bool(b[6] & 8),
            reset=bool(b[6] & 16),
            angles=list(b[19:22]) if len(b) >= 23 else [0, 10, 0],
        )
        return Event("desk_extra", values)
    return None
