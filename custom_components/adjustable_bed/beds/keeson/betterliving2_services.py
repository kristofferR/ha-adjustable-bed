"""BetterLiving2 actions with pre-await physical-owner/STOP admission."""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    BedTarget,
    _call_targets,
    _capture_command_admission,
    _CommandAdmission,
    _preflight_and_execute,
)
from .betterliving2_selection import Selection

if TYPE_CHECKING:
    from .betterliving2 import BetterLiving2Controller


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
        from .betterliving2 import BetterLiving2Controller

        if selection.stopped_before_preflight():
            return

        def prepare(controller: BetterLiving2Controller) -> None:
            selection.check()
            validate_diagnostic_action(controller, action, timer)

        async def execute(controller: BetterLiving2Controller) -> None:
            selection.start(controller)
            await execute_diagnostic_action(controller, action, timer)

        await _preflight_and_execute(
            targets,
            BetterLiving2Controller,
            "bed diagnostic action",
            execute,
            validate=prepare,
            cancel_running=True,
            resource=None,
            admissions=admissions,
        )


def integer(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is float and value.is_integer():
        return int(value)
    raise vol.Invalid("Expected an integer")


def weekday(value: object) -> int:
    if isinstance(value, str) and value in tuple(str(day) for day in range(7)):
        return int(value)
    return integer(value)


async def set_alarm(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    selection = Selection(targets, admissions)
    with selection.scope():
        await _set_alarm(call, targets, admissions, selection)


async def _set_alarm(
    call: ServiceCall,
    targets: list[tuple[BedTarget, str]],
    admissions: list[_CommandAdmission],
    selection: Selection,
) -> None:
    await async_import_modules(call.hass, "beds.keeson.betterliving2")
    from .betterliving2 import AlarmPlan, BetterLiving2Controller

    if selection.stopped_before_preflight():
        return
    selected_time = call.data["time"]
    if selected_time.second or selected_time.microsecond:
        raise ServiceValidationError("BetterLiving2 alarms use minute precision")
    plans: dict[int, AlarmPlan] = {}

    def prepare(controller: BetterLiving2Controller) -> None:
        selection.check()
        plan = controller.prepare_alarm(
            enabled=call.data["enabled"],
            hour=selected_time.hour,
            minute=selected_time.minute,
            weekdays=frozenset(call.data["weekdays"]),
            action=call.data["action"],
        )
        plans[id(controller._coordinator)] = plan

    async def execute(controller: BetterLiving2Controller) -> None:
        owner = id(controller._coordinator)
        if owner not in plans:
            raise ServiceValidationError("BetterLiving2 owner changed during alarm admission")
        selection.start(controller)
        # Rebind only after the app cohort has witnessed the native, owned
        # sequential release/connect (or its own initially-offline connection).
        await controller.set_alarm(replace(plans[owner], link=controller._live()))

    await _preflight_and_execute(
        targets,
        BetterLiving2Controller,
        "BetterLiving2 alarms",
        execute,
        validate=prepare,
        cancel_running=True,
        resource=None,
        admissions=admissions,
    )


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
    from .betterliving2 import BetterLiving2Controller

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
            raise ServiceValidationError("BetterLiving2 owner changed during massage admission")
        controller._live()
        await controller.massage_pair(call.data["head"], call.data["feet"])

    await _preflight_and_execute(
        targets,
        BetterLiving2Controller,
        "BetterLiving2 massage",
        execute,
        validate=prepare,
        cancel_running=True,
        resource=None,
        admissions=admissions,
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
        "betterliving2_set_alarm",
        set_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Required("time"): cv.time,
                vol.Optional("weekdays", default=[]): [vol.All(weekday, vol.Range(min=0, max=6))],
                vol.Optional("action", default="massage"): vol.In(
                    ("memory_1", "memory_2", "massage")
                ),
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
