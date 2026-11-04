"""Customatic Z-Series app alarm and clock actions."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_ZSERIES, DOMAIN
from .services import (
    ATTR_ENABLED,
    ATTR_SIDE,
    ATTR_TIME,
    ATTR_WAKE_MODE,
    SIDE_FIELD,
    _command_targets,
    _execute_sided,
    _get_controller_for_service,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController
    from .beds.serenity import ZSeriesController


SERVICE_ZSERIES_SET_ALARM = "zseries_set_alarm"


def _zseries_controller(controller: BedController | SideBoundController) -> ZSeriesController:
    """Return the Z-Series controller behind a possibly side-bound proxy."""
    from .beds.base import SideBoundController as Bound
    from .beds.serenity import ZSeriesController as ZSeries

    inner = controller._controller if isinstance(controller, Bound) else controller
    if not isinstance(inner, ZSeries):
        raise ServiceValidationError("This action requires a Customatic Z-Series app controller")
    return inner


async def _execute_zseries_alarm(
    call: ServiceCall,
    label: str,
    command: Callable[[BedController | SideBoundController], Coroutine[Any, Any, None]],
) -> None:
    """Preflight every physical Z-Series target before any alarm or clock write."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_ZSERIES:
                raise ServiceValidationError(
                    f"Device '{target.name}' is not a Customatic Z-Series app controller"
                )
    # The alarm page exists only after an exact CST13/CST14 manufacturer read.
    # A cached controller can only rule a bed out on a confirmed other string.
    preflighted = await _preflight_capability(targets, "alarm_not_ruled_out", label)
    try:
        # All-or-nothing: resolve every unknown state on a live connection before
        # any bed receives a clock or alarm frame.
        physical = [
            (coordinator, target)
            for coordinator, side in targets
            for target in _command_targets(coordinator, side)
        ]
        for coordinator, target in physical:
            cached = target.capability_controller
            state = _zseries_controller(cached).alarm_state if cached is not None else None
            if state is None:
                opened = not target.is_connected
                if not any(known is target for _, known in preflighted):
                    preflighted.append((coordinator, target))
                live = _zseries_controller(await _get_controller_for_service(target))
                state = await live.resolve_alarm_state()
                if opened and len(physical) > 1:
                    # Like _validation_controller, never hold a capability-only link
                    # while probing the next target: a sequential or one-slot path
                    # cannot open a second one. The read result is persisted, and
                    # execution reconnects each side through its normal path.
                    released = await target.async_disconnect("capability_probe")
                    if released is False or target.is_connected:
                        raise ServiceValidationError(
                            f"Could not release '{target.name}' before checking the next bed"
                        )
                    preflighted[:] = [item for item in preflighted if item[1] is not target]
            if state is None:
                raise ServiceValidationError(
                    f"Could not read the manufacturer string of '{target.name}' that "
                    "enables Z-Series alarms; try again"
                )
            if not state:
                raise ServiceValidationError(f"Device '{target.name}' does not support {label}")
        for coordinator, side in targets:
            # The app cancels the running stream first; HA also releases it safely.
            await _execute_sided(coordinator, side, command)
    except ValueError as err:
        await _release_preflighted(preflighted)
        raise ServiceValidationError(str(err)) from err
    except BaseException:
        await _release_preflighted(preflighted)
        raise


async def handle_zseries_set_alarm(call: ServiceCall) -> None:
    """Set or clear the Z-Series app alarm, using Home Assistant's local time."""
    enabled = call.data[ATTR_ENABLED]
    alarm_time = call.data.get(ATTR_TIME)
    wake_mode = call.data.get(ATTR_WAKE_MODE)
    if enabled and alarm_time is None:
        raise ServiceValidationError(
            "Choose an alarm time",
            translation_domain=DOMAIN,
            translation_key="zseries_alarm_time_required",
        )
    if enabled and wake_mode is None:
        # The app refuses to enable an alarm until a wake-up mode is chosen.
        raise ServiceValidationError(
            "Choose a wake-up mode",
            translation_domain=DOMAIN,
            translation_key="zseries_alarm_wake_mode_required",
        )
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise ServiceValidationError("Z-Series alarms use minute precision")
    hour, minute = (alarm_time.hour, alarm_time.minute) if alarm_time is not None else (0, 0)

    async def program(controller: BedController | SideBoundController) -> None:
        await controller.configure_clock_alarm(
            enabled=enabled,
            weekdays=(),
            hour=hour,
            minute=minute,
            preset=wake_mode or "massage",  # Ignored when clearing the alarm.
        )

    await _execute_zseries_alarm(call, "Z-Series app alarms", program)


def async_register_serenity_services(hass: HomeAssistant) -> None:
    """Register the Z-Series app alarm action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_ZSERIES_SET_ALARM,
        handle_zseries_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME): cv.time,
                vol.Optional(ATTR_WAKE_MODE): vol.In(("massage", "memory_1")),
                **SIDE_FIELD,
            }
        ),
    )
