"""Linak combined-motion and alarm actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...errors import invalid
from ...paired_coordinator import BedChild
from ...services import (
    ATTR_DURATION_MS,
    ATTR_FIRST_DIRECTION,
    ATTR_FIRST_MOTOR,
    ATTR_SECOND_DIRECTION,
    ATTR_SECOND_MOTOR,
    DEVICE_IDS,
    MAX_TIMED_MOVE_DURATION_MS,
    MIN_TIMED_MOVE_DURATION_MS,
    SIDE_FIELD,
    _call_targets,
    _execute_preflighted,
    _preflight_each,
)
from ..base import BedController

SERVICE_LINAK_MOVE_SIMULTANEOUS = "linak_move_simultaneously"
LINAK_MOTOR_OPTIONS = ("base", "feet", "head", "legs", "back")
LINAK_DIRECTION_OPTIONS = ("up", "down")
async def handle_linak_move_simultaneously(call: ServiceCall) -> None:
    """Drive two sections with one native combined-motion command."""
    first_motor = call.data[ATTR_FIRST_MOTOR]
    second_motor = call.data[ATTR_SECOND_MOTOR]
    first_up = call.data[ATTR_FIRST_DIRECTION] == "up"
    second_up = call.data[ATTR_SECOND_DIRECTION] == "up"
    duration_ms = call.data[ATTR_DURATION_MS]
    if first_motor == second_motor:
        raise invalid("motors_must_differ")

    def check(target: BedChild, controller: BedController) -> None:
        if not controller.supports_simultaneous_movement:
            raise invalid("feature_not_supported", device_name=target.name, feature="moving two motors together")
        unavailable = {first_motor, second_motor} - set(controller.simultaneous_movement_axes)
        if unavailable:
            axes = ", ".join(sorted(unavailable))
            raise invalid("feature_not_supported", device_name=target.name, feature=f"moving {axes} together")

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


def async_register_linak_services(hass: HomeAssistant) -> None:
    """Register the Linak combined-motion and alarm actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINAK_MOVE_SIMULTANEOUS,
        handle_linak_move_simultaneously,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
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
