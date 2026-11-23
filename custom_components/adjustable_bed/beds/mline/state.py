"""Observed M Line state; no defaults stand in for sensor feedback."""

from typing import Final

from ...controller_state import StateKey

HEART: Final = StateKey[int | None]("mline_heart")
BREATH: Final = StateKey[int | None]("mline_breath")
MOTION: Final = StateKey[bool | None]("mline_motion")
PROJECTION: Final = StateKey[bool | None]("mline_boolean_projection")
PRIVACY: Final = StateKey[bool | None]("mline_privacy")
ANTI_ENABLED: Final = StateKey[bool | None]("mline_anti_enabled")
ANTI_ANGLE: Final = StateKey[int | None]("mline_anti_angle")
ALARM: Final = StateKey[str | None]("mline_alarm")

ALARM_MODE: Final = StateKey[str | None]("mline_alarm_mode")
MOTION_WINDOW: Final = StateKey[tuple[bool, ...] | None]("mline_motion_window")
