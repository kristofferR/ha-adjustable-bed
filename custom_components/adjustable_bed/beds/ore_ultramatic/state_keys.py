"""Connection-owned Ultramatic raw reported state, never inferred positions."""

from typing import Final

from ...controller_state import StateKey

HOUR: Final = StateKey[int | None]("ultramatic_alarm_hour")
MINUTE: Final = StateKey[int | None]("ultramatic_alarm_minute")
REPEAT: Final = StateKey[int | None]("ultramatic_alarm_repeat")
ACTION: Final = StateKey[int | None]("ultramatic_alarm_action")
TIMER: Final = StateKey[int | None]("ultramatic_massage_timer_code")
INTENSITY: Final = StateKey[int | None]("ultramatic_massage_intensity")
ALL: Final = (HOUR, MINUTE, REPEAT, ACTION, TIMER, INTENSITY)
