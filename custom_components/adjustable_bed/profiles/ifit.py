"""iFit 1.1 (3), fixed 36_33_03A controls over the proven Okin 5A carrier.

Hand-maintained from the accepted bounded app report, not generated. Discovery
normalization is unresolved; none of the other 5A apps' name rules apply here.
"""

from dataclasses import dataclass
from typing import Final

from ..codec.okin_5a import ALTERNATE, WAKE, command
from ..execution import ExecutionCapabilities
from .okin_5a import Action, Okin5AProfile, Tap


@dataclass(frozen=True, kw_only=True)
class IfitProfile(Okin5AProfile):
    refresh_ms: dict[Action, int]
    save_actions: dict[Action, Action]
    save_threshold_ms: int = 3000
    flat_threshold_ms: int = 3000
    light_position_threshold_ms: int = 3000
    light_massage_threshold_ms: int = 1000
    voice_tick_ms: int = 250
    voice_repeats: int = 3


# fmt: off
_KEYS: Final[dict[Action, int]] = {
    "head_up": 0x00, "head_down": 0x01, "feet_up": 0x02, "feet_down": 0x03,
    "legs_up": 0x04, "legs_down": 0x05, "stop": 0x0F,
    "flat": 0x10, "zero_g": 0x13, "inverse": 0x14, "anti_snore": 0x16,
    "lounge": 0x17, "incline": 0x18, "stretch": 0x19,
    "save_zero_g": 0x23, "save_anti_snore": 0x26, "save_lounge": 0x27, "save_incline": 0x28,
    "massage_wave_1": 0x52, "massage_wave_2": 0x53, "massage_wave_3": 0x54,
    "massage_head_up": 0x60, "massage_head_down": 0x61,
    "massage_foot_up": 0x62, "massage_foot_down": 0x63, "massage_off": 0x6F,
    "light_toggle": 0x70, "light_on": 0x73, "light_off": 0x74,
}
_MAX_KEYS: Final[dict[Action, int]] = {
    "head_up_max": 0x00, "head_down_max": 0x01,
    "feet_up_max": 0x02, "feet_down_max": 0x03,
    "legs_up_max": 0x04, "legs_down_max": 0x05,
}
_REFRESH: Final[dict[Action, int]] = {
    "head_up": 220, "head_down": 220, "feet_up": 220, "feet_down": 220,
    "legs_up": 220, "legs_down": 220,
    "flat": 250, "light_toggle": 250,
    "zero_g": 100, "anti_snore": 100, "lounge": 100, "incline": 100,
    "inverse": 100, "stretch": 100,
    "massage_head_up": 1000, "massage_head_down": 1000,
    "massage_foot_up": 1000, "massage_foot_down": 1000,
    "massage_wave_1": 1000, "massage_wave_2": 1000, "massage_wave_3": 1000,
    "massage_off": 1000,
}
# fmt: on
_FRAMES: Final[dict[Action, bytes]] = {a: command(k) for a, k in _KEYS.items()}
_FRAMES.update({a: command(k, ALTERNATE) for a, k in _MAX_KEYS.items()})
IFIT: Final = IfitProfile(
    key="ifit",
    transport="nus",
    write_with_response=True,
    wake=(WAKE,),
    wake_with_response=False,
    frames=_FRAMES,
    recall=Tap(repeats=3, repeat_ms=250),
    stop=Tap(repeats=3, repeat_ms=250),
    refresh_ms=_REFRESH,
    save_actions={
        "zero_g": "save_zero_g",
        "anti_snore": "save_anti_snore",
        "lounge": "save_lounge",
        "incline": "save_incline",
    },
    execution=ExecutionCapabilities(
        hold="stream", hold_controls=frozenset(_REFRESH) | {"light_position", "light_massage"}
    ),
)
PRESETS: Final[tuple[Action, ...]] = (
    "flat",
    "zero_g",
    "anti_snore",
    "lounge",
    "incline",
    "inverse",
    "stretch",
)
MOTORS: Final = ("head", "feet", "legs")
