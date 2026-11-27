"""Comfort Bed 1.0.2 (10200), current productComfortCareBed, enum86 only.

Other persisted ordinals and shared optional pages are deliberately absent.
The accepted literal vectors prove this profile uses codec/richmat.py.
"""

from typing import Final

from ..execution import STREAM_HOLD
from .richmat import RichmatProfile

SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
TICK_S: Final = 0.1
MENU_DELAY_S: Final = 1.0
LONG_PRESS_MS: Final = 3000
RX_TIMEOUT_S: Final = 0.5
QUERIES: Final = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
)
PROFILE: Final = RichmatProfile(
    key="comfort_bed",
    execution=STREAM_HOLD,
    transports=("n1", "w1", "w2", "w3", "w4", "w5"),
    codes={
        "head_up": 0x24,
        "head_down": 0x25,
        "feet_up": 0x26,
        "feet_down": 0x27,
        "head_feet_up": 0x29,
        "head_feet_down": 0x2A,
        "flat": 0x31,
        "sync_on": 0xBC,
        "light_toggle": 0x3C,
        "tv": 0x58,
        "anti_snore": 0x46,
        "zero_g": 0x45,
        "lounge": 0x59,
        "save_anti_snore": 0x69,
        "save_zero_g": 0x66,
        "save_lounge": 0x65,
        "massage_head_up": 0x4C,
        "massage_foot_up": 0x4E,
        "massage_mode": 0x48,
        "massage_off": 0x5E,
        "massage_timer_10": 0x5F,
        "massage_timer_20": 0x63,
        "massage_timer_30": 0x61,
    },
    memory=((0x2E, 0x2B), (0x2F, 0x2C)),
    stop=0x6E,
    motor_repeat_ms=100,
)
# App save controls are single taps, even though they choose the long opcode.
SAVES: Final = {"tv": 0x64, "anti_snore": 0x69, "zero_g": 0x66, "lounge": 0x65}
# A real 3s text gesture sends these once; zero is NOT the movement release.
TEXT_LONG: Final = {"reset": 0, "sync": 0xBC, "timer_10": 0, "timer_20": 0, "timer_30": 0}
