"""Enso 2 settings that do not have a shared Home Assistant action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _preflight_and_execute,
)


async def _accessory(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.enso2.controller")
    from .controller import Enso2Controller

    if call.service == "enso2_light_color":

        async def command(controller: Enso2Controller) -> None:
            await controller.set_light_color(tuple(call.data["rgb_color"]))

        validate = Enso2Controller.check_light
    else:

        async def command(controller: Enso2Controller) -> None:
            await controller.set_aroma(
                call.data["mode_2_minutes"], call.data["mode_3_minutes"], call.data["pause_hours"]
            )

        validate = Enso2Controller.check_aroma

    await _preflight_and_execute(
        targets,
        Enso2Controller,
        command,
        validate=validate,
        resource="*",
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    minutes = vol.All(vol.Coerce(int), vol.Range(min=1, max=60))
    channel = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))
    for name, fields in (
        (
            "enso2_light_color",
            {
                vol.Required("rgb_color"): vol.All([channel], vol.Length(min=3, max=3)),
            },
        ),
        (
            "enso2_aroma_schedule",
            {
                vol.Required("mode_2_minutes"): minutes,
                vol.Required("mode_3_minutes"): minutes,
                vol.Required("pause_hours"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            },
        ),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            _accessory,
            vol.Schema({vol.Required(CONF_DEVICE_ID): DEVICE_IDS, **fields, **SIDE_FIELD}),
        )
