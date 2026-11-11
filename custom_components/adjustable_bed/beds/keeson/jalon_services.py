"""OkinComfortBed II bed-local alarm action."""

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
    ATTR_WAKE_MODE,
    ATTR_WEEKDAYS,
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


async def handle_set_alarm(call: ServiceCall) -> None:
    """Preflight every physical target before configuring its own app profile."""
    await async_import_modules(call.hass, "beds.keeson.jalon")
    from .jalon import JalonController

    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    if enabled and alarm_time is None:
        raise ServiceValidationError("Choose an OkinComfortBed II alarm time")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("OkinComfortBed II alarms use minute precision")

    async def program(controller: JalonController) -> None:
        await controller.configure_clock_alarm(
            enabled=enabled,
            weekdays=tuple(DAYS.index(day) + 1 for day in call.data[ATTR_WEEKDAYS]),
            hour=alarm_time.hour if alarm_time else 0,
            minute=alarm_time.minute if alarm_time else 0,
            preset=call.data[ATTR_WAKE_MODE],
        )

    await _preflight_and_execute(
        _call_targets(call),
        JalonController,
        "OkinComfortBed II alarms",
        program,
        supported=lambda controller: controller.supports_clock_alarm,
        cancel_running=True,
        resource=None,
    )


def async_register_jalon_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "jalon_set_alarm",
        handle_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(cv.ensure_list, [vol.In(DAYS)]),
                vol.Optional(ATTR_WAKE_MODE, default="flat"): vol.In(
                    ("flat", "memory_1", "memory_2", "zero_g", "anti_snore", "tv", "massage")
                ),
                **SIDE_FIELD,
            }
        ),
    )
