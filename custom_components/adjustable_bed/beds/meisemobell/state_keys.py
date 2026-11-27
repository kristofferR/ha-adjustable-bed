"""Declared raw readback and sent-state keys, scoped to one physical connection."""

from typing import Final

from ...controller_state import StateKey

ALARM_1: Final = StateKey[str | None]("meisemobell_alarm_1")
ALARM_2: Final = StateKey[str | None]("meisemobell_alarm_2")
SOURCE_1: Final = StateKey[str]("meisemobell_alarm_1_source")
SOURCE_2: Final = StateKey[str]("meisemobell_alarm_2_source")
ENABLED_1: Final = StateKey[bool]("meisemobell_alarm_1_enabled")
ENABLED_2: Final = StateKey[bool]("meisemobell_alarm_2_enabled")
WEEK_1: Final = StateKey[int]("meisemobell_alarm_1_week")
WEEK_2: Final = StateKey[int]("meisemobell_alarm_2_week")
TYPE_1: Final = StateKey[int]("meisemobell_alarm_1_type")
TYPE_2: Final = StateKey[int]("meisemobell_alarm_2_type")
MASSAGE_TIME: Final = StateKey[int | None]("meisemobell_massage_time")
MASSAGE_WAVE: Final = StateKey[int]("meisemobell_massage_wave")
MASSAGE_HEAD: Final = StateKey[int]("meisemobell_massage_head")
MASSAGE_FOOT: Final = StateKey[int]("meisemobell_massage_foot")
