"""Purely Sleep 2.0.1: accepted normal JLRN and VJRM routes only.

E49-E58 resolve the actual getters and selected normal widgets. Version-one
lists, other products and extended features are intentionally not profiles.
"""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD
from .richmat import Button, RichmatProfile


@dataclass(frozen=True, kw_only=True)
class PurelyProfile(RichmatProfile):
    label: str
    saves: tuple[tuple[str, str, int], ...] = ()


MOTORS: Final[dict[Button, int]] = {
    "head_up": 0x24,
    "head_down": 0x25,
    "feet_up": 0x26,
    "feet_down": 0x27,
    "flat": 0x31,
}
PROFILES: Final = {
    "JLRN": PurelyProfile(
        key="purely_sleep:JLRN",
        label="NXPS200 (JLRN), normal mode",
        execution=STREAM_HOLD,
        transports=("n1", "w1", "w2", "w3", "w4", "w5"),
        codes={
            **MOTORS,
            "head_feet_up": 0x29,
            "head_feet_down": 0x2A,
            "tv": 0x58,
            "anti_snore": 0x46,
            "lounge": 0x59,
            "zero_g": 0x45,
        },
        saves=(
            ("tv", "TV", 0x64),
            ("anti_snore", "Anti-snore", 0x69),
            ("lounge", "Lounge", 0x65),
            ("zero_g", "Zero gravity", 0x66),
        ),
        memory=((0x2E, 0x2B),),
        motor_repeat_ms=100,
    ),
    "VJRM": PurelyProfile(
        key="purely_sleep:VJRM",
        label="PS200 (VJRM), normal mode",
        execution=STREAM_HOLD,
        transports=("n1", "w1", "w2", "w3", "w4", "w5"),
        codes=MOTORS,
        memory=((0x2E, 0x2B),),
        motor_repeat_ms=100,
    ),
}
PRODUCT_CHOICES: Final = {code: profile.label for code, profile in PROFILES.items()}
# In-scope part of E24/O02's startup. Aroma/speech are companions; mattress,
# lumbar-mattress and detection selection/parsing remain statically deferred.
INITIALIZATION: Final = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
    ("deviceFunctionItemCheckSnore", 0),
    ("deviceFunctionItemQueryVersion", 0),
)
