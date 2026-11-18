"""Entity specs a controller declares for the Home Assistant platforms."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import EntityCategory

from ..card import CARD_HIDDEN, CARD_UTILITY, CardPlacement
from ..controller_state import AnyStateKey, StateKey

if TYPE_CHECKING:
    from .base import BedController

MotorCommandCallable = Callable[["BedController"], Coroutine[Any, Any, None]]


@dataclass(frozen=True, slots=True)
class ControllerButtonSpec:
    """An app-labelled action whose physical semantics need no inferred axis."""

    key: str
    name: str
    press_fn: MotorCommandCallable
    icon: str = "mdi:gesture-tap"
    translation_key: str | None = None
    cancel_movement: bool = field(default=True, kw_only=True)
    scheduler_resource: str | None = field(default=None, kw_only=True)
    hold: ControllerHoldSpec | None = field(default=None, kw_only=True)
    # Untimed movement without a hold still invalidates travel-time estimates.
    invalidates_position: bool = field(default=False, kw_only=True)
    # Cancel held admission; only the held task owns its protocol release frame.
    release_only: bool = field(default=False, kw_only=True)
    # The native card asks before an explicit destructive/save action.
    requires_confirmation: bool = field(default=False, kw_only=True)
    # A maintenance action (e.g. a refresh for a bed that never pushes state):
    # a diagnostic entity, disabled by default.
    diagnostic: bool = field(default=False, kw_only=True)
    # Fills a translated name template, e.g. ``{action}``, with an app label.
    translation_placeholders: Mapping[str, str] | None = field(default=None, kw_only=True)
    card: CardPlacement = field(default=CARD_UTILITY, kw_only=True)


@dataclass(frozen=True, slots=True)
class ControllerSelectSpec:
    """An immutable controller-declared option control backed by published state."""

    key: str
    translation_key: str
    state_key: StateKey[str | None]
    options: tuple[str, ...]
    select_fn: Callable[[BedController, str], Awaitable[None]]
    # An app-local choice that sends no frame: applied without connecting.
    local_select_fn: Callable[[str], None] | None = field(default=None, kw_only=True)
    card: CardPlacement = field(default=CARD_UTILITY, kw_only=True)
    is_available: Callable[[BedController], bool] | None = field(default=None, kw_only=True)
    entity_category: EntityCategory | None = field(default=None, kw_only=True)
    entity_registry_enabled_default: bool = field(default=True, kw_only=True)


@dataclass(frozen=True, slots=True)
class ControllerNumberSpec:
    """An immutable controller-declared numeric control backed by published state."""

    key: str
    translation_key: str
    state_key: StateKey[int | None] | StateKey[float | None]
    native_min_value: float
    native_max_value: float
    native_step: float
    set_fn: Callable[[BedController, float], Awaitable[None]]
    native_unit_of_measurement: str | None = None
    card: CardPlacement = field(default=CARD_UTILITY, kw_only=True)
    entity_category: EntityCategory | None = field(default=None, kw_only=True)
    entity_registry_enabled_default: bool = field(default=True, kw_only=True)


@dataclass(frozen=True, slots=True)
class ControllerSwitchSpec:
    """An immutable controller-declared on/off setting.

    ``state_key`` holds a bool, or a string equal to ``on_value`` when on;
    ``None`` (or a value of the wrong type) is unknown, so a controller clears
    connection-scoped settings by publishing ``None``. Without a state key the
    switch shows the last command it sent as assumed state until the link drops.
    """

    key: str
    translation_key: str
    set_fn: Callable[[BedController, bool], Awaitable[None]]
    state_key: StateKey[bool | None] | StateKey[str | None] | None = None
    on_value: bool | str = True
    icon: str | None = None
    # The published state echoes the last command rather than a bed readback.
    assumed_state: bool = field(default=False, kw_only=True)
    # A setting the integration keeps itself sends no frame: applied without connecting.
    local_set_fn: Callable[[bool], None] | None = field(default=None, kw_only=True)
    available_fn: Callable[[BedController], bool] | None = field(default=None, kw_only=True)
    entity_registry_enabled_default: bool = field(default=True, kw_only=True)
    entity_category: EntityCategory | None = field(default=None, kw_only=True)
    # Fills a translated name template, e.g. ``{side}``.
    translation_placeholders: Mapping[str, str] | None = field(default=None, kw_only=True)
    card: CardPlacement = field(default=CARD_UTILITY, kw_only=True)


@dataclass(frozen=True, slots=True)
class ProductButtonSpec(ControllerButtonSpec):
    """An optional product action with its own entity namespace."""

    icon: str = "mdi:gesture-tap-button"
    entity_registry_enabled_default: bool = False
    card: CardPlacement = field(default=CARD_HIDDEN, kw_only=True)


@dataclass(frozen=True, slots=True)
class ControllerActionSpec:
    """One ordered app action, including duplicate or arbitrary labels."""

    row_index: int
    name: str
    category: str
    duration_ms: int = 0
    frequency_ms: int = 0


@dataclass(frozen=True, slots=True)
class ControllerHoldSpec:
    """Timing around a controller-owned held action."""

    control: str
    start_delay_ms: int = 0
    release_delay_ms: int = 0
    release_button_key: str | None = None

    def __post_init__(self) -> None:
        _validate_hold_metadata(self.control, self.start_delay_ms, self.release_delay_ms)


@dataclass(frozen=True, slots=True)
class ControllerMotorHoldSpec:
    """Direction-specific controls for a bounded motor hold."""

    up_control: str
    down_control: str
    start_delay_ms: int = 0
    release_delay_ms: int = 0
    release_button_key: str | None = None
    stop_scope: Literal["motor", "side"] = field(default="motor", kw_only=True)
    # A cover or button press holds the control this long. None keeps the
    # plain motor route: the metadata then only describes the card's gesture.
    press_hold_ms: int | None = field(default=1000, kw_only=True)
    # The controller's hold prepares the motor and times the press itself, so a
    # press skips movement preparation and the card's start/release delays.
    press_is_native: bool = field(default=False, kw_only=True)

    def __post_init__(self) -> None:
        _validate_hold_metadata(self.up_control, self.start_delay_ms, self.release_delay_ms)
        _validate_hold_metadata(self.down_control, self.start_delay_ms, self.release_delay_ms)


def _validate_hold_metadata(control: str, start_delay_ms: int, release_delay_ms: int) -> None:
    if not isinstance(control, str) or not control:
        raise ValueError("Held control names must be non-empty strings")
    for name, delay in (
        ("start_delay_ms", start_delay_ms),
        ("release_delay_ms", release_delay_ms),
    ):
        if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
            raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class MotorControlSpec:
    """Describes a motor control surface exposed by a controller."""

    key: str
    translation_key: str
    open_fn: MotorCommandCallable
    close_fn: MotorCommandCallable
    stop_fn: MotorCommandCallable
    position_key: str | None = None
    max_angle: float = 68
    scheduler_resource: str | None = None
    hold: ControllerMotorHoldSpec | None = field(default=None, kw_only=True)
    # Logical sides drive the same physical actuator on a single receiver.
    shared_across_sides: bool = field(default=False, kw_only=True)


# Units a position slider can be scaled in.
POSITION_UNIT_PERCENT: Final = "%"
POSITION_UNIT_DEGREES: Final = "°"


@dataclass(frozen=True, slots=True)
class PositionNumberSpec:
    """Describes a position slider the controller exposes.

    Distinct from MotorControlSpec, which is about *movement* (and drives the
    cover entities): this describes a numeric position the bed can be told to
    seek. Values are fully resolved by the controller -- ``native_max_value``
    already accounts for the user's angle calibration where that applies -- so
    the number platform renders these without knowing any bed types.

    ``key`` names the entity while ``position_key`` names the axis to read from
    ``coordinator.position_data``; they differ on beds whose remote labels a
    motor differently from the axis its firmware reports (e.g. Keeson exposes
    "head" but reports it as "back").
    """

    key: str
    translation_key: str
    position_key: str
    icon: str
    native_max_value: float
    native_unit_of_measurement: str
    open_fn: MotorCommandCallable
    close_fn: MotorCommandCallable
    stop_fn: MotorCommandCallable
    # The motor (its cover's translation key) the slider sits with in the card.
    motor: str = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class ControllerStateSensorSpec:
    """Describe a sensor backed by coordinator controller state.

    Diagnostic unless the spec says otherwise; a unit implies a measurement.
    """

    key: str
    translation_key: str
    state_key: AnyStateKey
    icon: str
    native_unit_of_measurement: str | None = None
    attribute_keys: tuple[AnyStateKey, ...] = ()
    # Hidden unless the controller opts a user-facing value in explicitly.
    entity_registry_enabled_default: bool = False
    suggested_display_precision: int | None = None
    # Controller state is diagnostic; the card shows only what a spec places.
    card: CardPlacement = field(default=CARD_HIDDEN, kw_only=True)
    state_class: SensorStateClass | None = field(default=None, kw_only=True)
    entity_category: EntityCategory | None = field(
        default=EntityCategory.DIAGNOSTIC, kw_only=True
    )


@dataclass(frozen=True, slots=True)
class ControllerStateBinarySensorSpec:
    """Describe a binary sensor backed by coordinator controller state."""

    key: str
    translation_key: str
    state_key: AnyStateKey
    icon: str | None
    attribute_keys: tuple[AnyStateKey, ...] = ()
    # Hidden unless the controller opts a user-facing value in explicitly.
    entity_registry_enabled_default: bool = False
    card: CardPlacement = field(default=CARD_HIDDEN, kw_only=True)
    device_class: BinarySensorDeviceClass | None = field(default=None, kw_only=True)
    entity_category: EntityCategory | None = field(
        default=EntityCategory.DIAGNOSTIC, kw_only=True
    )


# Sleep-monitor readings: one shape and one name on every bed. ``side`` names a
# per-side reading ("Left heart rate"); a sensor for one sleeper has none.
type SleepSide = Literal["left", "right"] | None
type SleepRate = Literal["heart_rate", "breathing_rate"]
type SleepFlag = Literal["bed_presence", "snoring", "body_movement"]

_SLEEP_RATES: Final[dict[str, tuple[str, str]]] = {
    "heart_rate": ("mdi:heart-pulse", "bpm"),
    "breathing_rate": ("mdi:lungs", "breaths/min"),
}
_SLEEP_FLAGS: Final[dict[str, BinarySensorDeviceClass]] = {
    "bed_presence": BinarySensorDeviceClass.OCCUPANCY,
    "snoring": BinarySensorDeviceClass.SOUND,
    "body_movement": BinarySensorDeviceClass.MOTION,
}


def _sleep_translation_key(kind: str, side: SleepSide) -> str:
    return kind if side is None else f"{kind}_{side}"


def sleep_rate_sensor_spec(
    kind: SleepRate,
    key: str,
    state_key: StateKey[int | None],
    side: SleepSide = None,
    *,
    has_unit: bool = True,
    attribute_keys: tuple[AnyStateKey, ...] = (),
) -> ControllerStateSensorSpec:
    """A dashboard heart or breathing rate; unknown (``None``) while nobody is in bed.

    ``has_unit`` is False where the bed's unit is unproven.
    """
    icon, unit = _SLEEP_RATES[kind]
    return ControllerStateSensorSpec(
        key,
        _sleep_translation_key(kind, side),
        state_key,
        icon,
        native_unit_of_measurement=unit if has_unit else None,
        attribute_keys=attribute_keys,
        entity_registry_enabled_default=True,
        card=CARD_UTILITY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=None,
    )


def sleep_flag_binary_sensor_spec(
    kind: SleepFlag,
    key: str,
    state_key: StateKey[bool | None],
    side: SleepSide = None,
    *,
    attribute_keys: tuple[AnyStateKey, ...] = (),
) -> ControllerStateBinarySensorSpec:
    """A dashboard in-bed, snoring or body-movement reading."""
    return ControllerStateBinarySensorSpec(
        key,
        _sleep_translation_key(kind, side),
        state_key,
        None,
        attribute_keys=attribute_keys,
        entity_registry_enabled_default=True,
        card=CARD_UTILITY,
        device_class=_SLEEP_FLAGS[kind],
        entity_category=None,
    )


# Movement commands for the four standard position axes, so controllers can
# build sliders without restating the lambdas.
POSITION_AXIS_COMMANDS: Final[
    dict[str, tuple[MotorCommandCallable, MotorCommandCallable, MotorCommandCallable]]
] = {
    "back": (
        lambda ctrl: ctrl.move_back_up(),
        lambda ctrl: ctrl.move_back_down(),
        lambda ctrl: ctrl.move_back_stop(),
    ),
    "legs": (
        lambda ctrl: ctrl.move_legs_up(),
        lambda ctrl: ctrl.move_legs_down(),
        lambda ctrl: ctrl.move_legs_stop(),
    ),
    "head": (
        lambda ctrl: ctrl.move_head_up(),
        lambda ctrl: ctrl.move_head_down(),
        lambda ctrl: ctrl.move_head_stop(),
    ),
    "feet": (
        lambda ctrl: ctrl.move_feet_up(),
        lambda ctrl: ctrl.move_feet_down(),
        lambda ctrl: ctrl.move_feet_stop(),
    ),
    "lumbar": (
        lambda ctrl: ctrl.move_lumbar_up(),
        lambda ctrl: ctrl.move_lumbar_down(),
        lambda ctrl: ctrl.move_lumbar_stop(),
    ),
}

POSITION_AXIS_ICONS: Final[dict[str, str]] = {
    "back": "mdi:human-handsup",
    "legs": "mdi:human-handsdown",
    "head": "mdi:head",
    "feet": "mdi:foot-print",
    "lumbar": "mdi:human-handsup",
}


def build_position_number_spec(
    axis: str,
    *,
    max_value: float,
    unit: str,
    position_key: str | None = None,
    key: str | None = None,
    icon: str | None = None,
) -> PositionNumberSpec:
    """Build a slider for ``axis`` using that axis's standard commands and icon.

    ``position_key`` defaults to ``axis``; override it when the firmware reports
    the axis under a different name. ``key`` defaults to ``f"{axis}_position"``.
    """
    open_fn, close_fn, stop_fn = POSITION_AXIS_COMMANDS[axis]
    entity_key = key or f"{axis}_position"
    return PositionNumberSpec(
        key=entity_key,
        translation_key=entity_key,
        position_key=position_key or axis,
        icon=icon or POSITION_AXIS_ICONS.get(axis, "mdi:bed-outline"),
        native_max_value=max_value,
        native_unit_of_measurement=unit,
        open_fn=open_fn,
        close_fn=close_fn,
        stop_fn=stop_fn,
        motor=axis,
    )
