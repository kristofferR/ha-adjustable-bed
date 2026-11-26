"""Independence 1.1.0 (5), com.okin.bedding.customaticdemo."""

from types import MappingProxyType
from typing import Final

from ..codec import okin_nframe as codec
from ..const import BED_TYPE_CUSTOMATIC_DEMO
from ..execution import STREAM_HOLD
from .okin_nframe import Hold, OkinNFrameProfile, Tap

NAME_PREFIX: Final = "okin"
MANUFACTURER_UUID: Final = "00002a29-0000-1000-8000-00805f9b34fb"
REFRESH_MS: Final = 100
QUERY_DELAY_S: Final = 0.3
MANUFACTURER_DELAY_S: Final = 1.0
DEMO_PRESS_MS: Final = 300
DEMO_PHASE_S: Final = 120
MOTOR_AXES: Final = ("back", "legs", "seat", "rotation")
MOTOR_CONTROLS: Final = tuple(
    f"{axis}_{direction}" for axis in MOTOR_AXES for direction in ("up", "down")
)
BUTTON_CONTROLS: Final = ("auto_flat", "auto_sit", "light_toggle", "light_auto", "light_timer")
STATUS_QUERY: Final = codec.parameter_record(0x04, (0, 0, 0, 0))

PROFILE: Final = OkinNFrameProfile(
    key=BED_TYPE_CUSTOMATIC_DEMO,
    name="Independence (Customatic Demo)",
    bed_types=(BED_TYPE_CUSTOMATIC_DEMO,),
    width=12,
    write="characteristic",
    envelope="plain",
    axes=MOTOR_AXES,
    keys=MappingProxyType(
        {
            key: word << 64
            for key, word in {
                "back_up": 0x01,
                "back_down": 0x02,
                "legs_up": 0x04,
                "legs_down": 0x08,
                "rotation_up": 0x10,
                "rotation_down": 0x20,
                "seat_up": 0x40,
                "seat_down": 0x80,
                "auto_flat": 0x00100000,
                "auto_sit": 0x00080000,
                "light_toggle": 0x00020000,
                "light_auto": 0x40000000,
                "light_timer": 0x00000200,
                "stop": 0,
            }.items()
        }
    ),
    hold=Hold(repeat_ms=REFRESH_MS, releases=2, release_after_ms=100, release_ms=100),
    recall=Tap(releases=2),
    tap=Tap(releases=2),
    execution=STREAM_HOLD,
)
