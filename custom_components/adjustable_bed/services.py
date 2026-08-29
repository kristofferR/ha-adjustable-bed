"""Service registration for the Adjustable Bed integration.

Handlers live here as module-level functions rather than closures so they can be
read, tested, and type-checked independently of integration setup. Each one
recovers Home Assistant from ``call.hass``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    bed_type_has_position_feedback,
)
from .coordinator import AdjustableBedCoordinator

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_GENERATE_SUPPORT_BUNDLE = "generate_support_bundle"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_SET_POSITION = "set_position"
SERVICE_STOP_ALL = "stop_all"
SERVICE_TIMED_MOVE = "timed_move"

# Service call attributes
ATTR_PRESET = "preset"
ATTR_MOTOR = "motor"
ATTR_POSITION = "position"
ATTR_TARGET_ADDRESS = "target_address"
ATTR_CAPTURE_DURATION = "capture_duration"
ATTR_INCLUDE_LOGS = "include_logs"
ATTR_DIRECTION = "direction"
ATTR_DURATION_MS = "duration_ms"

TIMED_MOVE_MOTOR_OPTIONS = (
    "tv_lift",
    "back",
    "legs",
    "head",
    "feet",
    "tilt",
    "pillow",
    "lumbar",
    "bed_height",
    "stair",
)

# Default capture duration for diagnostics (seconds)
DEFAULT_CAPTURE_DURATION = 120

# Bound for the best-effort pre-capture log probe. Generous for a local stat,
# short enough that a stalled mount cannot delay the capture noticeably.
_LOG_PROBE_TIMEOUT = 5.0

# hass.data key: notification id -> tokens of the invocations that raised it.
_LOG_NOTICE_OWNERS = f"{DOMAIN}_log_notice_owners"
MIN_CAPTURE_DURATION = 10
MAX_CAPTURE_DURATION = 300

# Timed move duration limits (milliseconds)
MIN_TIMED_MOVE_DURATION_MS = 100
MAX_TIMED_MOVE_DURATION_MS = 30000  # 30 seconds max


async def _get_coordinator_from_device(
    hass: HomeAssistant, device_id: str
) -> AdjustableBedCoordinator | None:
    """Get coordinator from device ID."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if not device:
        return None

    for entry_id in device.config_entries:
        if entry_id in hass.data.get(DOMAIN, {}):
            return cast(AdjustableBedCoordinator, hass.data[DOMAIN][entry_id])
    return None


def _get_support_bundle_target_from_device(
    hass: HomeAssistant, device_id: str
) -> tuple[str, AdjustableBedCoordinator | None, ConfigEntry] | None:
    """Resolve support-bundle target details from a device registry ID."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if not device:
        return None

    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue

        address = entry.data.get(CONF_ADDRESS)
        if not isinstance(address, str):
            continue

        coordinator = cast(AdjustableBedCoordinator | None, hass.data.get(DOMAIN, {}).get(entry_id))
        return address, coordinator, entry

    return None


async def _get_controller_for_service(
    coordinator: AdjustableBedCoordinator,
) -> BedController:
    """Return an active controller for service validation/execution.

    Service calls may arrive while the coordinator is idle-disconnected and
    controller is None. Reconnect first so capability checks don't fail with
    a false "not supported" error.
    """
    controller = coordinator.controller
    if controller is not None:
        return controller

    _LOGGER.debug(
        "No active controller for %s during service call; attempting reconnect",
        coordinator.name,
    )
    connected = await coordinator.async_ensure_connected(reset_timer=False)
    controller = coordinator.controller
    if not connected or controller is None:
        raise ServiceValidationError(
            f"Device '{coordinator.name}' is currently unavailable (unable to connect)",
        )
    return controller


async def handle_goto_preset(call: ServiceCall) -> None:
    """Handle goto_preset service call."""
    hass = call.hass
    preset = call.data[ATTR_PRESET]
    device_ids = call.data.get(CONF_DEVICE_ID, [])

    _LOGGER.info("Service goto_preset called: preset=%d", preset)

    for device_id in device_ids:
        coordinator = await _get_coordinator_from_device(hass, device_id)
        if coordinator:
            # Check if controller supports memory presets
            controller = await _get_controller_for_service(coordinator)
            if not controller.supports_memory_presets:
                raise ServiceValidationError(
                    f"Device '{coordinator.name}' does not support memory presets",
                    translation_domain=DOMAIN,
                    translation_key="memory_presets_not_supported",
                    translation_placeholders={"device_name": coordinator.name},
                )
            # Validate preset against controller's memory slot count
            slot_count = controller.memory_slot_count
            if preset > slot_count:
                raise ServiceValidationError(
                    f"Device '{coordinator.name}' only supports memory presets 1-{slot_count}. "
                    f"Preset {preset} is not available for this bed type.",
                    translation_domain=DOMAIN,
                    translation_key="invalid_preset_number",
                    translation_placeholders={
                        "device_name": coordinator.name,
                        "max_preset": str(slot_count),
                        "requested_preset": str(preset),
                    },
                )
            await coordinator.async_execute_controller_command(
                lambda ctrl, p=preset: ctrl.preset_memory(p)  # type: ignore[misc]
            )
        else:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID {device_id}",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )


async def handle_save_preset(call: ServiceCall) -> None:
    """Handle save_preset service call."""
    hass = call.hass
    preset = call.data[ATTR_PRESET]
    device_ids = call.data.get(CONF_DEVICE_ID, [])

    _LOGGER.info("Service save_preset called: preset=%d", preset)

    for device_id in device_ids:
        coordinator = await _get_coordinator_from_device(hass, device_id)
        if coordinator:
            # Check if controller supports programming memory presets
            controller = await _get_controller_for_service(coordinator)
            if not controller.supports_memory_programming:
                raise ServiceValidationError(
                    f"Device '{coordinator.name}' does not support programming memory presets",
                    translation_domain=DOMAIN,
                    translation_key="memory_programming_not_supported",
                    translation_placeholders={"device_name": coordinator.name},
                )
            # Validate preset against controller's memory slot count
            slot_count = controller.memory_slot_count
            if preset > slot_count:
                raise ServiceValidationError(
                    f"Device '{coordinator.name}' only supports memory presets 1-{slot_count}. "
                    f"Preset {preset} is not available for this bed type.",
                    translation_domain=DOMAIN,
                    translation_key="invalid_preset_number",
                    translation_placeholders={
                        "device_name": coordinator.name,
                        "max_preset": str(slot_count),
                        "requested_preset": str(preset),
                    },
                )
            await coordinator.async_execute_controller_command(
                lambda ctrl, p=preset: ctrl.program_memory(p),  # type: ignore[misc]
                cancel_running=False,
            )
        else:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID {device_id}",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )


async def handle_stop_all(call: ServiceCall) -> None:
    """Handle stop_all service call."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])

    _LOGGER.info("Service stop_all called")

    missing_device_ids: list[str] = []

    for device_id in device_ids:
        coordinator = await _get_coordinator_from_device(hass, device_id)
        if coordinator:
            await coordinator.async_stop_command()
        else:
            missing_device_ids.append(device_id)

    if missing_device_ids:
        raise ServiceValidationError(
            f"Could not find Adjustable Bed device(s) with ID(s): {', '.join(missing_device_ids)}",
            translation_domain=DOMAIN,
            translation_key="devices_not_found",
            translation_placeholders={"device_ids": ", ".join(missing_device_ids)},
        )


async def handle_set_position(call: ServiceCall) -> None:
    """Handle set_position service call."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    motor = call.data[ATTR_MOTOR]
    position = call.data[ATTR_POSITION]

    _LOGGER.info(
        "Service set_position called: motor=%s, position=%.1f%%",
        motor,
        position,
    )

    for device_id in device_ids:
        coordinator = await _get_coordinator_from_device(hass, device_id)
        if not coordinator:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID {device_id}",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )
        controller = await _get_controller_for_service(coordinator)

        # Get config entry for bed type and motor count
        entry = coordinator.entry
        bed_type = entry.data.get(CONF_BED_TYPE)
        motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        supports_direct_position_control = controller.supports_direct_position_control

        # Validate bed supports position feedback
        if (
            not bed_type_has_position_feedback(bed_type, protocol_variant)
            and not supports_direct_position_control
        ):
            raise ServiceValidationError(
                f"Device '{coordinator.name}' (type: {bed_type}) does not support position feedback",
                translation_domain=DOMAIN,
                translation_key="position_feedback_not_supported",
                translation_placeholders={
                    "device_name": coordinator.name,
                    "bed_type": bed_type or "unknown",
                },
            )

        # Validate angle sensing is enabled
        if coordinator.disable_angle_sensing:
            raise ServiceValidationError(
                f"Angle sensing is disabled for device '{coordinator.name}'",
                translation_domain=DOMAIN,
                translation_key="angle_sensing_disabled",
                translation_placeholders={"device_name": coordinator.name},
            )

        # Define motor configurations.
        # For Keeson/Ergomotion: only head and feet are valid, they map to back/legs keys.
        # For BOX25: head, feet, and lumbar are valid, using direct percentage positions.
        # For Kaidi: direct position writes expose back/legs percentage targets.
        # For standard beds: based on motor_count (2=back/legs, 3=+head, 4=+feet).
        uses_percentage_positions = bed_type in (
            BED_TYPE_KEESON,
            BED_TYPE_ERGOMOTION,
            BED_TYPE_SLEEPYS_BOX25,
        ) or (bed_type == BED_TYPE_KAIDI and supports_direct_position_control)

        if bed_type == BED_TYPE_KAIDI and supports_direct_position_control:
            valid_motors = {"back", "legs"}
            motor_configs = {
                "back": {
                    "position_key": "back",
                    "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                    "max_value": 100.0,
                },
                "legs": {
                    "position_key": "legs",
                    "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                    "max_value": 100.0,
                },
            }
        elif bed_type in (BED_TYPE_KEESON, BED_TYPE_ERGOMOTION):
            # Keeson/Ergomotion only have head and feet motors
            valid_motors = {"head", "feet"}
            motor_configs = {
                "head": {
                    "position_key": "back",  # Maps to "back" in position_data
                    "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                    "max_value": 100.0,  # Percentage
                },
                "feet": {
                    "position_key": "legs",  # Maps to "legs" in position_data
                    "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                    "max_value": 100.0,  # Percentage
                },
            }
        elif bed_type == BED_TYPE_SLEEPYS_BOX25:
            valid_motors = {"head", "feet", "lumbar"}
            motor_configs = {
                "head": {
                    "position_key": "head",
                    "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                    "max_value": 100.0,
                },
                "feet": {
                    "position_key": "feet",
                    "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                    "max_value": 100.0,
                },
                "lumbar": {
                    "position_key": "lumbar",
                    "move_up_fn": lambda ctrl: ctrl.move_lumbar_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_lumbar_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_lumbar_stop(),
                    "max_value": 100.0,
                },
            }
        else:
            # Standard beds: motor availability depends on motor_count
            motor_configs = {
                "back": {
                    "position_key": "back",
                    "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                    "max_value": coordinator.get_max_angle("back"),  # Degrees
                    "min_motors": 2,
                },
                "legs": {
                    "position_key": "legs",
                    "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                    "max_value": coordinator.get_max_angle("legs"),  # Degrees
                    "min_motors": 2,
                },
                "head": {
                    "position_key": "head",
                    "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                    "max_value": coordinator.get_max_angle("head"),  # Degrees
                    "min_motors": 3,
                },
                "feet": {
                    "position_key": "feet",
                    "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                    "max_value": coordinator.get_max_angle("feet"),  # Degrees
                    "min_motors": 4,
                },
            }
            # Filter to valid motors based on motor_count
            valid_motors = {
                m for m, cfg in motor_configs.items() if motor_count >= cfg.get("min_motors", 2)
            }

        # Validate motor is valid for this bed
        if motor not in valid_motors:
            raise ServiceValidationError(
                f"Motor '{motor}' is not valid for device '{coordinator.name}'. "
                f"Valid motors: {', '.join(sorted(valid_motors))}",
                translation_domain=DOMAIN,
                translation_key="invalid_motor_for_bed_type",
                translation_placeholders={
                    "motor": motor,
                    "device_name": coordinator.name,
                    "valid_motors": ", ".join(sorted(valid_motors)),
                },
            )

        config = motor_configs[motor]
        max_value = config["max_value"]

        # Validate position is in range
        if position < 0 or position > max_value:
            unit = "%" if uses_percentage_positions else "°"
            raise ServiceValidationError(
                f"Position {position} is out of range for motor '{motor}'. "
                f"Valid range: 0-{max_value}{unit}",
                translation_domain=DOMAIN,
                translation_key="invalid_position_range",
                translation_placeholders={
                    "position": str(position),
                    "motor": motor,
                    "max_value": str(max_value),
                    "unit": unit,
                },
            )

        # Call async_seek_position
        await coordinator.async_seek_position(
            position_key=cast(str, config["position_key"]),
            target_angle=position,
            move_up_fn=config["move_up_fn"],  # type: ignore[arg-type]
            move_down_fn=config["move_down_fn"],  # type: ignore[arg-type]
            move_stop_fn=config["move_stop_fn"],  # type: ignore[arg-type]
        )


async def handle_timed_move(call: ServiceCall) -> None:
    """Handle timed_move service call."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    motor = call.data[ATTR_MOTOR]
    direction = call.data[ATTR_DIRECTION]
    duration_ms = call.data[ATTR_DURATION_MS]

    _LOGGER.info(
        "Service timed_move called: motor=%s, direction=%s, duration_ms=%d",
        motor,
        direction,
        duration_ms,
    )

    for device_id in device_ids:
        coordinator = await _get_coordinator_from_device(hass, device_id)
        if not coordinator:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID {device_id}",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )
        # Create a narrowed reference for use in closures (mypy doesn't narrow across closures)
        coordinator_: AdjustableBedCoordinator = coordinator
        controller = await _get_controller_for_service(coordinator)
        motor_configs = {
            spec.key: {
                "move_up_fn": spec.open_fn,
                "move_down_fn": spec.close_fn,
                "move_stop_fn": spec.stop_fn,
            }
            for spec in controller.motor_control_specs
            if spec.key in TIMED_MOVE_MOTOR_OPTIONS
        }
        valid_motors = set(motor_configs)

        # Validate motor is valid for this bed
        if motor not in valid_motors:
            raise ServiceValidationError(
                f"Motor '{motor}' is not valid for device '{coordinator.name}'. "
                f"Valid motors: {', '.join(sorted(valid_motors))}",
                translation_domain=DOMAIN,
                translation_key="invalid_motor_for_bed_type",
                translation_placeholders={
                    "motor": motor,
                    "device_name": coordinator.name,
                    "valid_motors": ", ".join(sorted(valid_motors)),
                },
            )

        config = motor_configs[motor]

        # Get the appropriate move function based on direction
        move_fn = config["move_up_fn"] if direction == "up" else config["move_down_fn"]
        stop_fn = config["move_stop_fn"]

        # Execute timed movement
        # Calculate repeat count: duration_ms / pulse_delay_ms
        # Example: 3500ms on Octo (350ms delay) = 10 repeats
        _, pulse_delay_ms = controller.motor_pulse_settings()
        if pulse_delay_ms <= 0:
            _LOGGER.warning(
                "Invalid motor_pulse_delay_ms (%d) for device %s, using default 100ms",
                pulse_delay_ms,
                coordinator.name,
            )
            pulse_delay_ms = 100  # DEFAULT_MOTOR_PULSE_DELAY_MS
        # The first write is immediate, so one additional repeat is needed
        # after the requested number of delay intervals.
        calculated_repeat_count = max(
            2,
            (duration_ms + pulse_delay_ms - 1) // pulse_delay_ms + 1,
        )

        _LOGGER.debug(
            "Timed move: duration=%dms, pulse_delay=%dms, repeat_count=%d",
            duration_ms,
            pulse_delay_ms,
            calculated_repeat_count,
        )

        # Store original pulse settings to restore after
        original_pulse_count = coordinator.motor_pulse_count
        original_pulse_delay_ms = coordinator.motor_pulse_delay_ms

        # Bind closure variables as defaults to avoid late-binding bugs
        async def timed_movement(
            ctrl: BedController,
            *,
            _coordinator: AdjustableBedCoordinator = coordinator_,
            _move_fn: Callable[..., Coroutine[Any, Any, None]] = move_fn,
            _stop_fn: Callable[..., Coroutine[Any, Any, None]] = stop_fn,
            _calculated_repeat_count: int = calculated_repeat_count,
            _pulse_delay_ms: int = pulse_delay_ms,
            _original_pulse_count: int = original_pulse_count,
            _original_pulse_delay_ms: int = original_pulse_delay_ms,
        ) -> None:
            """Execute movement for specified duration, always sending stop."""
            try:
                # Temporarily set the effective pulse settings
                # This is safe because we're inside the command lock
                _coordinator._motor_pulse_count = _calculated_repeat_count
                _coordinator._motor_pulse_delay_ms = _pulse_delay_ms

                # Call the movement function (uses coordinator's pulse settings)
                await _move_fn(ctrl)
            finally:
                # Restore original pulse settings
                _coordinator._motor_pulse_count = _original_pulse_count
                _coordinator._motor_pulse_delay_ms = _original_pulse_delay_ms

                # Always send stop command
                await asyncio.shield(_stop_fn(ctrl))

        await coordinator.async_execute_controller_command(timed_movement)


async def handle_generate_support_bundle(call: ServiceCall) -> None:
    """Handle generate_support_bundle service call."""
    hass = call.hass
    from homeassistant.components.persistent_notification import (
        async_create,
        async_dismiss,
    )

    from .download import register_download
    from .support_bundle import generate_support_bundle, save_support_bundle
    from .support_report import async_check_log_file, build_missing_log_notice

    device_ids = call.data.get(CONF_DEVICE_ID, [])
    target_address = call.data.get(ATTR_TARGET_ADDRESS)
    capture_duration = call.data.get(ATTR_CAPTURE_DURATION, DEFAULT_CAPTURE_DURATION)
    include_logs = call.data.get(ATTR_INCLUDE_LOGS, True)

    address: str | None = None
    coordinator: AdjustableBedCoordinator | None = None
    entry: ConfigEntry | None = None
    selected_device_id: str | None = None

    if target_address:
        from .config_flow import is_valid_mac_address

        address = str(target_address).upper().replace("-", ":")
        if not is_valid_mac_address(address):
            raise ServiceValidationError(
                f"Invalid MAC address format: {target_address}. "
                "Please provide a valid MAC address in the format "
                "XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX.",
                translation_domain=DOMAIN,
                translation_key="invalid_mac_address",
            )
        _LOGGER.info(
            "Generating support bundle for unconfigured device at %s",
            address,
        )
    elif device_ids:
        if len(device_ids) > 1:
            raise ServiceValidationError(
                "Support bundle generation only supports one configured device at a time. "
                "Select a single device or use target_address for an unconfigured bed.",
                translation_domain=DOMAIN,
                translation_key="multiple_device_targets_not_supported",
            )
        # str() narrows the untyped service-call value for the str-typed parameter
        selected_device_id = str(device_ids[0])
        target = _get_support_bundle_target_from_device(hass, selected_device_id)
        if target is not None:
            address, coordinator, entry = target
            device_name = coordinator.name if coordinator is not None else entry.title
            _LOGGER.info(
                "Generating support bundle for configured device %s at %s",
                device_name,
                address,
            )
        else:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID: {selected_device_id}. "
                "Please verify the device is configured and try again.",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
            )
    else:
        raise ServiceValidationError(
            "No device_id or target_address was provided. "
            "Please specify either a configured device or a target MAC address.",
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    assert address is not None

    # Probe the log file before capturing. The capture runs for minutes, and a
    # bundle without logs is missing the evidence that matters most for
    # connection problems, so warn while the user can still fix it and re-run
    # rather than only telling them afterwards (issue #385).
    log_notification_id = (
        f"adjustable_bed_support_bundle_logs_{address.replace(':', '_').lower()}"
    )
    # Only retract a notice this invocation still owns. The id is
    # address-stable on purpose, so a later run can clear a stale warning left
    # by an earlier one; per-invocation ids would lose that. The cost is that
    # overlapping captures share the id, so record who raised it last and let
    # only that invocation retract it. A later capture that re-raises the notice
    # takes ownership, and the earlier one then leaves it alone.
    log_notice_token = object()
    owns_log_notice = False
    # What the probe concluded, kept so the finished-bundle notice can repeat the
    # guidance even when the capture itself reports something else (an empty file
    # comes back as "empty", not "unavailable") or never read the log at all.
    probe_reason: str | None = None
    probe_error: str | None = None
    if include_logs:
        try:
            # O_NONBLOCK does not make regular-file I/O asynchronous, so a
            # stalled network or FUSE mount can still block the open. This probe
            # runs before the capture's own timeout, so bound it here or the
            # service could hang without ever starting or reporting. The
            # executor thread stays blocked either way, but the service does not.
            log_check = await asyncio.wait_for(
                async_check_log_file(hass), _LOG_PROBE_TIMEOUT
            )
        except TimeoutError:
            # Inconclusive, not proof of a wedged path: Home Assistant's shared
            # executor can be saturated enough that the job never started. Say
            # nothing and change nothing - the capture performs its own read and
            # reports what it actually found. Disabling logs here would drop them
            # from a minutes-long capture over a five-second queue delay.
            _LOGGER.warning(
                "Timed out checking whether %s is readable; capturing anyway",
                hass.config.path("home-assistant.log"),
            )
            log_check = None
        if log_check is not None:
            if log_check["available"]:
                # A previous run may have warned about missing logs, and that
                # warning is address-stable, so it would otherwise sit there
                # contradicting a bundle that does contain logs. Only clear it
                # when no capture still owns it: another logless capture may be
                # running right now and its warning is not stale.
                if not hass.data.get(_LOG_NOTICE_OWNERS, {}).get(log_notification_id):
                    async_dismiss(hass, log_notification_id)
            else:
                probe_reason = log_check["reason"]
                probe_error = log_check["error"]
                _LOGGER.warning(
                    "Support bundle for %s will not include logs: %s (%s)",
                    address,
                    log_check["path"],
                    probe_reason,
                )
                async_create(
                    hass,
                    build_missing_log_notice(
                        log_check["reason"], log_check["error"], future=True
                    )
                    + "\n\nThe capture is running anyway, so you will still get a "
                    "bundle with Bluetooth diagnostics.",
                    title="Adjustable Bed: this bundle will have no logs",
                    notification_id=log_notification_id,
                )
                hass.data.setdefault(_LOG_NOTICE_OWNERS, {}).setdefault(
                    log_notification_id, set()
                ).add(log_notice_token)
                owns_log_notice = True

    try:
        report = await asyncio.wait_for(
            generate_support_bundle(
                hass,
                address=address,
                capture_duration=capture_duration,
                include_logs=include_logs,
                coordinator=coordinator,
                entry=entry,
                device_id=selected_device_id,
            ),
            timeout=capture_duration + 120,
        )
        filepath = await hass.async_add_executor_job(
            save_support_bundle,
            hass,
            report,
            address,
        )

        download_url = register_download(hass, filepath)
        notification_count = len(report.get("notifications", []))
        evidence = report.get("evidence", {})
        evidence_warnings = evidence.get("warnings", [])
        warning_summary = ""
        if evidence_warnings:
            warning_summary = "\n\n**Capture warnings:**\n" + "\n".join(
                f"- {warning}" for warning in evidence_warnings
            )

        # A bundle without logs usually cannot explain why a command failed, and
        # the user only learns that after a maintainer asks for a second one. Say
        # it up front, at the moment they still have the bed in front of them.
        # The capture is the authority: it actually read the file, so a log that
        # appeared or filled up during the window really is usable whatever the
        # probe saw beforehand. The one carry-over is a file the probe measured
        # as empty, which the capture reports as "empty" rather than
        # "unavailable" but which is still unusable.
        log_status = evidence.get("log_capture_status")
        logs_missing = include_logs and (
            log_status == "unavailable"
            or (log_status == "empty" and probe_reason == "empty_file")
        )
        logging_notice = ""
        if logs_missing:
            log_error = evidence.get("log_capture_error") or probe_error
            _LOGGER.warning(
                "Support bundle for %s was generated without logs: %s",
                address,
                log_error or "the Home Assistant log file could not be read",
            )
            logging_notice = "\n\n" + build_missing_log_notice(
                evidence.get("log_capture_reason") or probe_reason, log_error
            )

        async_create(
            hass,
            f"[**Download support bundle**]({download_url})\n\n"
            f"Captured {notification_count} notifications over "
            f"{capture_duration} seconds."
            f"{logging_notice}"
            f"{warning_summary}\n\n"
            "Attach this JSON file when reporting unsupported or broken beds.\n\n"
            f"File path: `{filepath}`",
            title="Adjustable Bed Support Bundle Ready",
            notification_id=f"adjustable_bed_support_bundle_{address.replace(':', '_').lower()}",
        )
        _LOGGER.info("Support bundle saved to %s", filepath)
    except TimeoutError:
        _LOGGER.exception(
            "Support bundle generation timed out after %d seconds for %s",
            capture_duration + 120,
            address,
        )
        async_create(
            hass,
            f"Support bundle generation timed out after {capture_duration + 120} seconds "
            f"for {address}.\n\n"
            "The BLE diagnostics may be hanging. Check Bluetooth connectivity and try again.",
            title="Adjustable Bed Support Bundle Timeout",
            notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
        )
        raise
    except Exception as err:
        _LOGGER.exception("Failed to generate support bundle for %s", address)
        async_create(
            hass,
            f"Failed to generate support bundle for {address}:\n\n{err}",
            title="Adjustable Bed Support Bundle Error",
            notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
        )
        raise
    finally:
        # Whatever happened, the capture is no longer running, so the
        # pre-capture notice must not keep claiming that it is. A finally also
        # covers cancellation: CancelledError inherits from BaseException, so an
        # automation stopped mid-capture would skip an except Exception handler
        # and strand the notice forever.
        owners = hass.data.get(_LOG_NOTICE_OWNERS, {}).get(log_notification_id)
        if owns_log_notice and owners is not None:
            owners.discard(log_notice_token)
            # Retract only once the last overlapping logless capture is done,
            # so a short one finishing first cannot pull the notice out from
            # under a longer one that is still running without logs.
            if not owners:
                hass.data[_LOG_NOTICE_OWNERS].pop(log_notification_id, None)
                async_dismiss(hass, log_notification_id)

async def async_register_services(hass: HomeAssistant) -> None:
    """Register the Adjustable Bed services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET):
        return  # Services already registered

    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_PRESET,
        handle_goto_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_PRESET,
        handle_save_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_ALL,
        handle_stop_all,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POSITION,
        handle_set_position,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_MOTOR): vol.In(["back", "legs", "head", "feet", "lumbar"]),
                # No max cap here - per-motor validation handles bed-specific limits
                vol.Required(ATTR_POSITION): vol.All(vol.Coerce(float), vol.Range(min=0)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TIMED_MOVE,
        handle_timed_move,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_MOTOR): vol.In(TIMED_MOVE_MOTOR_OPTIONS),
                vol.Required(ATTR_DIRECTION): vol.In(["up", "down"]),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_TIMED_MOVE_DURATION_MS, max=MAX_TIMED_MOVE_DURATION_MS),
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_SUPPORT_BUNDLE,
        handle_generate_support_bundle,
        schema=vol.Schema(
            {
                vol.Exclusive(CONF_DEVICE_ID, "target"): cv.ensure_list,
                vol.Exclusive(ATTR_TARGET_ADDRESS, "target"): cv.string,
                vol.Optional(ATTR_CAPTURE_DURATION, default=DEFAULT_CAPTURE_DURATION): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_CAPTURE_DURATION, max=MAX_CAPTURE_DURATION),
                ),
                vol.Optional(ATTR_INCLUDE_LOGS, default=True): cv.boolean,
            }
        ),
    )

    _LOGGER.debug("Registered Adjustable Bed services")
