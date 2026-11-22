"""Jiecang app alarm and wake actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    ATTR_FOOT_LEVEL,
    ATTR_HEAD_LEVEL,
    ATTR_PRESET,
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)

SERVICE_JIECANG_WAKE = "jiecang_wake"
SERVICE_JIECANG_STOP_WAKE = "jiecang_stop_wake"
JIECANG_WAKE_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")


async def handle_jiecang_wake(call: ServiceCall) -> None:
    """Start the app's wake routine with its preset and massage levels."""
    await async_import_modules(call.hass, "beds.jiecang.controller")
    from .controller import JiecangProfileController

    async def wake(controller: JiecangProfileController) -> None:
        await controller.execute_wake_routine(
            preset=call.data[ATTR_PRESET],
            head_level=call.data[ATTR_HEAD_LEVEL],
            foot_level=call.data[ATTR_FOOT_LEVEL],
        )

    await _preflight_and_execute(
        _call_targets(call),
        JiecangProfileController,
        wake,
        supported=lambda controller: controller.supports_wake_routine,
        cancel_running=True,
        resource=None,
    )


async def handle_jiecang_stop_wake(call: ServiceCall) -> None:
    """Stop active wake massage without changing the stored clock alarm."""
    await async_import_modules(call.hass, "beds.jiecang.controller")
    from .controller import JiecangProfileController

    await _preflight_and_execute(
        _call_targets(call),
        JiecangProfileController,
        lambda controller: controller.stop_wake_routine(),
        supported=lambda controller: controller.supports_wake_routine,
        cancel_running=True,
        resource=None,
    )


def async_register_jiecang_app_services(hass: HomeAssistant) -> None:
    """Register the Jiecang app alarm and wake actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_JIECANG_WAKE,
        handle_jiecang_wake,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Optional(ATTR_PRESET, default="flat"): vol.In(JIECANG_WAKE_PRESETS),
                vol.Optional(ATTR_HEAD_LEVEL, default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=3)
                ),
                vol.Optional(ATTR_FOOT_LEVEL, default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=3)
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_JIECANG_STOP_WAKE,
        handle_jiecang_stop_wake,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                **SIDE_FIELD,
            }
        ),
    )
