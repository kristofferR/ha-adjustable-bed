"""Casper Base 1.0.8 requests and notifications, independently accepted row101 evidence.

The frames are built by ``codec/richmat.py``. These specifications belong to this
package. Shared UUIDs do not identify an app.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from .codec.richmat import is_valid

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


def alarm_countdown(hour: int, minute: int, now: datetime) -> int:
    """App DateTime epoch difference, including local offset transitions."""
    current = now.replace(second=0, microsecond=0)
    target = current.replace(hour=hour, minute=minute)
    seconds = int(target.timestamp()) - int(current.timestamp())
    return int((seconds + 86400 if seconds <= 0 else seconds) / 60)


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
                        (
                            n
                            for n in (5, 7, 16)
                            if len(self.pending) > n and self.pending[n] == 0x6E
                        ),
                        0,
                    )
                    if not size:
                        if len(self.pending) < 16:
                            break
                        self.pending.clear()
                        raise ValueError("Unsupported ordinary frame boundary")
            packet = bytes(self.pending[:size])
            del self.pending[:size]
            if packet[1:2] != b"\x20" or is_valid(packet):
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
    if len(b) < 7 or len(b) != b[2] or not is_valid(b):
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


class CasperBaseActions(ABC):
    """Typed product actions shared by the Casper and Hush bases and sleep sensors."""

    @property
    def supports_casper_base_controls(self) -> bool:
        """Whether the explicit Casper Base app's named actions are available."""
        return False

    @property
    def supports_hush_base_controls(self) -> bool:
        """Whether the explicit Hush Base app's named actions are available."""
        return False

    @abstractmethod
    def validate_casper_base_request(self, request: Request) -> None:
        """Validate a request before any selected target writes."""

    @abstractmethod
    async def async_execute_casper_base_request(self, request: Request) -> None:
        """Execute one validated product action."""
