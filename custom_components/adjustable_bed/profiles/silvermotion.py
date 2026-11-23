"""SILVERmotion Android 1.0.0 controls and caller timing."""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD, ExecutionCapabilities

SIZES: Final = {"queen": "Queen", "king": "King", "twin_xl": "Twin XL"}


@dataclass(frozen=True)
class SilvermotionProfile:
    key: str = "android"
    execution: ExecutionCapabilities = STREAM_HOLD
    refresh_ms: int = 150
    chunk_ms: int = 10
    response_ms: int = 1000
    recall_gap_ms: int = 50
    movement_ceiling_ms: int = 30000
    delay: int = 30


ANDROID: Final = SilvermotionProfile()
# UI names retain the app's Form Two/Three ordering, not analytics numbering.
COMMANDS: Final = {
    "back_up": bytes.fromhex("510000"),
    "back_down": bytes.fromhex("520000"),
    "legs_up": bytes.fromhex("510100"),
    "legs_down": bytes.fromhex("520100"),
    "flat": bytes.fromhex("5c0400"),
    "memory_1": bytes.fromhex("5c0000"),
    "memory_2": bytes.fromhex("5c0100"),
    "save_memory_1": bytes.fromhex("5b0000"),
    "save_memory_2": bytes.fromhex("5b0100"),
    "massage_up": bytes.fromhex("810000"),
    "massage_down": bytes.fromhex("820000"),
    "massage_form_one": bytes.fromhex("8d0000"),
    "massage_form_two": bytes.fromhex("8d0200"),
    "massage_form_three": bytes.fromhex("8d0100"),
    "massage_off": bytes.fromhex("860000"),
    "light_toggle": bytes.fromhex("95000f"),
    "light_off": bytes.fromhex("950000"),
    "anti_snore": bytes.fromhex("5f0f001f05"),
    "zero_g": bytes.fromhex("5f0f00274f"),
    "leg_up": bytes.fromhex("5f0f000538"),
    "lounge": bytes.fromhex("5f0f00692e"),
    "breakfast": bytes.fromhex("5f0f007d05"),
    "flat_reset": bytes.fromhex("080200"),
    "factory_reset": bytes.fromhex("080100"),
    "release": bytes.fromhex("b00001"),
    "any_key": bytes.fromhex("b00000"),
}
MOVEMENTS: Final = frozenset(("back_up", "back_down", "legs_up", "legs_down"))
PRESETS: Final = ("flat", "anti_snore", "zero_g", "leg_up", "lounge", "breakfast")
LABELS: Final = {
    "leg_up": "Leg up position",
    "breakfast": "Breakfast position",
    "massage_form_one": "Massage Form One",
    "massage_form_two": "Massage Form Two",
    "massage_form_three": "Massage Form Three",
    "light_off": "Under-bed light off",
    "flat_reset": "Flat realignment reset",
    "factory_reset": "Factory default reset",
}


def repeat_count(action: str) -> int:
    return 10 if action in MOVEMENTS else 3
