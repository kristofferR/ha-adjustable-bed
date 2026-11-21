"""Typed direct bed actions for Luuna Rise and Power Cool."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid, rejected
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
    "query", "alarm", "cancel_alarm", "rgb", "lamp_timer", "massage_timer", "massage_popup",
)
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
}
FIELDS.update(SIDE_FIELD.items())


async def handle_richmat_rise(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.richmat_classic.controller")
    from .controller import RichmatClassicController

    request = rise.Request(
        cast(rise.Operation, call.data["operation"]), actions=call.data.get("actions", ()),
        when=call.data.get("time"), color=call.data.get("rgb_color"),
        seconds=call.data.get("seconds"), timer_save=call.data["timer_save"],
        progress=call.data.get("progress"), popup=call.data.get("popup"),
    )
    targets = _call_targets(call)
    admissions = [_capture_command_admission(coordinator, side, ("configuration",)) for coordinator, side in targets]
    # First reject invalid static parameters on every target. Then establish a
    # current physical session for capability checks, including offline setup.
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            offline = target.capability_controller
            if offline is None:
                offline = await _get_controller_for_service(target)
            if not isinstance(offline, RichmatClassicController):
                raise invalid("action_for_other_beds", beds="Luuna Rise and Power Cool beds")
            try:
                offline.validate_richmat_rise_request(request, live=False)
            except ValueError as error:
                raise rejected(error) from error

    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            refreshed: list[RichmatClassicController] = []

            async def query(controller: BedController) -> RichmatClassicController:
                if not isinstance(controller, RichmatClassicController):
                    raise invalid("bed_changed")
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
                raise rejected(error) from error
            if not refreshed:
                raise invalid("action_stopped")

    await _execute_preflighted(
        targets, [], _family_command(RichmatClassicController, "Luuna Rise / Power Cool bed settings", lambda controller: controller.async_execute_richmat_rise_request(request)),
        cancel_running=False, resource="configuration", admissions=admissions,
    )


def async_register_richmat_rise_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "richmat_rise", handle_richmat_rise, schema=vol.Schema(FIELDS))
