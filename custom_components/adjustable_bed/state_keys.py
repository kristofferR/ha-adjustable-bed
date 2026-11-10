"""Controller-state keys shared by several controllers or read by generic layers.

Keys only one controller reads and writes live next to that controller. A key
an entity platform or the coordinator reads lives here, so those layers never
import a bed module to name it.
"""

from __future__ import annotations

from typing import Final

from .const import BED_TYPE_ISLEEP, BED_TYPE_RIZE
from .controller_state import StateKey

# Under-bed lights.
UNDER_BED_LIGHTS_ON: Final = StateKey[bool | None]("under_bed_lights_on")
LIGHT_LEVEL: Final = StateKey[int | None]("light_level")
LIGHT_TIMER_OPTION: Final = StateKey[str | None]("light_timer_option")
LIGHT_TIMER_MINUTES: Final = StateKey[int]("light_timer_minutes")
UNDER_BED_LIGHTS_RGB: Final = StateKey[tuple[int, int, int] | None]("under_bed_lights_rgb")
UNDER_BED_LIGHTS_RGBW: Final = StateKey[tuple[int, int, int, int] | None]("under_bed_lights_rgbw")
LIGHT_INTENSITY: Final = StateKey[int | None]("light_intensity")


def rgb_triple(value: object) -> tuple[int, int, int] | None:
    """``value`` as three integer channels, or ``None``."""
    if isinstance(value, (tuple, list)) and len(value) == 3:
        red, green, blue = value
        if type(red) is int and type(green) is int and type(blue) is int:
            return (red, green, blue)
    return None


# Octo's hardware light timeout; the light switch mirrors its expiry.
OCTO_LIGHT_DURATION: Final = StateKey[int | None]("octo_light_duration")
FAN_LEVEL: Final = StateKey[int | None]("fan_level")

# Switches backed by published state.
AUTOMATIC_LIGHT: Final = StateKey[bool | None]("automatic_light")
SYNCHRO_MODE: Final = StateKey[bool | None]("synchro_mode")
REMOTE_CONTROL_LOCK: Final = StateKey[bool | None]("remote_control_lock")
LINAK_AUTOMATIC_DRIVE: Final = StateKey[bool | None]("linak_automatic_drive")

# Linak: the coordinator reports the resolved model as device metadata.
LINAK_MODEL_VARIANT: Final = StateKey[str]("linak_model_variant")

# Sleep Number. Side-scoped copies use ``sided(KEY, side)``.
SLEEP_NUMBER: Final = StateKey[int]("sleep_number")
SLEEP_NUMBER_SIDE: Final = StateKey[str]("sleep_number_side")
BED_PRESENCE: Final = StateKey[str]("bed_presence")
BED_PRESENCE_SIDE: Final = StateKey[str]("bed_presence_side")
FOUNDATION_PRESET: Final = StateKey[str | None]("foundation_preset")

THERMAL_BACKEND: Final = StateKey[str | None]("thermal_backend")
THERMAL_PRESENT: Final = StateKey[bool]("thermal_present")
THERMAL_HVAC_MODE: Final = StateKey[str]("thermal_hvac_mode")
THERMAL_PRESET: Final = StateKey[str | None]("thermal_preset")
THERMAL_RESUME_PRESET_COOL: Final = StateKey[str | None]("thermal_resume_preset_cool")
THERMAL_RESUME_PRESET_HEAT: Final = StateKey[str | None]("thermal_resume_preset_heat")
THERMAL_MODE: Final = StateKey[str]("thermal_mode")
THERMAL_REMAINING_TIME_MINUTES: Final = StateKey[int]("thermal_remaining_time_minutes")
THERMAL_TIMER_OPTION: Final = StateKey[str | None]("thermal_timer_option")
THERMAL_SUPPORTS_HEATING: Final = StateKey[bool]("thermal_supports_heating")

FOOTWARMING_PRESENT: Final = StateKey[bool]("footwarming_present")
FOOTWARMING_HVAC_MODE: Final = StateKey[str]("footwarming_hvac_mode")
FOOTWARMING_PRESET: Final = StateKey[str | None]("footwarming_preset")
# Fuzion reports a level name, MCR a level number.
FOOTWARMING_LEVEL: Final = StateKey[str | int]("footwarming_level")
FOOTWARMING_REMAINING_TIME_MINUTES: Final = StateKey[int]("footwarming_remaining_time_minutes")
FOOTWARMING_TOTAL_REMAINING_TIME_MINUTES: Final = StateKey[int](
    "footwarming_total_remaining_time_minutes"
)
FOOTWARMING_TIMER_OPTION: Final = StateKey[str | None]("footwarming_timer_option")

# Massage, as each controller last tracked or received it. The massage number,
# timer select and sensors read these, connected or not.
MASSAGE_TIMER_MINUTES: Final = StateKey[int | None]("massage_timer")
MASSAGE_ACTIVE: Final = StateKey[bool]("massage_active")


def massage_intensity(zone: str) -> StateKey[int | None]:
    """Intensity of one massage zone: ``all``, ``head``, ``foot``, ``right`` or ``wave``."""
    return StateKey[int | None](f"massage_{zone}_intensity")


def massage_active(zone: str) -> StateKey[bool]:
    """Whether one massage zone was last published as running."""
    return StateKey[bool](f"{zone}_active")


def massage_state_side(bed_type: str, entity_side: str | None) -> str | None:
    """Side whose massage keys an entity reads; ISleep publishes one per side."""
    if bed_type not in (BED_TYPE_ISLEEP, BED_TYPE_RIZE):
        return None
    return entity_side or "both"
