"""Glideaway Motion app alarm action."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_GLIDEAWAY_MOTION, DOMAIN
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
    from .beds.base import BedController, SideBoundController


SERVICE_GLIDEAWAY_SET_ALARM = "glideaway_set_alarm"


async def handle_glideaway_set_alarm(call: ServiceCall) -> None:
    """Use the Glideaway app's automatic day selection and exact clock encoding."""
    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    if enabled and alarm_time is None:
        raise ServiceValidationError("Choose a Glideaway alarm time")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("Glideaway alarms use minute precision")
    targets = _call_targets(call)
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_GLIDEAWAY_MOTION:
                raise ServiceValidationError(f"Device '{target.name}' is not a Glideaway Motion app bed")
    preflighted = await _preflight_capability(targets, "supports_clock_alarm", "Glideaway alarms")

    async def program(controller: BedController | SideBoundController) -> None:
        await controller.configure_clock_alarm(
            enabled=enabled, weekdays=(),
            hour=alarm_time.hour if alarm_time is not None else 0,
            minute=alarm_time.minute if alarm_time is not None else 0,
            preset=call.data[ATTR_WAKE_MODE],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, program)
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


def async_register_glideaway_motion_services(hass: HomeAssistant) -> None:
    """Register the Glideaway alarm action."""
    hass.services.async_register(
        DOMAIN, SERVICE_GLIDEAWAY_SET_ALARM, handle_glideaway_set_alarm,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
            vol.Required(ATTR_ENABLED): cv.boolean,
            vol.Optional(ATTR_TIME): cv.time,
            vol.Optional(ATTR_WAKE_MODE, default="none"): vol.In(("none", "memory_1", "memory_2")),
            **SIDE_FIELD,
        }),
    )
