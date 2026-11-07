"""Logicdata app alarm and held-preset actions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...services import (
    ATTR_DURATION,
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
    _preflight_and_execute,
)

SERVICE_LOGICDATA_SET_ALARM = "logicdata_set_alarm"
SERVICE_LOGICDATA_HOLD_PRESET = "logicdata_hold_preset"
LOGICDATA_ALARM_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")
LOGICDATA_HOLD_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")


async def handle_logicdata_set_alarm(call: ServiceCall) -> None:
    """Configure the Logicdata app controller's recurring clock alarm."""
    from .app import LogicdataAppController

    alarm_time = call.data[ATTR_TIME]
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])

    async def program(controller: LogicdataAppController) -> None:
        await controller.configure_clock_alarm(
            enabled=call.data[ATTR_ENABLED],
            weekdays=weekdays,
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            preset=call.data[ATTR_PRESET],
            head_level=call.data[ATTR_HEAD_LEVEL],
            foot_level=call.data[ATTR_FOOT_LEVEL],
        )

    await _preflight_and_execute(
        _call_targets(call),
        LogicdataAppController,
        "Logicdata clock alarms",
        program,
        supported=lambda controller: controller.supports_clock_alarm,
    )


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
    from .app import LogicdataAppController

    duration_ms = int(call.data[ATTR_DURATION] * 1000)
    preset = call.data[ATTR_PRESET]

    def validate(controller: LogicdataAppController) -> None:
        if preset not in controller.held_preset_options:
            raise ServiceValidationError(
                f"The selected app profile cannot hold the {preset} preset"
            )

    await _preflight_and_execute(
        _call_targets(call),
        LogicdataAppController,
        "Logicdata held preset recall",
        lambda controller: controller.hold_preset(preset, duration_ms),
        supported=lambda controller: controller.supports_preset_hold,
        validate=validate,
        cancel_running=True,
        resource=None,
    )


def async_register_logicdata_app_services(hass: HomeAssistant) -> None:
    """Register the Logicdata app alarm and held-preset actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOGICDATA_SET_ALARM,
        handle_logicdata_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
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
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_PRESET): vol.In(LOGICDATA_HOLD_PRESETS),
                vol.Required(ATTR_DURATION): _preset_hold_duration_seconds,
                **SIDE_FIELD,
            }
        ),
    )
