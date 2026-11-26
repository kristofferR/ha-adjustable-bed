"""The four product choices in Jerome's Adjustable Base."""

from dataclasses import dataclass
from typing import Final

from ..codec.richmat import TransportKey
from ..execution import STREAM_HOLD, ExecutionCapabilities

TRANSPORTS: Final[tuple[TransportKey, ...]] = ("n1", "w1", "w2", "w3", "w4", "w5")
SCAN_TERMS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
TICK_MS: Final = 100
PROBE_DELAY_S: Final = 1.0
PRESET_SAVE_S: Final = 3.0
RECEIVE_EXPIRY_S: Final = 0.5

MOTORS: Final = {
    "head": (0x24, 0x25),
    "feet": (0x26, 0x27),
    "head_feet": (0x29, 0x2A),
}
FLAT: Final = 0x31
PRESETS: Final = {
    "tv": (0x58, 0x64),
    "anti_snore": (0x46, 0x69),
    "zero_g": (0x45, 0x66),
    "memory_1": (0x2E, 0x2B),
    "lounge": (0x59, 0x65),
    "memory_2": (0x2F, 0x2C),
}
WAVE_MASSAGE: Final = {
    "Head massage intensity up": 0x4C,
    "Foot massage intensity up": 0x4E,
    "Next massage pattern": 0x48,
    "Massage off": 0x5E,
}
MASSAGE_TIMERS: Final = {10: 0x5F, 20: 0x63, 30: 0x61}
LIGHT_TOGGLE: Final = 0x50
LIGHT_TIMERS: Final = {"Always On": 0, "5 min": 300, "10 min": 600, "15 min": 900}

EXIT_MODE: Final = ("deviceFunctionItemExitLimit", 0)
PROBES: Final = (
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
    ("deviceFunctionItemCheckMusic", 1),
)


@dataclass(frozen=True, slots=True)
class Product:
    name: str
    wave: bool = False
    split_head: bool = False
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def preset_names(self) -> tuple[str, ...]:
        return tuple(PRESETS) if self.wave else ("tv", "anti_snore", "zero_g", "memory_1")


PRODUCTS: Final = {
    "HARN": Product("ELEVATE 2.0"),
    "HERN": Product("ELEVATE 2.0 SH", split_head=True),
    "HDRN": Product("WAVE", wave=True),
    "JERN": Product("WAVE SH", wave=True, split_head=True),
}
PRODUCT_CHOICES: Final = {code: f"{model.name} ({code})" for code, model in PRODUCTS.items()}
