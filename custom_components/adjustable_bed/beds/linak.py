"""Linak bed controller implementation.

Reverse engineering by jascdk and Richard Hopton (smartbed-mqtt).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    LINAK_BACK_MAX_POSITION,
    LINAK_CONFIG_CHAR_UUID,
    LINAK_CONTROL_CHAR_UUID,
    LINAK_DEVICE_NAME_UUID,
    LINAK_ERROR_CHAR_UUID,
    LINAK_FEET_MAX_POSITION,
    LINAK_HEAD_MAX_POSITION,
    LINAK_LEG_MAX_POSITION,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_BASE_UUID,
    LINAK_POSITION_FEET_UUID,
    LINAK_POSITION_HEAD_UUID,
    LINAK_POSITION_LEG_UUID,
    LINAK_POSITION_MASK_UUID,
    LINAK_POSITION_SERVICE_UUID,
    LINAK_TIMER_CHAR_UUID,
    LINAK_TIMER_SERVICE_UUID,
)
from ..position_seek import PositionSeekPolicy, SeekSample
from .base import (
    POSITION_AXIS_COMMANDS,
    POSITION_UNIT_DEGREES,
    BedController,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .linak_protocol import (
    LinakAlarmStep,
    LinakCapabilitySnapshot,
    LinakModelVariant,
    LinakProfile,
    LinakReferenceState,
    build_automatic_drive,
    build_simultaneous_command,
    build_timer_event,
    build_timer_recurrence,
    decode_error,
    decode_reference,
    decode_timer,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

LINAK_CONTROL_READY_TIMEOUT_S = 6.0
LINAK_CONTROL_READY_RETRY_DELAY_S = 0.75
LINAK_PROTOCOL_READ_TIMEOUT_S = 0.75
LINAK_INITIAL_POSITION_RETRY_ATTEMPTS = 3
LINAK_INITIAL_POSITION_RETRY_DELAY_S = 0.75
LINAK_PASSIVE_POSITION_RECONCILIATION_INTERVAL_S = 120.0
LINAK_POSITION_SEEK_TOLERANCE = 0.3
LINAK_POSITION_SEEK_STALL_COUNT = 1
LINAK_POSITION_SEEK_REFRESH_INTERVAL_S = 0.1
LINAK_POSITION_SEEK_STALL_THRESHOLD = 0.2
LINAK_POSITION_SEEK_CACHED_FEEDBACK_MAX_AGE_S = 0.5
LINAK_DOWNWARD_STOP_LEAD_TIME_S = 0.4
LINAK_MAX_DOWNWARD_STOP_LEAD_DEGREES = 1.5
LINAK_LOWER_ENDPOINT_MAX_ANGLE_DEGREES = 1.1
LINAK_LOWER_ENDPOINT_STALL_CONFIRMATIONS = 2
LINAK_CONTROLLER_STATE_SENSOR_ENTITY_KEYS = frozenset(
    {
        "linak_protocol_error",
        "linak_alarm_status",
        *(f"linak_{axis}_reported_speed" for axis in ("base", "feet", "head", "legs", "back")),
    }
)
LINAK_CONTROLLER_STATE_BINARY_SENSOR_ENTITY_KEYS = frozenset({"linak_position_feedback_fault"})
LINAK_MEMORY_RECALL_DURATION_S = 30
LINAK_PERFORMANCE_HOLD_INTERVAL_MS = 300
LINAK_BED_CONTROL_HOLD_INTERVAL_MS = 100
LINAK_MASSAGE_ZONE_GAP_S = 0.1


@dataclass(frozen=True, slots=True)
class LinakPositionSpec:
    """Describe a Linak position characteristic and the logical axis it backs."""

    axis_name: str
    source_name: str
    uuid: str
    max_position: int
    max_angle: float


class LinakPositionSeekPolicy(PositionSeekPolicy):
    """Accept Linak's physically observed non-zero lower endpoint."""

    def __init__(self, controller: BedController) -> None:
        super().__init__(controller)
        self._last_lower_endpoint_stall: float | None = None
        self._lower_endpoint_stall_confirmations = 0

    @property
    def prefers_cached_position_feedback(self) -> bool:
        """Use the reference-output notifications already emitted during motion."""
        return True

    @property
    def cached_position_feedback_max_age(self) -> float:
        """Fall back to an explicit read if notifications stop arriving."""
        return LINAK_POSITION_SEEK_CACHED_FEEDBACK_MAX_AGE_S

    @staticmethod
    def _is_observed_lower_endpoint(sample: SeekSample) -> bool:
        """Return whether a sample sits on the lower travel limit of a 0° seek."""
        return (
            sample.target == 0.0
            and not sample.moving_up
            and 0.0 <= sample.current <= LINAK_LOWER_ENDPOINT_MAX_ANGLE_DEGREES
        )

    def _reset_lower_endpoint_stall(self) -> None:
        """Discard endpoint evidence after progress or an out-of-scope sample."""
        self._last_lower_endpoint_stall = None
        self._lower_endpoint_stall_confirmations = 0

    def accepts_position(self, sample: SeekSample) -> bool:
        """Apply endpoint bookkeeping and downward coast compensation."""
        previous_stall = self._last_lower_endpoint_stall
        if previous_stall is not None and (
            not self._is_observed_lower_endpoint(sample)
            or abs(sample.current - previous_stall) >= self.stall_threshold
        ):
            self._reset_lower_endpoint_stall()
        if super().accepts_position(sample):
            return True

        if sample.moving_up or sample.current <= sample.target:
            return False
        # A 0° seek cannot overshoot: the frame bottoms out on its end stop, so
        # releasing early only leaves it sitting a degree above flat.
        if sample.target <= 0.0:
            return False
        controller = self._controller
        if not isinstance(controller, LinakController):
            return False
        stop_lead = controller.downward_stop_lead(sample.position_key)
        if stop_lead is None:
            return False
        return sample.remaining <= min(stop_lead, LINAK_MAX_DOWNWARD_STOP_LEAD_DEGREES)

    def stall_completes_near_endpoint(self, sample: SeekSample) -> bool:
        """Accept only a persistent stall near the requested 0° hard limit."""
        if not self._is_observed_lower_endpoint(sample):
            self._reset_lower_endpoint_stall()
            return False

        previous_stall = self._last_lower_endpoint_stall
        if previous_stall is None or abs(sample.current - previous_stall) >= self.stall_threshold:
            self._lower_endpoint_stall_confirmations = 1
        else:
            self._lower_endpoint_stall_confirmations += 1
        self._last_lower_endpoint_stall = sample.current

        return self._lower_endpoint_stall_confirmations >= LINAK_LOWER_ENDPOINT_STALL_CONFIRMATIONS


class LinakCommands:
    """Linak command constants."""

    # Presets
    PRESET_MEMORY_1 = bytes([0x0E, 0x00])
    PRESET_MEMORY_2 = bytes([0x0F, 0x00])
    PRESET_MEMORY_3 = bytes([0x0C, 0x00])
    PRESET_MEMORY_4 = bytes([0x44, 0x00])

    # Program presets
    PROGRAM_MEMORY_1 = bytes([0x38, 0x00])
    PROGRAM_MEMORY_2 = bytes([0x39, 0x00])
    PROGRAM_MEMORY_3 = bytes([0x3A, 0x00])
    PROGRAM_MEMORY_4 = bytes([0x45, 0x00])

    # Under-bed lights
    LIGHTS_TOGGLE = bytes([0x94, 0x00])

    # Massage - all
    MASSAGE_ALL_OFF = bytes([0x80, 0x00])
    MASSAGE_ALL_UP = bytes([0xA8, 0x00])
    MASSAGE_ALL_DOWN = bytes([0xA9, 0x00])

    # Massage - head
    MASSAGE_HEAD_UP = bytes([0x8D, 0x00])
    MASSAGE_HEAD_DOWN = bytes([0x8E, 0x00])

    # Massage - foot
    MASSAGE_FOOT_UP = bytes([0x8F, 0x00])
    MASSAGE_FOOT_DOWN = bytes([0x90, 0x00])

    # Massage mode
    MASSAGE_MODE_STEP = bytes([0x81, 0x00])
    MASSAGE_WAVE_FREQUENCY_UP = bytes([0x87, 0x00])
    MASSAGE_WAVE_FREQUENCY_DOWN = bytes([0x88, 0x00])
    MASSAGE_ZONE_1_ON = bytes([0x89, 0x00])
    MASSAGE_ZONE_1_OFF = bytes([0x8A, 0x00])
    MASSAGE_ZONE_2_ON = bytes([0x8B, 0x00])
    MASSAGE_ZONE_2_OFF = bytes([0x8C, 0x00])
    # Legacy Performance profile massage start/toggle frame.
    MASSAGE_PERFORMANCE_START = bytes([0x91, 0x00])
    IMPULSE_TOGGLE = bytes([0x4D, 0x00])
    RESET_DEFAULTS = bytes([0x4E, 0x00])
    FACTORY_RESET = bytes([0x7F, 0x3E, 0x80])
    WAKE = bytes([0xFE, 0x00])
    # Bed Control alarm transaction terminator.
    TIMER_COMMIT = bytes([0x20])

    # Motor movement commands
    # Note: 0x00 is INITIALIZE_DOWN, not stop. 0xFF is the correct stop command.
    # Using 0x00 can cause a brief reverse movement.
    MOVE_STOP = bytes([0xFF, 0x00])
    # Legacy Performance uses the same release opcode as a one-byte frame.
    PERFORMANCE_RELEASE = bytes([0xFF])
    MOVE_ALL_DOWN = bytes([0x00, 0x00])
    MOVE_ALL_UP = bytes([0x01, 0x00])
    MOVE_BASE_DOWN = bytes([0x06, 0x00])
    MOVE_BASE_UP = bytes([0x07, 0x00])

    # Individual motor control
    MOVE_HEAD_UP = bytes([0x03, 0x00])
    MOVE_HEAD_DOWN = bytes([0x02, 0x00])
    MOVE_FEET_UP = bytes([0x05, 0x00])
    MOVE_FEET_DOWN = bytes([0x04, 0x00])
    MOVE_LEGS_UP = bytes([0x09, 0x00])
    MOVE_LEGS_DOWN = bytes([0x08, 0x00])
    MOVE_BACK_UP = bytes([0x0B, 0x00])
    MOVE_BACK_DOWN = bytes([0x0A, 0x00])


class LinakController(BedController):
    """Controller for Linak beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: LinakProfile = LinakProfile.BED_CONTROL,
        capability_snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the Linak controller."""
        super().__init__(coordinator)
        self._profile = profile
        self._capabilities = LinakCapabilitySnapshot.from_mapping(
            capability_snapshot,
            profile=profile,
        )
        if profile is LinakProfile.PERFORMANCE:
            self._capabilities = LinakCapabilitySnapshot(
                profile=profile,
                discovery_complete=True,
            )
        self._notify_callback: Callable[[str, float], None] | None = None
        self._notify_handles: dict[str, int] = {}
        self._active_position_notifications: set[str] = set()
        self._deferred_position_notifications: set[str] = set()
        self._resolved_two_motor_secondary_spec: LinakPositionSpec | None = None
        self._session_ready = False
        self._session_started_monotonic = monotonic()
        self._protocol_notification_uuids: set[str] = set()
        self._deferred_protocol_notifications: set[str] = set()
        self._capability_discovery_deferred = False
        self._timer_candidate = False
        self._performance_wave_active = False
        self._publish_capability_state()
        _LOGGER.debug(
            "LinakController initialized (motor_count: %d, profile: %s)",
            coordinator.motor_count,
            profile.value,
        )

    @property
    def supports_preset_flat(self) -> bool:
        """Return True for the app's native held flat/init-down command."""
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - Linak beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False because current apps expose only AUX/light toggle."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return whether the resolved app profile exposes memory recall."""
        return self.memory_slot_count > 0

    @property
    def auto_stops_on_idle(self) -> bool:
        """Return False because current Linak apps send an explicit release.

        The reverse movement reported in issue #45 came from sending 0x00,
        which is the all-down command. The protocol's STOP/release frame is
        0xFF 0x00.
        """
        return False

    @property
    def reverses_position_seek_on_overshoot(self) -> bool:
        """Return False - Linak seek steps are full pulses, so reversal hunts."""
        return False

    @property
    def uses_custom_position_seek_steps(self) -> bool:
        """Return True - Linak seek steps should use short remote-like pulses."""
        return True

    @property
    def position_seek_tolerance(self) -> float:
        """Return a tighter tolerance for Linak angle seeking."""
        return LINAK_POSITION_SEEK_TOLERANCE

    @property
    def position_seek_stall_count(self) -> int:
        """Return a faster reissue threshold so Linak pulses chain smoothly."""
        return LINAK_POSITION_SEEK_STALL_COUNT

    @property
    def position_seek_check_interval(self) -> float:
        """Match Bed Control's 100 ms held-command refresh cadence."""
        return LINAK_POSITION_SEEK_REFRESH_INTERVAL_S

    @property
    def position_seek_stall_threshold(self) -> float:
        """Return a smaller movement threshold for Linak angle feedback."""
        return LINAK_POSITION_SEEK_STALL_THRESHOLD

    @property
    def position_seek_policy(self) -> PositionSeekPolicy:
        """Return Linak's lower-endpoint-aware seek policy."""
        return LinakPositionSeekPolicy(self)

    @property
    def chains_position_seek_steps_while_moving(self) -> bool:
        """Keep feeding Linak seek bursts while the motor is still advancing."""
        return True

    @property
    def position_seek_chain_min_remaining_distance(self) -> float:
        """Keep refreshing movement until feedback enters the target band."""
        return LINAK_POSITION_SEEK_TOLERANCE

    @property
    def passive_position_reconciliation_interval(self) -> float | None:
        """Return a low-frequency idle read interval for out-of-band movement."""
        if not self.supports_position_feedback:
            return None
        return LINAK_PASSIVE_POSITION_RECONCILIATION_INTERVAL_S

    @property
    def allow_position_polling_during_commands(self) -> bool:
        """Return False - position reads can interrupt Linak's pulse stream."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return the resolved app-visible memory capacity."""
        return self._capabilities.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Linak beds support programming memory positions."""
        return self.memory_slot_count > 0

    @property
    def supports_position_feedback(self) -> bool:
        """Return whether an advanced Bed Control mask selected reference outputs."""
        return bool(self._capabilities.position_axes)

    @property
    def requires_notification_channel(self) -> bool:
        """Keep protocol error/timer notifications active without angle sensing."""
        return True

    @property
    def supports_preset_both_up(self) -> bool:
        """Return True for the native held all-up command."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_massage(self) -> bool:
        """Return True because both reachable Linak app profiles expose massage."""
        return True

    @property
    def auto_enable_massage(self) -> bool:
        """Legacy Performance is a massage-specific profile; Bed Control is configured."""
        return self._profile is LinakProfile.PERFORMANCE

    @property
    def supports_massage_off_control(self) -> bool:
        """Return whether the selected app profile defines an all-off command."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_massage_toggle_control(self) -> bool:
        """Return True because both app profiles expose a start/toggle action."""
        return True

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        """Return whether the profile exposes all-zone intensity steps."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        """Return whether the profile exposes app-reachable zone selection."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        """Return whether the profile exposes app-reachable zone selection."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_massage_mode_step_control(self) -> bool:
        """Return True for the wave-mode toggle reachable in both profiles."""
        return True

    @property
    def supports_massage_wave_frequency_control(self) -> bool:
        """Return whether legacy Performance exposes wave-frequency steps."""
        return self._profile is LinakProfile.PERFORMANCE

    @property
    def supports_impulse_control(self) -> bool:
        """Return whether legacy Performance exposes impulse mode."""
        return self._profile is LinakProfile.PERFORMANCE

    @property
    def supports_reset_defaults(self) -> bool:
        """Return True because both BLE app profiles expose reset."""
        return True

    @property
    def supports_factory_reset(self) -> bool:
        """Return whether the direct-BLE Bed Connect path exposes factory reset."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_wake_control(self) -> bool:
        """Return whether modern Bed Control exposes its wake command."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_automatic_drive(self) -> bool:
        """Return whether modern Bed Control exposes automatic-drive config."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def has_bed_height_support(self) -> bool:
        """Return whether the advanced mask exposes the BASE actuator."""
        return "base" in self._capabilities.position_axes

    @property
    def supports_alarm(self) -> bool:
        """Return whether timer subscription promoted this advanced model."""
        return self._capabilities.timer_supported

    @property
    def supports_device_rename(self) -> bool:
        """Return whether the modern Bed Control profile exposes Generic Access rename."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def supports_simultaneous_movement(self) -> bool:
        """Return whether the modern profile exposes two-section opcodes."""
        return self._profile is LinakProfile.BED_CONTROL

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        """Return only axes exposed by the resolved model or configured layout."""
        if not self.supports_simultaneous_movement:
            return ()
        if self._capabilities.position_axes:
            return self._capabilities.position_axes
        return tuple(
            "base" if spec.key == "bed_height" else spec.key for spec in super().motor_control_specs
        )

    @property
    def _stop_command(self) -> bytes:
        """Return the profile-specific release frame."""
        if self._profile is LinakProfile.PERFORMANCE:
            return LinakCommands.PERFORMANCE_RELEASE
        return LinakCommands.MOVE_STOP

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Use the legacy app's 300 ms cadence without changing hold duration."""
        pulse_count, pulse_delay = super().motor_pulse_settings()
        if self._profile is LinakProfile.BED_CONTROL:
            return pulse_count, pulse_delay
        duration_ms = max(0, pulse_count - 1) * pulse_delay
        adjusted_count = max(
            1,
            (duration_ms + LINAK_PERFORMANCE_HOLD_INTERVAL_MS - 1)
            // LINAK_PERFORMANCE_HOLD_INTERVAL_MS
            + 1,
        )
        return adjusted_count, LINAK_PERFORMANCE_HOLD_INTERVAL_MS

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        """Return the resolved profile, model variant, mask, and alarm state."""
        return {
            **self._capabilities.as_dict(),
            "position_axes": list(self._capabilities.position_axes),
            "timer_candidate": self._timer_candidate,
        }

    def capability_snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot for offline entity gating."""
        return self._capabilities.as_dict()

    def _publish_capability_state(self) -> None:
        """Publish capability state used by diagnostics entities."""
        self.forward_controller_state_updates(
            {
                "linak_profile": self._profile.value,
                "linak_model_variant": (
                    self._profile.value
                    if self._profile is LinakProfile.PERFORMANCE
                    else self._capabilities.model_variant.value
                ),
                "linak_actuator_mask": self._capabilities.actuator_mask,
                "linak_position_axes": list(self._capabilities.position_axes),
                "linak_alarm_supported": self._capabilities.timer_supported,
            }
        )

    def _has_service(self, uuid: str) -> bool:
        """Return whether the connected GATT collection contains a service UUID."""
        if self.client is None or self.client.services is None:
            return False
        services = self.client.services
        getter = getattr(services, "get_service", None)
        if callable(getter):
            try:
                return getter(uuid) is not None
            except KeyError, BleakError:
                pass
        return any(
            str(getattr(service, "uuid", "")).lower() == uuid.lower() for service in services
        )

    async def async_discover_capabilities(self) -> None:
        """Resolve Standard, TD3, and Advanced from services and mask byte 0."""
        if self._profile is LinakProfile.PERFORMANCE:
            self._capability_discovery_deferred = False
            self._publish_capability_state()
            return
        if self.client is None or not self.client.is_connected:
            return

        self._capability_discovery_deferred = False
        if not self._has_service(LINAK_POSITION_SERVICE_UUID):
            self._capabilities = LinakCapabilitySnapshot(
                profile=self._profile,
                model_variant=LinakModelVariant.STANDARD,
                discovery_complete=True,
            )
            self._timer_candidate = False
            self._publish_capability_state()
            return

        self._timer_candidate = self._has_service(LINAK_TIMER_SERVICE_UUID)
        try:
            async with self._ble_lock:
                data = await self.client.read_gatt_char(LINAK_POSITION_MASK_UUID)
            if not data:
                raise ValueError("Linak capability mask is empty")
        except BleakError as err:
            if self._is_authentication_window_error(err):
                self._capability_discovery_deferred = True
                _LOGGER.debug(
                    "Deferring Linak capability-mask discovery until control is ready: %s",
                    err,
                )
            else:
                _LOGGER.warning(
                    "Could not resolve Linak capability mask for %s; retaining cached capabilities: %s",
                    self._coordinator.address,
                    err,
                )
            self._publish_capability_state()
            return
        except (TimeoutError, ValueError) as err:
            _LOGGER.warning(
                "Could not resolve Linak capability mask for %s; retaining cached capabilities: %s",
                self._coordinator.address,
                err,
            )
            self._publish_capability_state()
            return

        mask = data[0]
        self._capabilities = LinakCapabilitySnapshot(
            profile=self._profile,
            model_variant=(LinakModelVariant.TD3 if mask == 0 else LinakModelVariant.ADVANCED),
            actuator_mask=mask,
            discovery_complete=True,
        )
        self._publish_capability_state()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        """Expose parsed speed, errors, and timer state."""
        specs: list[ControllerStateSensorSpec] = []
        if self._profile is LinakProfile.BED_CONTROL:
            specs.append(
                ControllerStateSensorSpec(
                    key="linak_protocol_error",
                    translation_key="linak_protocol_error",
                    state_key="linak_protocol_error",
                    icon="mdi:alert-circle-outline",
                    attribute_keys=(
                        "linak_protocol_error_code",
                        "linak_protocol_error_payload",
                    ),
                )
            )
        for axis in self._capabilities.position_axes:
            specs.append(
                ControllerStateSensorSpec(
                    key=f"linak_{axis}_reported_speed",
                    translation_key=f"linak_{axis}_reported_speed",
                    state_key=f"linak_{axis}_reported_speed",
                    icon="mdi:speedometer",
                    attribute_keys=(
                        f"linak_{axis}_raw_speed",
                        f"linak_{axis}_speed_direction",
                        f"linak_{axis}_extension",
                        f"linak_{axis}_status_flags",
                        f"linak_{axis}_sls",
                        f"linak_{axis}_end_position_up",
                        f"linak_{axis}_end_position_down",
                        f"linak_{axis}_position_lost",
                    ),
                    suggested_display_precision=3,
                )
            )
        if self.supports_alarm:
            specs.append(
                ControllerStateSensorSpec(
                    key="linak_alarm_status",
                    translation_key="linak_alarm_status",
                    state_key="linak_alarm_status",
                    icon="mdi:alarm",
                    attribute_keys=(
                        "linak_alarm_timer_index",
                        "linak_alarm_enabled",
                        "linak_alarm_seconds",
                        "linak_alarm_first_action",
                        "linak_alarm_lifetime",
                        "linak_alarm_pause",
                        "linak_alarm_error_code",
                    ),
                )
            )
        return tuple(specs)

    @property
    def controller_state_binary_sensor_specs(
        self,
    ) -> tuple[ControllerStateBinarySensorSpec, ...]:
        """Expose one aggregate position-lost diagnostic."""
        if not self._capabilities.position_axes:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="linak_position_feedback_fault",
                translation_key="linak_position_feedback_fault",
                state_key="linak_position_feedback_fault",
                icon="mdi:alert",
                attribute_keys=("linak_fault_axes",),
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        """Remove diagnostics omitted by the current profile and capability mask."""
        active = {spec.key for spec in self.controller_state_sensor_specs}
        return LINAK_CONTROLLER_STATE_SENSOR_ENTITY_KEYS - active

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        """Remove the aggregate feedback fault when no reference axes remain."""
        active = {spec.key for spec in self.controller_state_binary_sensor_specs}
        return LINAK_CONTROLLER_STATE_BINARY_SENSOR_ENTITY_KEYS - active

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        """Return sliders only for reference-output axes with calibrated angles."""
        return tuple(
            build_position_number_spec(
                axis,
                max_value=self._coordinator.get_max_angle(axis),
                unit=POSITION_UNIT_DEGREES,
            )
            for axis in self._capabilities.position_axes
            if axis in {"back", "legs", "head", "feet"}
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Use the advanced mask for exact axes, with BASE mapped to bed height."""
        if not self._capabilities.position_axes:
            return super().motor_control_specs
        specs: list[MotorControlSpec] = []
        for axis in self._capabilities.position_axes:
            if axis == "base":
                specs.append(
                    MotorControlSpec(
                        key="bed_height",
                        translation_key="bed_height",
                        open_fn=lambda ctrl: ctrl.move_bed_height_up(),
                        close_fn=lambda ctrl: ctrl.move_bed_height_down(),
                        stop_fn=lambda ctrl: ctrl.move_bed_height_stop(),
                    )
                )
                continue
            open_fn, close_fn, stop_fn = POSITION_AXIS_COMMANDS[axis]
            specs.append(
                MotorControlSpec(
                    key=axis,
                    translation_key=axis,
                    open_fn=open_fn,
                    close_fn=close_fn,
                    stop_fn=stop_fn,
                    position_key=axis,
                    max_angle=self._coordinator.get_max_angle(axis),
                )
            )
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Clean up covers omitted by the current Linak actuator mask or profile."""
        return frozenset({"back", "legs", "head", "feet", "bed_height"})

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LINAK_CONTROL_CHAR_UUID

    @staticmethod
    def _is_authentication_window_error(err: BleakError) -> bool:
        """Return True when Linak rejects writes during early session setup."""
        message = str(err).lower()
        return "insufficient authentication" in message or "error=5" in message

    def _make_position_handler(self, spec: LinakPositionSpec) -> Callable[[Any, bytearray], None]:
        """Build a notification callback for a Linak position characteristic."""

        def handler(_: Any, data: bytearray) -> None:
            angle = self._decode_position_data(
                spec.source_name,
                data,
                spec.max_position,
                spec.max_angle,
            )
            if angle is None:
                return

            _LOGGER.debug(
                "Notification received for %s: raw_data=%s (%d bytes)",
                spec.source_name,
                data.hex(),
                len(data),
            )
            self.forward_raw_notification(spec.uuid, bytes(data))
            self._maybe_resolve_two_motor_secondary_notification(spec)
            if self._notify_callback:
                self._notify_callback(spec.axis_name, angle)

        return handler

    def _handle_error_data(self, data: bytes | bytearray) -> None:
        """Parse and publish the control-error characteristic."""
        try:
            error = decode_error(data)
        except ValueError as err:
            _LOGGER.warning("Ignoring invalid Linak error payload %s: %s", bytes(data).hex(), err)
            return
        if error is None:
            self.forward_controller_state_updates(
                {
                    "linak_protocol_error": "none",
                    "linak_protocol_error_code": 0,
                    "linak_protocol_error_payload": "",
                }
            )
            return
        self.forward_controller_state_updates(
            {
                "linak_protocol_error": error.name,
                "linak_protocol_error_code": error.code,
                "linak_protocol_error_payload": error.payload.hex(),
            }
        )

    def _make_error_handler(self) -> Callable[[Any, bytearray], None]:
        """Build the control-error notification handler."""

        def handler(_: Any, data: bytearray) -> None:
            self.forward_raw_notification(LINAK_ERROR_CHAR_UUID, bytes(data))
            self._handle_error_data(data)

        return handler

    def _make_performance_notify_handler(self) -> Callable[[Any, bytearray], None]:
        """Forward legacy notifications without inventing payload semantics."""

        def handler(_: Any, data: bytearray) -> None:
            self.forward_raw_notification(LINAK_ERROR_CHAR_UUID, bytes(data))

        return handler

    def _make_config_handler(self) -> Callable[[Any, bytearray], None]:
        """Build the raw configuration notification handler."""

        def handler(_: Any, data: bytearray) -> None:
            self.forward_raw_notification(LINAK_CONFIG_CHAR_UUID, bytes(data))

        return handler

    def _handle_timer_data(self, data: bytes | bytearray) -> None:
        """Parse and publish timer info and lifecycle events."""
        try:
            timer = decode_timer(data)
        except ValueError as err:
            _LOGGER.warning("Ignoring invalid Linak timer payload %s: %s", bytes(data).hex(), err)
            return
        first_action = timer.first_action
        self.forward_controller_state_updates(
            {
                "linak_alarm_status": timer.status,
                "linak_alarm_timer_index": timer.timer_index,
                "linak_alarm_enabled": timer.enabled,
                "linak_alarm_seconds": timer.seconds,
                "linak_alarm_first_action": (
                    first_action.action.value if first_action is not None else None
                ),
                "linak_alarm_lifetime": (
                    first_action.lifetime if first_action is not None else None
                ),
                "linak_alarm_pause": first_action.pause if first_action is not None else None,
                "linak_alarm_error_code": timer.error_code,
            }
        )

    def _make_timer_handler(self) -> Callable[[Any, bytearray], None]:
        """Build the timer notification handler."""

        def handler(_: Any, data: bytearray) -> None:
            self.forward_raw_notification(LINAK_TIMER_CHAR_UUID, bytes(data))
            self._handle_timer_data(data)

        return handler

    async def _subscribe_protocol_characteristic(
        self,
        uuid: str,
        handler: Callable[[Any, bytearray], None],
    ) -> bool:
        """Subscribe once to a non-position protocol characteristic."""
        if uuid in self._protocol_notification_uuids:
            return True
        if self.client is None or not self.client.is_connected:
            return False
        try:
            async with self._ble_lock:
                await self.client.start_notify(uuid, handler)
        except BleakError as err:
            if self._is_authentication_window_error(err):
                self._deferred_protocol_notifications.add(uuid)
                _LOGGER.debug(
                    "Deferring Linak characteristic %s until control is ready: %s",
                    uuid,
                    err,
                )
                return False
            self._deferred_protocol_notifications.discard(uuid)
            _LOGGER.debug("Could not subscribe to Linak characteristic %s: %s", uuid, err)
            return False
        self._protocol_notification_uuids.add(uuid)
        self._deferred_protocol_notifications.discard(uuid)
        return True

    async def _read_protocol_characteristic(
        self,
        uuid: str,
        handler: Callable[[bytes | bytearray], None],
    ) -> None:
        """Best-effort initial read for a subscribed protocol characteristic."""
        if self.client is None or not self.client.is_connected:
            return
        try:
            async with asyncio.timeout(LINAK_PROTOCOL_READ_TIMEOUT_S):
                async with self._ble_lock:
                    data = await self.client.read_gatt_char(uuid)
        except (BleakError, TimeoutError) as err:
            _LOGGER.debug("Could not read Linak characteristic %s: %s", uuid, err)
            return
        if data:
            handler(data)

    async def _start_protocol_notifications(self) -> None:
        """Start mandatory error/config and conditional timer channels."""
        error_handler = (
            self._make_performance_notify_handler()
            if self._profile is LinakProfile.PERFORMANCE
            else self._make_error_handler()
        )
        error_ready = await self._subscribe_protocol_characteristic(
            LINAK_ERROR_CHAR_UUID,
            error_handler,
        )
        if error_ready and self._profile is LinakProfile.BED_CONTROL:
            await self._read_protocol_characteristic(
                LINAK_ERROR_CHAR_UUID,
                self._handle_error_data,
            )

        if self._profile is LinakProfile.BED_CONTROL:
            await self._subscribe_protocol_characteristic(
                LINAK_CONFIG_CHAR_UUID,
                self._make_config_handler(),
            )

        if not self._timer_candidate:
            return
        timer_ready = await self._subscribe_protocol_characteristic(
            LINAK_TIMER_CHAR_UUID,
            self._make_timer_handler(),
        )
        if not timer_ready:
            return
        self._capabilities = LinakCapabilitySnapshot(
            profile=self._profile,
            model_variant=LinakModelVariant.ADVANCED_WITH_ALARM,
            actuator_mask=self._capabilities.actuator_mask,
            timer_supported=True,
            discovery_complete=True,
        )
        self._publish_capability_state()
        await self._read_protocol_characteristic(
            LINAK_TIMER_CHAR_UUID,
            self._handle_timer_data,
        )

    def _back_position_spec(self) -> LinakPositionSpec:
        """Return the Linak back/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="back",
            source_name="back",
            uuid=LINAK_POSITION_BACK_UUID,
            max_position=LINAK_BACK_MAX_POSITION,
            max_angle=self._coordinator.back_max_angle,
        )

    def _base_position_spec(self) -> LinakPositionSpec:
        """Return BASE reference output as raw bed-height feedback."""
        return LinakPositionSpec(
            axis_name="base",
            source_name="base",
            uuid=LINAK_POSITION_BASE_UUID,
            max_position=0xFFFF,
            max_angle=0,
        )

    def _legs_position_spec(self) -> LinakPositionSpec:
        """Return the default Linak legs/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="legs",
            source_name="legs",
            uuid=LINAK_POSITION_LEG_UUID,
            max_position=LINAK_LEG_MAX_POSITION,
            max_angle=self._coordinator.legs_max_angle,
        )

    def _head_position_spec(self) -> LinakPositionSpec:
        """Return the Linak head/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="head",
            source_name="head",
            uuid=LINAK_POSITION_HEAD_UUID,
            max_position=LINAK_HEAD_MAX_POSITION,
            max_angle=self._coordinator.head_max_angle,
        )

    def _feet_position_spec(self) -> LinakPositionSpec:
        """Return the Linak foot/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="feet",
            source_name="feet",
            uuid=LINAK_POSITION_FEET_UUID,
            max_position=LINAK_FEET_MAX_POSITION,
            max_angle=self._coordinator.feet_max_angle,
        )

    def _two_motor_secondary_spec(self) -> LinakPositionSpec:
        """Return the currently resolved second actuator for a 2-motor bed."""
        return self._resolved_two_motor_secondary_spec or self._legs_position_spec()

    def _two_motor_secondary_candidates(self) -> list[LinakPositionSpec]:
        """Return candidate Linak reference outputs for the second 2-motor actuator."""
        return [
            self._legs_position_spec(),
            LinakPositionSpec(
                axis_name="legs",
                source_name="feet",
                uuid=LINAK_POSITION_FEET_UUID,
                max_position=LINAK_FEET_MAX_POSITION,
                max_angle=self._coordinator.legs_max_angle,
            ),
            LinakPositionSpec(
                axis_name="legs",
                source_name="head",
                uuid=LINAK_POSITION_HEAD_UUID,
                max_position=LINAK_HEAD_MAX_POSITION,
                max_angle=self._coordinator.legs_max_angle,
            ),
        ]

    def downward_stop_lead(self, position_key: str) -> float | None:
        """Estimate downward coast from the live signed reference speed."""
        specs = {
            "back": self._back_position_spec(),
            "legs": self._two_motor_secondary_spec(),
            "head": self._head_position_spec(),
            "feet": self._feet_position_spec(),
        }
        spec = specs.get(position_key)
        if spec is None or spec.max_position <= 0:
            return None
        raw_speed = self._coordinator.controller_state.get(f"linak_{spec.source_name}_raw_speed")
        if isinstance(raw_speed, bool) or not isinstance(raw_speed, (int, float)):
            return None
        if raw_speed >= 0:
            return None
        angular_speed = abs(float(raw_speed)) * spec.max_angle / spec.max_position
        return max(
            self.position_seek_tolerance,
            angular_speed * LINAK_DOWNWARD_STOP_LEAD_TIME_S,
        )

    def _build_position_characteristics(self, motor_count: int) -> list[LinakPositionSpec]:
        """Return the exact reference outputs selected by capability mask."""
        del motor_count
        specs = {
            "base": self._base_position_spec(),
            "feet": self._feet_position_spec(),
            "head": self._head_position_spec(),
            "legs": self._legs_position_spec(),
            "back": self._back_position_spec(),
        }
        return [specs[axis] for axis in self._capabilities.position_axes]

    def _build_notification_characteristics(self, motor_count: int) -> list[LinakPositionSpec]:
        """Return Linak position characteristics to subscribe for live updates."""
        return self._build_position_characteristics(motor_count)

    def _maybe_resolve_two_motor_secondary_notification(self, spec: LinakPositionSpec) -> None:
        """Lock onto the reporting second actuator for 2-motor Linak beds."""
        if self._coordinator.motor_count > 2:
            return
        if spec.axis_name != "legs":
            return
        if spec.uuid == self._two_motor_secondary_spec().uuid:
            return

        self._coordinator.hass.async_create_task(self._set_two_motor_secondary_spec(spec))

    async def _set_two_motor_secondary_spec(self, spec: LinakPositionSpec) -> None:
        """Persist the resolved second actuator for a 2-motor Linak bed."""
        current_spec = self._two_motor_secondary_spec()
        if current_spec.uuid == spec.uuid:
            return

        _LOGGER.info(
            "Resolved Linak secondary actuator for %s to %s (%s)",
            self._coordinator.address,
            spec.source_name,
            spec.uuid,
        )
        self._resolved_two_motor_secondary_spec = spec

        if self.client is None or not self.client.is_connected:
            return

        for candidate in self._two_motor_secondary_candidates():
            if candidate.uuid == spec.uuid:
                continue
            if candidate.uuid in self._active_position_notifications:
                with contextlib.suppress(BleakError):
                    await self.client.stop_notify(candidate.uuid)
            self._active_position_notifications.discard(candidate.uuid)
            self._deferred_position_notifications.discard(candidate.uuid)

        await self._ensure_position_notifications_started()

    async def _start_missing_position_notifications(
        self,
    ) -> tuple[list[str], list[str], list[str]]:
        """Start any Linak position notifications that are not already active."""
        successful: list[str] = []
        deferred: list[str] = []
        failed: list[str] = []

        if self.client is None or not self.client.is_connected:
            return successful, deferred, failed

        for spec in self._build_notification_characteristics(self._coordinator.motor_count):
            if spec.uuid in self._active_position_notifications:
                continue

            _LOGGER.debug(
                "Attempting to start notifications for %s (UUID: %s)...",
                spec.source_name,
                spec.uuid,
            )

            try:
                async with self._ble_lock:
                    await self.client.start_notify(
                        spec.uuid,
                        self._make_position_handler(spec),
                    )
            except BleakError as err:
                if self._is_authentication_window_error(err):
                    self._deferred_position_notifications.add(spec.uuid)
                    deferred.append(spec.source_name)
                    _LOGGER.debug(
                        "Deferring Linak %s notifications until control is ready: %s",
                        spec.source_name,
                        err,
                    )
                    continue

                _LOGGER.debug(
                    "Could not start notifications for %s position (UUID: %s): %s (type: %s)",
                    spec.source_name,
                    spec.uuid,
                    err,
                    type(err).__name__,
                )
                failed.append(spec.source_name)
                continue

            self._active_position_notifications.add(spec.uuid)
            self._deferred_position_notifications.discard(spec.uuid)
            successful.append(spec.source_name)
            _LOGGER.debug(
                "Successfully started notifications for %s position (UUID: %s, max_pos: %d, max_angle: %.1f°)",
                spec.source_name,
                spec.uuid,
                spec.max_position,
                spec.max_angle,
            )

        return successful, deferred, failed

    async def _ensure_position_notifications_started(self) -> None:
        """Start Linak position notifications, retrying deferred auth-window attempts."""
        if self._notify_callback is None:
            return

        successful, deferred, failed = await self._start_missing_position_notifications()

        if successful:
            _LOGGER.info(
                "Position notifications active for: %s",
                ", ".join(successful),
            )

        if deferred:
            _LOGGER.debug(
                "Linak position notifications deferred until control is ready: %s",
                ", ".join(deferred),
            )

        if failed:
            _LOGGER.warning(
                "Position notifications unavailable for: %s (bed may not support position feedback for these motors)",
                ", ".join(failed),
            )

    async def _await_control_ready(self, cancel_event: asyncio.Event | None = None) -> None:
        """Wait until Linak accepts control writes after a fresh BLE connect."""
        if self._session_ready:
            if self._capability_discovery_deferred:
                await self.async_discover_capabilities()
            return

        effective_cancel = cancel_event or self._coordinator.cancel_command
        deadline = self._session_started_monotonic + LINAK_CONTROL_READY_TIMEOUT_S
        attempt = 0

        while True:
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.debug(
                    "Cancelled Linak readiness wait for %s",
                    self._coordinator.address,
                )
                return

            attempt += 1
            session_age = monotonic() - self._session_started_monotonic
            _LOGGER.debug(
                "Probing Linak control readiness for %s (attempt %d, session age %.2fs)",
                self._coordinator.address,
                attempt,
                session_age,
            )

            if self._deferred_position_notifications:
                await self._ensure_position_notifications_started()

            try:
                await self._write_gatt_with_retry(
                    self.control_characteristic_uuid,
                    self._stop_command,
                    repeat_count=1,
                    repeat_delay_ms=0,
                    cancel_event=cancel_event,
                    log_errors=False,
                )
            except BleakError as err:
                if not self._is_authentication_window_error(err):
                    raise

                remaining = deadline - monotonic()
                if remaining <= 0:
                    _LOGGER.error(
                        "Linak control stayed unavailable for %s after %.2fs",
                        self._coordinator.address,
                        session_age,
                    )
                    raise

                delay = min(LINAK_CONTROL_READY_RETRY_DELAY_S, remaining)
                _LOGGER.debug(
                    "Linak control not ready for %s yet: %s; retrying in %.2fs",
                    self._coordinator.address,
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            self._session_ready = True
            if self._capability_discovery_deferred:
                await self.async_discover_capabilities()
            if self._deferred_position_notifications:
                await self._ensure_position_notifications_started()
            if self._deferred_protocol_notifications:
                await self._start_protocol_notifications()
            _LOGGER.debug(
                "Linak control ready for %s after %.2fs (%d probe attempts)",
                self._coordinator.address,
                monotonic() - self._session_started_monotonic,
                attempt,
            )
            return

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        await self._await_control_ready(cancel_event)
        _LOGGER.debug(
            "Writing command to Linak bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )
        _LOGGER.debug("Command sequence ended (%d writes attempted)", repeat_count)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start mandatory protocol notifications and optional position feedback."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning(
                "Cannot start position notifications: BLE client not connected (client=%s, is_connected=%s)",
                self.client,
                getattr(self.client, "is_connected", "N/A") if self.client else "N/A",
            )
            return

        await self._start_protocol_notifications()
        if self._deferred_protocol_notifications or self._capability_discovery_deferred:
            # Do not make optional capability/state channels gate integration
            # setup. Some unbonded controllers reject them during the cold-link
            # window even though the same session later accepts control. The
            # first command retries every deferred channel after readiness.
            _LOGGER.debug("Leaving Linak capability/state channels deferred until control is ready")

        if callback is None or not self.supports_position_feedback:
            return

        motor_count = self._coordinator.motor_count
        _LOGGER.info(
            "Setting up position notifications for %d-motor Linak bed at %s",
            motor_count,
            self._coordinator.address,
        )
        _LOGGER.debug(
            "Client state: is_connected=%s, mtu_size=%s",
            self.client.is_connected,
            getattr(self.client, "mtu_size", "N/A"),
        )

        position_chars = self._build_position_characteristics(motor_count)

        _LOGGER.debug(
            "Will attempt to subscribe to %d position characteristics: %s",
            len(position_chars),
            [spec.source_name for spec in position_chars],
        )
        await self._ensure_position_notifications_started()

    async def _read_position_characteristic(
        self,
        spec: LinakPositionSpec,
        timeout_seconds: float = 0.75,
    ) -> float | None:
        """Read a single Linak position characteristic without blocking others."""
        if self.client is None or not self.client.is_connected:
            return None

        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._ble_lock:
                    data = await self.client.read_gatt_char(spec.uuid)
        except TimeoutError:
            _LOGGER.debug(
                "Timed out reading position for %s (UUID: %s)",
                spec.source_name,
                spec.uuid,
            )
            return None
        except BleakError as err:
            _LOGGER.debug(
                "Could not read position for %s (UUID: %s): %s",
                spec.source_name,
                spec.uuid,
                err,
            )
            return None

        if not data:
            return None

        _LOGGER.debug("Read position for %s: %s", spec.source_name, data.hex())
        angle = self._decode_position_data(
            spec.source_name,
            bytearray(data),
            spec.max_position,
            spec.max_angle,
        )
        if angle is None:
            return None

        if self._notify_callback:
            self._notify_callback(spec.axis_name, angle)
        return angle

    def _decode_position_data(
        self,
        source_name: str,
        data: bytearray,
        max_position: int,
        max_angle: float,
    ) -> float | None:
        """Decode a reference sample, publish status/speed, and derive angle."""
        try:
            reference = decode_reference(data)
        except ValueError:
            _LOGGER.warning(
                "Received invalid position data for %s: expected exactly 4 bytes, got %d",
                source_name,
                len(data),
            )
            # Bed Control catches malformed reference payloads and emits an
            # all-zero reference state. Do the same so a stale non-zero speed
            # or position-lost flag never survives a bad notification.
            self._publish_reference_state(
                source_name,
                LinakReferenceState(
                    extension=0,
                    raw_extension=0,
                    status_flags=0,
                    raw_speed=0,
                    speed=0,
                ),
            )
            return None

        self._publish_reference_state(source_name, reference)
        raw_position = reference.raw_extension

        # The extension is a signed 16-bit count. An actuator resting a count or
        # two below its learned zero reports 0xFFFE/0xFFFF; discarding those left
        # the axis with no current-session sample, so every seek on it failed.
        # A small negative is simply fully down.
        if raw_position >= 0x8000:
            signed_position = raw_position - 0x10000
            if signed_position < -max_position * 0.1:
                _LOGGER.debug(
                    "Ignoring invalid position data for %s: raw=%d is %d below zero",
                    source_name,
                    raw_position,
                    -signed_position,
                )
                return None
            _LOGGER.debug(
                "Position update [%s]: raw=%d (%d below zero), angle=0.0°",
                source_name,
                raw_position,
                -signed_position,
            )
            return 0.0

        if raw_position > max_position * 1.1:
            _LOGGER.debug(
                "Ignoring invalid position data for %s: raw=%d exceeds max=%d by >10%%",
                source_name,
                raw_position,
                max_position,
            )
            return None

        if raw_position >= max_position:
            angle = max_angle
        else:
            angle = round(max_angle * (raw_position / max_position), 1)

        _LOGGER.debug(
            "Position update [%s]: raw=%d (max=%d), angle=%.1f° (max=%.1f°)",
            source_name,
            raw_position,
            max_position,
            angle,
            max_angle,
        )
        return angle

    def _publish_reference_state(
        self,
        source_name: str,
        reference: LinakReferenceState,
    ) -> None:
        """Publish the complete reference-output state without guessing units."""
        prefix = f"linak_{source_name}"
        updates: dict[str, Any] = {
            f"{prefix}_reported_speed": reference.speed,
            f"{prefix}_raw_speed": reference.raw_speed,
            f"{prefix}_speed_direction": reference.speed_direction,
            f"{prefix}_extension": reference.extension,
            f"{prefix}_status_flags": reference.status_flags,
            f"{prefix}_sls": reference.sls,
            f"{prefix}_end_position_up": reference.end_position_up,
            f"{prefix}_end_position_down": reference.end_position_down,
            f"{prefix}_position_lost": reference.position_lost,
        }
        current = self._coordinator.controller_state
        fault_axes = [
            axis
            for axis in self._capabilities.position_axes
            if (
                reference.position_lost
                if axis == source_name
                else current.get(f"linak_{axis}_position_lost") is True
            )
        ]
        updates["linak_position_feedback_fault"] = bool(fault_axes)
        updates["linak_fault_axes"] = fault_axes
        self.forward_controller_state_updates(updates)

    def _handle_position_data(
        self,
        name: str,
        data: bytearray,
        max_position: int,
        max_angle: float,
        *,
        source_name: str | None = None,
    ) -> None:
        """Handle position notification data."""
        angle = self._decode_position_data(
            source_name or name,
            data,
            max_position,
            max_angle,
        )
        if angle is None:
            return

        if self._notify_callback:
            self._notify_callback(name, angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None
        if self.client is None or not self.client.is_connected:
            return

        self._active_position_notifications.clear()
        self._deferred_position_notifications.clear()
        self._protocol_notification_uuids.clear()
        self._deferred_protocol_notifications.clear()
        uuids = [
            LINAK_ERROR_CHAR_UUID,
            LINAK_CONFIG_CHAR_UUID,
            LINAK_TIMER_CHAR_UUID,
            LINAK_POSITION_BASE_UUID,
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
            LINAK_POSITION_HEAD_UUID,
            LINAK_POSITION_FEET_UUID,
        ]

        for uuid in uuids:
            with contextlib.suppress(BleakError):
                await self.client.stop_notify(uuid)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Actively read position data from all motor position characteristics.

        This provides a way to get current positions without relying solely
        on notifications, which may not always be sent by the bed.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot read positions: not connected")
            return

        if not self.supports_position_feedback:
            return
        expected_axes = self._expected_position_axes(motor_count)
        received_axes = await self._read_positions_once(motor_count)
        if self._session_ready or received_axes >= expected_axes:
            return

        for attempt in range(2, LINAK_INITIAL_POSITION_RETRY_ATTEMPTS + 1):
            if self.client is None or not self.client.is_connected:
                return

            _LOGGER.debug(
                "Linak cold-session position read returned no data for %s; retrying in %.2fs (attempt %d/%d)",
                self._coordinator.address,
                LINAK_INITIAL_POSITION_RETRY_DELAY_S,
                attempt,
                LINAK_INITIAL_POSITION_RETRY_ATTEMPTS,
            )
            await asyncio.sleep(LINAK_INITIAL_POSITION_RETRY_DELAY_S)

            if self._deferred_position_notifications:
                await self._ensure_position_notifications_started()

            missing_axes = expected_axes - received_axes
            received_axes.update(await self._read_positions_once(motor_count, axes=missing_axes))
            if received_axes >= expected_axes:
                return

    def _expected_position_axes(self, motor_count: int) -> set[str]:
        """Return the logical axes expected from a Linak position read."""
        del motor_count
        return set(self._capabilities.position_axes)

    async def _read_positions_once(
        self,
        motor_count: int,
        *,
        axes: set[str] | None = None,
    ) -> set[str]:
        """Read Linak positions once and return the axes that produced data."""
        received_axes: set[str] = set()
        for spec in self._build_position_characteristics(motor_count):
            if axes is not None and spec.axis_name not in axes:
                continue
            angle = await self._read_position_characteristic(spec)
            if angle is not None:
                received_axes.add(spec.axis_name)
        return received_axes

    async def _read_two_motor_secondary_position(self) -> float | None:
        """Read and resolve the second actuator for a 2-motor Linak bed."""
        current_spec = self._two_motor_secondary_spec()
        candidates = [current_spec] + [
            candidate
            for candidate in self._two_motor_secondary_candidates()
            if candidate.uuid != current_spec.uuid
        ]

        for spec in candidates:
            angle = await self._read_position_characteristic(spec)
            if angle is None:
                continue

            if spec.uuid != current_spec.uuid:
                await self._set_two_motor_secondary_spec(spec)
            return angle

        return None

    async def read_non_notifying_positions(self) -> None:
        """Read positions for manual refresh flows that need a back-motor read."""
        if self.client is None or not self.client.is_connected:
            return

        if "back" in self._capabilities.position_axes:
            await self._read_position_characteristic(
                self._back_position_spec(), timeout_seconds=0.4
            )

    async def prepare_for_position_read(self) -> None:
        """Wait for Linak's post-connect auth window before passive reads."""
        await self._await_control_ready()

    # Motor control methods
    # Linak protocol requires continuous command sending to keep motors moving.
    # Bed Control uses the configured 100 ms default. The explicit Performance
    # profile preserves the configured hold duration at its proven 300 ms cadence.

    async def _send_stop(self) -> None:
        """Send Linak's explicit STOP/release frame."""
        await self.write_command(self._stop_command, cancel_event=asyncio.Event())

    async def seek_position_step(
        self,
        position_key: str,
        moving_up: bool,
        remaining_distance: float | None = None,
    ) -> None:
        """Refresh one held Linak movement without releasing between samples."""
        command_map = {
            ("back", True): LinakCommands.MOVE_BACK_UP,
            ("back", False): LinakCommands.MOVE_BACK_DOWN,
            ("legs", True): LinakCommands.MOVE_LEGS_UP,
            ("legs", False): LinakCommands.MOVE_LEGS_DOWN,
            ("head", True): LinakCommands.MOVE_HEAD_UP,
            ("head", False): LinakCommands.MOVE_HEAD_DOWN,
            ("feet", True): LinakCommands.MOVE_FEET_UP,
            ("feet", False): LinakCommands.MOVE_FEET_DOWN,
        }
        command = command_map.get((position_key, moving_up))
        if command is None:
            await super().seek_position_step(
                position_key,
                moving_up,
                remaining_distance,
            )
            return

        # Bed Control refreshes a held command every 100 ms and writes one STOP
        # only when the gesture ends. The seek runner provides that cadence and
        # owns the terminal STOP, allowing one continuous motor movement.
        await self.write_command(command)

    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(LinakCommands.MOVE_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(LinakCommands.MOVE_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(LinakCommands.MOVE_BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(LinakCommands.MOVE_BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(LinakCommands.MOVE_LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(LinakCommands.MOVE_LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(LinakCommands.MOVE_FEET_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(LinakCommands.MOVE_FEET_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._send_stop()

    async def move_bed_height_up(self) -> None:
        """Raise the BASE actuator exposed by the modern capability mask."""
        await self._move_with_stop(LinakCommands.MOVE_BASE_UP)

    async def move_bed_height_down(self) -> None:
        """Lower the BASE actuator exposed by the modern capability mask."""
        await self._move_with_stop(LinakCommands.MOVE_BASE_DOWN)

    async def move_bed_height_stop(self) -> None:
        """Stop the BASE actuator."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        """Run the app's held flat/initialise-down action."""
        await self._held_preset(LinakCommands.MOVE_ALL_DOWN)

    async def preset_both_up(self) -> None:
        """Run the modern app's held all-up action."""
        if not self.supports_preset_both_up:
            raise NotImplementedError("All-up is not exposed by this Linak profile")
        await self._held_preset(LinakCommands.MOVE_ALL_UP)

    async def _held_preset(self, command: bytes) -> None:
        """Hold a favorite-like command for the app's 30 second ceiling."""
        interval_ms = (
            LINAK_PERFORMANCE_HOLD_INTERVAL_MS
            if self._profile is LinakProfile.PERFORMANCE
            else LINAK_BED_CONTROL_HOLD_INTERVAL_MS
        )
        repeat_count = max(1, LINAK_MEMORY_RECALL_DURATION_S * 1000 // interval_ms)
        await self._preset_with_stop(
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=interval_ms,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LinakCommands.PRESET_MEMORY_1,
            2: LinakCommands.PRESET_MEMORY_2,
            3: LinakCommands.PRESET_MEMORY_3,
            4: LinakCommands.PRESET_MEMORY_4,
        }
        if memory_num > self.memory_slot_count or (command := commands.get(memory_num)) is None:
            raise ValueError(f"Linak memory {memory_num} is not available")
        await self._held_preset(command)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: LinakCommands.PROGRAM_MEMORY_1,
            2: LinakCommands.PROGRAM_MEMORY_2,
            3: LinakCommands.PROGRAM_MEMORY_3,
            4: LinakCommands.PROGRAM_MEMORY_4,
        }
        if memory_num > self.memory_slot_count or (command := commands.get(memory_num)) is None:
            raise ValueError(f"Linak memory {memory_num} is not available")
        await self.write_command(command)

    # Light methods
    async def lights_on(self) -> None:
        """Reject a discrete action the applications do not expose."""
        raise NotImplementedError("Linak exposes only an AUX/light toggle")

    async def lights_off(self) -> None:
        """Reject a discrete action the applications do not expose."""
        raise NotImplementedError("Linak exposes only an AUX/light toggle")

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_TOGGLE)

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        if not self.supports_massage_off_control:
            raise NotImplementedError("Massage off is not exposed by this Linak profile")
        await self.write_command(LinakCommands.MASSAGE_ALL_OFF)

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        if self._profile is LinakProfile.PERFORMANCE:
            if self._performance_wave_active:
                await self.write_command(LinakCommands.MASSAGE_MODE_STEP)
                self._performance_wave_active = False
            await self.write_command(LinakCommands.MASSAGE_PERFORMANCE_START)
            return
        await self._write_massage_zone_sequence(
            LinakCommands.MASSAGE_ZONE_1_ON,
            LinakCommands.MASSAGE_ZONE_2_ON,
        )

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        if not self.supports_head_massage_toggle_control:
            raise NotImplementedError("Zone selection is not exposed by this Linak profile")
        await self._write_massage_zone_sequence(
            LinakCommands.MASSAGE_ZONE_1_ON,
            LinakCommands.MASSAGE_ZONE_2_OFF,
        )

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        if not self.supports_foot_massage_toggle_control:
            raise NotImplementedError("Zone selection is not exposed by this Linak profile")
        await self._write_massage_zone_sequence(
            LinakCommands.MASSAGE_ZONE_1_OFF,
            LinakCommands.MASSAGE_ZONE_2_ON,
        )

    async def _write_massage_zone_sequence(self, first: bytes, second: bytes) -> None:
        """Send the modern app's two-zone selection sequence."""
        await self.write_command(first)
        await asyncio.sleep(LINAK_MASSAGE_ZONE_GAP_S)
        await self.write_command(second)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        if not self.supports_massage_intensity_step_control:
            raise NotImplementedError("All-zone intensity is not exposed by this profile")
        await self.write_command(LinakCommands.MASSAGE_ALL_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        if not self.supports_massage_intensity_step_control:
            raise NotImplementedError("All-zone intensity is not exposed by this profile")
        await self.write_command(LinakCommands.MASSAGE_ALL_DOWN)

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(LinakCommands.MASSAGE_MODE_STEP)
        if self._profile is LinakProfile.PERFORMANCE:
            self._performance_wave_active = not self._performance_wave_active

    async def massage_wave_frequency_up(self) -> None:
        """Increase legacy Performance wave frequency."""
        if not self.supports_massage_wave_frequency_control:
            raise NotImplementedError("Wave frequency is not exposed by this profile")
        await self.write_command(LinakCommands.MASSAGE_WAVE_FREQUENCY_UP)
        self._performance_wave_active = True

    async def massage_wave_frequency_down(self) -> None:
        """Decrease legacy Performance wave frequency."""
        if not self.supports_massage_wave_frequency_control:
            raise NotImplementedError("Wave frequency is not exposed by this profile")
        await self.write_command(LinakCommands.MASSAGE_WAVE_FREQUENCY_DOWN)
        self._performance_wave_active = True

    async def impulse_toggle(self) -> None:
        """Toggle the legacy Performance impulse mode."""
        if not self.supports_impulse_control:
            raise NotImplementedError("Impulse mode is not exposed by this profile")
        await self.write_command(LinakCommands.IMPULSE_TOGGLE)

    async def reset_defaults(self) -> None:
        """Reset the controller settings exposed by both app profiles."""
        await self.write_command(LinakCommands.RESET_DEFAULTS)

    async def _write_protected_characteristic(self, uuid: str, data: bytes) -> None:
        """Wait out the cold-session auth window before a protected GATT write."""
        await self._await_control_ready()
        await self._write_gatt_with_retry(uuid, data)

    async def factory_reset(self) -> None:
        """Run Bed Connect's distinct configuration-level factory reset."""
        if not self.supports_factory_reset:
            raise NotImplementedError("Factory reset is unavailable for this profile")
        await self._write_protected_characteristic(
            LINAK_CONFIG_CHAR_UUID,
            LinakCommands.FACTORY_RESET,
        )

    async def wake(self) -> None:
        """Send the modern Bed Control wake action."""
        if not self.supports_wake_control:
            raise NotImplementedError("Wake is not exposed by this Linak profile")
        await self.write_command(LinakCommands.WAKE)

    async def set_automatic_drive(self, enabled: bool) -> None:
        """Write modern Bed Control's automatic-drive configuration."""
        if not self.supports_automatic_drive:
            raise NotImplementedError("Automatic drive is not exposed by this profile")
        await self._write_protected_characteristic(
            LINAK_CONFIG_CHAR_UUID,
            build_automatic_drive(enabled),
        )
        self.forward_controller_state_updates({"linak_automatic_drive": enabled})

    async def rename_device(self, name: str) -> None:
        """Write the modern app's raw Generic Access device name."""
        if not self.supports_device_rename:
            raise NotImplementedError("Rename is not exposed by this Linak profile")
        encoded = name.encode()
        if not name or len(name) > 17 or len(encoded) > 17:
            raise ValueError("Linak device names must contain 1 to 17 bytes")
        await self._write_protected_characteristic(LINAK_DEVICE_NAME_UUID, encoded)

    async def program_alarm(
        self,
        seconds: int,
        actions: Sequence[Any],
        recurrence_count: int,
        recurrence_minutes: int,
    ) -> None:
        """Program an alarm using the complete app write sequence."""
        if not self.supports_alarm:
            raise NotImplementedError("Alarm programming is unavailable for this model")
        if not all(isinstance(action, LinakAlarmStep) for action in actions):
            raise TypeError("Linak alarms require LinakAlarmStep actions")
        alarm_steps = tuple(action for action in actions if isinstance(action, LinakAlarmStep))
        await self.set_automatic_drive(True)
        for packet in (
            build_timer_event(seconds, alarm_steps),
            build_timer_recurrence(recurrence_count, recurrence_minutes),
            LinakCommands.TIMER_COMMIT,
        ):
            await self._write_protected_characteristic(LINAK_TIMER_CHAR_UUID, packet)

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        """Move two different sections with one modern Bed Control opcode."""
        if not self.supports_simultaneous_movement:
            raise NotImplementedError("Simultaneous movement is unavailable")
        available_axes = set(self.simultaneous_movement_axes)
        unavailable_axes = {first_axis, second_axis} - available_axes
        if unavailable_axes:
            unavailable = ", ".join(sorted(unavailable_axes))
            raise ValueError(f"Linak model does not expose simultaneous axis: {unavailable}")
        command = build_simultaneous_command(
            first_axis,
            first_up,
            second_axis,
            second_up,
        )
        if duration_ms is None:
            await self._move_with_stop(command)
            return
        _, pulse_delay_ms = self.motor_pulse_settings()
        repeat_count = max(2, (duration_ms + pulse_delay_ms - 1) // pulse_delay_ms + 1)
        try:
            await self.write_command(
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=pulse_delay_ms,
            )
        finally:
            await self._send_stop()
