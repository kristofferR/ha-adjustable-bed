"""Leggett Okin sleep and alarm timer actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_LEGGETT_OKIN, CONF_PROTOCOL_VARIANT, DOMAIN, resolve_explicit_bed_type
from .services import (
    ATTR_ACTION,
    ATTR_MINUTES,
    ATTR_PRESET,
    ATTR_SIDE,
    SIDE_FIELD,
    BedTarget,
    PreflightedSides,
    _command_targets,
    _execute_sided,
    _leggett_integer,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
    _validation_controller,
)

if TYPE_CHECKING:
    from .beds.base import BedController


SERVICE_LEGGETT_SLEEP_TIMER = "leggett_sleep_timer"
SERVICE_LEGGETT_ALARM_TIMER = "leggett_alarm_timer"


async def _preflight_leggett(
    targets: list[tuple[BedTarget, str]], capability: str, label: str
) -> PreflightedSides:
    """Check exact protocol and capability before commanding any physical side."""
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            bed_type = resolve_explicit_bed_type(
                target.bed_type, target.entry.data.get(CONF_PROTOCOL_VARIANT)
            )
            if bed_type != BED_TYPE_LEGGETT_OKIN:
                raise ServiceValidationError(
                    f"Device '{target.name}' is not a Leggett Okin controller"
                )
    return await _preflight_capability(targets, capability, label)


async def _handle_leggett_timer(call: ServiceCall, *, alarm: bool) -> None:
    """Validate all timer targets, then program or cancel each through its queue."""
    start = call.data[ATTR_ACTION] == "start"
    minutes = call.data.get(ATTR_MINUTES)
    if start and minutes is None:
        raise ServiceValidationError("Starting a timer requires minutes")
    memory_num = call.data.get(ATTR_PRESET, 1)
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_leggett(
        targets,
        "supports_alarm_timer" if alarm else "supports_sleep_timer",
        "Leggett alarm timers" if alarm else "Leggett sleep timers",
    )
    try:
        if start and not alarm:
            for coordinator, side in targets:
                for target in _command_targets(coordinator, side):
                    controller = await _validation_controller(coordinator, target, preflighted)
                    if memory_num not in controller.sleep_timer_memory_options:
                        raise ServiceValidationError(
                            f"Device '{target.name}' does not support sleep action {memory_num}"
                        )
                    options = controller.sleep_timer_duration_options
                    if options and minutes not in options:
                        raise ServiceValidationError(
                            f"Device '{target.name}' requires a sleep duration from {options} minutes"
                        )

        async def timer(controller: BedController) -> None:
            if start:
                assert minutes is not None
                if alarm:
                    await controller.set_alarm_timer(minutes)
                else:
                    await controller.set_sleep_timer(minutes, memory_num)
            elif alarm:
                await controller.cancel_alarm_timer()
            else:
                await controller.cancel_sleep_timer()

        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, timer, cancel_running=False, resource="configuration"
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_leggett_sleep_timer(call: ServiceCall) -> None:
    """Start or cancel the profile's delayed-preset timer."""
    await _handle_leggett_timer(call, alarm=False)


async def handle_leggett_alarm_timer(call: ServiceCall) -> None:
    """Start or cancel the profile's alarm delay."""
    await _handle_leggett_timer(call, alarm=True)


def async_register_leggett_okin_services(hass: HomeAssistant) -> None:
    """Register the Leggett Okin sleep and alarm timer actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEGGETT_SLEEP_TIMER,
        handle_leggett_sleep_timer,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ACTION): vol.In(("start", "cancel")),
                vol.Optional(ATTR_MINUTES): vol.All(_leggett_integer, vol.Range(min=1, max=1439)),
                vol.Optional(ATTR_PRESET, default=1): vol.All(
                    _leggett_integer, vol.Range(min=0, max=4)
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEGGETT_ALARM_TIMER,
        handle_leggett_alarm_timer,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ACTION): vol.In(("start", "cancel")),
                vol.Optional(ATTR_MINUTES): vol.All(_leggett_integer, vol.Range(min=1, max=1440)),
                **SIDE_FIELD,
            }
        ),
    )
