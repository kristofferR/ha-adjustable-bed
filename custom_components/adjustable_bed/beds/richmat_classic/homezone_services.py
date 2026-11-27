"""Home Zone settings through native side-aware admission and shared alarm actions."""

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
)
from .resource_protocol import Operation, Request

OPERATIONS = ("query", "rgb", "lamp_timeout", "aroma", "massage_timer", "massage_popup")
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=300)),
    vol.Optional("aroma_times"): vol.All(
        vol.ExactSequence((cv.positive_int,) * 3), vol.Coerce(tuple)
    ),
    vol.Optional("progress"): vol.All(cv.positive_int, vol.Range(max=5)),
    vol.Optional("popup"): vol.In(("15", "30", "45", "toggle")),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_homezone(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(c, side, ("configuration",)) for c, side in targets]
    await async_import_modules(call.hass, "beds.richmat_classic.homezone")
    from .homezone import HomeZoneController

    request = Request(
        cast(Operation, call.data["operation"]),
        color=call.data.get("rgb_color"),
        seconds=call.data.get("seconds"),
        aroma_times=call.data.get("aroma_times"),
        progress=call.data.get("progress"),
        popup=call.data.get("popup"),
    )
    # Static validation across all sides first. Execution rechecks capabilities
    # on its current link; replies from earlier links never authorize writes.
    preflighted = await _preflight_capability(
        targets, HomeZoneController, validate=lambda c: c.validate_request(request, live=False)
    )
    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(HomeZoneController, lambda c: c.execute_request(request)),
        cancel_running=False,
        resource="configuration",
        admissions=admissions,
    )


def async_register_homezone_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "homezone", handle_homezone, schema=vol.Schema(FIELDS))
