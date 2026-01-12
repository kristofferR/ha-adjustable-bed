"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import CONF_BED_TYPE, CONF_HAS_MASSAGE, CONF_MOTOR_COUNT, DOMAIN
from .coordinator import AdjustableBedCoordinator

# Service constants
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_STOP_ALL = "stop_all"
ATTR_PRESET = "preset"

# Timeout for initial connection at startup
SETUP_TIMEOUT = 15.0

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.COVER,
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
                return hass.data[DOMAIN][entry_id]
        return None

    async def handle_goto_preset(call: ServiceCall) -> None:
        """Handle goto_preset service call."""
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                await coordinator.async_execute_controller_command(
                    lambda ctrl, p=preset: ctrl.preset_memory(p)
                )

    async def handle_save_preset(call: ServiceCall) -> None:
        """Handle save_preset service call."""
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                await coordinator.async_execute_controller_command(
                    lambda ctrl, p=preset: ctrl.program_memory(p),
                    cancel_running=False,
                )

    async def handle_stop_all(call: ServiceCall) -> None:
        """Handle stop_all service call."""
        device_ids = call.data.get(CONF_DEVICE_ID, [])

        for device_id in device_ids:
            coordinator = await _get_coordinator_from_device(hass, device_id)
            if coordinator:
                await coordinator.async_stop_command()

    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_PRESET,
        handle_goto_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=4)
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
                    vol.Coerce(int), vol.Range(min=1, max=4)
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
    for service in (SERVICE_GOTO_PRESET, SERVICE_SAVE_PRESET, SERVICE_STOP_ALL):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    _LOGGER.debug("Unregistered Adjustable Bed services")
