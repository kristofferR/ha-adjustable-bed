"""eShine E2000/E3000/E3100/E5000 app alarm action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .services import (
    ATTR_ENABLED,
    ATTR_TIME,
    ATTR_WAKE_MODE,
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)

SERVICE_ESHINE_SET_ALARM = "eshine_set_alarm"


async def handle_eshine_set_alarm(call: ServiceCall) -> None:
    """Configure the explicit com.okin.eshine profile's next-occurrence alarm."""
    from .beds.eshine_okin import EshineOkinController

    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    preset = call.data.get(ATTR_WAKE_MODE, "zero_g")
    if enabled and alarm_time is None:
        raise ServiceValidationError("Choose an eShine alarm time")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("eShine alarms use minute precision")

    def validate(controller: EshineOkinController) -> None:
        if enabled and preset not in controller.clock_alarm_preset_options:
            raise ServiceValidationError("This eShine profile does not expose the selected alarm action")

    async def program(controller: EshineOkinController) -> None:
        if enabled:
            await controller.sync_clock()
        await controller.configure_clock_alarm(
            enabled=enabled, weekdays=(), hour=alarm_time.hour if alarm_time else 0,
            minute=alarm_time.minute if alarm_time else 0, preset=preset,
        )

    await _preflight_and_execute(
        _call_targets(call),
        EshineOkinController,
        "eShine alarms",
        program,
        supported=lambda controller: controller.supports_clock_alarm,
        validate=validate,
        cancel_running=True,
        resource=None,
    )


def async_register_eshine_okin_services(hass: HomeAssistant) -> None:
    """Register the eShine alarm action."""
    hass.services.async_register(
        DOMAIN, SERVICE_ESHINE_SET_ALARM, handle_eshine_set_alarm,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required(ATTR_ENABLED): cv.boolean,
            vol.Optional(ATTR_TIME): cv.time,
            vol.Optional(ATTR_WAKE_MODE, default="zero_g"): vol.In(("zero_g", "flat", "massage")),
            **SIDE_FIELD,
        }),
    )
