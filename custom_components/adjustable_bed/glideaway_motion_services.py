"""Glideaway Motion app alarm action."""

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

SERVICE_GLIDEAWAY_SET_ALARM = "glideaway_set_alarm"


async def handle_glideaway_set_alarm(call: ServiceCall) -> None:
    """Use the Glideaway app's automatic day selection and exact clock encoding."""
    from .beds.glideaway_motion import GlideawayMotionController

    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    if enabled and alarm_time is None:
        raise ServiceValidationError("Choose a Glideaway alarm time")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("Glideaway alarms use minute precision")

    async def program(controller: GlideawayMotionController) -> None:
        await controller.configure_clock_alarm(
            enabled=enabled, weekdays=(),
            hour=alarm_time.hour if alarm_time is not None else 0,
            minute=alarm_time.minute if alarm_time is not None else 0,
            preset=call.data[ATTR_WAKE_MODE],
        )

    await _preflight_and_execute(
        _call_targets(call),
        GlideawayMotionController,
        "Glideaway alarms",
        program,
        supported=lambda controller: controller.supports_clock_alarm,
        cancel_running=True,
        resource=None,
    )


def async_register_glideaway_motion_services(hass: HomeAssistant) -> None:
    """Register the Glideaway alarm action."""
    hass.services.async_register(
        DOMAIN, SERVICE_GLIDEAWAY_SET_ALARM, handle_glideaway_set_alarm,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required(ATTR_ENABLED): cv.boolean,
            vol.Optional(ATTR_TIME): cv.time,
            vol.Optional(ATTR_WAKE_MODE, default="none"): vol.In(("none", "memory_1", "memory_2")),
            **SIDE_FIELD,
        }),
    )
