"""BedTech 7.1.3 sleeper routing, independent of its shared wire builder."""

from ...const import SIDE_BOTH, SIDE_LEFT, SIDE_RIGHT
from ...profiles.richmat import Button


def app_side(model: str, sleeper: int, action: str) -> str:
    """Resolve app selectors 1..5 to HA sides (Hermes relayCommand #4377)."""
    if sleeper not in range(1, 6):
        raise ValueError("BedTech sleeper must be 1..5")
    if model.endswith("fh"):
        # All FH actions use one receiver. 1/2 are unchanged methods, like 4.
        return {3: SIDE_BOTH, 5: SIDE_RIGHT}.get(sleeper, SIDE_LEFT)
    if sleeper == 3 or (sleeper in (4, 5) and ("foot" in action or action == "stop")):
        return SIDE_BOTH
    return SIDE_LEFT if sleeper in (1, 4) else SIDE_RIGHT


APP_ACTIONS: dict[str, Button] = {
    "headUp": "head_up",
    "headDown": "head_down",
    "footUp": "feet_up",
    "footDown": "feet_down",
    "pillowUp": "pillow_up",
    "pillowDown": "pillow_down",
    "lumbarUp": "lumbar_up",
    "lumbarDown": "lumbar_down",
    "presetFlat": "flat",
    "presetZeroG": "zero_g",
    "presetAntiSnore": "anti_snore",
    "presetTV": "tv",
    "lightToggle": "light_toggle",
    "massageOn": "massage_toggle",
    "massageOff": "massage_off",
    "headMassageUp": "massage_head",
    "footMassageUp": "massage_foot",
    "massageMode": "massage_mode",
    "massageTimer20": "massage_timer_20",
}
APP_ACTION_CHOICES = (
    *APP_ACTIONS,
    "memory1",
    "memory1Save",
    "memory2",
    "memory2Save",
    "stop",
    "connectionTest",
)
