"""Pure builders and parsers for the Linak Bed Control BLE protocol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final


class LinakProfile(StrEnum):
    """Selectable Linak application protocol profiles."""

    BED_CONTROL = "bed_control"
    PERFORMANCE = "performance_legacy"


class LinakModelVariant(StrEnum):
    """Service-derived Bed Control model variants."""

    UNKNOWN = "unknown"
    STANDARD = "standard"
    TD3 = "td3"
    ADVANCED = "advanced"
    ADVANCED_WITH_ALARM = "advanced_with_alarm"


LINAK_AXIS_MASKS: Final[dict[str, int]] = {
    "back": 1 << 7,
    "legs": 1 << 6,
    "head": 1 << 5,
    "feet": 1 << 4,
    "base": 1 << 3,
}


@dataclass(frozen=True, slots=True)
class LinakCapabilitySnapshot:
    """Resolved Bed Control capabilities safe to cache across connections."""

    profile: LinakProfile = LinakProfile.BED_CONTROL
    model_variant: LinakModelVariant = LinakModelVariant.UNKNOWN
    actuator_mask: int | None = None
    timer_supported: bool = False
    discovery_complete: bool = False

    @property
    def position_axes(self) -> tuple[str, ...]:
        """Return the exact reference-output axes enabled by the mask."""
        if self.actuator_mask is None:
            return ()
        return tuple(axis for axis, mask in LINAK_AXIS_MASKS.items() if self.actuator_mask & mask)

    @property
    def memory_slots(self) -> int:
        """Return the app-visible memory capacity for this model variant."""
        if self.profile is LinakProfile.PERFORMANCE:
            return 4
        if self.model_variant in {
            LinakModelVariant.TD3,
            LinakModelVariant.ADVANCED,
            LinakModelVariant.ADVANCED_WITH_ALARM,
        }:
            return 4
        return 0

    def as_dict(self) -> dict[str, Any]:
        """Return a config-entry-safe representation."""
        return {
            "profile": self.profile.value,
            "model_variant": self.model_variant.value,
            "actuator_mask": self.actuator_mask,
            "timer_supported": self.timer_supported,
            "discovery_complete": self.discovery_complete,
        }

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any] | None,
        *,
        profile: LinakProfile,
    ) -> LinakCapabilitySnapshot:
        """Parse a stored snapshot, ignoring invalid or mismatched data."""
        if not value or value.get("profile") != profile.value:
            return cls(profile=profile)
        try:
            model_variant = LinakModelVariant(str(value.get("model_variant", "unknown")))
        except ValueError:
            model_variant = LinakModelVariant.UNKNOWN
        raw_mask = value.get("actuator_mask")
        actuator_mask = raw_mask if isinstance(raw_mask, int) and 0 <= raw_mask <= 255 else None
        return cls(
            profile=profile,
            model_variant=model_variant,
            actuator_mask=actuator_mask,
            timer_supported=value.get("timer_supported") is True,
            discovery_complete=value.get("discovery_complete") is True,
        )


@dataclass(frozen=True, slots=True)
class LinakReferenceState:
    """Decoded four-byte reference-output sample."""

    extension: float
    raw_extension: int
    status_flags: int
    raw_speed: int
    speed: float

    @property
    def speed_direction(self) -> str:
        """Return protocol-sign direction without guessing physical orientation."""
        if self.raw_speed > 0:
            return "positive"
        if self.raw_speed < 0:
            return "negative"
        return "stopped"

    @property
    def sls(self) -> bool:
        return bool(self.status_flags & 0x01)

    @property
    def end_position_up(self) -> bool:
        return bool(self.status_flags & 0x02)

    @property
    def end_position_down(self) -> bool:
        return bool(self.status_flags & 0x04)

    @property
    def position_lost(self) -> bool:
        return bool(self.status_flags & 0x08)


def decode_reference(data: bytes | bytearray) -> LinakReferenceState:
    """Decode an exact four-byte little-endian reference-output value."""
    if len(data) != 4:
        raise ValueError(f"Linak reference data must be exactly 4 bytes, got {len(data)}")
    word = int.from_bytes(data, "little")
    raw_extension = word & 0xFFFF
    signed_extension = int.from_bytes(data[:2], "little", signed=True)
    status_flags = (word >> 16) & 0x0F
    raw_speed = (word >> 20) & 0x0FFF
    if raw_speed & 0x0800:
        raw_speed -= 0x1000
    return LinakReferenceState(
        extension=signed_extension / 100,
        raw_extension=raw_extension,
        status_flags=status_flags,
        raw_speed=raw_speed,
        speed=abs(raw_speed * 0.09765625),
    )


LINAK_ERROR_NAMES: Final[tuple[str, ...]] = (
    "position_lost",
    "overload_down",
    "overload_up",
    "sls_error",
    "placeholder_error_five",
    "placeholder_error_six",
    "placeholder_error_seven",
    "unexpected_result",
    "lin_error",
    "power_fail",
    "channel_count_changed",
    "position_difference",
    "short_circuit",
    "checksum",
    "power_limit",
    "key_error",
    "no_safety",
    "missing_initialisation_plug",
    "lin_power_below_acceptable_level",
    *(
        f"channel_{channel}_{suffix}"
        for suffix in ("missing", "type", "pulse")
        for channel in ("one", "two", "three", "four", "five", "six")
    ),
    *(
        f"channel_{channel}_overload_up"
        for channel in ("one", "two", "three", "four", "five", "six")
    ),
    *(
        f"channel_{channel}_overload_down"
        for channel in ("one", "two", "three", "four", "five", "six")
    ),
    *(
        f"channel_{channel}_anti_collision"
        for channel in ("one", "two", "three", "four", "five", "six")
    ),
    *(
        f"channel_{channel}_sls_activation"
        for channel in ("one", "two", "three", "four", "five", "six")
    ),
    *(f"channel_{channel}_b_type" for channel in ("one", "two", "three", "four", "five", "six")),
    "channel_one_a_shorted",
    "channel_one_b_shorted",
    "channel_two_a_shorted",
    "channel_two_b_shorted",
    "channel_three_a_shorted",
    "channel_three_b_shorted",
    "channel_four_a_shorted",
    "channel_four_b_shorted",
    "channel_five_a_shorted",
    "channel_five_b_shorted",
    "channel_six_a_shorted",
    "channel_six_b_shorted",
    "massage",
    "dc_out",
    "radio_dead",
    "master",
    "slave_one",
    "slave_two",
    "slave_three",
    "motor_temp_exceeded",
    "ambient_temp_exceeded",
    "overvoltage_detected",
    "lin_sls_detected",
    "lin_sls_missing",
    "battery",
    "oem_id",
    *(
        f"forced_initialisation_reference_{number}"
        for number in ("one", "two", "three", "four", "five", "six", "seven", "eight")
    ),
    "error_ref_input",
    "error_ref_feedback",
    "error_slave_reset",
)


@dataclass(frozen=True, slots=True)
class LinakErrorState:
    """Decoded diagnostic characteristic state."""

    code: int
    name: str
    payload: bytes


def decode_error(data: bytes | bytearray) -> LinakErrorState | None:
    """Decode the type-one Linak error payload, or None for no active error."""
    if len(data) < 3:
        return None
    error_type = int.from_bytes(data[:2], "little")
    if error_type != 1:
        raise ValueError(f"Unsupported Linak error type {error_type}")
    code = data[2]
    if code == 0:
        return None
    if code > len(LINAK_ERROR_NAMES):
        raise ValueError(f"Unknown Linak error code {code}")
    return LinakErrorState(code, LINAK_ERROR_NAMES[code - 1], bytes(data[2:]))


class LinakAlarmAction(StrEnum):
    """Actions accepted by the Bed Control timer characteristic."""

    MEMORY_1 = "memory_1"
    MEMORY_2 = "memory_2"
    MEMORY_3 = "memory_3"
    MEMORY_4 = "memory_4"
    LIGHT_TOGGLE = "light_toggle"
    MASSAGE_TOGGLE = "massage_toggle"


LINAK_ALARM_ACTION_OPCODES: Final[dict[LinakAlarmAction, int]] = {
    LinakAlarmAction.MEMORY_1: 0x0E,
    LinakAlarmAction.MEMORY_2: 0x0F,
    LinakAlarmAction.MEMORY_3: 0x0C,
    LinakAlarmAction.MEMORY_4: 0x44,
    LinakAlarmAction.LIGHT_TOGGLE: 0x94,
    LinakAlarmAction.MASSAGE_TOGGLE: 0x91,
}
LINAK_ALARM_ACTIONS_BY_OPCODE: Final = {
    opcode: action for action, opcode in LINAK_ALARM_ACTION_OPCODES.items()
}


@dataclass(frozen=True, slots=True)
class LinakAlarmStep:
    """One action in a timer event."""

    action: LinakAlarmAction
    lifetime: int = 1
    pause: int = 0


def build_timer_event(seconds: int, actions: Sequence[LinakAlarmStep]) -> bytes:
    """Build a timer event with one to four actions."""
    if not 0 <= seconds <= 0x1FFFF:
        raise ValueError("Linak alarm seconds must be between 0 and 131071")
    if not 1 <= len(actions) <= 4:
        raise ValueError("Linak alarms require between 1 and 4 actions")
    # The app writes a fixed event marker of 1 here even when it appends two to
    # four action records. It is not an action-count field.
    payload = bytearray((1 if seconds > 0xFFFF else 0, seconds & 0xFF, (seconds >> 8) & 0xFF, 1))
    for step in actions:
        if not 0 <= step.lifetime <= 0xFF or not 0 <= step.pause <= 0xFF:
            raise ValueError("Linak alarm lifetime and pause must fit in one byte")
        payload.extend((LINAK_ALARM_ACTION_OPCODES[step.action], 0, step.lifetime, step.pause))
    return bytes(payload)


def build_timer_recurrence(count: int, minutes: int) -> bytes:
    """Build the packed timer recurrence packet."""
    if not 0 <= count <= 31:
        raise ValueError("Linak recurrence count must be between 0 and 31")
    if not 0 <= minutes <= 2047:
        raise ValueError("Linak recurrence minutes must be between 0 and 2047")
    packed = ((count & 0x1F) << 11) | (minutes & 0x07FF)
    return bytes((0x10, packed & 0xFF, packed >> 8))


@dataclass(frozen=True, slots=True)
class LinakTimerState:
    """Decoded timer notification/readback."""

    status: str
    timer_index: int | None = None
    enabled: bool | None = None
    seconds: int | None = None
    first_action: LinakAlarmStep | None = None
    error_code: int | None = None


LINAK_TIMER_ERRORS: Final[dict[int, str]] = {
    1: "unsupported_action",
    2: "illegal_length",
    3: "illegal_event_action",
    4: "illegal_recurrence",
}


def decode_timer(data: bytes | bytearray) -> LinakTimerState:
    """Decode timer info, lifecycle events, and timer errors."""
    if not data:
        raise ValueError("Linak timer data is empty")
    event = data[0]
    if event in (0x20, 0x21):
        if len(data) < 4:
            raise ValueError("Linak timer info is truncated")
        seconds = ((event & 1) << 16) | data[1] | (data[2] << 8)
        first_action = None
        if len(data) >= 8:
            action = LINAK_ALARM_ACTIONS_BY_OPCODE.get(data[4])
            if action is None:
                raise ValueError(f"Unknown Linak timer action opcode {data[4]}")
            first_action = LinakAlarmStep(action, data[6], data[7])
        return LinakTimerState(
            status="scheduled" if seconds else "disabled",
            enabled=seconds > 0,
            seconds=seconds,
            first_action=first_action,
        )
    if 0x80 <= event <= 0x83:
        return LinakTimerState("elapsed", timer_index=event - 0x80 + 1)
    if 0x90 <= event <= 0x93:
        return LinakTimerState("interrupted", timer_index=event - 0x90 + 1)
    if 0xA0 <= event <= 0xA3:
        return LinakTimerState("action_done", timer_index=event - 0xA0 + 1)
    if event == 0xFF:
        if len(data) < 2 or data[1] not in LINAK_TIMER_ERRORS:
            raise ValueError("Unknown or truncated Linak timer error")
        return LinakTimerState(f"error_{LINAK_TIMER_ERRORS[data[1]]}", error_code=data[1])
    raise ValueError(f"Unknown Linak timer event 0x{event:02x}")


def build_automatic_drive(enabled: bool) -> bytes:
    """Build the five-byte automatic-drive configuration packet."""
    return bytes((0x89, 0x3B, 0x80, 0x00, int(enabled)))


_SIMULTANEOUS_BASES: Final[dict[tuple[str, str], int]] = {
    ("base", "feet"): 0x10,
    ("base", "head"): 0x11,
    ("base", "legs"): 0x12,
    ("base", "back"): 0x13,
    ("feet", "head"): 0x20,
    ("feet", "legs"): 0x21,
    ("feet", "back"): 0x22,
    ("head", "legs"): 0x2C,
    ("head", "back"): 0x2D,
    ("legs", "back"): 0x34,
}
_AXIS_ORDER: Final[dict[str, int]] = {
    axis: index for index, axis in enumerate(("base", "feet", "head", "legs", "back"))
}


def build_simultaneous_command(
    first_axis: str,
    first_up: bool,
    second_axis: str,
    second_up: bool,
) -> bytes:
    """Build one of the 40 reachable two-section movement commands."""
    if first_axis == second_axis:
        raise ValueError("Linak simultaneous movement requires two different axes")
    try:
        if _AXIS_ORDER[first_axis] > _AXIS_ORDER[second_axis]:
            first_axis, second_axis = second_axis, first_axis
            first_up, second_up = second_up, first_up
        base = _SIMULTANEOUS_BASES[(first_axis, second_axis)]
    except KeyError as err:
        raise ValueError(
            f"Unsupported Linak simultaneous axes: {first_axis}, {second_axis}"
        ) from err

    second_offset = 0
    if (first_axis, second_axis)[0] == "base":
        second_offset = {"feet": 0, "head": 1, "legs": 2, "back": 3}[second_axis]
        base = 0x10 + second_offset
        direction_offset = (0x08 if first_up else 0) + (0x04 if second_up else 0)
    elif first_axis == "feet":
        second_offset = {"head": 0, "legs": 1, "back": 2}[second_axis]
        base = 0x20 + second_offset
        direction_offset = (0x06 if first_up else 0) + (0x03 if second_up else 0)
    elif first_axis == "head":
        second_offset = {"legs": 0, "back": 1}[second_axis]
        base = 0x2C + second_offset
        direction_offset = (0x04 if first_up else 0) + (0x02 if second_up else 0)
    else:
        direction_offset = (0x02 if first_up else 0) + (0x01 if second_up else 0)
    return bytes((base + direction_offset, 0))
