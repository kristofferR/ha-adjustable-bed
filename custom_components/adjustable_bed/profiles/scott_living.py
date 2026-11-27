"""Scott Living 1.0.2 (25): explicit A/B/C layouts, no inferred memory slots."""

from typing import Final

from ..execution import STREAM_HOLD
from .keeson import AppAction, AppProfile

LAYOUTS: Final = {"A": "A, 8 buttons", "B": "B, 13 buttons", "C": "C, 17 buttons"}
REFRESH_MS: Final = 100
_BASIC: Final = (
    AppAction("head_up", "Back up", 1, "held"),
    AppAction("head_down", "Back down", 2, "held"),
    AppAction("foot_up", "Legs up", 4, "held"),
    AppAction("foot_down", "Legs down", 8, "held"),
    AppAction("flat", "Flat", 0x08000000, "single"),
    AppAction("zero_g", "Zero G", 0x1000, "single"),
    AppAction("read", "Reading", 0x2000, "single"),
    AppAction("tv", "TV", 0x4000, "single"),
)
_MASSAGE: Final = (
    AppAction("anti_snore", "Anti-snore", 0x8000, "single"),
    AppAction("light", "Light", 0x20000, "single"),
    AppAction("head_massage", "Head massage", 0x800, "single"),
    AppAction("foot_massage", "Foot massage", 0x400, "single"),
    AppAction("massage_timer", "Massage timer", 0x200, "single"),
)
_EXTRA: Final = (
    AppAction("tilt_up", "Head tilt up", 16, "held"),
    AppAction("tilt_down", "Head tilt down", 32, "held"),
    AppAction("m_button", "M button", 0x40000000, "single"),
    AppAction("star_button", "Star button", 0x10000, "single"),
)


def profile(layout: str = "A") -> AppProfile:
    """Only the user's saved selection determines the layout."""
    if layout not in LAYOUTS:
        raise ValueError("Choose Scott Living layout A, B or C")
    return AppProfile(
        key="scott_living",
        app="Scott Living",
        layout=layout,
        execution=STREAM_HOLD,
        actions=_BASIC + (_MASSAGE if layout != "A" else ()) + (_EXTRA if layout == "C" else ()),
        alarm=None,
        rename_units=0,
        clock=False,
    )
