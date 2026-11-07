"""Comfort Enhancements alarm action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    ATTR_ENABLED,
    ATTR_TIME,
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)


async def handle_comfort_enhancements_set_alarm(call: ServiceCall) -> None:
    """Program the app's current-day alarm, validating every side before writes."""
    await async_import_modules(call.hass, "beds.comfort_enhancements.controller")
    from .controller import ComfortEnhancementsController

    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    if enabled and alarm_time is None:
        raise ServiceValidationError("Choose an alarm time")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("Comfort Enhancements alarms use minute precision")
    fields = {
        "enabled": enabled,
        "hour": alarm_time.hour if alarm_time is not None else 0,
        "minute": alarm_time.minute if alarm_time is not None else 0,
        "memory": call.data["memory"],
        "massage": call.data["massage"],
    }

    async def program(controller: ComfortEnhancementsController) -> None:
        await controller.set_alarm(**fields)

    await _preflight_and_execute(
        _call_targets(call),
        ComfortEnhancementsController,
        "Comfort Enhancements alarms",
        program,
        validate=lambda controller: controller.validate_alarm(**fields),
    )


def async_register_comfort_enhancements_services(hass: HomeAssistant) -> None:
    """Register the Comfort Enhancements alarm action."""
    hass.services.async_register(
        DOMAIN, "comfort_enhancements_set_alarm", handle_comfort_enhancements_set_alarm,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required(ATTR_ENABLED): cv.boolean,
            vol.Optional(ATTR_TIME): cv.time,
            vol.Optional("memory", default=0): vol.All(vol.Coerce(int), vol.In((0, 1, 2))),
            vol.Optional("massage", default=False): cv.boolean,
            **SIDE_FIELD,
        }),
    )
