"""Connection-scoped reports, separate from submitted AMADA alarm settings."""
from typing import Final

from ...controller_state import StateKey

MASSAGE_TIME: Final = StateKey[int | None]("amada_massage_time_bucket")
MASSAGE_HEAD: Final = StateKey[int | None]("amada_massage_head")
MASSAGE_FOOT: Final = StateKey[int | None]("amada_massage_foot")
MASSAGE_MODE: Final = StateKey[int | None]("amada_massage_mode")
MASSAGE_ON: Final = StateKey[bool | None]("amada_massage_on")
LIGHT: Final = StateKey[bool | None]("amada_light")
ALARM_TIME: Final = StateKey[str | None]("amada_alarm_time")
ALARM_ENABLED: Final = StateKey[bool | None]("amada_alarm_enabled")
ALARM_REPEAT: Final = StateKey[int | None]("amada_alarm_repeat")
ALARM_KIND: Final = StateKey[int | None]("amada_alarm_kind")
ALARM_SENT: Final = StateKey[str | None]("amada_alarm_submitted")
