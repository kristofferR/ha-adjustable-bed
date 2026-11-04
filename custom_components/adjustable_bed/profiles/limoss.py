"""Profiles over the Limoss DD codec.

``LEGACY`` serves the ``limoss`` bed type, from the pre-v5 controller.
``LIMOSS_REMOTE`` (``limoss_remote``, Limoss Remote 7.1.8) and ``FSM_RELAX``
(``fsm_relax``, FSM Relax 1.9) come from their accepted APK Protocol Audit
reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from ..codec import limoss as codec
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

Counter = Literal["controller", "session", "app"]
WriteMode = Literal["property", "without_response"]
Layout = tuple[int | None, ...]
"""Held opcodes in the app's key order; ``None`` is an empty key."""


@dataclass(frozen=True)
class Burst:
    """``frames`` copies of one release body, one per tick."""

    opcode: int
    frames: int


@dataclass(frozen=True)
class Calibration:
    refresh_ms: int | None
    """Held refresh interval; ``None`` sends one frame."""
    release: Burst | None = None


@dataclass(frozen=True, kw_only=True)
class LimossProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    counter: Counter
    """Owner of the sequence byte: ``controller`` takes one value per command and
    resends that frame for repeats; ``session`` and ``app`` take one per frame,
    from the bed's stored session or one process-wide counter."""
    write_mode: WriteMode
    """``property`` follows the characteristic's write property."""
    tick_ms: int | None
    """Write cadence: holds refresh every tick, after an initial tick. ``None``
    repeats immediately at the entry's motor pulse count and delay."""
    stop: Burst
    """Sent after a hold and on an explicit stop."""
    recall_ms: int
    """Interval between memory recall writes."""
    recall_release: Burst | None
    calibration: Calibration | None = None
    feature_off_frames: int = 0
    """Frames of the light-off or massage-off body when a local feature is disabled."""
    layouts: dict[str, Layout] = field(default_factory=dict)
    """App key tables by name. Empty: the motor count decides the axes."""


# Limoss Remote names each held opcode by its app channel, not a physical actuator.
REMOTE_CHANNELS: Final[dict[str, int]] = {
    "motor_1_up": 0x12,
    "motor_1_down": 0x13,
    "motor_2_up": 0x22,
    "motor_2_down": 0x23,
    "motor_3_up": 0x32,
    "motor_3_down": 0x33,
    "motor_4_up": 0x42,
    "motor_4_down": 0x43,
    "combined_up": 0x50,
    "combined_down": 0x51,
    "lift_up": 0x52,
    "lift_down": 0x53,
    "shift_up": 0x54,
    "shift_down": 0x55,
    "massage_back_plus": 0x60,
    "massage_back_minus": 0x61,
    "massage_foot_plus": 0x62,
    "massage_foot_minus": 0x63,
    "massage_both_plus": 0x64,
    "massage_both_minus": 0x65,
    "light": 0x70,
}
REMOTE_THEMES: Final = (
    "bed_legacy",
    "bed_hc319",
    "bed_clear",
    "bed_red",
    "chairs_legacy",
    "chairs_hc314",
    "chairs_hc338",
    "chairs_clear",
)
FSM_LABELS: Final[dict[int, str]] = {
    0x12: "Back up",
    0x13: "Back down",
    0x22: "Legs up",
    0x23: "Legs down",
    0x32: "Tilt up",
    0x33: "Tilt down",
    0x50: "Combined up",
    0x51: "Combined down",
    0x52: "Elevation up",
    0x53: "Elevation down",
    0x54: "All regions up",
    0x55: "All regions down",
    0x60: "Back massage plus",
    0x61: "Back massage minus",
    0x62: "Legs massage plus",
    0x63: "Legs massage minus",
    0x64: "Both massage plus",
    0x65: "Both massage minus",
    0x70: "Underbed light control",
}

LEGACY: Final = LimossProfile(
    key="legacy",
    counter="controller",
    write_mode="property",
    tick_ms=None,
    stop=Burst(codec.STOP, 1),
    recall_ms=300,
    recall_release=None,
)

# Rendered app tables. Hidden cKey4 declarations and null cells are not actions.
LIMOSS_REMOTE: Final = LimossProfile(
    key="limoss_remote",
    counter="app",
    write_mode="property",
    tick_ms=80,
    stop=Burst(codec.STOP, 5),
    recall_ms=300,
    recall_release=Burst(codec.STOP, 5),
    calibration=Calibration(100, Burst(codec.RECALL_RELEASE, 5)),
    feature_off_frames=10,
    layouts={
        "cKey2": (0x12, 0x13),
        "cKey4": (0x12, 0x13, 0x22, 0x23),
        "cKey6": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51),
        "cKey8": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x42, 0x43),
        "cKey8_customAlpha": (0x13, 0x12, 0x22, 0x23, 0x32, 0x33, 0x43, 0x42),
        "gKey10": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55),
        "gKey10BothUnderBedLightVibrate": (
            *(0x12, 0x13, 0x64, 0x22, 0x23, 0x65, 0x50, 0x51, 0x70),
            *(0x52, 0x53, None, 0x54, 0x55, None),
        ),
        "gKey10UnderBedLight": (
            *(0x12, 0x13, 0x70, 0x22, 0x23, None, 0x50, 0x51, None),
            *(0x52, 0x53, None, 0x54, 0x55, None),
        ),
        "gKey10Vibrate": (
            *(0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x50, 0x51, 0x62),
            *(0x52, 0x53, 0x63, 0x54, 0x55, None),
        ),
        "gKey12": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53, 0x32, 0x33, 0x54, 0x55),
        "gKey12BothUnderBedLightVibrate": (
            *(0x12, 0x13, 0x64, 0x22, 0x23, 0x65, 0x50, 0x51, 0x70),
            *(0x52, 0x53, None, 0x32, 0x33, None, 0x54, 0x55, None),
        ),
        "gKey12UnderBedLight": (
            *(0x12, 0x13, 0x70, 0x22, 0x23, None, 0x50, 0x51, None),
            *(0x52, 0x53, None, 0x32, 0x33, None, 0x54, 0x55, None),
        ),
        "gKey12Vibrate": (
            *(0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x50, 0x51, 0x62),
            *(0x52, 0x53, 0x63, 0x32, 0x33, None, 0x54, 0x55, None),
        ),
        "gKey2": (0x12, 0x13),
        "gKey2BothUnderBedLightVibrate": (0x12, 0x13, 0x64, 0x65, 0x70, None),
        "gKey2UnderBedLight": (0x12, 0x13, 0x70, None),
        "gKey2Vibrate": (0x12, 0x13, 0x60, 0x61, 0x62, 0x63),
        "gKey4": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51),
        "gKey4BothUnderBedLightVibrate": (0x12, 0x13, 0x22, 0x23, 0x70, 0x51, 0x64, 0x65),
        "gKey4UnderBedLight": (0x12, 0x13, 0x22, 0x23, 0x70, 0x51),
        "gKey4Vibrate": (0x12, 0x13, 0x22, 0x23, 0x60, 0x61, 0x62, 0x63),
        "gKey6": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x54, 0x55),
        "gKey6BothUnderBedLightVibrate": (
            *(0x12, 0x13, 0x64, 0x22, 0x23, 0x65),
            *(0x32, 0x33, 0x70, 0x54, 0x55, None),
        ),
        "gKey6UnderBedLight": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x70, 0x54),
        "gKey6Vibrate": (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x32, 0x33, 0x62, 0x54, 0x55, 0x63),
        "gKey8": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53),
        "gKey8BothUnderBedLightVibrate": (
            *(0x12, 0x13, 0x64, 0x22, 0x23, 0x65),
            *(0x50, 0x51, 0x70, 0x52, 0x53, None),
        ),
        "gKey8UnderBedLight": (
            *(0x12, 0x13, 0x70, 0x22, 0x23, None),
            *(0x50, 0x51, None, 0x52, 0x53, None),
        ),
        "gKey8Vibrate": (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x50, 0x51, 0x62, 0x52, 0x53, 0x63),
    },
)

# Exact source order, including the asymmetric light-only six-key table. Keyboard
# tables are keyed by key count and feature index: 1 light, 2 massage, 3 both.
_CHAIR: Final = (0x22, 0x23, 0x12, 0x13, 0x50, 0x51)
FSM_RELAX: Final = LimossProfile(
    key="fsm_relax",
    counter="session",
    write_mode="without_response",
    tick_ms=60,
    stop=Burst(codec.STOP, 5),
    recall_ms=60,
    recall_release=Burst(codec.RECALL_RELEASE, 5),
    calibration=Calibration(None),
    layouts={
        "chair/02": (0x50, 0x51),
        "chair/04": _CHAIR,
        "chair/06": _CHAIR,
        "chair/08": _CHAIR,
        "keyboard/02/0": (0x12, 0x13),
        "keyboard/02/1": (0x12, 0x13, 0x70),
        "keyboard/02/2": (0x12, 0x13, 0x60, 0x61, 0x62, 0x63),
        "keyboard/02/3": (0x12, 0x13, 0x64, 0x65, 0x70),
        "keyboard/04/0": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51),
        "keyboard/04/1": (0x12, 0x13, 0x22, 0x23, 0x70, 0x51),
        "keyboard/04/2": (0x12, 0x13, 0x22, 0x23, 0x60, 0x61, 0x62, 0x63),
        "keyboard/04/3": (0x12, 0x13, 0x22, 0x23, 0x70, 0x51, 0x64, 0x65),
        "keyboard/06/0": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x54, 0x55),
        "keyboard/06/1": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x70, 0x54),
        "keyboard/06/2": (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x32, 0x33, 0x62, 0x54, 0x55, 0x63),
        "keyboard/06/3": (0x12, 0x13, 0x64, 0x22, 0x23, 0x65, 0x32, 0x33, 0x70, 0x54, 0x55),
        "keyboard/08/0": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53),
        "keyboard/08/1": (0x12, 0x13, 0x70, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53),
        "keyboard/08/2": (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x50, 0x51, 0x62, 0x52, 0x53, 0x63),
        "keyboard/08/3": (0x12, 0x13, 0x64, 0x22, 0x23, 0x65, 0x50, 0x51, 0x70, 0x52, 0x53),
    },
)
PROFILES: Final = {profile.key: profile for profile in (LEGACY, LIMOSS_REMOTE, FSM_RELAX)}


def fsm_relax_layout(chair: bool, key_count: int, light: bool, massage: bool) -> str:
    """FSM Relax table for an accepted key count of 2, 4, 6 or 8."""
    if chair:
        return f"chair/{key_count:02d}"
    return f"keyboard/{key_count:02d}/{int(light) + 2 * int(massage)}"
