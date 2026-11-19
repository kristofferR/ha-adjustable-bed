"""SUTA direct BED requests with STOP/ownership captured before lazy imports."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...errors import invalid, rejected
from ...import_executor import async_import_modules

# The payload names the mattress or heating side: 1 left, 2 right.
_LOGICAL_SIDES = {"left": 1, "right": 2}


async def handle_request(call: ServiceCall) -> None:
    from ...services import (
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _execute_preflighted,
        _family_command,
        _release_preflighted,
        _validation_controller,
    )

    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.suta.controller")
    from .controller import CLOCK_COMMAND, Request, SutaController

    if call.data["action"] == CLOCK_COMMAND:
        raise invalid("clock_uses_sync_clock")
    logical = call.data.get("logical_side")
    request = Request(call.data["action"], call.data["suffix"], None if logical is None else _LOGICAL_SIDES[logical], call.data.get("value"))
    preflighted = []
    try:
        # First validate every offline catalog and parameter before any live
        # connection can run its startup. Then validate received-state gates.
        for parent, side in targets:
            for child in _command_targets(parent, side):
                controller = child.capability_controller
                if not isinstance(controller, SutaController):
                    raise invalid("action_for_other_beds", beds="SUTA Smart Home beds")
                try:
                    controller.validate_request(request, live=False)
                except ValueError as error:
                    raise rejected(error) from error
        for parent, side in targets:
            for child in _command_targets(parent, side):
                controller = await _validation_controller(parent, child, preflighted)
                if not isinstance(controller, SutaController):
                    raise invalid("bed_changed")
                try:
                    controller.validate_request(request)
                except ValueError as error:
                    raise rejected(error) from error
        await _execute_preflighted(
            targets, preflighted,
            _family_command(SutaController, "SUTA Smart Home", lambda controller: controller.execute_request(request)),
            admissions=admissions,
        )
    finally:
        await _release_preflighted(preflighted)


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD

    hass.services.async_register(
        DOMAIN, "suta", handle_request,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required("action"): str,
            vol.Optional("suffix", default=""): str,
            vol.Optional("logical_side"): vol.In(tuple(_LOGICAL_SIDES)),
            vol.Optional("value"): vol.Coerce(int),
            **SIDE_FIELD,
        }),
    )
