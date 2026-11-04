"""Linak combined-motion and alarm actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .beds.linak_protocol import LinakAlarmAction, LinakAlarmStep
from .const import DOMAIN
from .services import (
    ATTR_ACTION,
    ATTR_ACTIONS,
    ATTR_DURATION_MS,
    ATTR_FIRST_DIRECTION,
    ATTR_FIRST_MOTOR,
    ATTR_LIFETIME,
    ATTR_PAUSE,
    ATTR_RECURRENCE_COUNT,
    ATTR_RECURRENCE_MINUTES,
    ATTR_SECOND_DIRECTION,
    ATTR_SECOND_MOTOR,
    ATTR_SECONDS,
    ATTR_SIDE,
    MAX_TIMED_MOVE_DURATION_MS,
    MIN_TIMED_MOVE_DURATION_MS,
    SIDE_FIELD,
    _command_targets,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
    _validation_controller,
)

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController


SERVICE_LINAK_MOVE_SIMULTANEOUS = "linak_move_simultaneously"
SERVICE_LINAK_SET_ALARM = "linak_set_alarm"
LINAK_MOTOR_OPTIONS = ("base", "feet", "head", "legs", "back")
LINAK_DIRECTION_OPTIONS = ("up", "down")
LINAK_ALARM_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ACTION): vol.In(tuple(action.value for action in LinakAlarmAction)),
        vol.Optional(ATTR_LIFETIME, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_PAUSE, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    }
)


async def handle_linak_move_simultaneously(call: ServiceCall) -> None:
    """Drive two sections with one native combined-motion command."""
    hass = call.hass
    first_motor = call.data[ATTR_FIRST_MOTOR]
    second_motor = call.data[ATTR_SECOND_MOTOR]
    first_up = call.data[ATTR_FIRST_DIRECTION] == "up"
    second_up = call.data[ATTR_SECOND_DIRECTION] == "up"
    duration_ms = call.data[ATTR_DURATION_MS]
    explicit_side = call.data.get(ATTR_SIDE)
    if first_motor == second_motor:
        raise ServiceValidationError("Select two different motors")

    targets, missing = _resolve_sided_targets(
        hass,
        call.data.get(CONF_DEVICE_ID, []),
        explicit_side,
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_simultaneous_movement",
        "simultaneous movement",
    )
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(
                    coordinator,
                    target,
                    preflighted,
                )
                unavailable = {first_motor, second_motor} - set(
                    controller.simultaneous_movement_axes
                )
                if unavailable:
                    axes = ", ".join(sorted(unavailable))
                    raise ServiceValidationError(
                        f"Device '{target.name}' cannot combine motor: {axes}",
                    )
    except ServiceValidationError:
        await _release_preflighted(preflighted)
        raise

    async def move(controller: BedController | SideBoundController) -> None:
        await controller.move_simultaneously(
            first_motor,
            first_up,
            second_motor,
            second_up,
            duration_ms,
        )

    try:
        resources = tuple(
            f"motor:{'bed_height' if motor == 'base' else motor}"
            for motor in (first_motor, second_motor)
        )
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, move, resources=resources)
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_linak_set_alarm(call: ServiceCall) -> None:
    """Program a Linak alarm using event, recurrence, and commit writes."""
    hass = call.hass
    steps = tuple(
        LinakAlarmStep(
            action=LinakAlarmAction(item[ATTR_ACTION]),
            lifetime=item[ATTR_LIFETIME],
            pause=item[ATTR_PAUSE],
        )
        for item in call.data[ATTR_ACTIONS]
    )
    explicit_side = call.data.get(ATTR_SIDE)
    targets, missing = _resolve_sided_targets(
        hass,
        call.data.get(CONF_DEVICE_ID, []),
        explicit_side,
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_alarm",
        "Linak alarm programming",
    )

    async def program(controller: BedController | SideBoundController) -> None:
        await controller.program_alarm(
            call.data[ATTR_SECONDS],
            steps,
            call.data[ATTR_RECURRENCE_COUNT],
            call.data[ATTR_RECURRENCE_MINUTES],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                program,
                cancel_running=False,
                resource="configuration",
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


def async_register_linak_services(hass: HomeAssistant) -> None:
    """Register the Linak combined-motion and alarm actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINAK_MOVE_SIMULTANEOUS,
        handle_linak_move_simultaneously,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_FIRST_MOTOR): vol.In(LINAK_MOTOR_OPTIONS),
                vol.Required(ATTR_FIRST_DIRECTION): vol.In(LINAK_DIRECTION_OPTIONS),
                vol.Required(ATTR_SECOND_MOTOR): vol.In(LINAK_MOTOR_OPTIONS),
                vol.Required(ATTR_SECOND_DIRECTION): vol.In(LINAK_DIRECTION_OPTIONS),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_TIMED_MOVE_DURATION_MS,
                        max=MAX_TIMED_MOVE_DURATION_MS,
                    ),
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINAK_SET_ALARM,
        handle_linak_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_SECONDS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=0x1FFFF),
                ),
                vol.Required(ATTR_ACTIONS): vol.All(
                    [LINAK_ALARM_ACTION_SCHEMA],
                    vol.Length(min=1, max=4),
                ),
                vol.Optional(ATTR_RECURRENCE_COUNT, default=0): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=31),
                ),
                vol.Optional(ATTR_RECURRENCE_MINUTES, default=0): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=2047),
                ),
                **SIDE_FIELD,
            }
        ),
    )
