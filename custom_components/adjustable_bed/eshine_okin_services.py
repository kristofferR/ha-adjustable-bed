"""eShine E2000/E3000/E3100/E5000 app alarm action."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_ESHINE_OKIN, DOMAIN
from .services import (
    ATTR_ENABLED,
    ATTR_TIME,
    ATTR_WAKE_MODE,
    SIDE_FIELD,
    _call_targets,
    _command_targets,
    _execute_sided,
    _preflight_capability,
    _release_preflighted,
)

if TYPE_CHECKING:
    from .beds.base import BedController


SERVICE_ESHINE_SET_ALARM = "eshine_set_alarm"


async def handle_eshine_set_alarm(call: ServiceCall) -> None:
    """Configure the explicit com.okin.eshine profile's next-occurrence alarm."""
    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    preset = call.data.get(ATTR_WAKE_MODE, "zero_g")
    if enabled and alarm_time is None:
        raise ServiceValidationError("Choose an eShine alarm time")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("eShine alarms use minute precision")
    targets = _call_targets(call)
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_ESHINE_OKIN:
                raise ServiceValidationError("Choose an eShine E2000/E3000/E3100/E5000 app bed")

    def validate(controller: BedController) -> None:
        if enabled and preset not in controller.clock_alarm_preset_options:
            raise ServiceValidationError("This eShine profile does not expose the selected alarm action")

    preflighted = await _preflight_capability(
        targets, "supports_clock_alarm", "eShine alarms", validate=validate,
    )
    async def program(controller: BedController) -> None:
        if enabled:
            await controller.sync_clock()
        await controller.configure_clock_alarm(
            enabled=enabled, weekdays=(), hour=alarm_time.hour if alarm_time else 0,
            minute=alarm_time.minute if alarm_time else 0, preset=preset,
        )
    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, program)
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


def async_register_eshine_okin_services(hass: HomeAssistant) -> None:
    """Register the eShine alarm action."""
    hass.services.async_register(
        DOMAIN, SERVICE_ESHINE_SET_ALARM, handle_eshine_set_alarm,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
            vol.Required(ATTR_ENABLED): cv.boolean,
            vol.Optional(ATTR_TIME): cv.time,
            vol.Optional(ATTR_WAKE_MODE, default="zero_g"): vol.In(("zero_g", "flat", "massage")),
            **SIDE_FIELD,
        }),
    )
