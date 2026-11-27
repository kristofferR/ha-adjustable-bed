"""Linak combined-motion and alarm actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...command_scheduler import PAIRED_SESSION_BOUND_ABORTS
from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
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
    _capture_command_admission,
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
    session_bound_receivers: set[str] = set()

    async def check(target: BedChild, controller: BedController) -> None:
        if isinstance(controller, LinakController):
            await controller.prepare_simultaneous_movement()
        if not controller.supports_simultaneous_movement:
            raise invalid("feature_not_supported", device_name=target.name, feature="moving two motors together")
        unavailable = {first_motor, second_motor} - set(controller.simultaneous_movement_axes)
        if unavailable:
            axes = ", ".join(sorted(unavailable))
            raise invalid("feature_not_supported", device_name=target.name, feature=f"moving {axes} together")
        if isinstance(controller, LinakController):
            controller.validate_simultaneous_directions(first_up, second_up)
            if controller.binds_grouped_abort_to_session:
                session_bound_receivers.add(target.address)

    async def move(controller: BedController) -> None:
        await controller.move_simultaneously(
            first_motor,
            first_up,
            second_motor,
            second_up,
            duration_ms,
        )

    targets = _call_targets(call)
    resources = tuple(
        f"motor:{'bed_height' if motor == 'base' else motor}"
        for motor in (first_motor, second_motor)
    )
    admissions = [
        _capture_command_admission(coordinator, side, resources) for coordinator, side in targets
    ]
    await async_import_modules(call.hass, "beds.linak.controller")
    from .controller import LinakController

    preflighted = await _preflight_each(targets, check)
    abort_scope = PAIRED_SESSION_BOUND_ABORTS.set(frozenset(session_bound_receivers))
    try:
        await _execute_preflighted(
            targets,
            preflighted,
            move,
            cancel_running=True,
            resource=None,
            resources=resources,
            admissions=admissions,
            translate_side_errors=True,
        )
    finally:
        PAIRED_SESSION_BOUND_ABORTS.reset(abort_scope)


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
