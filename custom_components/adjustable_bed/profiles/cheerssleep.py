"""CheersSleep v2.7.0/code40: all 36 accepted catalog keys remain distinct."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..beds.cheerssleep.catalog import MODELS as MODELS
from ..beds.cheerssleep.catalog import Model as Model
from ..beds.cheerssleep.catalog import advertisement as advertisement
from ..codec import cheerssleep as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class CheersSleepProfile:
    key: codec.Format
    execution: ExecutionCapabilities
    refresh_ms: int = 100
    release_ms: int = 0

    @property
    def frames(self) -> dict[str, bytes]:
        if self.key == "p1":
            return {"head_up": codec.p1(2, 1, 257), "stop": codec.p1(3, 1, 256)}
        return {"head_up": codec.normal(1), "stop": codec.normal(0), "query": codec.query()}


PROFILES: Final = {
    "p1": CheersSleepProfile("p1", ExecutionCapabilities(hold="latched"), release_ms=120),
    "p2": CheersSleepProfile("p2", STREAM_HOLD),
}


# (up, down, release). The split foot is intentionally shared.
P1_AXES: Final = {
    "all": (0x110, 0x111, 1),
    "back": (0x101, 0x102, 0x100),
    "legs": (0x105, 0x106, 0x104),
    "lumbar": (0x109, 0x10A, 0x108),
}
P1_SPLIT: Final = {
    1: {
        "all": (0x6444, 0x6445, 0x6443),
        "back": (0x6401, 0x6402, 0x6400),
        "lumbar": (0x6407, 0x6408, 0x6406),
        "legs": (0x640D, 0x640E, 0x640C),
    },
    2: {
        "all": (0x6456, 0x6457, 0x6455),
        "back": (0x6404, 0x6405, 0x6403),
        "lumbar": (0x640A, 0x640B, 0x6409),
        "legs": (0x640D, 0x640E, 0x640C),
    },
}
P2_AXES: Final = {
    "back": (1, 2),
    "legs": (4, 8),
    "lumbar": (16, 32),
    "lift_head": (64, 128),
    "lift_foot": (256, 512),
    "lift": (320, 640),
}
PRESETS: Final = {"anti_snore": (0x301, 0x8000), "tv": (0x302, 0x4000), "zero_g": (0x303, 0x1000)}
SONIC: Final = {
    "sonic_back": 0x303,
    "sonic_foot": 0xC03,
    "sonic_toggle": 0x3C,
    "sonic_mode_1": 0xCC,
    "sonic_mode_2": 0x30C,
    "sonic_switch": 0xC0C,
}
AXIS_LABELS: Final = {
    "back": "back",
    "legs": "legs",
    "lumbar": "lumbar",
    "head": "head",
    "all": "cheerssleep_all",
    "lift_head": "cheerssleep_lift_head",
    "lift_foot": "cheerssleep_lift_foot",
    "lift": "cheerssleep_lift",
}

# Level0 is off. Wave intensities have no zero member and retain the right-head typo.
P1_STEADY: Final = {
    0: {"head": (0x123, 0x201, 0x202, 0x203), "foot": (0x124, 0x204, 0x205, 0x206)},
    1: {"head": (0x123, 0x201, 0x202, 0x203), "foot": (0x124, 0x204, 0x205, 0x206)},
    2: {"head": (0x133, 0x207, 0x208, 0x209), "foot": (0x134, 0x20A, 0x20B, 0x20C)},
}
P1_WAVE: Final = {
    0: {"head": (0x220, 0x221, 0x222), "foot": (0x228, 0x229, 0x22A)},
    1: {"head": (0x220, 0x221, 0x222), "foot": (0x228, 0x229, 0x22A)},
    2: {"head": (0x240, 0x2401, 0x242), "foot": (0x248, 0x249, 0x24A)},
}
P1_WAVE_MODE: Final = {0: (0x200, 0x230, 0x231), 1: (0x233, 0x230, 0x231), 2: (0x253, 0x250, 0x251)}
P2_MASSAGE: Final = {"head": 0x200000, "foot": 0x400000, "mode": 0x10000000}
P1_SETTINGS: Final = {"delay": 0x1101, "out_of_bed_setting": 0x1102, "snore_setting": 0x1103}
RGB_PREVIEW_MS: Final = {"rgb_preview": 200, "rgb2_preview": 150}
RGB_SAVE_MS: Final = 500
MAC_QUERY_ATTEMPTS: Final = 20
MAC_QUERY_INTERVAL_MS: Final = 120
YB_SPEEDS: Final = (0x201, 0x202, 0x203)
YB_TIMERS: Final = (300, 900)
