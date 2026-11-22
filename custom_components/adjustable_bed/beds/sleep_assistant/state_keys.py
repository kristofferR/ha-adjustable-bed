"""Bed observations, scoped to the current BLE session."""

from typing import Final

from ...controller_state import StateKey

STORAGE: Final = StateKey[bool | None]("sleep_assistant_storage")
PALETTE: Final = StateKey[str | None]("sleep_assistant_palette")
ANTI_SNORE: Final = StateKey[str | None]("sleep_assistant_anti_snore")
ONE_BUTTON: Final = StateKey[bool | None]("sleep_assistant_one_button")
MASSAGE: Final = StateKey[bool | None]("sleep_assistant_massage")
ALARMS: Final = tuple(StateKey[str | None](f"sleep_assistant_alarm_{i}") for i in range(1, 7))
OCCUPIED: Final = {
    side: StateKey[bool | None](f"sleep_assistant_occupied_{side}") for side in ("left", "right")
}
HEART: Final = {
    side: StateKey[int | None](f"sleep_assistant_heart_{side}") for side in ("left", "right")
}
BREATH: Final = {
    side: StateKey[int | None](f"sleep_assistant_breath_{side}") for side in ("left", "right")
}
MOVEMENT: Final = {
    side: StateKey[bool | None](f"sleep_assistant_movement_{side}") for side in ("left", "right")
}

FLAT_MINUTES: Final = StateKey[int | None]("sleep_assistant_flat_minutes")

CAPABILITY_REVISION: Final = StateKey[int]("sleep_assistant_capability_revision")
