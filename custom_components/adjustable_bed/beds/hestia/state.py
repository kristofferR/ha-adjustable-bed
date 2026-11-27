"""Local choices and last-sent intentions, never peripheral feedback."""

from typing import Final

from ...controller_state import StateKey
from ...profiles.hestia import DEFAULTS

CHOICE: Final = {key: StateKey[str | None](f"hestia_{key}") for key in DEFAULTS}
MASSAGE: Final = StateKey[bool | None]("hestia_massage")
ALARM: Final = StateKey[bool | None]("hestia_alarm")
