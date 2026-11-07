"""FurniMove profile actions, massage and rename."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_FURNIMOVE, DOMAIN
from .pairing import iter_children
from .services import (
    ATTR_DURATION,
    ATTR_DURATION_MS,
    ATTR_FIRST_DIRECTION,
    ATTR_FIRST_MOTOR,
    ATTR_SECOND_DIRECTION,
    ATTR_SECOND_MOTOR,
    ATTR_SIDE,
    SIDE_FIELD,
    BedTarget,
    _command_targets,
    _execute_sided,
    _hold_seconds,
    _leggett_integer,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

if TYPE_CHECKING:
    from .beds.base import BedController


SERVICE_FURNIMOVE_ACTION = "furnimove_action"
SERVICE_FURNIMOVE_MASSAGE_PROGRAM = "furnimove_massage_program"
SERVICE_FURNIMOVE_MASSAGE_DURATION = "furnimove_massage_duration"
SERVICE_FURNIMOVE_MOVE_SIMULTANEOUSLY = "furnimove_move_simultaneously"


def _furnimove_targets(call: ServiceCall) -> list[tuple[BedTarget, str]]:
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_FURNIMOVE:
                raise ServiceValidationError(f"Device '{target.name}' is not a FurniMove profile")
    return targets


async def _execute_furnimove(
    call: ServiceCall,
    validate: Callable[[BedController], None],
    operation: Callable[[BedController], Coroutine[Any, Any, None]],
    *,
    cancel_running: bool = True,
) -> None:
    targets = _furnimove_targets(call)
    preflighted = await _preflight_capability(
        targets, "furnimove_action_specs", "FurniMove app controls", validate
    )
    try:
        for coordinator, side in targets:
            # Every consumer uses one mutable write role and global release.
            await _execute_sided(
                coordinator, side, operation, cancel_running=cancel_running, resource="*"
            )
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


async def handle_furnimove_action(call: ServiceCall) -> None:
    """Dispatch an ordered row through its artifact-proven consumer."""
    row_index = call.data["row_index"]
    duration = call.data.get(ATTR_DURATION)
    duration_ms = int(duration * 1000) if duration is not None else None
    consumer = call.data["consumer"]
    selected_action: tuple[str, str] | None = None

    def validate(controller: BedController) -> None:
        nonlocal selected_action
        action = controller.validate_furnimove_action(
            row_index, duration_ms=duration_ms, consumer=consumer
        )
        if selected_action is not None and action != selected_action:
            raise ValueError(
                "The selected row represents different actions; target one device or side"
            )
        selected_action = action

    async def execute(controller: BedController) -> None:
        await controller.async_execute_furnimove_action(
            row_index, duration_ms=duration_ms, consumer=consumer
        )

    await _execute_furnimove(call, validate, execute)


async def _rename_furnimove(
    call: ServiceCall, targets: list[tuple[BedTarget, str]], name: str
) -> None:
    """Write the original validated name to this app's discovered rename role."""
    from .beds.furnimove import validate_furnimove_name

    try:
        validate_furnimove_name(name)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    physical = [
        target for coordinator, side in targets for target in _command_targets(coordinator, side)
    ]
    if len(physical) != 1:
        raise ServiceValidationError("Rename one physical FurniMove receiver at a time")
    names = {physical[0].name.strip().lower()}
    for entry in call.hass.config_entries.async_entries(DOMAIN):
        names.add(entry.title.strip().lower())
        for data in (entry.data, *iter_children(entry.data)):
            stored = data.get(CONF_NAME)
            if isinstance(stored, str):
                names.add(stored.strip().lower())
    if name.strip().lower() in names:
        raise ServiceValidationError("Choose a different, unique FurniMove name")

    def validate(controller: BedController) -> None:
        controller.validate_furnimove_rename(name)
        if not controller.supports_device_rename:
            raise ValueError("This receiver has no writable rename characteristic")

    async def execute(controller: BedController) -> None:
        await controller.rename_device(name)

    try:
        if not await physical[0].async_ensure_connected():
            raise ServiceValidationError("Could not connect to the FurniMove receiver")
        await _execute_furnimove(call, validate, execute)
    except Exception, asyncio.CancelledError:
        await _release_preflighted([(targets[0][0], physical[0])])
        raise
    entry = physical[0].entry
    data = {**entry.data, CONF_NAME: name.strip()}
    if isinstance(entry, ConfigEntry):
        call.hass.config_entries.async_update_entry(entry, title=name.strip(), data=data)
    else:
        from .coordinator import ChildEntryView

        if isinstance(entry, ChildEntryView):
            entry.persist_data(data, keys=(CONF_NAME,))


async def handle_furnimove_massage_program(call: ServiceCall) -> None:
    """Choose an app massage program independently of arbitrary row labels."""
    program = call.data["program"]

    def validate(controller: BedController) -> None:
        controller.validate_furnimove_massage_program(program)

    async def execute(controller: BedController) -> None:
        await controller.set_furnimove_massage_program(program)

    await _execute_furnimove(call, validate, execute)


async def handle_furnimove_massage_duration(call: ServiceCall) -> None:
    """Store the app's advisory duration without programming a hardware timer."""
    from .coordinator import AdjustableBedCoordinator

    minutes = call.data["minutes"]
    physical_targets: list[AdjustableBedCoordinator] = []
    for coordinator, side in _furnimove_targets(call):
        for target in _command_targets(coordinator, side):
            if not isinstance(target, AdjustableBedCoordinator):
                raise ServiceValidationError("FurniMove requires a physical receiver target")
            await target.async_prime_offline_controller()
            physical_targets.append(target)

    for target in physical_targets:
        controller = target.capability_controller
        if controller is None:
            raise ServiceValidationError("No selected FurniMove handset is available")
        if not controller.supports_massage or minutes not in controller.massage_timer_options:
            raise ServiceValidationError("This handset has no supported local massage duration")

    for target in physical_targets:
        await target.async_set_furnimove_massage_duration(minutes)


async def handle_furnimove_move_simultaneously(call: ServiceCall) -> None:
    """Combine two supported axes by OR, retaining the app's checksum rule."""
    first = call.data[ATTR_FIRST_MOTOR]
    second = call.data[ATTR_SECOND_MOTOR]
    first_up = call.data[ATTR_FIRST_DIRECTION] == "up"
    second_up = call.data[ATTR_SECOND_DIRECTION] == "up"
    duration_ms = call.data[ATTR_DURATION_MS]

    def validate(controller: BedController) -> None:
        controller.validate_furnimove_simultaneous(first, first_up, second, second_up, duration_ms)

    async def execute(controller: BedController) -> None:
        await controller.move_simultaneously(first, first_up, second, second_up, duration_ms)

    await _execute_furnimove(call, validate, execute)


def async_register_furnimove_services(hass: HomeAssistant) -> None:
    """Register the FurniMove profile actions."""
    device_fields = {
        vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
        **SIDE_FIELD,
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_FURNIMOVE_ACTION,
        handle_furnimove_action,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required("row_index"): vol.All(_leggett_integer, vol.Range(min=0)),
                vol.Optional(ATTR_DURATION): _hold_seconds,
                vol.Optional("consumer", default="app"): vol.In(("app", "widget")),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FURNIMOVE_MASSAGE_PROGRAM,
        handle_furnimove_massage_program,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required("program"): vol.All(_leggett_integer, vol.Range(min=1, max=4)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FURNIMOVE_MOVE_SIMULTANEOUSLY,
        handle_furnimove_move_simultaneously,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required(ATTR_FIRST_MOTOR): vol.In(("head", "back", "legs", "feet")),
                vol.Required(ATTR_SECOND_MOTOR): vol.In(("head", "back", "legs", "feet")),
                vol.Required(ATTR_FIRST_DIRECTION): vol.In(("up", "down")),
                vol.Required(ATTR_SECOND_DIRECTION): vol.In(("up", "down")),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    _leggett_integer, vol.Range(min=1, max=60000)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FURNIMOVE_MASSAGE_DURATION,
        handle_furnimove_massage_duration,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required("minutes"): vol.All(
                    vol.In((10, 15, 20, 30, "10", "15", "20", "30")), vol.Coerce(int)
                ),
            }
        ),
    )
