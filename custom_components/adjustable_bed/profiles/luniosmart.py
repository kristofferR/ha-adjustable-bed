"""Lunio Smart+ 1.0.4: one fixed BED layout across six discovered GATT routes."""

from dataclasses import dataclass
from typing import Final

from ..codec.richmat import TransportKey
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class LunioSmartProfile:
    key: str = "luniosmart"
    execution: ExecutionCapabilities = STREAM_HOLD
    transports: tuple[TransportKey, ...] = ("n1", "w1", "w2", "w3", "w4", "w5")
    tick_s: float = 0.1
    receive_expiry_s: float = 0.5


PROFILE: Final = LunioSmartProfile()
KEYWORDS: Final = (
    "QRRM",
    "MlRM",
    "COOL",
    "MPE_",
    "209A05",
    "208A14",
    "200U",
    "FC200",
    "200I",
    "400I",
    "800I",
    "L&P-",
    "L&P ",
)
DIRECTIONS: Final = {"head_up": 0x24, "head_down": 0x25, "foot_up": 0x26, "foot_down": 0x27}
PRESETS: Final = {
    "flat": 0x31,
    "memory_recall_1": 0x2E,
    "memory_save_1": 0x2B,
    "zero_gravity": 0x45,
    "anti_snore": 0x46,
}
RELEASE: Final = 0x6E
