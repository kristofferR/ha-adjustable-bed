"""Logicdata app alarm and held-preset actions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Collection
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_LOGICDATA_APP, DOMAIN
from .services import (
    ATTR_DURATION,
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
    from .beds.base import BedController, SideBoundController


SERVICE_LOGICDATA_SET_ALARM = "logicdata_set_alarm"
SERVICE_LOGICDATA_HOLD_PRESET = "logicdata_hold_preset"
LOGICDATA_ALARM_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")
LOGICDATA_HOLD_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")


async def _preflight_logicdata(
    targets: list[tuple[BedTarget, str]],
    capability: str,
    label: str,
    validate: Callable[[BedController | SideBoundController], None] | None = None,
    bed_types: Collection[str] = (BED_TYPE_LOGICDATA_APP,),
) -> PreflightedSides:
    """Restrict app-specific services before connecting or commanding any side."""
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type not in bed_types:
                raise ServiceValidationError(
                    f"Device '{target.name}' is not a Logicdata app controller"
                )
    return await _preflight_capability(targets, capability, label, validate)


async def handle_logicdata_set_alarm(call: ServiceCall) -> None:
    """Configure the Logicdata app controller's recurring clock alarm."""
    alarm_time = call.data[ATTR_TIME]
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data[CONF_DEVICE_ID],
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_logicdata(
        targets, "supports_clock_alarm", "Logicdata clock alarms"
    )

    async def program(controller: BedController | SideBoundController) -> None:
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
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, program, cancel_running=False, resource="configuration"
            )
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


def _preset_hold_duration_seconds(value: object) -> Decimal:
    """Accept bounded seconds that convert exactly to whole milliseconds."""
    try:
        duration = Decimal(str(value))
    except InvalidOperation as err:
        raise vol.Invalid("Duration must be a number of seconds") from err
    if not duration.is_finite() or not Decimal("0.2") <= duration <= 60:
        raise vol.Invalid("Duration must be between 0.2 and 60 seconds")
    milliseconds = int(duration * 1000)
    if duration != Decimal(milliseconds) / 1000:
        raise vol.Invalid("Duration must resolve to whole milliseconds")
    return duration


async def handle_logicdata_hold_preset(call: ServiceCall) -> None:
    """Hold a MOTIONrelax P2 or Sleep Smart preset through the cancellable command queue."""
    duration_ms = int(call.data[ATTR_DURATION] * 1000)
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data[CONF_DEVICE_ID],
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preset = call.data[ATTR_PRESET]

    def validate(controller: BedController | SideBoundController) -> None:
        if preset not in controller.held_preset_options:
            raise ServiceValidationError(
                f"The selected app profile cannot hold the {preset} preset"
            )

    preflighted = await _preflight_logicdata(
        targets, "supports_preset_hold", "Logicdata held preset recall", validate
    )

    async def hold(controller: BedController | SideBoundController) -> None:
        await controller.hold_preset(preset, duration_ms)

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, hold, cancel_running=True)
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


def async_register_logicdata_app_services(hass: HomeAssistant) -> None:
    """Register the Logicdata app alarm and held-preset actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOGICDATA_SET_ALARM,
        handle_logicdata_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]
                ),
                vol.Optional(ATTR_PRESET, default="flat"): vol.In(LOGICDATA_ALARM_PRESETS),
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
        SERVICE_LOGICDATA_HOLD_PRESET,
        handle_logicdata_hold_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_PRESET): vol.In(LOGICDATA_HOLD_PRESETS),
                vol.Required(ATTR_DURATION): _preset_hold_duration_seconds,
                **SIDE_FIELD,
            }
        ),
    )
