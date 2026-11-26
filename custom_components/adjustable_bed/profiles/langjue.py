"""Local P1 selections from the Comfort Smart Bed app."""

from typing import Final, Literal

SERVICE: Final = "5a020001-c591-e131-0eb8-a30e24fe1275"
PRESETS_ONLY: Final = "presets_only"
HEAD_FOOT: Final = "head_foot"
HANDSHAKE_DELAY_MS: Final = 1000
MOTOR_REFRESH_MS: Final = 500
DIRECTIONS: Final = {
    "back_up": (0, True),
    "back_down": (0, False),
    "legs_up": (1, True),
    "legs_down": (1, False),
}
PRESETS: Final = {
    "flat": 0x80,
    "relax_to_sleep": 0x20,
    "zero_g": 0x01,
    "reading": 0x02,
    "anti_snore": 0x04,
    "stretch": 0x08,
    "backrest": 0x09,
}
EXTRA_PRESETS: Final = {
    "relax_to_sleep": "Relax to Sleep",
    "stretch": "Stretch",
    "backrest": "Backrest",
}
MEMORY_MODES: Final = (0x05, 0x06, 0x07)
MASSAGE_ZONES: Final = {"head": 1, "foot": 2}
MASSAGE_PATTERNS: Final = (1, 2, 3, 4)
MASSAGE_TIMERS: Final = {10: 1, 20: 2, 30: 3}
MassageSetting = Literal["head", "foot", "timer", "pattern"]
MASSAGE_START: Final[tuple[tuple[int, MassageSetting, int], ...]] = (
    (0, "head", 1),
    (50, "timer", 10),
    (100, "pattern", 1),
    (150, "foot", 1),
)
MASSAGE_STOP: Final[tuple[tuple[int, MassageSetting, int], ...]] = ((0, "head", 0), (50, "foot", 0))
ALARM_ACTIONS: Final = {
    "flat": 3,
    "zero_g": 4,
    "reading": 5,
    "tv": 6,
    "anti_snore": 7,
    "memory_1": 8,
    "memory_2": 9,
    "memory_3": 10,
    "stretch": 11,
    "backrest": 12,
}
