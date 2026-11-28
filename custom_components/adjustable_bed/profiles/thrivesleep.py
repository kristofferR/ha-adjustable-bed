"""Thrive Sleep 1.1.2 current products over the literal-verified Richmat codec."""

from dataclasses import dataclass
from typing import Final

from ..codec import richmat as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class Action:
    label: str
    code: int
    alternate: int | None = None


ACTIONS: Final = {
    "head_up": Action("Head up", 36, None),
    "head_down": Action("Head down", 37, None),
    "foot_up": Action("Foot up", 38, None),
    "foot_down": Action("Foot down", 39, None),
    "lumber_up": Action("Lumbar up", 63, None),
    "lumber_down": Action("Lumbar down", 64, None),
    "pillow_up": Action("Pillow up", 65, None),
    "pillow_down": Action("Pillow down", 66, None),
    "motor3_up": Action("Motor 3 up", 113, None),
    "motor3_down": Action("Motor 3 down", 114, None),
    "motor_reset": Action("Flat", 49, None),
    "light_board": Action("Light board", 80, None),
    "massage_head_instensity_strengthen": Action("Massage head intensity increase", 76, None),
    "massage_foot_instensity_strengthen": Action("Massage foot intensity increase", 78, None),
    "massage_mode_constant": Action("Massage constant", 58, None),
    "massage_mode_pulse": Action("Massage pulse", 56, None),
    "massage_mode_wave": Action("Massage wave", 57, None),
    "massage_mode_all_off": Action("Massage off", 94, None),
    "massage10_minute_timer": Action("Massage 10 minute timer", 95, None),
    "massage20_minute_timer": Action("Massage 20 minute timer", 99, None),
    "massage30_minute_timer": Action("Massage 30 minute timer", 97, None),
    "anti_snoring": Action("Anti-snore", 70, 105),
    "zero_gravity": Action("Zero Gravity", 69, 102),
    "t_v_position": Action("TV", 88, 100),
    "lounge_position": Action("Lounge", 89, 101),
    "memory_position1": Action("Memory 1", 46, 43),
    "memory_position2": Action("Memory 2", 47, 44),
    "memory_position3": Action("Memory 3", 48, 45),
    "coaxing_sleep_mode": Action("Coaxing sleep mode", 134, 137),
    "massage_mode_change": Action("Massage mode change", 72, None),
    "fan1_instensity_strengthen": Action("Fan 1 intensity increase", 138, None),
    "fan2_instensity_strengthen": Action("Fan 2 intensity increase", 139, None),
    "fan_change_mode": Action("Fan mode change", 162, None),
    "fan_forward_and_backward_change": Action("Fan forward/backward change", 140, None),
    "fan_all_off": Action("Fan off", 161, None),
    "fan_timer2_hour": Action("Fan 2 hour timer", 166, None),
    "fan_timer3_hour": Action("Fan 3 hour timer", 167, None),
    "fan_timer5_hour": Action("Fan 5 hour timer", 168, None),
    "eco_sleep_power": Action("ON/OFF", 135),
    "eco_sleep_soothing": Action("SLEEP SOOTHING", 134),
    "eco_sleep_sm": Action("SM", 137),
}
MASSAGE_TIMERS: Final = {
    10: "massage10_minute_timer",
    20: "massage20_minute_timer",
    30: "massage30_minute_timer",
}
DIRECTIONS: Final = tuple(key for key in ACTIONS if key.endswith(("_up", "_down")))
ROUTES: Final[tuple[codec.TransportKey, ...]] = ("w1", "n1", "w5", "w4", "w3", "w2")
TICK_S: Final = 0.1
STARTUP_DELAY_S: Final = 1.0
RESIDUAL_EXPIRY_S: Final = 0.5
LONG_PRESS_MS: Final = 3000
STARTUP: Final = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
)
THERAPY: Final = {"warm": (255, 140, 20), "neutral": (255, 220, 120), "cool": (255, 255, 255)}


@dataclass(frozen=True, slots=True)
class ThriveSleepProfile:
    key: str
    label: str
    actions: tuple[str, ...]
    alarms: tuple[str, ...]
    execution: ExecutionCapabilities = STREAM_HOLD

    def frame(self, code: int, *, raw: bool, action: str = "") -> bytes:
        return codec.function(code, single=raw, action=action)


PROFILES: Final = {
    "level5": ThriveSleepProfile(
        "level5",
        "Level 5",
        (
            "head_up",
            "head_down",
            "foot_up",
            "foot_down",
            "lumber_up",
            "lumber_down",
            "pillow_up",
            "pillow_down",
            "motor3_up",
            "motor3_down",
            "motor_reset",
            "light_board",
            "massage_head_instensity_strengthen",
            "massage_foot_instensity_strengthen",
            "massage_mode_constant",
            "massage_mode_pulse",
            "massage_mode_wave",
            "massage_mode_all_off",
            "massage10_minute_timer",
            "massage20_minute_timer",
            "massage30_minute_timer",
            "anti_snoring",
            "zero_gravity",
            "t_v_position",
            "lounge_position",
            "memory_position1",
            "memory_position2",
            "memory_position3",
            "coaxing_sleep_mode",
        ),
        (
            "anti_snoring",
            "zero_gravity",
            "t_v_position",
            "lounge_position",
            "memory_position1",
            "memory_position2",
            "memory_position3",
        ),
    ),
    "eco_comfort": ThriveSleepProfile(
        "eco_comfort",
        "Eco Comfort",
        (
            "head_up",
            "head_down",
            "foot_up",
            "foot_down",
            "lumber_up",
            "lumber_down",
            "motor_reset",
            "massage_head_instensity_strengthen",
            "massage_foot_instensity_strengthen",
            "massage_mode_all_off",
            "massage_mode_change",
            "massage10_minute_timer",
            "massage20_minute_timer",
            "massage30_minute_timer",
            "zero_gravity",
            "memory_position1",
            "anti_snoring",
            "eco_sleep_power",
            "eco_sleep_soothing",
            "eco_sleep_sm",
        ),
        ("zero_gravity", "memory_position1", "anti_snoring"),
    ),
    "cool_flow": ThriveSleepProfile(
        "cool_flow",
        "Cool flow",
        (
            "head_up",
            "head_down",
            "foot_up",
            "foot_down",
            "lumber_up",
            "lumber_down",
            "pillow_up",
            "pillow_down",
            "motor_reset",
            "fan1_instensity_strengthen",
            "fan2_instensity_strengthen",
            "fan_change_mode",
            "fan_forward_and_backward_change",
            "fan_all_off",
            "fan_timer2_hour",
            "fan_timer3_hour",
            "fan_timer5_hour",
            "anti_snoring",
            "zero_gravity",
            "t_v_position",
            "lounge_position",
            "memory_position1",
            "memory_position2",
        ),
        (
            "anti_snoring",
            "zero_gravity",
            "t_v_position",
            "lounge_position",
            "memory_position1",
            "memory_position2",
        ),
    ),
}
VARIANTS: Final = {key: profile.label for key, profile in PROFILES.items()}
