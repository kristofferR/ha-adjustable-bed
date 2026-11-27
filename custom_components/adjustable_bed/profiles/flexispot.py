"""Flexispot com.loctek.flexispotpro 1.1 (2), explicitly selected layouts."""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD, ExecutionCapabilities

NAME: Final = "W_LeGe"
REFRESH_MS: Final = 200
RELEASE_MS: Final = 100
SAVE_HOLD_MS: Final = 5000
MASSAGE_STEP_MS: Final = 200
MODES: Final = ("general", "continuous", "pulse", "wave")


@dataclass(frozen=True, slots=True)
class FlexispotProfile:
    key: str
    label: str
    motors: tuple[tuple[str, int], ...]
    memories: tuple[tuple[str, int], ...]
    light: bool
    split: bool = False
    execution: ExecutionCapabilities = STREAM_HOLD


PROFILES: Final = {
    "eb632": FlexispotProfile(
        "eb632",
        "EB632MF-8060-02",
        (("back", 1), ("feet", 2)),
        (("memory_1", 1), ("memory_2", 3), ("memory_3", 2), ("sleep", 4)),
        True,
    ),
    "eb703": FlexispotProfile(
        "eb703",
        "EB703M-8060-02",
        (("back", 1), ("feet", 2), ("lumbar", 4)),
        (("tv", 2), ("sleep", 4)),
        False,
    ),
    "eb704": FlexispotProfile(
        "eb704",
        "EB704M-8060-02",
        (("back", 1), ("feet", 2), ("head", 3), ("lumbar", 4)),
        (("tv", 2), ("sleep", 4)),
        True,
    ),
    "eb803": FlexispotProfile(
        "eb803",
        "EB803M-8060",
        (("left_back", 1), ("feet", 2), ("right_back", 3)),
        (("memory", 3), ("tv", 2)),
        True,
        True,
    ),
}
