"""Mattress and weekly alarm actions for explicitly selected RUF/Richmat app profiles."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .row061_protocol import AlarmRequest
from .services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

SERVICE = "richmat_app_alarm"
_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("family"): vol.In(("mattress", "calendar")),
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("delete", default=False): cv.boolean,
    vol.Required("time"): cv.time,
    vol.Optional("mattress_side", default="left"): vol.In(("left", "right")),
    vol.Optional("repeat", default="once"): vol.In(("once", "daily")),
    vol.Optional("intensity", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
    vol.Optional("slot", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    vol.Optional("mode", default=0): cv.byte,
    vol.Optional("weekdays", default=[]): vol.All(
        cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))]
    ),
}
_FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(_FIELDS)


async def handle_alarm(call: ServiceCall) -> None:
    from .beds.row061 import Row061Controller

    data = call.data
    when = data["time"]
    request = AlarmRequest(
        family=data["family"],
        enabled=data["enabled"],
        delete=data["delete"],
        hour=when.hour,
        minute=when.minute,
        mattress_side=data["mattress_side"],
        repeat=data["repeat"],
        intensity=data["intensity"],
        slot=data["slot"],
        mode=data["mode"],
        weekdays=tuple(data["weekdays"]),
    )
    await _preflight_and_execute(
        _call_targets(call),
        Row061Controller,
        "Richmat app alarms",
        lambda ctrl: ctrl.row061_alarm(request),
        supported=lambda ctrl: ctrl.supports_row061_alarms,
        validate=lambda ctrl: ctrl.validate_row061_alarm(request),
    )


def async_register_row061_services(hass: HomeAssistant) -> None:
    hass.services.async_register("adjustable_bed", SERVICE, handle_alarm, schema=SCHEMA)
