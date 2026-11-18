"""BED state only. Sleep measurements are not position feedback."""

from typing import Final

from ...controller_state import StateKey

PRIVACY: Final = StateKey[str | None]("onlysnore_privacy")
DETECTION: Final = StateKey[str | None]("onlysnore_detection")
INTERVENTION: Final = StateKey[str | None]("onlysnore_intervention")
LEVEL: Final = StateKey[int | None]("onlysnore_level")
TIMER: Final = StateKey[int | None]("onlysnore_massage_timer_index")
PATTERN: Final = StateKey[int | None]("onlysnore_massage_pattern_index")
HEAD: Final = StateKey[int | None]("onlysnore_massage_head_index")
FOOT: Final = StateKey[int | None]("onlysnore_massage_foot_index")
SHARED: Final = StateKey[int | None]("onlysnore_massage_shared_index")
ALARM_COUNT: Final = StateKey[int | None]("onlysnore_alarm_count")
FIRMWARE: Final = StateKey[str | None]("onlysnore_firmware")
HARDWARE: Final = StateKey[str | None]("onlysnore_hardware")
MODEL: Final = StateKey[str | None]("onlysnore_model")
ALARM_TIME: Final = tuple(StateKey[str | None](f"onlysnore_alarm_{i}_time") for i in range(1, 4))
ALARM_WEEK: Final = tuple(StateKey[int | None](f"onlysnore_alarm_{i}_week") for i in range(1, 4))
ALARM_ACTION: Final = tuple(
    StateKey[int | None](f"onlysnore_alarm_{i}_action") for i in range(1, 4)
)
ALARM_OPEN: Final = tuple(
    StateKey[bool | None](f"onlysnore_alarm_{i}_enabled") for i in range(1, 4)
)
ALARM_SOFT: Final = tuple(StateKey[bool | None](f"onlysnore_alarm_{i}_soft") for i in range(1, 4))
