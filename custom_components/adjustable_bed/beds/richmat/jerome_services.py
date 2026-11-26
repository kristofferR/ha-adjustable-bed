"""Manage the reported repeat-alarm records on Jerome's SH models."""

from contextlib import ExitStack
from typing import Final

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN, PAIR_CONNECTION_MODE_SEQUENTIAL
from ...errors import failed, invalid
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _child_side,
    _execute_preflighted,
    _execute_sided_translated,
    _family_command,
    _preflight_capability,
    _release_preflighted,
    _Selection,
    _whole_number,
)

SERVICE: Final = "jerome_repeat_alarm"


async def handle_repeat_alarm(call: ServiceCall) -> None:
    targets = _call_targets(call)
    selection = _Selection.capture(targets)
    admissions = [
        _capture_command_admission(parent, side, ("configuration",)) for parent, side in targets
    ]
    operation = call.data["operation"]
    slot = call.data.get("slot")
    if (operation == "list") != (slot is None):
        raise invalid("jerome_repeat_alarm_slot")

    sequential = (
        [i for i, mode in enumerate(selection.modes) if mode == PAIR_CONNECTION_MODE_SEQUENTIAL]
        if operation != "list"
        else []
    )
    if any(len(selection.children[index]) > 1 for index in sequential):
        raise invalid("jerome_alarm_needs_two_links")
    if len(sequential) > 1:
        raise invalid("jerome_alarm_needs_separate_calls")
    checks = [
        (
            parent,
            child_side,
            child,
            _capture_command_admission(parent, child_side, ("configuration",)),
        )
        for index, ((parent, side), group) in enumerate(
            zip(targets, selection.children, strict=True)
        )
        if index not in sequential
        for child in group
        for child_side in (_child_side(parent, side, child),)
    ]

    await async_import_modules(call.hass, "beds.richmat.jerome_adjustable_base")
    from .jerome_adjustable_base import JeromeAdjustableBaseController, PreparedRepeatAlarm

    preflighted = await _preflight_capability(
        targets, JeromeAdjustableBaseController, lambda controller: controller.profile.split_head
    )
    prepared: dict[JeromeAdjustableBaseController, PreparedRepeatAlarm] = {}
    started: set[JeromeAdjustableBaseController] = set()
    delivered: set[JeromeAdjustableBaseController] = set()

    async def prepare(controller: JeromeAdjustableBaseController) -> None:
        if not controller.profile.split_head:
            raise invalid("bed_changed")
        prepared[controller] = await controller.prepare_repeat_alarm(operation, slot)

    def ready() -> bool:
        selection.require_unchanged(call)
        if selection.stopped():
            return False
        if any(
            (controller := child.controller) not in started
            and (
                not isinstance(controller, JeromeAdjustableBaseController)
                or (plan := prepared.get(controller)) is None
                or not controller.repeat_alarm_plan_is_current(plan)
            )
            for _, _, child, _ in checks
        ):
            raise invalid("bed_changed")
        return True

    async def dispatch(
        controller: JeromeAdjustableBaseController, plan: PreparedRepeatAlarm
    ) -> None:
        def admit_write() -> bool:
            if not ready():
                return False
            started.add(controller)
            return True

        await controller.execute_repeat_alarm(
            plan, admit_write=admit_write, on_delivery=lambda: delivered.add(controller)
        )

    async def execute(controller: JeromeAdjustableBaseController) -> None:
        plan = prepared.get(controller)
        if plan is None:
            raise invalid("bed_changed")
        await dispatch(controller, plan)

    async def execute_sequential(controller: JeromeAdjustableBaseController) -> None:
        if not ready():
            return
        await prepare(controller)
        await dispatch(controller, prepared[controller])

    try:
        if operation == "list":
            # Listing never mutates the bed, so it also works across a sequential pair.
            async def list_records(controller: JeromeAdjustableBaseController) -> None:
                await prepare(controller)
                await controller.execute_repeat_alarm(prepared[controller])

            await _execute_preflighted(
                targets,
                preflighted,
                _family_command(JeromeAdjustableBaseController, list_records),
                admissions=admissions,
            )
            return

        with ExitStack() as held:
            for _, _, child, _ in checks:
                held.enter_context(child.hold_command_connection())
            for parent, side, _child, admission in checks:
                selection.require_unchanged(call)
                if selection.stopped():
                    return
                await _execute_sided_translated(
                    parent,
                    side,
                    _family_command(JeromeAdjustableBaseController, prepare),
                    resource="configuration",
                    cancel_running=False,
                    admission=admission,
                )
            if not ready():
                return
            # A sequential cycle releases its link when the callback ends.
            # Validate the other receivers first, then check and write the
            # sequential receiver within one cycle.
            if sequential:
                index = sequential[0]
                parent, side = targets[index]
                await _execute_sided_translated(
                    parent,
                    side,
                    _family_command(JeromeAdjustableBaseController, execute_sequential),
                    resource="configuration",
                    cancel_running=False,
                    admission=admissions[index],
                )
            if not sequential or delivered:
                for index, ((parent, side), admission) in enumerate(
                    zip(targets, admissions, strict=True)
                ):
                    if index not in sequential and ready():
                        await _execute_sided_translated(
                            parent,
                            side,
                            _family_command(JeromeAdjustableBaseController, execute),
                            resource="configuration",
                            cancel_running=False,
                            admission=admission,
                        )
            if started and len(delivered) != len(checks) + len(sequential):
                raise failed("action_stopped")
    finally:
        await _release_preflighted(preflighted)


def async_register_jerome_repeat_alarm(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        SERVICE,
        handle_repeat_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("operation"): vol.In(("list", "enable", "delete")),
                vol.Optional("slot"): vol.All(_whole_number, vol.Range(min=1, max=7)),
                **SIDE_FIELD,
            }
        ),
    )
