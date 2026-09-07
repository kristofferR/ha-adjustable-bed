"""Structured, product-gated RMControl alarm and snore configuration actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .beds.base import BedController
from .const import DOMAIN
from .services import (
    SIDE_FIELD,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_ALARM_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): cv.ensure_list,
    vol.Required("operation"): vol.In(
        ("single", "cancel_single", "repeat", "delete", "query", "sync")
    ),
    vol.Optional("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Optional("action"): cv.string,
    vol.Optional("alarm_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    vol.Optional("time"): cv.time,
    vol.Optional("weekdays"): vol.All(cv.ensure_list, [vol.In(WEEKDAYS)]),
}
_ALARM_FIELDS.update(SIDE_FIELD.items())
ALARM_SCHEMA = vol.Schema(_ALARM_FIELDS)
_ANTI_SNORE_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): cv.ensure_list,
    vol.Required("operation"): vol.In(("switch", "configure", "query")),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("mode"): vol.In(("count", "time")),
    vol.Optional("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
}
_ANTI_SNORE_FIELDS.update(SIDE_FIELD.items())
ANTI_SNORE_SCHEMA = vol.Schema(_ANTI_SNORE_FIELDS)


async def _execute(
    call: ServiceCall, capability: str, command: Callable[[BedController], Awaitable[None]]
) -> None:
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get("side")
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(targets, capability, "RMControl configuration")

    async def control(controller: BedController) -> None:
        try:
            await command(controller)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                control,
                cancel_running=False,
                skip_disconnect=call.data["operation"] == "query",
                resource="configuration",
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


def _require(call: ServiceCall, *fields: str) -> None:
    for field in fields:
        if field not in call.data:
            raise ServiceValidationError(f"{call.data['operation']} requires {field}")


async def handle_rmcontrol_alarm(call: ServiceCall) -> None:
    """Configure an alarm using a selected product action, never an arbitrary byte."""
    operation = call.data["operation"]
    if operation == "single":
        _require(call, "minutes", "action")
    elif operation == "repeat":
        _require(call, "alarm_id", "time", "weekdays", "action")
        if not call.data["weekdays"]:
            raise ServiceValidationError("A repeating alarm requires at least one weekday")
        if call.data["time"].second or call.data["time"].microsecond:
            raise ServiceValidationError("RMControl alarms have minute precision")
    elif operation == "delete":
        _require(call, "alarm_id")

    async def control(controller: BedController) -> None:
        if operation == "single":
            await controller.rmcontrol_single_alarm(call.data["minutes"], call.data["action"])
        elif operation == "cancel_single":
            await controller.rmcontrol_single_alarm(0, None)
        elif operation == "repeat":
            when = call.data["time"]
            await controller.rmcontrol_repeat_alarm(
                call.data["alarm_id"],
                when.hour,
                when.minute,
                tuple(WEEKDAYS.index(day) for day in call.data["weekdays"]),
                call.data["action"],
            )
        elif operation == "delete":
            await controller.rmcontrol_delete_alarm(call.data["alarm_id"])
        elif operation == "query":
            await controller.rmcontrol_query_alarms()
        else:
            await controller.rmcontrol_sync_alarm_time(dt_util.now())

    if operation == "sync":
        capability = "supports_rmcontrol_alarm_time_sync"
    elif operation in ("single", "cancel_single"):
        capability = "supports_rmcontrol_single_alarm"
    else:
        capability = "supports_rmcontrol_repeat_alarm"
    await _execute(call, capability, control)


async def handle_rmcontrol_anti_snore(call: ServiceCall) -> None:
    """Keep intervention count/duration configuration separate from enabling it."""
    operation = call.data["operation"]
    if operation == "switch":
        _require(call, "enabled")
    elif operation == "configure":
        _require(call, "mode", "value")

    async def control(controller: BedController) -> None:
        if operation == "switch":
            await controller.rmcontrol_anti_snore_switch(call.data["enabled"])
        elif operation == "configure":
            await controller.rmcontrol_anti_snore_config(call.data["mode"], call.data["value"])
        else:
            await controller.rmcontrol_query_anti_snore()

    await _execute(call, "supports_rmcontrol_anti_snore", control)


def async_register_rmcontrol_services(hass: HomeAssistant) -> None:
    """Register the two configuration actions alongside the integration services."""
    hass.services.async_register(
        DOMAIN, "rmcontrol_alarm", handle_rmcontrol_alarm, schema=ALARM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "rmcontrol_anti_snore", handle_rmcontrol_anti_snore, schema=ANTI_SNORE_SCHEMA
    )
