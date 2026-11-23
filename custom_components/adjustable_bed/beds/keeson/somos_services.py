"""Exact Somos app buttons with all-target STOP admission before lazy import."""

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


async def handle_action(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.keeson.somos")
    from .somos import SomosController

    action = call.data["action"]
    await _preflight_and_execute(
        targets,
        SomosController,
        lambda controller: controller.perform_action(action),
        validate=lambda controller: controller.validate_action(action),
        resource=None,
        cancel_running=True,
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "somos_action",
        handle_action,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(
                    (
                        "flat",
                        "zero_g",
                        "anti_snore",
                        "memory_1",
                        "memory_2",
                        "memory_3",
                        "head_massage",
                        "foot_massage",
                        "massage_timer_cycle",
                        "light",
                        "status_query",
                    )
                ),
                **SIDE_FIELD,
            }
        ),
    )
