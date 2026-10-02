"""Richmat MH app alarm and aroma actions (Revive, Best Mattress, Blvd Home, HARMONY, Idealbed)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .beds.base import BedController, SideBoundController
from .beds.richmat_mh import ALARM_OPTION_CODES
from .beds.richmat_mh_protocol import WAIST_ALARM_REPEAT, WAIST_SIDES, alarm_countdown_minutes
from .const import DOMAIN
from .services import (
    SIDE_FIELD,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

SERVICE_RICHMAT_MH_ALARM = "richmat_mh_alarm"
SERVICE_RICHMAT_MH_AROMA = "richmat_mh_aroma"
SERVICE_RICHMAT_MH_WAIST_ALARM = "richmat_mh_waist_alarm"
_OPTIONS = tuple(ALARM_OPTION_CODES)

_ALARM_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
    vol.Required("enabled"): cv.boolean,
    vol.Optional("time"): cv.time,
    vol.Optional("position"): vol.In(_OPTIONS),
    vol.Optional("massage", default=[]): vol.All(cv.ensure_list, [vol.In(_OPTIONS)]),
    vol.Optional("slot"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
}
_ALARM_FIELDS.update(SIDE_FIELD.items())
ALARM_SCHEMA = vol.Schema(_ALARM_FIELDS)
_AROMA_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
    vol.Required("mode2_startup_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
    vol.Required("mode3_startup_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
    vol.Required("mode3_pause_hours"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
}
_AROMA_FIELDS.update(SIDE_FIELD.items())
AROMA_SCHEMA = vol.Schema(_AROMA_FIELDS)
_WAIST_ALARM_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
    vol.Required("enabled"): cv.boolean,
    vol.Required("waist_side"): vol.In(tuple(WAIST_SIDES)),
    vol.Optional("time"): cv.time,
    vol.Optional("repeat", default="once"): vol.In(tuple(WAIST_ALARM_REPEAT)),
    vol.Optional("intensity", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
}
_WAIST_ALARM_FIELDS.update(SIDE_FIELD.items())
WAIST_ALARM_SCHEMA = vol.Schema(_WAIST_ALARM_FIELDS)


async def _execute(
    call: ServiceCall,
    capability: str,
    label: str,
    command: Callable[[BedController], Awaitable[None]],
    validate: Callable[[BedController | SideBoundController], None] | None = None,
) -> None:
    """Validate every physical target first, then write each one in turn."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get("side")
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(targets, capability, label, validate)

    async def control(controller: BedController) -> None:
        try:
            await command(controller)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, control, cancel_running=False, resource="configuration"
            )
    except BaseException:
        # Cancellation must also hand the preflighted links back to idle.
        await _release_preflighted(preflighted)
        raise


async def handle_richmat_mh_alarm(call: ServiceCall) -> None:
    """Set or cancel the app's countdown alarm with a page-listed position."""
    enabled: bool = call.data["enabled"]
    position: str | None = call.data.get("position")
    massage: list[str] = call.data["massage"]
    slot: int | None = call.data.get("slot")
    minutes = 0
    if enabled:
        when = call.data.get("time")
        if when is None:
            raise ServiceValidationError("Setting an alarm requires a time")
        if when.second or when.microsecond:
            raise ServiceValidationError("Richmat MH alarms use minute precision")
        now = dt_util.now()
        # The app sends the minutes from now until the next occurrence.
        minutes = alarm_countdown_minutes(when.hour * 60 + when.minute, now.hour * 60 + now.minute)

    def validate(controller: BedController | SideBoundController) -> None:
        controller.validate_richmat_mh_alarm(
            enabled=enabled, position=position, massage=massage, slot=slot
        )

    async def program(controller: BedController) -> None:
        await controller.richmat_mh_alarm(
            enabled=enabled, minutes=minutes, position=position, massage=massage, slot=slot
        )

    await _execute(call, "supports_richmat_mh_alarm", "Richmat MH alarms", program, validate)


async def handle_richmat_mh_aroma(call: ServiceCall) -> None:
    """Write the aroma page's three timing sliders as the app does on release."""

    async def program(controller: BedController) -> None:
        await controller.richmat_mh_aroma(
            call.data["mode2_startup_minutes"],
            call.data["mode3_startup_minutes"],
            call.data["mode3_pause_hours"],
        )

    await _execute(call, "supports_richmat_mh_aroma", "Richmat MH aroma timing", program)


async def handle_richmat_mh_waist_alarm(call: ServiceCall) -> None:
    """Save or cancel one side's waist mattress alarm with the phone's current time."""
    enabled: bool = call.data["enabled"]
    when = call.data.get("time")
    if enabled and when is None:
        raise ServiceValidationError("Setting an alarm requires a time")
    if when is not None and (when.second or when.microsecond):
        raise ServiceValidationError("Richmat MH alarms use minute precision")
    now = dt_util.now()

    async def program(controller: BedController) -> None:
        await controller.richmat_mh_waist_alarm(
            enabled=enabled,
            waist_side=call.data["waist_side"],
            hour=when.hour if when else 0,
            minute=when.minute if when else 0,
            now_hour=now.hour,
            now_minute=now.minute,
            repeat=call.data["repeat"],
            intensity=call.data["intensity"],
        )

    await _execute(
        call, "supports_richmat_mh_waist_alarm", "Richmat MH waist mattress alarms", program
    )


def async_register_richmat_mh_services(hass: HomeAssistant) -> None:
    """Register the Richmat MH configuration actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_RICHMAT_MH_ALARM, handle_richmat_mh_alarm, schema=ALARM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RICHMAT_MH_AROMA, handle_richmat_mh_aroma, schema=AROMA_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RICHMAT_MH_WAIST_ALARM, handle_richmat_mh_waist_alarm,
        schema=WAIST_ALARM_SCHEMA,
    )
