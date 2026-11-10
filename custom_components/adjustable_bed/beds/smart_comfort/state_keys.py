"""Smart Comfort state: device replies are group-scoped, not seat telemetry."""

from typing import Final

from ...controller_state import StateKey

SEAT: Final = StateKey[str | None]("smart_comfort_seat")
MODEL: Final = StateKey[int | None]("smart_comfort_model")
READ_ON: Final = StateKey[bool | None]("smart_comfort_read_on")
CUP_ON: Final = StateKey[bool | None]("smart_comfort_cup_on")
READ_BRIGHTNESS: Final = StateKey[int | None]("smart_comfort_read_brightness")
COUNTER_1: Final = StateKey[int | None]("smart_comfort_counter_1")
COUNTER_2: Final = StateKey[int | None]("smart_comfort_counter_2")
COUNTER_3: Final = StateKey[int | None]("smart_comfort_counter_3")
