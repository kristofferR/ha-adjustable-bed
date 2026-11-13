"""Named KomfyD/ComfyDS app commands with all-target preflight."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.comfy import COMFY_ACTIONS
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)


async def handle_comfy_control(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.kaidi.comfy")
    from .comfy import ComfyController

    targets, action = _call_targets(call), call.data["action"]
    label = "KomfyD/ComfyDS control"
    await _preflight_and_execute(
        targets,
        ComfyController,
        label,
        lambda c: c.control(action),
        validate=lambda c: c.validate_control(action),
        cancel_running=True,
        resource=None,
        admit=True,
    )


def async_register_comfy_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "comfy_control",
        handle_comfy_control,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(COMFY_ACTIONS),
                **SIDE_FIELD,
            }
        ),
    )
