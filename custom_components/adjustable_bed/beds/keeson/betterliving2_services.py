"""BetterLiving2 actions with pre-await physical-owner/STOP admission."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...alarm import AlarmRequest
from ...command_scheduler import (
    CommandKind,
    CommandOutcome,
    PreparedCommandInvalidated,
    current_command_context,
)
from ...const import DOMAIN
from ...coordinator import AdjustableBedCoordinator
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    BedTarget,
    _call_targets,
    _capture_command_admission,
    _check_alarm,
    _CommandAdmission,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)
from .betterliving2_selection import PreparationCancelled, Selection

if TYPE_CHECKING:
    from ...paired_coordinator import BedChild
    from .betterliving2 import BetterLiving2Controller


async def _run_owned(
    child: AdjustableBedCoordinator,
    selection: Selection,
    operation: Callable[[], Awaitable[None]],
) -> None:
    """Enter the captured app scope before the admitted operation can connect."""
    from .betterliving2 import drain

    async def admitted() -> None:
        with selection.bind_operation():
            try:
                selection.begin(child)
                await operation()
            except PreparationCancelled as err:
                if err.selection is not selection or err.child is not child:
                    raise
            finally:
                selection.finished(child)

    context = current_command_context()
    if context is not None and context.scheduler_token is child._command_scheduler.token:
        await admitted()
        return
    handle = await child.async_prepare_command_operation(
        admitted,
        kind=CommandKind.COMMAND,
        cancel_running=True,
        group_id=uuid4().hex,
        expected_stop_epoch=selection.owners[id(child)].stop_epoch,
    )
    try:
        await child.async_wait_prepared_command(handle)
        child.commit_prepared_command(handle)
        await child.async_wait_prepared_command_result(handle)
    except PreparedCommandInvalidated:
        if handle.outcome not in {CommandOutcome.STOPPED, CommandOutcome.REPLACED}:
            raise
    finally:
        if not handle.future.done():
            await drain(asyncio.create_task(child.async_abort_prepared_command(handle)))


async def _execute_selection(
    targets: list[tuple[BedTarget, str]],
    admissions: list[_CommandAdmission],
    selection: Selection,
    label: str,
    execute: Callable[[BetterLiving2Controller], Awaitable[None]],
    validate: Callable[[BetterLiving2Controller], None],
) -> None:
    from .betterliving2 import BetterLiving2Controller

    preflighted = await _preflight_capability(
        targets, BetterLiving2Controller, label, validate=validate
    )

    async def prepared(controller: BetterLiving2Controller) -> None:
        if await selection.prepared(controller):
            await execute(controller)

    command = _family_command(BetterLiving2Controller, label, prepared)

    async def child_operation(child: BedChild) -> None:
        if not isinstance(child, AdjustableBedCoordinator):
            raise ServiceValidationError(
                "Choose a physical receiver",
                translation_domain=DOMAIN,
                translation_key="betterliving2_selection_changed",
                translation_placeholders={"reason": "Choose a physical receiver"},
            )

        async def operation() -> None:
            await child.async_execute_controller_command(
                command,
                cancel_running=False,
                resource=None,
                expected_stop_epoch=selection.owners[id(child)].stop_epoch,
            )

        await _run_owned(child, selection, operation)

    try:
        for (parent, side), admission in zip(targets, admissions, strict=True):
            if isinstance(parent, PairedBedCoordinator):
                await parent.async_run_child_operation(
                    "command",
                    child_operation,
                    side=side,
                    cancel_running=True,
                    resource=None,
                    expected_pair_generations=admission.expected_pair_generations,
                    expected_stop_epochs=admission.expected_stop_epochs,
                )
                if selection.invalid:
                    selection.check()
                selection.completed(parent, side)
            else:
                await child_operation(parent)
    except BaseException:
        await _release_preflighted(preflighted)
        raise


class DiagnosticAction(StrEnum):
    REFRESH_ALARM = "refresh_alarm"
    REFRESH_MASSAGE = "refresh_massage"
    SET_MASSAGE_TIMER = "set_massage_timer"


def validate_diagnostic_action(
    controller: BetterLiving2Controller,
    action: DiagnosticAction,
    timer: int | None,
) -> None:
    if action is DiagnosticAction.REFRESH_MASSAGE and controller.wire == "P1":
        raise ValueError("This profile has no massage status query")
    if action is DiagnosticAction.SET_MASSAGE_TIMER:
        if controller.wire != "P1" or type(timer) is not int or not -1 <= timer <= 2:
            raise ValueError("Choose a supported massage timer setting")
    elif timer is not None:
        raise ValueError("A timer setting applies only to the timer action")


async def execute_diagnostic_action(
    controller: BetterLiving2Controller,
    action: DiagnosticAction,
    timer: int | None,
) -> None:
    validate_diagnostic_action(controller, action, timer)
    if action is DiagnosticAction.REFRESH_ALARM:
        await controller.query_alarm()
    elif action is DiagnosticAction.REFRESH_MASSAGE:
        await controller.query_massage()
    else:
        assert timer is not None
        await controller.set_level("timer", timer)


async def diagnostic_action(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    action = DiagnosticAction(call.data["action"])
    timer: int | None = call.data.get("timer")
    selection = Selection(
        targets,
        admissions,
        required_wire="p1" if action is DiagnosticAction.SET_MASSAGE_TIMER else None,
    )
    with selection.scope():
        await async_import_modules(call.hass, "beds.keeson.betterliving2")

        if selection.stopped_before_preflight():
            return

        def prepare(controller: BetterLiving2Controller) -> None:
            selection.check()
            validate_diagnostic_action(controller, action, timer)

        async def execute(controller: BetterLiving2Controller) -> None:
            selection.start(controller)
            await execute_diagnostic_action(controller, action, timer)

        await _execute_selection(
            targets, admissions, selection, "bed diagnostic action", execute, prepare
        )


def integer(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is float and value.is_integer():
        return int(value)
    raise vol.Invalid("Expected an integer")


async def set_alarm(call: ServiceCall, alarm: AlarmRequest, given: list[str]) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    selection = Selection(targets, admissions)
    if (
        not alarm.enabled
        and call.data.get("time") is None
        and any(owner.data.get("protocol_variant") == "p3" for owner in selection.owners.values())
    ):
        raise ServiceValidationError(
            "Choose an alarm time",
            translation_domain=DOMAIN,
            translation_key="alarm_time_required",
        )
    with selection.scope():
        await _set_alarm(call, targets, admissions, selection, alarm, given)


async def _set_alarm(
    call: ServiceCall,
    targets: list[tuple[BedTarget, str]],
    admissions: list[_CommandAdmission],
    selection: Selection,
    alarm: AlarmRequest,
    given: list[str],
) -> None:
    await async_import_modules(call.hass, "beds.keeson.betterliving2")
    from .betterliving2 import AlarmPlan

    if selection.stopped_before_preflight():
        return
    plans: dict[int, AlarmPlan] = {}

    def prepare(controller: BetterLiving2Controller) -> None:
        selection.check()
        request = _check_alarm(controller._coordinator.name, controller, alarm, given)
        plans[id(controller._coordinator)] = controller.alarm_plan(request)

    async def execute(controller: BetterLiving2Controller) -> None:
        owner = id(controller._coordinator)
        if owner not in plans:
            raise ServiceValidationError(
                "BetterLiving2 owner changed during alarm admission",
                translation_domain=DOMAIN,
                translation_key="betterliving2_alarm_owner_changed",
            )
        selection.start(controller)
        # Only the cohort can admit the native same-owner sequential switch.
        await controller.set_alarm(replace(plans[owner], link=controller._live()))

    await _execute_selection(targets, admissions, selection, "bed alarms", execute, prepare)


async def massage(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    selection = Selection(targets, admissions, required_wire="p1")
    with selection.scope():
        await _massage(call, targets, admissions, selection)


async def _massage(
    call: ServiceCall,
    targets: list[tuple[BedTarget, str]],
    admissions: list[_CommandAdmission],
    selection: Selection,
) -> None:
    await async_import_modules(call.hass, "beds.keeson.betterliving2")

    if selection.stopped_before_preflight():
        return
    layouts: dict[int, str] = {}

    def prepare(controller: BetterLiving2Controller) -> None:
        selection.check()
        if controller.wire != "P1":
            raise ValueError("Absolute paired massage levels require BetterLiving2 P1")
        layouts[id(controller._coordinator)] = controller.layout

    async def execute(controller: BetterLiving2Controller) -> None:
        owner = id(controller._coordinator)
        selection.start(controller)
        if owner not in layouts or controller.wire != "P1" or controller.layout != layouts[owner]:
            raise ServiceValidationError(
                "BetterLiving2 owner changed during massage admission",
                translation_domain=DOMAIN,
                translation_key="betterliving2_massage_owner_changed",
            )
        controller._live()
        await controller.massage_pair(call.data["head"], call.data["feet"])

    await _execute_selection(
        targets, admissions, selection, "BetterLiving2 massage", execute, prepare
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "betterliving2_diagnostic_action",
        diagnostic_action,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("action"): vol.In(tuple(action.value for action in DiagnosticAction)),
                vol.Optional("timer"): vol.All(integer, vol.Range(min=-1, max=2)),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "betterliving2_massage",
        massage,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("head"): vol.All(integer, vol.Range(min=0, max=3)),
                vol.Required("feet"): vol.All(integer, vol.Range(min=0, max=3)),
                **SIDE_FIELD,
            }
        ),
    )
