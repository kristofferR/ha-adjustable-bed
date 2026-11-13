"""Public direct BED actions for the four cluster-017 resource apps."""

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
    _require_hold_topology,
)
from .resource_protocol import BED_COMMANDS, Operation, Request

FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(
        ("query", "alarm", "cancel_alarm", "rgb", "lamp_timeout", "massage_timer", "bed_command")
    ),
    vol.Optional("actions"): vol.All(cv.ensure_list, [cv.string], vol.Coerce(tuple)),
    vol.Optional("time"): cv.time,
    vol.Optional("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=300)),
    vol.Optional("progress"): vol.All(cv.positive_int, vol.Range(max=5)),
    vol.Optional("command"): vol.In(BED_COMMANDS),
    vol.Optional("duration_ms", default=1000): vol.All(
        cv.positive_int, vol.Range(min=1, max=60000)
    ),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_resource_bed(call: ServiceCall) -> None:
    targets = _call_targets(call)
    movement = call.data["operation"] == "bed_command"
    resource = "movement" if movement else "configuration"
    # Every target's STOP epoch is captured before any import, preflight or
    # connection await. A STOP on B while A awaits fences B's later writes.
    admissions = [
        _capture_command_admission(coordinator, side, (resource,)) for coordinator, side in targets
    ]
    held = (
        movement
        and call.data.get("command") in BED_COMMANDS
        and BED_COMMANDS[call.data["command"]][1]
    )
    if held:
        _require_hold_topology(targets)
    await async_import_modules(call.hass, "beds.richmat_classic.resource_controller")
    from .resource_controller import ResourceBedController

    request = Request(
        cast(Operation, call.data["operation"]),
        actions=call.data.get("actions", ()),
        when=call.data.get("time"),
        color=call.data.get("rgb_color"),
        seconds=call.data.get("seconds"),
        progress=call.data.get("progress"),
        command=call.data.get("command"),
        duration_ms=call.data["duration_ms"],
    )
    preflighted = await _preflight_capability(
        targets,
        ResourceBedController,
        "Resource app bed actions",
        None,
        lambda controller: controller.validate_request(request),
    )
    async def execute(controller: ResourceBedController) -> None:
        if held:
            _require_hold_topology(targets)
        await controller.execute_request(request)

    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(
            ResourceBedController,
            "Resource app bed actions",
            execute,
        ),
        cancel_running=movement,
        resource=resource,
        admissions=admissions,
    )


def async_register_resource_bed_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, "richmat_resource_bed", handle_resource_bed, schema=vol.Schema(FIELDS)
    )
