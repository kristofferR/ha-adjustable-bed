"""GhostBed 1.3 (4), fixed current screen, independent of Flexispot products."""

from typing import Final

from .flexispot import FlexispotProfile

PROFILE: Final = FlexispotProfile(
    "ghostbed",
    "GhostBed",
    (("back", 1), ("feet", 2)),
    (("memory_1", 1), ("memory_2", 3), ("memory_3", 2), ("sleep", 4)),
    True,
)
NAMES: Final = ("W_LeGe", "GhostBed")
REFRESH_MS: Final = 200
RELEASE_MS: Final = 100
MASSAGE_STEP_MS: Final = 200
SAVE_HOLD_MS: Final = 3000
ALARM_DELETE_GAP_MS: Final = 200
MODES: Final = ("basic", "cycle", "pulse", "wave")
SENSITIVITIES: Final = ("low", "medium", "high")
ANGLES: Final = ("8", "12", "15")
TIMER_OPTIONS: Final = tuple(range(61))
