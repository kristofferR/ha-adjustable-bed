"""Only app-consumed bed state. Sleep fields retain unproven raw units."""

from typing import Final, Literal

from ...controller_state import StateKey

HEAD: Final = StateKey[int | None]("cheerssleep_head_massage")
FOOT: Final = StateKey[int | None]("cheerssleep_foot_massage")
MODE: Final = StateKey[int | None]("cheerssleep_massage_mode")
SONIC_LEVEL: Final = StateKey[int | None]("cheerssleep_sonic_level")
# Snore flags and the gatem/gateo fields have no proven meaning, so they stay unexposed.
SLEEP_FIELDS: Final = ("on_bed", "asleep", "heart", "breath", "snore_count", "snore_power")
SIDES: Final[tuple[Literal["left", "right"], ...]] = ("left", "right")
SLEEP_KEYS: Final[dict[str, dict[str, StateKey[int | bool | None]]]] = {
    side: {name: StateKey[int | bool | None](f"cheerssleep_{side}_{name}") for name in SLEEP_FIELDS}
    for side in SIDES
}
