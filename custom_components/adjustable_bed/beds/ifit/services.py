"""iFit's combined Flat/preset save gesture, with all-target admission."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        ALL_COMMAND_RESOURCES,
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    async def handle(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [
            _capture_command_admission(c, side, ALL_COMMAND_RESOURCES) for c, side in targets
        ]
        await async_import_modules(hass, "beds.ifit.controller")
        from .controller import IfitController

        async def execute(controller: IfitController) -> None:
            await controller.save_named_preset(call.data["preset"])

        await _preflight_and_execute(
            targets,
            IfitController,
            execute,
            validate=lambda c: c.validate_save(call.data["preset"]),
            resource=None,
            cancel_running=True,
            admissions=admissions,
        )

    hass.services.async_register(
        DOMAIN,
        "ifit_save_preset",
        handle,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("preset"): vol.In(("zero_g", "anti_snore", "lounge", "incline")),
                **SIDE_FIELD,
            }
        ),
    )
