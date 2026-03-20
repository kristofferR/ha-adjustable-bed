"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .beds.base import BedController

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_VIBRADORM,
    BEDS_WITH_POSITION_FEEDBACK,
    BEDTECH_SERVICE_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_ADV_TYPE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_KAIDI_VARIANT_SOURCE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    KEESON_VARIANT_ERGOMOTION,
    RICHMAT_REMOTE_AUTO,
    VARIANT_AUTO,
    requires_pairing,
)
from .coordinator import AdjustableBedCoordinator
from .detection import detect_richmat_remote_from_name
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .unsupported import create_pairing_required_issue

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Service constants
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_GENERATE_SUPPORT_BUNDLE = "generate_support_bundle"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_SET_POSITION = "set_position"
SERVICE_STOP_ALL = "stop_all"
SERVICE_TIMED_MOVE = "timed_move"
ATTR_PRESET = "preset"
ATTR_MOTOR = "motor"
ATTR_POSITION = "position"
ATTR_TARGET_ADDRESS = "target_address"
ATTR_CAPTURE_DURATION = "capture_duration"
ATTR_INCLUDE_LOGS = "include_logs"
ATTR_DIRECTION = "direction"
ATTR_DURATION_MS = "duration_ms"
TIMED_MOVE_MOTOR_OPTIONS = (
    "back",
    "legs",
    "head",
    "feet",
    "tilt",
    "lumbar",
    "bed_height",
)

# Default capture duration for diagnostics (seconds)
DEFAULT_CAPTURE_DURATION = 120
MIN_CAPTURE_DURATION = 10
MAX_CAPTURE_DURATION = 300

# Timed move duration limits (milliseconds)
MIN_TIMED_MOVE_DURATION_MS = 100
MAX_TIMED_MOVE_DURATION_MS = 30000  # 30 seconds max

# Timeout for initial connection at startup
# Must be long enough to cover at least one full connection attempt (30s) with margin
SETUP_TIMEOUT = 45.0

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Adjustable Bed integration domain."""
    hass.data.setdefault(DOMAIN, {})

    from .download import SupportBundleDownloadView

    hass.http.register_view(SupportBundleDownloadView)

    await _async_register_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries to newer schema versions."""
    _LOGGER.debug(
        "Migrating config entry %s for %s from version %s",
        entry.entry_id,
        entry.title,
        entry.version,
    )

    if entry.version > 3:
        _LOGGER.error(
            "Cannot migrate config entry %s for %s from unsupported future version %s",
            entry.entry_id,
            entry.title,
            entry.version,
        )
        return False

    if entry.version <= 2:
        new_data = {**entry.data}

        # Legacy Vibradorm entries that predate disable_angle_sensing defaulted
        # position feedback to disabled, so entities stayed unavailable unless
        # users manually reconfigured options.
        if (
            new_data.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM
            and CONF_DISABLE_ANGLE_SENSING not in new_data
        ):
            new_data[CONF_DISABLE_ANGLE_SENSING] = False
            _LOGGER.info(
                "Migrated %s (%s): enabled angle sensing only for legacy Vibradorm "
                "entries missing disable_angle_sensing (existing user setting left unchanged)",
                entry.title,
                entry.entry_id,
            )

        hass.config_entries.async_update_entry(entry, data=new_data, version=3)

    _LOGGER.debug(
        "Migration complete for config entry %s (%s), now at version %s",
        entry.title,
        entry.entry_id,
        entry.version,
    )
    return True


def _maybe_cache_kaidi_metadata(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Cache Kaidi room/VADDR state from Bluetooth history for existing entries."""
    if entry.data.get(CONF_BED_TYPE) != BED_TYPE_KAIDI:
        return

    advertisement = resolve_kaidi_advertisement(
        hass,
        entry.data[CONF_ADDRESS],
    )
    if advertisement is None:
        return

    new_data = add_kaidi_entry_metadata(entry.data, advertisement)
    if new_data == dict(entry.data):
        return

    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info(
        "Cached Kaidi metadata for %s (room_id=%s, target_vaddr=%s, product_id=%s, sofa_acu_no=%s, adv_type=%s, resolved_variant=%s, variant_source=%s)",
        entry.data[CONF_ADDRESS],
        new_data.get(CONF_KAIDI_ROOM_ID),
        new_data.get(CONF_KAIDI_TARGET_VADDR),
        new_data.get(CONF_KAIDI_PRODUCT_ID),
        new_data.get(CONF_KAIDI_SOFA_ACU_NO),
        new_data.get(CONF_KAIDI_ADV_TYPE),
        new_data.get(CONF_KAIDI_RESOLVED_VARIANT),
        new_data.get(CONF_KAIDI_VARIANT_SOURCE),
    )


async def _async_finish_entry_setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    *,
    schedule_initial_position_read: bool,
) -> bool:
    """Store coordinator, forward platforms, and finish setup."""
    hass.data[DOMAIN][entry.entry_id] = coordinator

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if schedule_initial_position_read:
        hass.async_create_task(coordinator.async_read_initial_positions())

    _LOGGER.info("Adjustable Bed integration setup complete for %s", entry.title)
    return True


async def _async_setup_offline_diagnostic_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    reason: str,
) -> bool:
    """Load a diagnostic entry even when initial BLE connection fails."""
    from .beds.diagnostic import DiagnosticBedController

    _LOGGER.warning(
        "Loading diagnostic entry %s (%s) without an initial BLE connection so "
        "diagnostic actions remain available: %s",
        entry.title,
        entry.data.get(CONF_ADDRESS),
        reason,
    )
    coordinator._controller = DiagnosticBedController(coordinator)
    return await _async_finish_entry_setup(
        hass,
        entry,
        coordinator,
        schedule_initial_position_read=False,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adjustable Bed from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_services(hass)

    await _async_maybe_reclassify_legacy_bedtech_entry(hass, entry)
    _maybe_cache_kaidi_metadata(hass, entry)

    _LOGGER.info(
        "Setting up Adjustable Bed integration for %s (address: %s, type: %s, motors: %s, massage: %s)",
        entry.title,
        entry.data.get(CONF_ADDRESS),
        entry.data.get(CONF_BED_TYPE),
        entry.data.get(CONF_MOTOR_COUNT),
        entry.data.get(CONF_HAS_MASSAGE),
    )

    coordinator = AdjustableBedCoordinator(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Helper to create pairing issue — only when there's actual evidence of a pairing
    # problem. Generic connection failures (timeout, device not found) should NOT
    # trigger this, since the bed may just be temporarily unreachable after a restart.
    async def _maybe_create_pairing_issue() -> None:
        bed_type = entry.data.get(CONF_BED_TYPE)
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        if not (bed_type and requires_pairing(bed_type, protocol_variant)):
            return

        address = entry.data.get(CONF_ADDRESS, "")

        # Check if the device is already paired/bonded at the OS level (BlueZ).
        # If it is, the connection failure is transient — not a pairing problem.
        if address:
            ble_device = bluetooth.async_ble_device_from_address(
                hass, address, connectable=True
            )
            if ble_device is not None and isinstance(
                getattr(ble_device, "details", None), dict
            ):
                props = ble_device.details.get("props", {})
                if props.get("Paired") or props.get("Bonded"):
                    _LOGGER.debug(
                        "Bed %s is already paired/bonded at OS level — "
                        "connection failure is transient, skipping pairing repair",
                        address,
                    )
                    return

        # Adapter explicitly doesn't support pairing (e.g. old ESPHome proxy)
        if coordinator.pairing_supported is False:
            await create_pairing_required_issue(
                hass, address or "Unknown", entry.data.get("name", entry.title)
            )
            return

        # Connection failed before pairing was even attempted (device not found,
        # timeout, etc.). Don't create repair — HA will retry automatically and
        # pairing will be attempted on the next successful connection.
        _LOGGER.debug(
            "Bed %s requires pairing but connection failed before pairing could be "
            "attempted — not creating pairing repair (will retry automatically)",
            address,
        )

    # Connect to the bed with a timeout to avoid blocking startup forever
    _LOGGER.debug("Attempting initial connection to bed (timeout: %.0fs)...", SETUP_TIMEOUT)
    try:
        async with asyncio.timeout(SETUP_TIMEOUT):
            connected = await coordinator.async_connect()
    except TimeoutError:
        await _maybe_create_pairing_issue()
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason=f"initial connection timed out after {SETUP_TIMEOUT:.0f}s",
            )
        raise ConfigEntryNotReady(
            f"Connection to bed at {entry.data.get(CONF_ADDRESS)} timed out after {SETUP_TIMEOUT:.0f}s. "
            "The integration will retry automatically."
        ) from None

    if not connected:
        await _maybe_create_pairing_issue()
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason="device was not reachable during initial setup",
            )
        raise ConfigEntryNotReady(
            f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}. "
            "Check that the bed is powered on and in range of your Bluetooth adapter/proxy."
        )

    _LOGGER.info("Successfully connected to bed at %s", entry.data.get(CONF_ADDRESS))
    return await _async_finish_entry_setup(
        hass,
        entry,
        coordinator,
        schedule_initial_position_read=True,
    )


async def _async_maybe_reclassify_legacy_bedtech_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Correct legacy BedTech entries that were created for Richmat QRRM beds.

    BedTech and Richmat WiLinke share the FEE9 service, and older versions of
    the integration could persist QRRM devices as `bedtech`. That leaves the
    entry sending BedTech preset/light bytes to a Richmat controller, which is
    why issue #243 reported lounge and light commands either doing nothing or
    triggering the wrong behavior.
    """
    if entry.data.get(CONF_BED_TYPE) != BED_TYPE_BEDTECH:
        return

    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return

    service_info = bluetooth.async_last_service_info(hass, address, connectable=True)
    if service_info is None:
        return

    service_uuids = {
        uuid.lower() for uuid in (getattr(service_info, "service_uuids", None) or [])
    }
    if BEDTECH_SERVICE_UUID.lower() not in service_uuids:
        return

    device_name = getattr(service_info, "name", None)
    detected_remote = detect_richmat_remote_from_name(device_name)
    if not detected_remote:
        return

    new_data = {
        **entry.data,
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
    }
    if entry.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO) == RICHMAT_REMOTE_AUTO:
        new_data[CONF_RICHMAT_REMOTE] = detected_remote

    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.warning(
        "Corrected config entry %s (%s) from BedTech to Richmat because BLE name %r "
        "matches Richmat remote %r on the shared FEE9 service",
        entry.title,
        entry.entry_id,
        device_name,
        detected_remote,
    )


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register Adjustable Bed services."""
    if hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET):
        return  # Services already registered

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
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])

        _LOGGER.info("Service goto_preset called: preset=%d", preset)

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                # Check if controller supports memory presets
                controller = await _get_controller_for_service(coordinator)
                if not getattr(controller, "supports_memory_presets", False):
                    raise ServiceValidationError(
                        f"Device '{coordinator.name}' does not support memory presets",
                        translation_domain=DOMAIN,
                        translation_key="memory_presets_not_supported",
                        translation_placeholders={"device_name": coordinator.name},
                    )
                # Validate preset against controller's memory slot count
                slot_count = getattr(controller, "memory_slot_count", 4)
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
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])

        _LOGGER.info("Service save_preset called: preset=%d", preset)

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                # Check if controller supports programming memory presets
                controller = await _get_controller_for_service(coordinator)
                if not getattr(controller, "supports_memory_programming", False):
                    raise ServiceValidationError(
                        f"Device '{coordinator.name}' does not support programming memory presets",
                        translation_domain=DOMAIN,
                        translation_key="memory_programming_not_supported",
                        translation_placeholders={"device_name": coordinator.name},
                    )
                # Validate preset against controller's memory slot count
                slot_count = getattr(controller, "memory_slot_count", 4)
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

    async def handle_set_position(call: ServiceCall) -> None:
        """Handle set_position service call."""
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
            entry: ConfigEntry | None = None
            for entry_id, coord in hass.data[DOMAIN].items():
                if coord is coordinator:
                    entry = hass.config_entries.async_get_entry(entry_id)
                    break

            if not entry:
                raise ServiceValidationError(
                    f"Could not find config entry for device {device_id}",
                    translation_domain=DOMAIN,
                    translation_key="device_not_found",
                    translation_placeholders={"device_id": device_id},
                )

            bed_type = entry.data.get(CONF_BED_TYPE)
            motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
            protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
            supports_direct_position_control = bool(
                getattr(controller, "supports_direct_position_control", False)
            )

            # Validate bed supports position feedback
            # Special case: BED_TYPE_KEESON only supports position feedback with ergomotion variant
            has_position_feedback = bed_type in BEDS_WITH_POSITION_FEEDBACK or (
                bed_type == BED_TYPE_KEESON
                and protocol_variant == KEESON_VARIANT_ERGOMOTION
            )
            if not has_position_feedback and not supports_direct_position_control:
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
            # For BOX25: only head and feet are valid, using direct percentage positions.
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
                valid_motors = {"head", "feet"}
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
                }
            else:
                # Standard beds: motor availability depends on motor_count
                motor_configs = {
                    "back": {
                        "position_key": "back",
                        "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                        "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                        "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                        "max_value": 68.0,  # Degrees
                        "min_motors": 2,
                    },
                    "legs": {
                        "position_key": "legs",
                        "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                        "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                        "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                        "max_value": 45.0,  # Degrees
                        "min_motors": 2,
                    },
                    "head": {
                        "position_key": "head",
                        "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                        "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                        "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                        "max_value": 68.0,  # Degrees
                        "min_motors": 3,
                    },
                    "feet": {
                        "position_key": "feet",
                        "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                        "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                        "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                        "max_value": 45.0,  # Degrees
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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POSITION,
        handle_set_position,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_MOTOR): vol.In(["back", "legs", "head", "feet"]),
                # No max cap here - per-motor validation handles bed-specific limits
                vol.Required(ATTR_POSITION): vol.All(vol.Coerce(float), vol.Range(min=0)),
            }
        ),
    )

    async def handle_timed_move(call: ServiceCall) -> None:
        """Handle timed_move service call."""
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
            pulse_delay_ms = coordinator.motor_pulse_delay_ms
            if pulse_delay_ms <= 0:
                _LOGGER.warning(
                    "Invalid motor_pulse_delay_ms (%d) for device %s, using default 100ms",
                    pulse_delay_ms,
                    coordinator.name,
                )
                pulse_delay_ms = 100  # DEFAULT_MOTOR_PULSE_DELAY_MS
            # Round up to honor requested duration as minimum
            calculated_repeat_count = max(1, (duration_ms + pulse_delay_ms - 1) // pulse_delay_ms)

            _LOGGER.debug(
                "Timed move: duration=%dms, pulse_delay=%dms, repeat_count=%d",
                duration_ms,
                pulse_delay_ms,
                calculated_repeat_count,
            )

            # Store original pulse count to restore after
            original_pulse_count = coordinator.motor_pulse_count

            # Bind closure variables as defaults to avoid late-binding bugs
            async def timed_movement(
                ctrl: BedController,
                *,
                _coordinator: AdjustableBedCoordinator = coordinator_,
                _move_fn: Callable[..., Coroutine[Any, Any, None]] = move_fn,
                _stop_fn: Callable[..., Coroutine[Any, Any, None]] = stop_fn,
                _calculated_repeat_count: int = calculated_repeat_count,
                _original_pulse_count: int = original_pulse_count,
            ) -> None:
                """Execute movement for specified duration, always sending stop."""
                try:
                    # Temporarily set pulse count to calculated value
                    # This is safe because we're inside the command lock
                    _coordinator._motor_pulse_count = _calculated_repeat_count

                    # Call the movement function (uses coordinator's pulse settings)
                    await _move_fn(ctrl)
                finally:
                    # Restore original pulse count
                    _coordinator._motor_pulse_count = _original_pulse_count

                    # Always send stop command
                    await asyncio.shield(_stop_fn(ctrl))

            await coordinator.async_execute_controller_command(timed_movement)

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

    async def handle_generate_support_bundle(call: ServiceCall) -> None:
        """Handle generate_support_bundle service call."""
        from homeassistant.components.persistent_notification import async_create

        from .download import register_download
        from .support_bundle import generate_support_bundle, save_support_bundle

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
            selected_device_id = device_ids[0]
            coordinator = await _get_coordinator_from_device(hass, selected_device_id)
            if coordinator:
                address = coordinator.address
                for entry_id, coord in hass.data.get(DOMAIN, {}).items():
                    if coord is coordinator:
                        entry = hass.config_entries.async_get_entry(entry_id)
                        break
                _LOGGER.info(
                    "Generating support bundle for configured device %s at %s",
                    coordinator.name,
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
            async_create(
                hass,
                f"[**Download support bundle**]({download_url})\n\n"
                f"Captured {notification_count} notifications over "
                f"{capture_duration} seconds.\n\n"
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Adjustable Bed integration for %s", entry.title)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: AdjustableBedCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Disconnecting from bed...")
        await coordinator.async_disconnect()
        _LOGGER.info("Successfully unloaded Adjustable Bed integration for %s", entry.title)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    await hass.config_entries.async_reload(entry.entry_id)
