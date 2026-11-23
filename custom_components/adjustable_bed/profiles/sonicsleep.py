"""SonicSleep 1.0.4's fixed IQRM product, independent of device names."""

from dataclasses import dataclass
from typing import Final

from ..codec.richmat import TransportKey
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class SonicSleepProfile:
    key: str = "one"
    label: str = "IQRM"
    execution: ExecutionCapabilities = STREAM_HOLD


PROFILE: Final = SonicSleepProfile()
SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
ROUTES: Final[dict[str, TransportKey]] = {"Nordic": "n1", "W1": "w1", "W2": "w2", "W3": "w3", "W4": "w4", "W5": "w5"}
TICK_S: Final = 0.1
DIRECTIONS: Final = {
    "head_up": 0x24, "head_down": 0x25,
    "foot_up": 0x26, "foot_down": 0x27,
    "both_up": 0x29, "both_down": 0x2A,
}
PRESETS: Final = {
    "zero_gravity": (0x45, 0x66), "lounge": (0x59, 0x65),
    "tv": (0x58, 0x64), "anti_snore": (0x46, 0x69),
    "memory_1": (0x2E, 0x2B), "memory_2": (0x2F, 0x2C),
}
FLAT: Final = 0x31
EXIT_LIMIT: Final = ("deviceFunctionItemExitLimit", 0)
QUERY_CLOCK: Final = ("deviceFunctionItemCheckClock", 1)
