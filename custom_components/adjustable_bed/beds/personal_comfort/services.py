"""Personal Comfort sequences over the existing paired group reservation."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...command_scheduler import CommandOutcome, current_command_context
from ...const import DOMAIN, PAIR_CONNECTION_MODE_CONCURRENT, SIDE_BOTH
from ...errors import invalid
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    BedTarget,
    PreflightedSides,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_sided,
    _get_controller_for_service,
    _release_preflighted,
    _validation_controller,
)
from ..base import BedController, require_controller

if TYPE_CHECKING:
    from ...services import _CommandAdmission
    from .controller import PersonalComfortBase
    from .session import Owner

OPERATIONS = ("full_body_massage", "flat_with_peer_foot", "anti_snore_with_peer_foot")


async def full_body(controller: PersonalComfortBase, owner: Owner) -> None:
    await controller.action(owner, "massage_head")
    await controller.pause(owner, 0.5)
    await controller.action(owner, "massage_foot")


async def handle_sequence(call: ServiceCall) -> None:
    targets = _call_targets(call)
    operation = call.data["operation"]
    foot_sync = operation != "full_body_massage"
    # Capture BOTH participants before any import/connect/capability wait.
    admissions = [
        _capture_command_admission(parent, SIDE_BOTH if foot_sync else side)
        for parent, side in targets
    ]
    rosters = [
        tuple(parent.children.items()) if isinstance(parent, PairedBedCoordinator) else ()
        for parent, _side in targets
    ]
    await async_import_modules(call.hass, "beds.personal_comfort.controller")
    from .controller import PersonalComfortBase

    preflighted: PreflightedSides = []
    plans = []
    try:
        for index, (parent, side) in enumerate(targets):
            scope = SIDE_BOTH if foot_sync else side
            if foot_sync and (not isinstance(parent, PairedBedCoordinator) or side == SIDE_BOTH):
                raise ValueError("Target one side of a combined bed for this sequence")
            children = tuple(_command_targets(parent, scope))
            if (
                isinstance(parent, PairedBedCoordinator)
                and len(children) > 1
                and parent.connection_mode != PAIR_CONNECTION_MODE_CONCURRENT
            ):
                raise ValueError("This sequence needs both bases connected at the same time, and this combined bed connects one side at a time")
            selected = frozenset(id(child) for child in _command_targets(parent, side))
            controllers = {}
            for child in children:
                candidate = require_controller(
                    await _validation_controller(parent, child, preflighted), PersonalComfortBase
                )
                action = (
                    ("flat" if operation == "flat_with_peer_foot" else "anti_snore")
                    if foot_sync and id(child) in selected
                    else "feet_down"
                    if foot_sync
                    else "massage_head"
                )
                candidate.validate_action(action)
                if not foot_sync:
                    candidate.validate_action("massage_foot")
                was_connected = child.is_connected
                controller = require_controller(
                    await _get_controller_for_service(child), PersonalComfortBase
                )
                if not was_connected:
                    preflighted.append((parent, child))
                controller.validate_action(action)
                if not foot_sync:
                    controller.validate_action("massage_foot")
                controllers[controller] = (controller.capture(), id(child) in selected)
            roster = rosters[index]
            plans.append((parent, scope, controllers, roster))
        # Preflight every request before the first physical write.
        for (parent, scope, controllers, roster), admission in zip(plans, admissions, strict=True):
            if _capture_command_admission(parent, scope, admission.resources) != admission:
                raise ValueError("A bed was stopped or changed while the sequence was starting. Try again")
            if (
                isinstance(parent, PairedBedCoordinator)
                and tuple(parent.children.items()) != roster
            ):
                raise ValueError("The combined bed changed while the sequence was starting. Try again")
            for controller, (owner, _selected) in controllers.items():
                controller.check_owner(owner, cleanup=True)
                if controller._coordinator.stop_epoch != owner.stop_epoch:
                    raise ValueError("The sequence was stopped before it started")

        for (parent, scope, controllers, roster), admission in zip(plans, admissions, strict=True):
            running: list[_CommandAdmission] = []

            async def execute(
                controller: BedController,
                controllers: dict[PersonalComfortBase, tuple[Owner, bool]] = controllers,
                parent: BedTarget = parent,
                roster: tuple = roster,
                scope: str = scope,
                running: list[_CommandAdmission] = running,
            ) -> None:
                if controller not in controllers:
                    raise ValueError("A base changed while the sequence was starting. Try again")
                if not running:
                    running.append(_capture_command_admission(parent, scope))

                def validate() -> None:
                    if (
                        isinstance(parent, PairedBedCoordinator)
                        and tuple(parent.children.items()) != roster
                    ):
                        raise ValueError("The combined bed changed while the sequence was starting. Try again")
                    for participant, (captured, _selected) in controllers.items():
                        participant.check_owner(captured, cleanup=True)
                    current = _capture_command_admission(parent, scope)
                    stopped = any(
                        participant._coordinator.stop_epoch != captured.stop_epoch
                        for participant, (captured, _selected) in controllers.items()
                    )
                    if stopped or current != running[0]:
                        if context := current_command_context():
                            context.request_cancel(
                                CommandOutcome.STOPPED if stopped else CommandOutcome.REPLACED
                            )
                        raise asyncio.CancelledError

                validate()
                base = require_controller(controller, PersonalComfortBase)
                captured, is_selected = controllers[base]
                # The group scheduler owns the new command's cancellation event;
                # the physical client, session and STOP epoch remain captured.
                owner = replace(
                    captured, cancel=base._coordinator.cancel_command, validate=validate
                )
                if not foot_sync:
                    await full_body(base, owner)
                elif is_selected:
                    await base.action(
                        owner, "flat" if operation == "flat_with_peer_foot" else "anti_snore"
                    )
                else:
                    await base.held_axis(owner, "feet", False, 30_000)

            await _execute_sided(parent, scope, execute, admission=admission)
    except (ValueError, TypeError, NotImplementedError, ConnectionError) as error:
        raise invalid("personal_comfort_sequence") from error
    finally:
        await _release_preflighted(preflighted)


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "personal_comfort_sequence",
        handle_sequence,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("operation"): vol.In(OPERATIONS),
                **SIDE_FIELD,
            }
        ),
    )
