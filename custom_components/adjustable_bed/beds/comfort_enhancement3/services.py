"""Profile-gated Comfort Enhancement 3 relative massage action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _invalid,
        _preflight_and_execute,
    )

    async def start_massage(call: ServiceCall) -> None:
        await async_import_modules(call.hass, "beds.comfort_enhancement3.controller")
        from .controller import ComfortEnhancement3Controller, validate_massage

        def validate(controller: ComfortEnhancement3Controller) -> None:
            validate_massage(call.data["duration"], call.data["intensity"], call.data["kind"])
            if not controller.remote.massage:
                raise _invalid(
                    "feature_not_supported",
                    device_name=controller._coordinator.name,
                    feature="massage",
                )

        await _preflight_and_execute(
            _call_targets(call),
            ComfortEnhancement3Controller,
            lambda controller: controller.start_massage(
                call.data["duration"], call.data["intensity"], call.data["kind"]
            ),
            validate=validate,
            cancel_running=True,
            resource="*",
            admit=True,
        )

    hass.services.async_register(
        DOMAIN,
        "comfort_enhancement3_start_massage",
        start_massage,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                **SIDE_FIELD,
                vol.Optional("duration", default=10): vol.All(
                    vol.Coerce(int), vol.In((10, 20, 30))
                ),
                vol.Optional("intensity", default=1): vol.In((1, 2, 3)),
                vol.Optional("kind", default="head"): vol.In(("head", "feet", "both", "wave")),
            }
        ),
    )
