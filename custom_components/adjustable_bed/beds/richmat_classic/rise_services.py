"""Typed direct bed actions for Luuna Rise and Power Cool."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild, PairedBedCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _get_controller_for_service,
)
from ..base import BedController
from . import rise

OPERATIONS = (
    "query", "alarm", "cancel_alarm", "rgb", "lamp_timer", "massage_timer",
    "massage_popup", "diagnostic_cycle", "program_schedule",
)
INTEGER = vol.All(vol.Coerce(int), vol.Range(min=0, max=2147483647))
ROW = vol.All(vol.ExactSequence((vol.All(vol.Coerce(int), vol.Range(min=1, max=12)), INTEGER, INTEGER)), vol.Coerce(tuple))
SCHEDULE = vol.Schema({
    vol.Required("records"): vol.All([ROW], vol.Length(min=12, max=12), vol.Coerce(tuple)),
    vol.Required("rest"): INTEGER,
    vol.Required("count"): INTEGER,
    vol.Required("radio"): vol.In(("rf", "ble")),
    vol.Required("code"): vol.In(("new", "old")),
    vol.Required("identifier"): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
    vol.Required("motors"): vol.All([vol.All(vol.Coerce(int), vol.Range(min=1, max=4))], vol.Length(min=4, max=4), vol.Coerce(tuple)),
})
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("actions"): vol.All(cv.ensure_list, [cv.string], vol.Coerce(tuple)),
    vol.Optional("time"): cv.time,
    vol.Optional("rgb_color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=300)),
    vol.Optional("timer_save", default=False): cv.boolean,
    vol.Optional("progress"): vol.All(cv.positive_int, vol.Range(max=5)),
    vol.Optional("popup"): vol.In(("15", "30", "45", "toggle")),
    vol.Optional("schedule"): SCHEDULE,
}
FIELDS.update(SIDE_FIELD.items())


async def handle_richmat_rise(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.richmat_classic.controller")
    from .controller import RichmatClassicController

    schedule = rise.Schedule(**call.data["schedule"]) if "schedule" in call.data else None
    request = rise.Request(
        cast(rise.Operation, call.data["operation"]), actions=call.data.get("actions", ()),
        when=call.data.get("time"), color=call.data.get("rgb_color"),
        seconds=call.data.get("seconds"), timer_save=call.data["timer_save"],
        progress=call.data.get("progress"), popup=call.data.get("popup"), schedule=schedule,
    )
    targets = _call_targets(call)
    movement = request.operation in ("diagnostic_cycle", "program_schedule")
    resource = "movement" if movement else "configuration"
    admissions = [_capture_command_admission(coordinator, side, (resource,)) for coordinator, side in targets]
    # First reject invalid static parameters on every target. Then establish a
    # current physical session for capability checks, including offline setup.
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            offline = target.capability_controller
            if offline is None:
                offline = await _get_controller_for_service(target)
            if not isinstance(offline, RichmatClassicController):
                raise ServiceValidationError("Choose a Luuna Rise or Power Cool bed")
            try:
                offline.validate_richmat_rise_request(request, live=False)
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error

    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            refreshed: list[RichmatClassicController] = []

            async def query(controller: BedController) -> RichmatClassicController:
                if not isinstance(controller, RichmatClassicController):
                    raise ServiceValidationError("The selected app controller changed")
                controller.validate_richmat_rise_request(request)
                return controller

            async def inspect(child: BedChild, results: list[RichmatClassicController] = refreshed) -> None:
                selected = await child.async_execute_controller_query(query, cancel_running=False)
                if selected is not None:
                    results.append(selected)

            try:
                if isinstance(coordinator, PairedBedCoordinator):
                    child_side = next(key for key, child in coordinator.children.items() if child is target)
                    await coordinator.async_run_child_operation("Bed settings preflight", inspect, side=child_side, cancel_running=False)
                else:
                    await inspect(target)
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error
            if not refreshed:
                raise ServiceValidationError("Bed capability preflight was interrupted")

    await _execute_preflighted(
        targets, [], _family_command(RichmatClassicController, "Luuna Rise / Power Cool bed settings", lambda controller: controller.async_execute_richmat_rise_request(request)),
        cancel_running=movement, resource=resource, admissions=admissions,
    )


def async_register_richmat_rise_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "richmat_rise", handle_richmat_rise, schema=vol.Schema(FIELDS))
