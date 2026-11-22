"""Connection-scoped, reported and assumed Relax Motion settings."""

from typing import Final

from ...controller_state import StateKey

SLEEP: Final = StateKey[bool | None]("relax_motion_sleep")
SNORE_READY: Final = StateKey[bool | None]("relax_motion_snore_ready")
SNORE: Final = StateKey[bool | None]("relax_motion_snore")
INTERVAL: Final = StateKey[int | None]("relax_motion_snore_interval")
LIGHT_TIME: Final = StateKey[int | None]("relax_motion_light_time")

RHYTHM: Final = StateKey[bool | None]("relax_motion_rhythm")
