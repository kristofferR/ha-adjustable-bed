"""Selected speech-command semantics, without phone audio infrastructure."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.superior_sleep import SPEECH_ACTIONS
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _preflight_and_execute,
)


async def handle_speech(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.superior_sleep.controller")
    from .controller import SuperiorSleepController

    action, duration = call.data["action"], call.data["duration_ms"]
    await _preflight_and_execute(
        targets,
        SuperiorSleepController,
        "Superior Sleep",
        lambda controller: controller.action(action, speech=True, duration_ms=duration),
        validate=lambda controller: controller.validate_action(action, True),
        resource="*",
        cancel_running=True,
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "superior_sleep_speech",
        handle_speech,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(SPEECH_ACTIONS),
                vol.Optional("duration_ms", default=1000): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=60000)
                ),
                **SIDE_FIELD,
            }
        ),
    )
