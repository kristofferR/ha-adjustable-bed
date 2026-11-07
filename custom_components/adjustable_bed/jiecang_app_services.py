"""Jiecang app alarm and wake actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_JIECANG_APP, DOMAIN
from .services import (
    ATTR_ENABLED,
    ATTR_FOOT_LEVEL,
    ATTR_HEAD_LEVEL,
    ATTR_PRESET,
    ATTR_SIDE,
    ATTR_TIME,
    ATTR_WEEKDAYS,
    SIDE_FIELD,
    SOLACE_WEEKDAY_OPTIONS,
    BedTarget,
    PreflightedSides,
    _command_targets,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

if TYPE_CHECKING:
    from .beds.base import BedController


SERVICE_JIECANG_SET_ALARM = "jiecang_set_alarm"
SERVICE_JIECANG_WAKE = "jiecang_wake"
SERVICE_JIECANG_STOP_WAKE = "jiecang_stop_wake"
JIECANG_WAKE_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")
JIECANG_ALARM_PRESETS = (*JIECANG_WAKE_PRESETS, "yoga")


async def _preflight_jiecang(
    targets: list[tuple[BedTarget, str]], capability: str, label: str
) -> PreflightedSides:
    """Restrict app-specific services before connecting or commanding any side."""
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_JIECANG_APP:
                raise ServiceValidationError(
                    f"Device '{target.name}' is not a Jiecang app controller"
                )
    return await _preflight_capability(targets, capability, label)


async def handle_jiecang_set_alarm(call: ServiceCall) -> None:
    """Configure the Jiecang app controller's recurring clock alarm."""
    alarm_time = call.data[ATTR_TIME]
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data[CONF_DEVICE_ID],
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_jiecang(targets, "supports_clock_alarm", "Jiecang clock alarms")

    async def program(controller: BedController) -> None:
        await controller.configure_clock_alarm(
            enabled=call.data[ATTR_ENABLED],
            weekdays=weekdays,
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            preset=call.data[ATTR_PRESET],
            head_level=call.data[ATTR_HEAD_LEVEL],
            foot_level=call.data[ATTR_FOOT_LEVEL],
        )

    try:
        if call.data[ATTR_PRESET] == "yoga":
            preflighted.extend(
                await _preflight_capability(targets, "supports_preset_yoga", "Yoga alarms")
            )
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, program, cancel_running=False, resource="configuration"
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_jiecang_wake(call: ServiceCall) -> None:
    """Start the app's wake routine with its preset and massage levels."""
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data[CONF_DEVICE_ID],
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_jiecang(
        targets, "supports_wake_routine", "Jiecang wake routines"
    )

    async def wake(controller: BedController) -> None:
        await controller.execute_wake_routine(
            preset=call.data[ATTR_PRESET],
            head_level=call.data[ATTR_HEAD_LEVEL],
            foot_level=call.data[ATTR_FOOT_LEVEL],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, wake, cancel_running=True)
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_jiecang_stop_wake(call: ServiceCall) -> None:
    """Stop active wake massage without changing the stored clock alarm."""
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data[CONF_DEVICE_ID],
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_jiecang(
        targets, "supports_wake_routine", "Jiecang wake routines"
    )

    async def stop(controller: BedController) -> None:
        await controller.stop_wake_routine()

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, stop, cancel_running=True)
    except Exception:
        await _release_preflighted(preflighted)
        raise


def async_register_jiecang_app_services(hass: HomeAssistant) -> None:
    """Register the Jiecang app alarm and wake actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_JIECANG_SET_ALARM,
        handle_jiecang_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
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
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
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
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                **SIDE_FIELD,
            }
        ),
    )
