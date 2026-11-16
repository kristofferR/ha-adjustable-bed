"""Sophie state belongs to one physical coordinator, never an Android global cache."""

from typing import Final

from ...controller_state import StateKey

ALARM_SUPPORTED: Final = StateKey[bool]("sophie_alarm_supported")
ALARM_ENABLED: Final = StateKey[bool]("sophie_alarm_enabled")
ALARM_TIME: Final = StateKey[str | None]("sophie_alarm_time")
ALARM_WEEKDAYS: Final = StateKey[str]("sophie_alarm_weekdays")
ALARM_MODE: Final = StateKey[str]("sophie_alarm_mode")
ALARM_MASSAGE: Final = StateKey[bool]("sophie_alarm_massage")
ALARM_RING: Final = StateKey[bool]("sophie_alarm_ring")
SYNC_SUPPORTED: Final = StateKey[bool]("sophie_sync_supported")
SYNC: Final = StateKey[str | None]("sophie_sync")
HEAD_LEVEL: Final = StateKey[int]("sophie_head_level")
FOOT_LEVEL: Final = StateKey[int]("sophie_foot_level")
WAVE: Final = StateKey[int]("sophie_wave")
