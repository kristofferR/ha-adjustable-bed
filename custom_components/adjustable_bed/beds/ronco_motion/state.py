"""The last received alarm result, never optimistic success."""

from typing import Final

from ...controller_state import StateKey

ALARM: Final = StateKey[str | None]("ronco_motion_alarm")
