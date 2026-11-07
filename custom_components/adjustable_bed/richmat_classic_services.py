"""Validated direct BLE settings for the five resource-driven apps."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .richmat_classic_requests import Operation, Request
from .services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

OPERATIONS = (
    "query", "alarm", "cancel_alarm", "rgb", "lamp_slider", "lamp_save", "aroma",
    "massage_timer", "massage_popup", "desk_target", "desk_unit", "desk_recall", "desk_reset",
)
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("action"): cv.string,
    vol.Optional("time"): cv.time,
    vol.Optional("minutes"): vol.All(cv.positive_int, vol.Range(max=15)),
    vol.Optional("rgb_color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
    vol.Optional("aroma_times"): vol.All(vol.ExactSequence((cv.positive_int, cv.positive_int, cv.positive_int)), vol.Coerce(tuple)),
    vol.Optional("progress"): vol.All(cv.positive_int, vol.Range(max=5)),
    vol.Optional("height"): vol.Coerce(float),
    vol.Optional("unit"): vol.In(("cm", "inches")),
    vol.Optional("duration_ms", default=1000): vol.All(cv.positive_int, vol.Range(min=1, max=60000)),
    vol.Optional("popup"): vol.In(("15", "30", "45", "toggle")),
    vol.Optional("slot"): vol.All(cv.positive_int, vol.Range(min=1, max=4)),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_richmat_classic(call: ServiceCall) -> None:
    from .beds.richmat_classic import RichmatClassicController

    request = Request(
        operation=cast(Operation, call.data["operation"]), action=call.data.get("action"),
        when=call.data.get("time"), minutes=call.data.get("minutes"),
        color=call.data.get("rgb_color"), aroma_values=call.data.get("aroma_times"),
        progress=call.data.get("progress"), height=call.data.get("height"),
        unit=call.data.get("unit"), slot=call.data.get("slot"), duration_ms=call.data["duration_ms"], popup=call.data.get("popup"),
    )
    resource = "movement" if request.operation in ("desk_recall", "desk_target", "desk_reset") else "configuration"
    await _preflight_and_execute(
        _call_targets(call),
        RichmatClassicController,
        "Selected app settings",
        lambda controller: controller.async_execute_richmat_classic_request(request),
        validate=lambda controller: controller.validate_richmat_classic_request(request),
        cancel_running=resource == "movement",
        resource=resource,
        admit=True,
    )


def async_register_richmat_classic_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "richmat_classic", handle_richmat_classic, schema=vol.Schema(FIELDS))
