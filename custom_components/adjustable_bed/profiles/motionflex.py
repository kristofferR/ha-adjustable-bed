"""MotionFlex 1.0.2's three Motion-picker products, over the Richmat codec."""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD
from .richmat import Button, RichmatProfile

TRANSPORTS: Final = ("w1", "n1", "w5", "w4", "w3", "w2")
REFRESH_MS: Final = 100
MENU_DELAY_S: Final = 0.3
LIGHT_DELAY_S: Final = 0.2
SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
COMMON: Final[dict[Button, int]] = {
    "head_up": 0x24,
    "head_down": 0x25,
    "feet_up": 0x26,
    "feet_down": 0x27,
    "flat": 0x31,
    "zero_g": 0x45,
    "anti_snore": 0x46,
    "save_zero_g": 0x66,
    "save_anti_snore": 0x69,
    "light_toggle": 0x3C,
    "light_off": 0x75,
    "massage_head": 0x4C,
    "massage_foot": 0x4E,
    "massage_mode": 0x48,
    "massage_off": 0x5E,
    "massage_timer_10": 0x5F,
    "massage_timer_20": 0x63,
    "massage_timer_30": 0x61,
}


@dataclass(frozen=True)
class Product:
    wire: RichmatProfile
    saves: tuple[tuple[str, int], ...]


def _product(key: str, motors: dict[Button, int], *, memory: bool, tv: bool = False) -> Product:
    return Product(
        RichmatProfile(
            key="motionflex_" + key,
            transports=TRANSPORTS,
            execution=STREAM_HOLD,
            motor_repeat_ms=REFRESH_MS,
            pace_from_write_start=True,
            codes={**COMMON, **motors, **({"tv": 0x58} if tv else {})},
            memory=((0x2E, 0x2B),) if memory else (),
        ),
        (("zero_g", 0x66), ("anti_snore", 0x69), *((("tv", 0x64),) if tv else ())),
    )


PRODUCTS: Final = {
    "sn300": _product(
        "sn300", {"head_feet_up": 0x29, "head_feet_down": 0x2A}, memory=True, tv=True
    ),
    "sn500": _product(
        "sn500",
        {"lumbar_up": 0x3F, "lumbar_down": 0x40, "pillow_up": 0x41, "pillow_down": 0x42},
        memory=False,
    ),
    "hc800": _product("hc800", {"lumbar_up": 0x3F, "lumbar_down": 0x40}, memory=True),
}
CHOICES: Final = {key: key.upper() for key in PRODUCTS}
