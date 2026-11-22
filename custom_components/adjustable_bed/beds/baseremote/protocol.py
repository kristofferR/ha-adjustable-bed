"""Base Remote's direct settings, using the shared Richmat codec."""

from typing import Final

from ...codec import richmat as codec
from ..richmat_classic.rise import ALARM_COMBINATIONS, MASSAGE_CODES

ALARM_ACTIONS: Final = {
    0x45: "zero_g",
    0x6B: "zero_g_2",
    0x46: "anti_snore",
    0x58: "tv",
    0x59: "lounge",
    0x2E: "memory_1",
    0x2F: "memory_2",
    0x30: "memory_3",
    0xF6: "sleep_aid",
    0xB0: "wake_mode_1",
    0xB1: "wake_mode_2",
    0x5D: "massage",
    0x4C: "head_massage",
    0x4E: "foot_massage",
}


def alarm_code(available: tuple[int, ...], action: str, zone: str | None = None) -> int:
    """The first selected bed action and the source's massage combination table."""
    selected = next((code for code in available if ALARM_ACTIONS[code] == action), None)
    if selected is None:
        raise ValueError("The layout does not offer this wake action")
    if zone is None:
        return selected
    massage = {"both": 0x5D, "head": 0x4C, "feet": 0x4E}[zone]
    if massage not in available and not (massage == 0x5D and {0x4C, 0x4E} <= set(available)):
        raise ValueError("The layout does not offer this alarm massage zone")
    if selected in MASSAGE_CODES:
        return massage
    return ALARM_COMBINATIONS[selected][MASSAGE_CODES.index(massage)]


def light_timeout(seconds: int) -> bytes:
    """Zero means keep on, encoded as ffff on the slider path."""
    if type(seconds) is not int or not 0 <= seconds <= 300:
        raise ValueError("Light timeout must be 0 to 300 seconds")
    value = seconds or 65535
    return codec.light_timer(value >> 8, value)
