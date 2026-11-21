"""Superior Sleep's connection-scoped app display fields."""

from typing import Final

from ...controller_state import StateKey

TIMER: Final = StateKey[int | None]("superior_sleep_timer_minutes")
SECONDS: Final = StateKey[int | None]("superior_sleep_timer_seconds")
MODE: Final = StateKey[int | None]("superior_sleep_massage_mode")
HEAD: Final = StateKey[int | None]("superior_sleep_head_level")
FOOT: Final = StateKey[int | None]("superior_sleep_foot_level")
MOTION: Final = StateKey[bool | None]("superior_sleep_motion")
MASSAGE: Final = StateKey[bool | None]("superior_sleep_massage")
ALARM_HOUR: Final = StateKey[int | None]("superior_sleep_alarm_hour")
ALARM_MINUTE: Final = StateKey[int | None]("superior_sleep_alarm_minute")
ALARM_MASK: Final = StateKey[int | None]("superior_sleep_alarm_mask")
ALARM_SELECTOR: Final = StateKey[int | None]("superior_sleep_alarm_selector")
ALARM_DAYS: Final = StateKey[str | None]("superior_sleep_alarm_display_days")
ALARM_ENABLED: Final = StateKey[bool | None]("superior_sleep_alarm_enabled")
