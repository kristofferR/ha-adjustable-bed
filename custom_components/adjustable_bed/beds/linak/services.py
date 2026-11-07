"""Linak combined-motion and alarm actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...paired_coordinator import BedChild
from ...services import (
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
    MAX_TIMED_MOVE_DURATION_MS,
    MIN_TIMED_MOVE_DURATION_MS,
    SIDE_FIELD,
    _call_targets,
    _execute_preflighted,
    _preflight_and_execute,
    _preflight_each,
)
from ..base import BedController
from .protocol import LinakAlarmAction, LinakAlarmStep

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
    first_motor = call.data[ATTR_FIRST_MOTOR]
    second_motor = call.data[ATTR_SECOND_MOTOR]
    first_up = call.data[ATTR_FIRST_DIRECTION] == "up"
    second_up = call.data[ATTR_SECOND_DIRECTION] == "up"
    duration_ms = call.data[ATTR_DURATION_MS]
    if first_motor == second_motor:
        raise ServiceValidationError("Select two different motors")

    def check(target: BedChild, controller: BedController) -> None:
        if not controller.supports_simultaneous_movement:
            raise ServiceValidationError(
                f"Device '{target.name}' does not support simultaneous movement"
            )
        unavailable = {first_motor, second_motor} - set(controller.simultaneous_movement_axes)
        if unavailable:
            axes = ", ".join(sorted(unavailable))
            raise ServiceValidationError(f"Device '{target.name}' cannot combine motor: {axes}")

    async def move(controller: BedController) -> None:
        await controller.move_simultaneously(
            first_motor,
            first_up,
            second_motor,
            second_up,
            duration_ms,
        )

    targets = _call_targets(call)
    preflighted = await _preflight_each(targets, check)
    await _execute_preflighted(
        targets,
        preflighted,
        move,
        cancel_running=True,
        resource=None,
        resources=tuple(
            f"motor:{'bed_height' if motor == 'base' else motor}"
            for motor in (first_motor, second_motor)
        ),
    )


async def handle_linak_set_alarm(call: ServiceCall) -> None:
    """Program a Linak alarm using event, recurrence, and commit writes."""
    from .controller import LinakController

    steps = tuple(
        LinakAlarmStep(
            action=LinakAlarmAction(item[ATTR_ACTION]),
            lifetime=item[ATTR_LIFETIME],
            pause=item[ATTR_PAUSE],
        )
        for item in call.data[ATTR_ACTIONS]
    )

    async def program(controller: LinakController) -> None:
        await controller.program_alarm(
            call.data[ATTR_SECONDS],
            steps,
            call.data[ATTR_RECURRENCE_COUNT],
            call.data[ATTR_RECURRENCE_MINUTES],
        )

    await _preflight_and_execute(
        _call_targets(call),
        LinakController,
        "Linak alarm programming",
        program,
        supported=lambda controller: controller.supports_alarm,
    )


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
