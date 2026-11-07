"""Product/ACK-gated HJBed alarms, light settings and control mode."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .hjbed_requests import Operation, Request
from .services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
OPERATIONS = (
    "single",
    "cancel_single",
    "repeat",
    "delete",
    "query",
    "toggle",
    "sync",
    "light_timeout",
    "light_color",
    "mode",
)
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("action"): cv.string,
    vol.Optional("time"): cv.time,
    vol.Optional("alarm_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    vol.Optional("weekdays", default=[]): vol.All(cv.ensure_list, [vol.In(WEEKDAYS)]),
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=0, max=28800)),
    vol.Optional("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
    vol.Optional("mode"): vol.In(("split_head", "standard")),
}
FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(FIELDS)


async def handle_hjbed(call: ServiceCall) -> None:
    from .beds.hjbed import HJBedController

    request = Request(
        operation=cast(Operation, call.data["operation"]),
        action=call.data.get("action"),
        when=call.data.get("time"),
        alarm_id=call.data.get("alarm_id"),
        weekdays=tuple(WEEKDAYS.index(day) for day in call.data["weekdays"]),
        enabled=call.data["enabled"],
        seconds=call.data.get("seconds"),
        rgb=call.data.get("rgb_color"),
        mode=call.data.get("mode"),
    )
    await _preflight_and_execute(
        _call_targets(call),
        HJBedController,
        "HJBed configuration",
        lambda controller: controller.async_execute_hjbed_request(request),
        validate=lambda controller: controller.validate_hjbed_request(request),
    )


def async_register_hjbed_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "hjbed", handle_hjbed, schema=SCHEMA)
