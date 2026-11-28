"""AI Bed typed services through shared targeting, admission and serialization."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...errors import rejected
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _release_preflighted,
    _validation_controller,
)
from ..base import require_controller
from .requests import Request


async def handle_request(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.ai_bed.controller")
    from .controller import AiBedController

    fields = {key: value for key, value in call.data.items() if key not in (CONF_DEVICE_ID, "side")}
    fields["weekdays"] = tuple(fields.get("weekdays", ()))
    request = Request(**fields)
    preflighted = []
    try:
        for parent, side in targets:
            for child in _command_targets(parent, side):
                bed = require_controller(
                    await _validation_controller(parent, child, preflighted), AiBedController
                )
                bed.validate_request(request)

        async def execute(controller):
            bed = require_controller(controller, AiBedController)
            # Sequential pairs release the link when this callback returns.
            stamp = await bed.prepare_request(request)
            await bed.execute_request(request, stamp)

        await _execute_preflighted(
            targets, preflighted, _family_command(AiBedController, execute), admissions=admissions
        )
    except (ValueError, NotImplementedError, TypeError) as error:
        raise rejected(error) from error
    finally:
        await _release_preflighted(preflighted)


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "ai_bed",
        handle_request,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(
                    (
                        "inflation",
                        "vibration_apply",
                        "vibration_preview",
                        "privacy_pin",
                        "settings_query",
                    )
                ),
                vol.Optional("enabled", default=True): bool,
                vol.Optional("hour", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Optional("minute", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=59)
                ),
                vol.Optional("weekdays", default=[]): [
                    vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
                ],
                vol.Optional("mode", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
                vol.Optional("head", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=15)),
                vol.Optional("foot", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=15)),
                vol.Optional("seconds", default=5): vol.All(
                    vol.Coerce(int), vol.In((3, 5, 10, 15, 30))
                ),
                vol.Optional("pin", default=""): str,
                **SIDE_FIELD,
            }
        ),
    )
