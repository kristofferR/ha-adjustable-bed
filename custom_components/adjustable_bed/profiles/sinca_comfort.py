"""Sinca Comfort Bed 1.0.2 controls, layouts and route selection."""

from dataclasses import dataclass
from typing import Final

from ..codec import mline as wire
from ..execution import ExecutionCapabilities

LAYOUTS: Final = {
    "two": ("back", "legs"),
    "triple": ("back", "legs", "neck"),
    "four": ("back", "legs", "neck", "lumbar"),
    "unknown": ("back", "legs", "neck", "lumbar"),
}
LAYOUT_LABELS: Final = {
    "two": "Head and foot",
    "triple": "Head, foot and neck",
    "four": "Head, foot, neck and lumbar (shared adjustment)",
    "unknown": "Unknown layout (shared neck and lumbar adjustment)",
}
PROTOCOL_LABELS: Final[dict[wire.Protocol, str]] = {
    "sleep": "Sleep receiver",
    "smart": "Smart receiver",
    "smartsainuo": "Smart receiver (Sainuo)",
    "okin": "Okin receiver (extended commands)",
    "unknown": "Unclassified receiver (basic commands)",
}
MOTORS: Final = {
    "back": (1, 2),
    "legs": (4, 8),
    "neck": (16, 32),
    "lumbar": (16, 32),
}
PRESETS: Final = {
    "flat": 0x08000000,
    "reading": 0x00002000,
    "anti_snore": 0x00008000,
    "tv": 0x00004000,
    "zero_g": 0x00001000,
    "memory_1": 0x00010000,
    "memory_2": 0x00040000,
}
MASSAGE: Final = {
    "toggle": 0x00000100,
    "wave": 0x10000000,
    "timer": 0x00000200,
    "foot": 0x00000400,
    "head": 0x00000800,
}
LIGHT: Final = 0x00020000
MOTION_PRESS_MS: Final = 1000
MEMORY_SAVE_PRESS_MS: Final = 5500
MASSAGE_TOGGLE_PRESS_MS: Final = 200
STARTUP_DELAY_MS: Final = 100
QUERY_MS: Final = 300
HISTORY_REPEAT_MS: Final = 100
HISTORY_IDLE_SECONDS: Final = 2.0
HISTORY_TRANSFER_SECONDS: Final = 30.0
HISTORY_RECORD_LIMIT: Final = 16384

EXECUTION: Final = ExecutionCapabilities(hold="latched")


@dataclass(frozen=True, slots=True)
class SincaProfile:
    key: wire.Protocol
    execution: ExecutionCapabilities = EXECUTION

    @property
    def release_ms(self) -> int:
        return QUERY_MS if self.key == "okin" else 100

    @property
    def status_repeat_ms(self) -> int:
        return 1000 if self.key == "smartsainuo" else QUERY_MS

    @property
    def clock_count(self) -> int:
        return 2 if self.key == "okin" else 1

    @property
    def status(self) -> bytes:
        return self.control(0) if self.key == "okin" else wire.AUXILIARY["checkState"]

    def alarm_frame(self, *, disable: bool = False) -> bytes:
        command = "closeAlarm" if disable else "checkAlarm"
        return wire.AUXILIARY[f"{command}.{'P2' if self.key == 'okin' else 'P1'}"]

    def control(self, word: int) -> bytes:
        return wire.control_word(word, self.key)


PROFILES: Final[dict[wire.Protocol, SincaProfile]] = {
    key: SincaProfile(key) for key in wire.PROTOCOLS
}


def scan_name(name: str) -> bool:
    return any(marker in name.upper() for marker in ("SLEEP", "SMARTBED", "OKIN"))


def protocol_from_scan(name: str, manufacturer: dict[int, bytes]) -> wire.Protocol:
    upper = name.upper()
    if "OKIN" in upper:
        return "okin"
    if "SMART" in upper:
        payload = manufacturer.get(89, b"")
        return "smartsainuo" if len(payload) == 5 and payload[0] == 5 else "smart"
    return "sleep" if not name or "SLEEP" in upper else "unknown"
