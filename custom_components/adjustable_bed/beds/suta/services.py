"""SUTA direct BED requests with STOP/ownership captured before lazy imports."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...const import DOMAIN
from ...import_executor import async_import_modules


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
    from .controller import Request, SutaController

    request = Request(call.data["action"], call.data["suffix"], call.data.get("logical_side"), call.data.get("value"), tuple(call.data["weekdays"]), call.data["time"], call.data["loop"])
    preflighted = []
    try:
        # First validate every offline catalog and parameter before any live
        # connection can run its startup. Then validate received-state gates.
        for parent, side in targets:
            for child in _command_targets(parent, side):
                controller = child.capability_controller
                if not isinstance(controller, SutaController):
                    raise ServiceValidationError("Select a SUTA Smart Home bed for this action")
                try:
                    controller.validate_request(request, live=False)
                except ValueError as error:
                    raise ServiceValidationError(str(error)) from error
        for parent, side in targets:
            for child in _command_targets(parent, side):
                controller = await _validation_controller(parent, child, preflighted)
                if not isinstance(controller, SutaController):
                    raise ServiceValidationError("SUTA controller ownership changed")
                try:
                    controller.validate_request(request)
                except ValueError as error:
                    raise ServiceValidationError(str(error)) from error
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
            vol.Optional("logical_side"): vol.All(vol.Coerce(int), vol.In((1, 2))),
            vol.Optional("value"): vol.Coerce(int),
            vol.Optional("weekdays", default=[]): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
            vol.Optional("time", default="0630"): str,
            vol.Optional("loop", default="00"): vol.In(("00", "01")),
            **SIDE_FIELD,
        }),
    )
