"""Direct bed lighting with shared typed target admission and scheduler ownership."""

from __future__ import annotations

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
    _whole_number,
)


async def handle_light(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.dreamsense.controller")
    from .controller import DreamSenseController

    color = tuple(call.data["rgb_color"]) if "rgb_color" in call.data else None
    rgb = (color[0], color[1], color[2]) if color is not None else None
    seconds = call.data.get("seconds")

    def validate(controller: DreamSenseController) -> None:
        controller.validate_light(rgb, seconds)

    preflighted = await _preflight_capability(
        targets, DreamSenseController, None, validate
    )

    async def execute(controller: DreamSenseController) -> None:
        await controller.light_settings(color=rgb, seconds=seconds)

    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(DreamSenseController, execute),
        cancel_running=False,
        resource="configuration",
        admissions=admissions,
    )


def async_register_dreamsense_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "dreamsense_delete_alarm",
        handle_delete_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("alarm_number"): vol.All(_whole_number, vol.Range(min=0, max=255)),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "dreamsense_light",
        handle_light,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Optional("rgb_color"): vol.All(
                    vol.ExactSequence([cv.byte, cv.byte, cv.byte]), list
                ),
                vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=0, max=28800)),
                **SIDE_FIELD,
            }
        ),
    )


async def handle_delete_alarm(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.dreamsense.controller")
    from .controller import DreamSenseController

    number = call.data["alarm_number"]
    stamps: dict[DreamSenseController, tuple[int, int]] = {}

    def validate(controller: DreamSenseController) -> None:
        stamps[controller] = controller.validate_record(number)

    preflighted = await _preflight_capability(
        targets, DreamSenseController, None, validate
    )

    async def execute(controller: DreamSenseController) -> None:
        identity = stamps.get(controller)
        if identity is None:
            from ...errors import invalid

            raise invalid("dreamsense_alarm_record")
        await controller.delete_alarm(number, identity)

    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(DreamSenseController, execute),
        cancel_running=False,
        resource="configuration",
        admissions=admissions,
    )
