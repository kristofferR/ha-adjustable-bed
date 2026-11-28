"""AMINACH Platinum 1.36's three layouts and independent press schedules.

Hand-transcribed from the accepted artifact report; no catalog generator.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import aminach as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities

SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NAME_PREFIX: Final = "AMB2"
LAYOUTS: Final = {1: ("back",), 2: ("back", "legs"), 3: ("back", "legs", "head")}
LAYOUT_CHOICES: Final = {1: "Back", 2: "Back and foot", 3: "Back, foot and head"}
KEYS: Final = {
    "sleep": 0xBA,
    "light": 0xD1,
    "memo": 0xE9,
    "back_up": 0x74,
    "back_down": 0x5D,
    "legs_up": 0x46,
    "legs_down": 0x2F,
    "head_up": 0xA3,
    "head_down": 0x8C,
    "release": 0xFF,
}


@dataclass(frozen=True, slots=True)
class AminachProfile:
    key: str = "platinum"
    execution: ExecutionCapabilities = STREAM_HOLD
    refresh_ms: int = 170
    memo_refresh_ms: int = 90
    memo_minimum_ms: int = 160
    default_motor_count: int = 3

    def frame(self, action: str) -> bytes:
        return codec.control(KEYS[action])

    def interval(self, action: str) -> int:
        return self.memo_refresh_ms if action == "memo" else self.refresh_ms


PLATINUM: Final = AminachProfile()
