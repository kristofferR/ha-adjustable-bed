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
    sections = frozenset(call.data.get("sections", ()))
    first_motor = call.data.get(ATTR_FIRST_MOTOR, "back")
    second_motor = call.data.get(ATTR_SECOND_MOTOR, "legs")
    first_up = call.data.get(ATTR_FIRST_DIRECTION, call.data.get("direction")) == "up"
    second_up = call.data.get(ATTR_SECOND_DIRECTION, call.data.get("direction")) == "up"
    duration_ms = call.data[ATTR_DURATION_MS]
    if first_motor == second_motor:
        raise invalid("motors_must_differ")
    session_bound_receivers: set[str] = set()

    async def check(target: BedChild, controller: BedController) -> None:
        if isinstance(controller, LinakController):
            await controller.prepare_simultaneous_movement()
        if not controller.supports_simultaneous_movement:
            raise invalid(
                "feature_not_supported",
                device_name=target.name,
                feature="moving two motors together",
            )
        if sections and (
            not isinstance(controller, LinakController)
            or controller._profile is not LinakProfile.CARPE_DIEM
        ):
            raise invalid(
                "feature_not_supported",
                device_name=target.name,
                feature="selected-section movement",
            )
        unavailable = (sections or {first_motor, second_motor}) - set(
            controller.simultaneous_movement_axes
        )
        if unavailable:
            axes = ", ".join(sorted(unavailable))
            raise invalid(
                "feature_not_supported", device_name=target.name, feature=f"moving {axes} together"
            )
        if isinstance(controller, LinakController):
            controller.validate_simultaneous_directions(first_up, second_up)
            if controller.binds_grouped_abort_to_session:
                session_bound_receivers.add(target.address)

    async def move(controller: BedController) -> None:
        if sections and isinstance(controller, LinakController):
            await controller.move_selected_sections(sections, first_up, duration_ms)
            return
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
        for motor in (sorted(sections) if sections else (first_motor, second_motor))
    )
    admissions = [
        _capture_command_admission(coordinator, side, resources) for coordinator, side in targets
    ]
    await async_import_modules(call.hass, "beds.linak.controller")
    from .controller import LinakController
    from .protocol import LinakProfile

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

    hass.services.async_register(
        DOMAIN,
        "linak_move_sections",
        handle_linak_move_simultaneously,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("sections"): vol.All(
                    [vol.In(("back", "legs", "head", "feet"))], vol.Length(min=1, max=4)
                ),
                vol.Required("direction"): vol.In(LINAK_DIRECTION_OPTIONS),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_TIMED_MOVE_DURATION_MS, max=MAX_TIMED_MOVE_DURATION_MS),
                ),
                **SIDE_FIELD,
            }
        ),
    )
