"""Jiecang app alarm and wake actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild
from ...services import (
    ATTR_ENABLED,
    ATTR_FOOT_LEVEL,
    ATTR_HEAD_LEVEL,
    ATTR_PRESET,
    ATTR_TIME,
    ATTR_WEEKDAYS,
    DEVICE_IDS,
    SIDE_FIELD,
    SOLACE_WEEKDAY_OPTIONS,
    _call_targets,
    _execute_preflighted,
    _family_command,
    _preflight_and_execute,
    _preflight_each,
)
from ..base import BedController, controller_as

SERVICE_JIECANG_SET_ALARM = "jiecang_set_alarm"
SERVICE_JIECANG_WAKE = "jiecang_wake"
SERVICE_JIECANG_STOP_WAKE = "jiecang_stop_wake"
JIECANG_WAKE_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")
JIECANG_ALARM_PRESETS = (*JIECANG_WAKE_PRESETS, "yoga")


async def handle_jiecang_set_alarm(call: ServiceCall) -> None:
    """Configure the Jiecang app controller's recurring clock alarm."""
    await async_import_modules(call.hass, "beds.jiecang.controller")
    from .controller import JiecangProfileController

    alarm_time = call.data[ATTR_TIME]
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])
    label = "Jiecang clock alarms"

    def check(target: BedChild, controller: BedController) -> None:
        jiecang = controller_as(controller, JiecangProfileController)
        if jiecang is None or not jiecang.supports_clock_alarm:
            raise ServiceValidationError(f"Device '{target.name}' does not support {label}")
        if call.data[ATTR_PRESET] == "yoga" and not jiecang.supports_preset_yoga:
            raise ServiceValidationError(f"Device '{target.name}' does not support Yoga alarms")

    async def program(controller: JiecangProfileController) -> None:
        await controller.configure_clock_alarm(
            enabled=call.data[ATTR_ENABLED],
            weekdays=weekdays,
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            preset=call.data[ATTR_PRESET],
            head_level=call.data[ATTR_HEAD_LEVEL],
            foot_level=call.data[ATTR_FOOT_LEVEL],
        )

    targets = _call_targets(call)
    preflighted = await _preflight_each(targets, check)
    await _execute_preflighted(
        targets, preflighted, _family_command(JiecangProfileController, label, program)
    )


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
        "Jiecang wake routines",
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
        "Jiecang wake routines",
        lambda controller: controller.stop_wake_routine(),
        supported=lambda controller: controller.supports_wake_routine,
        cancel_running=True,
        resource=None,
    )


def async_register_jiecang_app_services(hass: HomeAssistant) -> None:
    """Register the Jiecang app alarm and wake actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_JIECANG_SET_ALARM,
        handle_jiecang_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]
                ),
                vol.Optional(ATTR_PRESET, default="flat"): vol.In(JIECANG_ALARM_PRESETS),
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
