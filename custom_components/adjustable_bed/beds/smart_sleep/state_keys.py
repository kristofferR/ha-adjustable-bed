"""Declared Smart Sleep state, distinct from sleep/accessory telemetry."""

from typing import Final

from ...controller_state import StateKey

CHILD_MODE: Final = StateKey[str | None]("smart_sleep_child_mode")
PRIVACY: Final = StateKey[str | None]("smart_sleep_privacy")
ANTISNORE: Final = StateKey[str | None]("smart_sleep_antisnore")
SENSITIVITY: Final = StateKey[str | None]("smart_sleep_sensitivity")
WAVE: Final = StateKey[str | None]("smart_sleep_wave")
HEAD: Final = StateKey[str | None]("smart_sleep_head_strength")
FOOT: Final = StateKey[str | None]("smart_sleep_foot_strength")
TIMER: Final = StateKey[str | None]("smart_sleep_timer")
MASSAGE_ON: Final = StateKey[bool | None]("smart_sleep_massage_on")
ALARM_ON: Final = StateKey[bool | None]("smart_sleep_alarm_on")
ALARM_WEEK: Final = StateKey[int | None]("smart_sleep_alarm_week")
ALARM_ACTION: Final = StateKey[int | None]("smart_sleep_alarm_action")
ALARM_TIME: Final = StateKey[str | None]("smart_sleep_alarm_time")
FLEXIBLE: Final = StateKey[bool | None]("smart_sleep_flexible_wake")
BRIGHTNESS: Final = StateKey[int | None]("smart_sleep_light_brightness")
AI_STATUS: Final = StateKey[int | None]("smart_sleep_ai_status")
AI_SCORE: Final = StateKey[int | None]("smart_sleep_ai_score")
MODEL: Final = StateKey[int | None]("smart_sleep_model")
