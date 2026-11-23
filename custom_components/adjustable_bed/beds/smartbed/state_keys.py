"""Non-position state of the SmartBed controls."""

from typing import Final

from ...controller_state import StateKey

MASSAGE: Final = StateKey[bool | None]("smartbed_massage")
WAVE: Final = StateKey[int | None]("smartbed_wave")
SONIC: Final = StateKey[bool | None]("smartbed_sonic")
SONIC_HEAD: Final = StateKey[int | None]("smartbed_sonic_head")
SONIC_FOOT: Final = StateKey[int | None]("smartbed_sonic_foot")
SONIC_WAVE: Final = StateKey[int | None]("smartbed_sonic_wave")
SONIC_MODE: Final = StateKey[str | None]("smartbed_sonic_mode")
SONIC_TIMER: Final = StateKey[str | None]("smartbed_sonic_timer")
ALARM_TIME: Final = StateKey[str | None]("smartbed_alarm_time")
ALARM_ON: Final = StateKey[bool | None]("smartbed_alarm_on")
ALARM_ACTION: Final = StateKey[str | None]("smartbed_alarm_action")
ALARM_REPEAT: Final = StateKey[int | None]("smartbed_alarm_repeat")
ALL: Final = (
    MASSAGE,
    WAVE,
    SONIC,
    SONIC_HEAD,
    SONIC_FOOT,
    SONIC_WAVE,
    SONIC_MODE,
    SONIC_TIMER,
    ALARM_TIME,
    ALARM_ON,
    ALARM_ACTION,
    ALARM_REPEAT,
)
