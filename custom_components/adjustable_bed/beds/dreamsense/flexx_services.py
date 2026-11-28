"""Flexx-specific action names using the shared typed admission and session paths."""

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
    _whole_number,
)
from .flexx_motion import FlexxMotionController


async def _record(call: ServiceCall, *, delete: bool) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    number = call.data["alarm_number"]
    identities: dict[FlexxMotionController, tuple[int, int]] = {}

    def validate(controller: FlexxMotionController) -> None:
        identities[controller] = (
            controller.validate_record(number)
            if delete
            else controller.validate_record_update(number)
        )

    ready = await _preflight_capability(targets, FlexxMotionController, None, validate)

    async def execute(controller: FlexxMotionController) -> None:
        if delete:
            await controller.delete_alarm(number, identities[controller])
        else:
            await controller.enable_alarm(number, call.data["enabled"], identities[controller])

    await _execute_preflighted(
        targets,
        ready,
        _family_command(FlexxMotionController, execute),
        cancel_running=False,
        resource="configuration",
        admissions=admissions,
    )


async def enable(call: ServiceCall) -> None:
    await _record(call, delete=False)


async def delete(call: ServiceCall) -> None:
    await _record(call, delete=True)


def async_register_flexx_services(hass: HomeAssistant) -> None:
    schema = {
        vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
        vol.Required("alarm_number"): vol.All(_whole_number, vol.Range(min=1, max=7)),
        **SIDE_FIELD,
    }
    hass.services.async_register(
        DOMAIN,
        "flexx_motion_enable_alarm",
        enable,
        schema=vol.Schema({**schema, vol.Required("enabled"): cv.boolean}),
    )
    hass.services.async_register(
        DOMAIN, "flexx_motion_delete_alarm", delete, schema=vol.Schema(schema)
    )
