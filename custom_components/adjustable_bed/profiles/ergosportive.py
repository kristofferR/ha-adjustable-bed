"""Explicit ErgoSportive 2.5.5 remote subset, without inferred model gates."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..const import CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT
from ..execution import STREAM_HOLD, ExecutionCapabilities

CONF_CONTROLS: Final = "ergosportive_controls"
REFRESH_MS: Final = 100
RELEASE_MS: Final = 500
SECONDARY_MS: Final = 800
BRIGHTNESS_RELEASE_MS: Final = 200
BRIGHTNESS_MAX: Final = 13
VARIANTS: Final = {
    "remote": "Remote subset: standard release (not Hardware221)",
    "hardware221": "Remote subset: confirmed Hardware221 release",
}
SENSORS: Final = {
    "remote_only": "Remote only",
    "old_dsp_normal": "Confirmed OldDSP normal sensor stream (one sleeper)",
}
WORDS: Final = {
    "head_up": 1,
    "head_down": 2,
    "feet_up": 4,
    "feet_down": 8,
    "tilt_up": 16,
    "tilt_down": 32,
    "massage_all": 256,
    "massage_timer": 512,
    "massage_feet_up": 1024,
    "massage_head_up": 2048,
    "zero_g": 4096,
    "position_1": 8192,
    "position_2": 16384,
    "lamp": 131072,
    "massage_head_down": 8388608,
    "massage_feet_down": 16777216,
    "flat": 134217728,
}
ACTIONS: Final = {
    "massage_all": "Cycle all-zone massage",
    "massage_timer": "Cycle massage timer",
    "massage_feet_up": "Foot massage up",
    "massage_head_up": "Head massage up",
    "massage_head_down": "Head massage down",
    "massage_feet_down": "Foot massage down",
    "position_1": "Position 1 / lounge",
    "position_2": "Position 2 / TV",
    "lamp": "Toggle bedside lamp",
}
CONTROLS: Final = {
    "head": "Head movement",
    "feet": "Foot movement",
    "tilt": "Tilt movement",
    "flat": "Flat",
    "zero_g": "Zero gravity",
    **ACTIONS,
    "brightness": "Bedside lamp brightness",
}
DEFAULT_CONTROLS: Final = ("head", "feet", "flat", "zero_g")


@dataclass(frozen=True, slots=True)
class Profile:
    key: str
    controls: frozenset[str]
    old_dsp_normal: bool
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def secondary_release(self) -> bool:
        return self.key == "hardware221"


def selected(data: Mapping[str, object]) -> Profile:
    variant = data.get(CONF_PROTOCOL_VARIANT)
    sensor = data.get(CONF_PRODUCT_TYPE)
    controls = data.get(CONF_CONTROLS, DEFAULT_CONTROLS)
    if not isinstance(variant, str) or variant not in VARIANTS:
        raise ValueError(CONF_PROTOCOL_VARIANT)
    if not isinstance(sensor, str) or sensor not in SENSORS:
        raise ValueError(CONF_PRODUCT_TYPE)
    if not isinstance(controls, (list, tuple)) or any(
        not isinstance(c, str) or c not in CONTROLS for c in controls
    ):
        raise ValueError(CONF_CONTROLS)
    return Profile(variant, frozenset(controls), sensor == "old_dsp_normal")
