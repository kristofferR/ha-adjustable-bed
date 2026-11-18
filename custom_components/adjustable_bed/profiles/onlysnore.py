"""Snore Monitor 2.3.8 (202), no hardware confirmation.

Hand-transcribed app catalog from the accepted immutable report. No generator.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import onlysnore as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities

KEYS: Final = {
    "head_up": 1,
    "head_down": 2,
    "foot_up": 4,
    "foot_down": 8,
    "headrest_up": 16,
    "headrest_down": 32,
    "lumbar_up": 64,
    "lumbar_down": 128,
    "hips_up": 0x40000000,
    "hips_down": 0x80000000,
    "flat": 0x08000000,
    "reading": 0x2000,
    "tv": 0x4000,
    "zero_gravity": 0x1000,
    "anti_snore_preset": 0x8000,
    "memory_1": 0x10000,
    "memory_2": 0x40000,
    "massage_all": 0x100,
    "massage_stop_all": 0x02000000,
    "massage_wave_next": 0x10000000,
    "massage_timer_next": 0x200,
    "massage_foot_strength_next": 0x400,
    "massage_head_strength_next": 0x800,
    "light": 0x20000,
    "stop": 0,
}
PRESETS: Final = ("reading", "tv", "zero_gravity", "anti_snore_preset", "memory_1", "memory_2")
AXES: Final = {
    "back": "head",
    "legs": "foot",
    "lumbar": "lumbar",
    "head": "headrest",
    "hips": "hips",
}
MODELS: Final = (
    "unKnow",
    "single",
    "double",
    "meise",
    "dormimundo",
    "singleOnlySound",
    "noBreathheart",
)
INTERVENTION_LEVELS: Final = (1, 3, 6)


def advertisement(name: str, manufacturer_data: dict[int, bytes], address: str) -> str | None:
    """The app's BED scan predicate, separate from its model getter."""
    if not name.upper().startswith("SLEEP_V") or 89 not in manufacturer_data:
        return None
    mac, model = codec.manufacturer(manufacturer_data[89])
    if mac != address.replace(":", "").lower() or model == "wifi":
        return None
    return model


@dataclass(frozen=True, slots=True)
class OnlySnoreProfile:
    key: str = "onlysnore"
    refresh_ms: int = 150
    release_ms: int = 100
    save_ms: int = 5500
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def frames(self) -> dict[str, bytes]:
        frames = {key: codec.control(word) for key, word in KEYS.items()}
        frames.update(
            {f"{key}_program": codec.control(KEYS[key], save=True) for key in (*PRESETS, "stop")}
        )
        return frames


PROFILE: Final = OnlySnoreProfile()
