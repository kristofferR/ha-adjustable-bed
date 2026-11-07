"""Validated direct BLE settings for the five resource-driven apps."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .beds.base import BedController
from .cluster018_requests import Operation, Request
from .const import DOMAIN
from .services import (
    SIDE_FIELD,
    _capture_command_admission,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

OPERATIONS = (
    "query", "alarm", "cancel_alarm", "rgb", "lamp_slider", "lamp_save", "aroma",
    "massage_timer", "massage_popup", "desk_target", "desk_unit", "desk_recall", "desk_reset",
)
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
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


async def handle_cluster018(call: ServiceCall) -> None:
    request = Request(
        operation=cast(Operation, call.data["operation"]), action=call.data.get("action"),
        when=call.data.get("time"), minutes=call.data.get("minutes"),
        color=call.data.get("rgb_color"), aroma_values=call.data.get("aroma_times"),
        progress=call.data.get("progress"), height=call.data.get("height"),
        unit=call.data.get("unit"), slot=call.data.get("slot"), duration_ms=call.data["duration_ms"], popup=call.data.get("popup"),
    )
    targets, missing = _resolve_sided_targets(call.hass, call.data[CONF_DEVICE_ID], call.data.get("side"))
    if missing:
        raise _missing_device_error(missing[0])

    resource = "movement" if request.operation in ("desk_recall", "desk_target", "desk_reset") else "configuration"
    admissions = {
        (id(coordinator), side): _capture_command_admission(coordinator, side, (resource,))
        for coordinator, side in targets
    }

    def validate(controller: BedController) -> None:
        controller.validate_cluster018_request(request)

    preflighted = await _preflight_capability(targets, "supports_cluster018", "Selected app settings", validate)

    async def execute(controller: BedController) -> None:
        try:
            await controller.async_execute_cluster018_request(request)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, execute, cancel_running=resource == "movement", resource=resource, admission=admissions[(id(coordinator), side)])
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def async_register_cluster018_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "richmat_classic", handle_cluster018, schema=vol.Schema(FIELDS))
