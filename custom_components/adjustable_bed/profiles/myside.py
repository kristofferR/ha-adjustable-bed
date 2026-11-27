"""My Side 1.0.6's four normal-picker products over the Richmat codec.

The related sensor protocol and persisted/other products are not established.
The transport does not identify the app or product.
"""

from dataclasses import dataclass
from typing import Final

from ..execution import ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class MySideProfile:
    ordinal: int
    label: str
    coaxing: bool
    sleep: bool
    tick_ms: int = 100
    startup_ms: int = 1000
    long_ms: int = 3000
    execution: ExecutionCapabilities = ExecutionCapabilities(
        hold="stream",
        hold_controls=frozenset(
            {
                "head_up",
                "head_down",
                "foot_up",
                "foot_down",
                "head_and_foot_up",
                "head_and_foot_down",
            }
        ),
    )

    @property
    def memories(self) -> int:
        return 3 if self.coaxing else 2


PROFILES: Final = {
    "76": MySideProfile(76, "Deep Relax Smart", False, False),
    "77": MySideProfile(77, "Deep Relax Smart with Sleep", False, True),
    "78": MySideProfile(78, "Deep Relax Smart with Coaxing", True, False),
    "79": MySideProfile(79, "Deep Relax Smart with Coaxing and Sleep", True, True),
}
CHOICES: Final = {key: profile.label for key, profile in PROFILES.items()}
TRANSPORTS: Final = ("n1", "w1", "w2", "w3", "w4", "w5")
SCAN_WORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
MOTORS: Final = {
    "head_up": 0x24,
    "head_down": 0x25,
    "foot_up": 0x26,
    "foot_down": 0x27,
    "head_and_foot_up": 0x29,
    "head_and_foot_down": 0x2A,
}
PRESETS: Final = {
    "flat": (0x31, None),
    "anti_snoring": (0x46, 0x69),
    "zero_gravity": (0x45, 0x66),
    "tv_position": (0x58, 0x64),
    "memory1": (0x2E, 0x2B),
    "memory2": (0x2F, 0x2C),
    "memory3": (0x30, 0x2D),
    "coaxing_mode": (0x86, None),
}
MASSAGE: Final = {
    "massage_head_strengthen": 0x4C,
    "massage_foot_strengthen": 0x4E,
    "massage_mode_change": 0x48,
    "massage_all_off": 0x5E,
    "massage_timer10": 0x5F,
    "massage_timer20": 0x63,
    "massage_timer30": 0x61,
}
ALARM_MODES: Final = (
    "anti_snoring",
    "zero_gravity",
    "tv_position",
    "memory1",
    "memory2",
    "memory3",
)


def presets(profile: MySideProfile) -> tuple[str, ...]:
    return tuple(PRESETS) if profile.coaxing else ("flat", "memory1", "memory2")


def scan_matches(name: str | None) -> bool:
    return name is not None and any(word in name for word in SCAN_WORDS)
