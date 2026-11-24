"""Named settings shared by SleepIQ's two direct BLE routes."""

from typing import Final

from ...controller_state import StateKey

PRIVACY: Final = StateKey[bool | None]("sleepiq_privacy")
RESPONSIVE_AIR: Final = StateKey[bool | None]("sleepiq_responsive_air")
AUTO_LIGHT: Final = StateKey[bool | None]("sleepiq_auto_light")
AUTO_LIGHT_LEVEL: Final = StateKey[str | None]("sleepiq_auto_light_level")
AUTO_KIDS_LIGHT: Final = StateKey[bool | None]("sleepiq_auto_kids_light")
KIDS_OUTLET: Final = StateKey[bool | None]("sleepiq_kids_outlet")
HEAD_TILT: Final = StateKey[bool | None]("sleepiq_head_tilt")
