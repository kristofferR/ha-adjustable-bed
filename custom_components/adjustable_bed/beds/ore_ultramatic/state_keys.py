"""Connection-owned reported state for the dual-route ORE apps."""

from typing import Final

from ...controller_state import StateKey

# "HH:MM" when the reported hour and minute are a valid time of day.
TIME: Final = StateKey[str | None]("ore_ultramatic_alarm_time")
# Signed repeat byte and the app's raw action value; exposed as alarm attributes.
REPEAT: Final = StateKey[int | None]("ore_ultramatic_alarm_repeat")
ACTION: Final = StateKey[int | None]("ore_ultramatic_alarm_action")
# Raw massage timer value; its units are unproven, so it is an attribute.
TIMER: Final = StateKey[int | None]("ore_ultramatic_massage_timer")
INTENSITY: Final = StateKey[int | None]("ore_ultramatic_massage_intensity")
ALL: Final = (TIME, REPEAT, ACTION, TIMER, INTENSITY)
ALARM_ENABLED: Final = StateKey[bool | None]("alarm_enabled")
REPORTED_MASSAGE_TIMER_MINUTES: Final = StateKey[int | None]("reported_massage_timer_minutes")
