"""Typed app state; unknown device state is never initialized from UI defaults."""

from typing import Final

from ...controller_state import StateKey

CHILD: Final = StateKey[str | None]("symphony_child_mode")
FIRMWARE: Final = StateKey[str | None]("symphony_firmware")
PROTOCOL: Final = StateKey[str | None]("symphony_protocol")
PRIVACY: Final = StateKey[bool | None]("symphony_privacy")
SNORE: Final = StateKey[bool | None]("symphony_anti_snore")
STRENGTH: Final = StateKey[int | None]("symphony_anti_snore_strength")
LIGHT_ON: Final = StateKey[bool | None]("symphony_light_on")
COLOR: Final = StateKey[int | None]("symphony_light_color")
BRIGHTNESS: Final = StateKey[int | None]("symphony_light_brightness")
MASSAGE: Final = StateKey[bool | None]("symphony_massage_running")
TIMER: Final = StateKey[int | None]("symphony_massage_timer_index")
WAVE: Final = StateKey[int | None]("symphony_massage_wave")
HEAD: Final = StateKey[int | None]("symphony_head_strength")
FOOT: Final = StateKey[int | None]("symphony_foot_strength")
SONIC: Final = StateKey[bool | None]("symphony_sonic")
PREMIER: Final = StateKey[str | None]("symphony_premier_display")
ALARM: Final = StateKey[bool | None]("symphony_alarm_enabled")
WEEK: Final = StateKey[int | None]("symphony_alarm_week")
MODE: Final = StateKey[int | None]("symphony_alarm_mode")
HOUR: Final = StateKey[int | None]("symphony_alarm_hour")
MINUTE: Final = StateKey[int | None]("symphony_alarm_minute")
SECOND: Final = StateKey[int | None]("symphony_alarm_second")
