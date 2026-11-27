"""Explicit M3 Ambient layouts and the app's direct BLE control ranges."""

from typing import Final

from ..codec.ambient import Coordinates, Side

ONE_PIECE: Final = "one_piece"
SPLIT: Final = "split"
LAYOUTS: Final = {ONE_PIECE: "One-piece", SPLIT: "Split"}

SERVICE: Final = "6e40fffe-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e40aa02-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e40aa03-b5a3-f393-e0a9-e50e24dcca9e"

SIDES: Final = {"left": Side.LEFT, "right": Side.RIGHT}
AXIS_LIMITS: Final = {"head": 60, "feet": 24, "neck": 7}
PRESETS: Final = {
    "flat": Coordinates(0, 0, 0),
    "tv": Coordinates(41, 16, 0),
    "zero_g": Coordinates(23, 24, 0),
    "anti_snore": Coordinates(9, 0, 0),
}
HEAT_LEVEL_MAX: Final = 30
HEAT_TIMER_HOURS: Final = 2

WRITE_PACING: Final = 0.100
SAMPLE_TIMEOUT: Final = 2.0
HEAT_PROBE_INTERVAL: Final = 0.800
HEAT_PROBES: Final = 4
HEAT_TIMEOUT: Final = 5.0
HEAT_TIMER_DELAY: Final = 3.0


def picker_value(channel: int) -> int:
    """Map an HA RGB component to the app's rounded 0–120 picker value."""
    return (channel * 120 + 127) // 255


def picker_color(red: int, green: int, blue: int) -> tuple[int, int, int]:
    """Display confirmed channel bytes on HA's 0–255 color scale."""
    return (
        min(255, (red * 255 + 60) // 120),
        min(255, (green * 255 + 60) // 120),
        min(255, (blue * 255 + 60) // 120),
    )
