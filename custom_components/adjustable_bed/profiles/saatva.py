"""Saatva's explicitly selected model and installation over Richmat 6E."""

from typing import Final

from ..execution import STREAM_HOLD
from .richmat import Button, RichmatProfile

SERVICE_UUID: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "d44bc439-abfd-45a2-b575-925416129600"
SCAN_UUIDS: Final = (SERVICE_UUID, WRITE_UUID)
REPEAT_MS: Final = 100
TEST_SECONDS: Final = 2
CHOICES: Final = {
    "bt2000_standard": "Adjustable Base: standard",
    "bt2000_split": "Adjustable Base: split (two receivers)",
    "bt3000_standard": "Adjustable Base Plus: standard",
    "bt3000_split": "Adjustable Base Plus: split (two receivers)",
    "bt3000fh_split_top": "Adjustable Base Plus: split top (one receiver)",
}
LAYOUTS: Final = {
    key: "splitTop" if key.endswith("split_top") else key.rsplit("_", 1)[1] for key in CHOICES
}
TWO_RECEIVER_PROFILES: Final = frozenset(
    key for key, layout in LAYOUTS.items() if layout != "splitTop"
)
MOTORS: Final = frozenset((0x24, 0x25, 0x26, 0x27))
HEAD_CODES: Final = frozenset((0x24, 0x25, 0x4C, 0x4D))
_BASE: Final[dict[Button, int]] = {
    "head_up": 0x24,
    "head_down": 0x25,
    "feet_up": 0x26,
    "feet_down": 0x27,
    "flat": 0x31,
    "zero_g": 0x45,
    "anti_snore": 0x46,
}
_PLUS: Final[dict[Button, int]] = {
    "tv": 0x58,
    "massage_head_up": 0x4C,
    "massage_head_down": 0x4D,
    "massage_foot_up": 0x4E,
    "massage_foot_down": 0x4F,
    "massage_toggle": 0x5D,
    "massage_mode": 0x48,
    "massage_timer_10": 0x5F,
    "massage_timer_20": 0x63,
    "light_toggle": 0x3C,
}
PROFILES: Final = {
    key: RichmatProfile(
        key=f"saatva_{key}",
        transports=("w1",),
        execution=STREAM_HOLD,
        codes={**_BASE, **(_PLUS if key.startswith("bt3000") else {})},
        memory=((0x2E, 0x2B), (0x2F, 0x2C)),
        stop=None,
        motor_repeat_ms=REPEAT_MS,
        pace_from_write_start=True,
    )
    for key in CHOICES
}
