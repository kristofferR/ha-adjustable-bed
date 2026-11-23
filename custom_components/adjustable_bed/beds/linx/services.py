"""The Linx manual snore intervention action. Alarm clears use the shared ``set_alarm``."""

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
        # All physical STOP epochs must be captured before even the lazy import.
        targets = _call_targets(call)
        admissions = [
            _capture_command_admission(c, side, ALL_COMMAND_RESOURCES) for c, side in targets
        ]
        await async_import_modules(hass, "beds.linx.controller")
        from .controller import LinxController

        async def execute(controller: LinxController) -> None:
            await controller.snore_intervention(
                keep=call.data["hold_minutes"],
                speed=call.data["up_speed"],
                lift=call.data["lift_time"],
            )

        await _preflight_and_execute(
            targets,
            LinxController,
            execute,
            validate=lambda controller: controller.validate_snore_intervention(),
            resource=None,
            cancel_running=True,
            admissions=admissions,
        )

    # These are the app's stored integer parameters, not a general motor-speed
    # capability. The UART builder retains Java byte narrowing, independently.
    parameter = vol.All(vol.Coerce(int), vol.Range(min=0, max=2**31 - 1))
    hass.services.async_register(
        DOMAIN,
        "linx_snore_intervention",
        handle,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Optional("hold_minutes", default=10): parameter,
                vol.Optional("up_speed", default=10): parameter,
                vol.Optional("lift_time", default=10): parameter,
                **SIDE_FIELD,
            }
        ),
    )
