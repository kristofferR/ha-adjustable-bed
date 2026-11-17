"""Only app-consumed bed state. Sleep fields retain unproven raw units."""

from typing import Final

from ...controller_state import StateKey

MODEL: Final = StateKey[int]("cheerssleep_model")
SIDE: Final = StateKey[str | None]("cheerssleep_side")
HEAD: Final = StateKey[int | None]("cheerssleep_head_massage")
FOOT: Final = StateKey[int | None]("cheerssleep_foot_massage")
MODE: Final = StateKey[int | None]("cheerssleep_massage_mode")
SONIC_LEVEL: Final = StateKey[int | None]("cheerssleep_sonic_level")
SONIC_MODE: Final = StateKey[bool | None]("cheerssleep_sonic_mode")
BRIGHTNESS: Final = StateKey[int | None]("cheerssleep_brightness")
MAC: Final = StateKey[str | None]("cheerssleep_sleep_mac")
SLEEP_FIELDS: Final = (
    "snore",
    "on_bed",
    "asleep",
    "heart",
    "breath",
    "gatem",
    "gateo",
    "snore_count",
    "snore_power",
)
SLEEP_KEYS: Final = {
    side: {name: StateKey[int | bool | None](f"cheerssleep_{side}_{name}") for name in SLEEP_FIELDS}
    for side in ("left", "right")
}
POSITION_LIGHT: Final = StateKey[bool | None]("cheerssleep_position_light")
COLOR_LIGHT: Final = StateKey[bool | None]("cheerssleep_color_light")
