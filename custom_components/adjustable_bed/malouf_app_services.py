"""Malouf app alarm action."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_MALOUF_APP, DOMAIN
from .services import (
    ATTR_ENABLED,
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


SERVICE_MALOUF_SET_ALARM = "malouf_set_alarm"
MALOUF_ALARM_PRESETS = ("zero_g", "lounge", "tv", "anti_snore", "memory_1", "memory_2")


async def _preflight_malouf(
    targets: list[tuple[BedTarget, str]],
    capability: str,
    label: str,
    validate: Callable[[BedController | SideBoundController], None] | None = None,
) -> PreflightedSides:
    """Validate the explicit app profile on every physical target before writing."""
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_MALOUF_APP:
                raise ServiceValidationError(
                    f"Device '{target.name}' is not a Malouf Base / Lucid Base app controller"
                )
    return await _preflight_capability(targets, capability, label, validate=validate)


async def handle_malouf_set_alarm(call: ServiceCall) -> None:
    """Set or clear the app profile's clock alarm through its command lock."""
    alarm_time = call.data[ATTR_TIME]
    if alarm_time.second or alarm_time.microsecond:
        raise ServiceValidationError("Malouf alarms use minute precision")
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])

    def validate_alarm(controller: BedController | SideBoundController) -> None:
        if (
            call.data[ATTR_ENABLED]
            and call.data[ATTR_PRESET] not in controller.clock_alarm_preset_options
        ):
            raise ServiceValidationError("The selected alarm preset is unavailable on this model")

    preflighted = await _preflight_malouf(
        targets, "supports_clock_alarm", "Malouf clock alarms", validate=validate_alarm
    )

    async def program(controller: BedController | SideBoundController) -> None:
        await controller.configure_clock_alarm(
            enabled=call.data[ATTR_ENABLED],
            weekdays=weekdays,
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            preset=call.data[ATTR_PRESET],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, program, cancel_running=False, resource="configuration"
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


def async_register_malouf_app_services(hass: HomeAssistant) -> None:
    """Register the Malouf app alarm action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_MALOUF_SET_ALARM,
        handle_malouf_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]
                ),
                vol.Optional(ATTR_PRESET, default="zero_g"): vol.In(MALOUF_ALARM_PRESETS),
                **SIDE_FIELD,
            }
        ),
    )
