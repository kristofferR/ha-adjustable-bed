"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import CONF_BED_TYPE, CONF_HAS_MASSAGE, CONF_MOTOR_COUNT, DOMAIN
from .coordinator import AdjustableBedCoordinator

# Service constants
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_STOP_ALL = "stop_all"
SERVICE_RUN_DIAGNOSTICS = "run_diagnostics"
SERVICE_GENERATE_SUPPORT_REPORT = "generate_support_report"
ATTR_PRESET = "preset"
ATTR_TARGET_ADDRESS = "target_address"
ATTR_CAPTURE_DURATION = "capture_duration"
ATTR_INCLUDE_LOGS = "include_logs"

# Default capture duration for diagnostics (seconds)
DEFAULT_CAPTURE_DURATION = 120
MIN_CAPTURE_DURATION = 10
MAX_CAPTURE_DURATION = 300

# Timeout for initial connection at startup
# Must be long enough to cover at least one full connection attempt (30s) with margin
SETUP_TIMEOUT = 45.0

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adjustable Bed from a config entry."""
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

    # Connect to the bed with a timeout to avoid blocking startup forever
    _LOGGER.debug("Attempting initial connection to bed (timeout: %.0fs)...", SETUP_TIMEOUT)
    try:
        async with asyncio.timeout(SETUP_TIMEOUT):
            connected = await coordinator.async_connect()
    except TimeoutError:
        raise ConfigEntryNotReady(
            f"Connection to bed at {entry.data.get(CONF_ADDRESS)} timed out after {SETUP_TIMEOUT:.0f}s. "
            "The integration will retry automatically."
        ) from None

    if not connected:
        raise ConfigEntryNotReady(
            f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}. "
            "Check that the bed is powered on and in range of your Bluetooth adapter/proxy."
        )

    _LOGGER.info("Successfully connected to bed at %s", entry.data.get(CONF_ADDRESS))

    # Read initial positions in background (don't block startup)
    hass.async_create_task(coordinator.async_read_initial_positions())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services if not already registered
    await _async_register_services(hass)

    _LOGGER.info("Adjustable Bed integration setup complete for %s", entry.title)
    return True


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

    async def handle_goto_preset(call: ServiceCall) -> None:
        """Handle goto_preset service call."""
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                # Check if controller supports memory presets
                controller = coordinator.controller
                if controller is None or not getattr(
                    controller, "supports_memory_presets", False
                ):
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

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                # Check if controller supports programming memory presets
                controller = coordinator.controller
                if controller is None or not getattr(
                    controller, "supports_memory_programming", False
                ):
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
                vol.Required(ATTR_PRESET): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
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
                vol.Required(ATTR_PRESET): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
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

    async def handle_run_diagnostics(call: ServiceCall) -> None:
        """Handle run_diagnostics service call."""
        from homeassistant.components.persistent_notification import async_create

        from .ble_diagnostics import BLEDiagnosticRunner, save_diagnostic_report

        device_ids = call.data.get(CONF_DEVICE_ID, [])
        target_address = call.data.get(ATTR_TARGET_ADDRESS)
        capture_duration = call.data.get(ATTR_CAPTURE_DURATION, DEFAULT_CAPTURE_DURATION)

        # Determine which address to use
        address: str | None = None
        coordinator: AdjustableBedCoordinator | None = None

        if target_address:
            # Use the provided target address
            from .config_flow import is_valid_mac_address

            address = str(target_address).upper().replace("-", ":")
            if not is_valid_mac_address(address):
                _LOGGER.error(
                    "Invalid MAC address format for run_diagnostics: %s",
                    target_address,
                )
                async_create(
                    hass,
                    f"**Diagnostics Failed**\n\n"
                    f"Invalid MAC address format: `{target_address}`\n\n"
                    f"Please provide a valid MAC address in the format "
                    f"`XX:XX:XX:XX:XX:XX` or `XX-XX-XX-XX-XX-XX`.",
                    title="Adjustable Bed Diagnostics Error",
                    notification_id="adjustable_bed_diagnostics_error",
                )
                return
            _LOGGER.info(
                "Running diagnostics on unconfigured device at %s",
                address,
            )
        elif device_ids:
            # Use the first device ID to get the coordinator
            device_id = device_ids[0]
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                address = coordinator.address
                _LOGGER.info(
                    "Running diagnostics on configured device %s at %s",
                    coordinator.name,
                    address,
                )
            else:
                _LOGGER.error(
                    "Could not find Adjustable Bed device with ID %s for run_diagnostics service",
                    device_id,
                )
                async_create(
                    hass,
                    f"**Diagnostics Failed**\n\n"
                    f"Could not find Adjustable Bed device with ID: `{device_id}`\n\n"
                    f"Please verify the device is configured and try again.",
                    title="Adjustable Bed Diagnostics Error",
                    notification_id="adjustable_bed_diagnostics_error",
                )
                return
        else:
            _LOGGER.error("No device_id or target_address provided for run_diagnostics service")
            async_create(
                hass,
                "**Diagnostics Failed**\n\n"
                "No `device_id` or `target_address` was provided.\n\n"
                "Please specify either a configured device or a target MAC address.",
                title="Adjustable Bed Diagnostics Error",
                notification_id="adjustable_bed_diagnostics_error",
            )
            return

        # Run diagnostics (address is guaranteed to be str at this point)
        assert address is not None
        try:
            runner = BLEDiagnosticRunner(
                hass,
                address,
                capture_duration=capture_duration,
                coordinator=coordinator,
            )
            report = await runner.run_diagnostics()
            filepath = save_diagnostic_report(hass, report, address)

            # Create persistent notification
            async_create(
                hass,
                f"BLE diagnostic report saved to:\n\n`{filepath}`\n\n"
                f"Captured {len(report.notifications)} notifications over {capture_duration} seconds.\n\n"
                "Please attach this file when reporting the device.",
                title="Adjustable Bed Diagnostic Report Ready",
                notification_id=f"adjustable_bed_diagnostic_{address.replace(':', '_').lower()}",
            )
            _LOGGER.info("Diagnostic report saved to %s", filepath)
        except Exception as err:
            _LOGGER.exception("Failed to run diagnostics for %s", address)
            async_create(
                hass,
                f"Failed to run BLE diagnostics for {address}:\n\n{err}",
                title="Adjustable Bed Diagnostic Error",
                notification_id=f"adjustable_bed_diagnostic_error_{address.replace(':', '_').lower()}",
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_DIAGNOSTICS,
        handle_run_diagnostics,
        schema=vol.Schema(
            {
                vol.Exclusive(CONF_DEVICE_ID, "target"): cv.ensure_list,
                vol.Exclusive(ATTR_TARGET_ADDRESS, "target"): cv.string,
                vol.Optional(ATTR_CAPTURE_DURATION, default=DEFAULT_CAPTURE_DURATION): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_CAPTURE_DURATION, max=MAX_CAPTURE_DURATION)
                ),
            }
        ),
    )

    async def handle_generate_support_report(call: ServiceCall) -> None:
        """Handle generate_support_report service call."""
        from homeassistant.components.persistent_notification import async_create

        from .support_report import generate_support_report, save_support_report

        device_ids = call.data.get(CONF_DEVICE_ID, [])
        include_logs = call.data.get(ATTR_INCLUDE_LOGS, True)

        if not device_ids:
            _LOGGER.error("No device_id provided for generate_support_report service")
            async_create(
                hass,
                "No device was selected for the generate_support_report service.\n\n"
                "Please select an Adjustable Bed device and try again.",
                title="Adjustable Bed Support Report Error",
                notification_id="adjustable_bed_support_report_no_device",
            )
            return

        device_id = device_ids[0]
        coordinator = await _get_coordinator_from_device(hass, device_id)
        if not coordinator:
            _LOGGER.error(
                "Could not find Adjustable Bed device with ID %s for generate_support_report service",
                device_id,
            )
            async_create(
                hass,
                f"Could not find Adjustable Bed device with ID:\n\n`{device_id}`\n\n"
                "The device may have been removed or is no longer available.",
                title="Adjustable Bed Support Report Error",
                notification_id=f"adjustable_bed_support_report_not_found_{device_id[:8]}",
            )
            return

        # Find the config entry for this coordinator
        entry: ConfigEntry | None = None
        for entry_id, coord in hass.data[DOMAIN].items():
            if coord is coordinator:
                entry = hass.config_entries.async_get_entry(entry_id)
                break

        if not entry:
            _LOGGER.error("Could not find config entry for device %s", device_id)
            return

        try:
            _LOGGER.info("Generating support report for %s", coordinator.name)
            report = await generate_support_report(
                hass, entry, coordinator, include_logs=include_logs
            )
            filepath = await hass.async_add_executor_job(
                save_support_report, hass, report, coordinator.address
            )

            async_create(
                hass,
                f"Support report saved to:\n\n`{filepath}`\n\n"
                "**How to submit a bug report:**\n"
                "1. Go to [GitHub Issues](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml)\n"
                "2. Fill out the form\n"
                "3. Attach this JSON file to the issue\n\n"
                "The report contains diagnostic information with sensitive data (MAC address) redacted.",
                title="Adjustable Bed Support Report Ready",
                notification_id=f"adjustable_bed_support_report_{coordinator.address.replace(':', '_').lower()}",
            )
            _LOGGER.info("Support report saved to %s", filepath)
        except Exception as err:
            _LOGGER.exception("Failed to generate support report")
            async_create(
                hass,
                f"Failed to generate support report:\n\n{err}",
                title="Adjustable Bed Support Report Error",
                notification_id="adjustable_bed_support_report_error",
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_SUPPORT_REPORT,
        handle_generate_support_report,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
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

        # Unregister services if this was the last entry
        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister Adjustable Bed services."""
    for service in (
        SERVICE_GOTO_PRESET,
        SERVICE_SAVE_PRESET,
        SERVICE_STOP_ALL,
        SERVICE_RUN_DIAGNOSTICS,
        SERVICE_GENERATE_SUPPORT_REPORT,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    _LOGGER.debug("Unregistered Adjustable Bed services")
