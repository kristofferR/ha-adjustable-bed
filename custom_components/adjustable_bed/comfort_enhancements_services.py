"""Comfort Enhancements alarm action."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_COMFORT_ENHANCEMENTS, DOMAIN
from .paired_coordinator import BedChild
from .services import (
    ATTR_ENABLED,
    ATTR_TIME,
    SIDE_FIELD,
    _call_targets,
    _execute_sided,
    _preflight_each,
    _release_preflighted,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.comfort_enhancements import ComfortEnhancementsController


async def handle_comfort_enhancements_set_alarm(call: ServiceCall) -> None:
    """Program the app's current-day alarm, validating every side before writes."""
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
    targets = _call_targets(call)

    def validate(target: BedChild, controller: BedController) -> None:
        if target.bed_type != BED_TYPE_COMFORT_ENHANCEMENTS:
            raise ServiceValidationError("Choose a Comfort Enhancements app controller")
        cast("ComfortEnhancementsController", controller).validate_alarm(**fields)

    preflighted = await _preflight_each(targets, validate)

    async def program(controller: BedController) -> None:
        await cast("ComfortEnhancementsController", controller).set_alarm(**fields)

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, program, cancel_running=False, resource="configuration")
    except Exception:
        await _release_preflighted(preflighted)
        raise


def async_register_comfort_enhancements_services(hass: HomeAssistant) -> None:
    """Register the Comfort Enhancements alarm action."""
    hass.services.async_register(
        DOMAIN, "comfort_enhancements_set_alarm", handle_comfort_enhancements_set_alarm,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
            vol.Required(ATTR_ENABLED): cv.boolean,
            vol.Optional(ATTR_TIME): cv.time,
            vol.Optional("memory", default=0): vol.All(vol.Coerce(int), vol.In((0, 1, 2))),
            vol.Optional("massage", default=False): cv.boolean,
            **SIDE_FIELD,
        }),
    )
