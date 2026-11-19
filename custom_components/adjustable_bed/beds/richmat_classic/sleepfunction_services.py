"""Native admission for SleepFunction's local bed settings."""

import asyncio
from contextlib import ExitStack
from typing import Literal, cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild, PairedBedCoordinator, SingleAddressSideCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _connection_generation,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)
from ..base import BedController
from .sleepfunction_settings import Settings
from .transport import Transport


def _fan_speed(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or value not in (0, 20, 40, 60, 80, 100)
    ):
        raise vol.Invalid("Expected a fan percentage in steps of 20")
    return int(value)


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(("head_fan", "foot_fan", "aroma")),
    vol.Optional("hours"): vol.All(cv.positive_int, vol.Range(max=6)),
    vol.Optional("speed"): _fan_speed,
    vol.Optional("mode_2_minutes"): vol.All(cv.positive_int, vol.Range(min=1, max=60)),
    vol.Optional("mode_3_minutes"): vol.All(cv.positive_int, vol.Range(min=1, max=60)),
    vol.Optional("pause_hours"): vol.All(cv.positive_int, vol.Range(min=1, max=12)),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_sleepfunction_settings(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(c, s, ("configuration",)) for c, s in targets]
    await async_import_modules(call.hass, "beds.richmat_classic.sleepfunction")
    from .sleepfunction import SleepFunctionController

    request = Settings(
        cast(Literal["head_fan", "foot_fan", "aroma"], call.data["operation"]),
        hours=call.data.get("hours"),
        speed=call.data.get("speed"),
        mode_2_minutes=call.data.get("mode_2_minutes"),
        mode_3_minutes=call.data.get("mode_3_minutes"),
        pause_hours=call.data.get("pause_hours"),
    )
    request.frames()
    physical = [(parent, side, tuple(_command_targets(parent, side))) for parent, side in targets]
    call_task = asyncio.current_task()
    checked: dict[BedChild, tuple[SleepFunctionController, Transport, object]] = {}
    sequential: dict[BedChild, PairedBedCoordinator] = {}
    with ExitStack() as connections:
        held: set[int] = set()
        for parent, _side, children in physical:
            for child in children:
                if (
                    isinstance(parent, PairedBedCoordinator)
                    and parent.connection_mode == "sequential"
                ):
                    sequential[child] = parent
                elif child.operation_identity not in held:
                    connections.enter_context(child.hold_command_connection())
                    held.add(child.operation_identity)
        preflighted = await _preflight_capability(
            targets, SleepFunctionController, "SleepFunction settings", None
        )
        try:
            for parent, _side, children in physical:
                for child in children:

                    async def query(controller: BedController, *, target=child) -> bool:
                        if not isinstance(controller, SleepFunctionController):
                            raise invalid("sleepfunction_control")
                        session = await controller.check_settings(request)
                        checked[target] = (controller, session, _connection_generation(target))
                        return True

                    async def inspect(target: BedChild) -> None:
                        if not await target.async_execute_controller_query(
                            query, cancel_running=False
                        ):
                            raise invalid("action_stopped")

                    preflighted.append((parent, child))
                    if isinstance(parent, PairedBedCoordinator):
                        child_side = next(
                            key for key, target in parent.children.items() if target is child
                        )
                        await parent.async_run_child_operation(
                            "SleepFunction settings preflight",
                            inspect,
                            side=child_side,
                            cancel_running=False,
                        )
                    else:
                        await inspect(child)
            if any(child not in checked for _, _, children in physical for child in children):
                raise invalid("action_stopped")
        except BaseException:
            await _release_preflighted(preflighted)
            raise

        async def apply(controller: SleepFunctionController) -> None:
            target = next(
                (child for child, proof in checked.items() if proof[0] is controller), None
            )
            if target is not None:
                session = checked[target][1]
            else:
                # Only this call's native one-link pair cycle may replace a
                # checked session. Other reconnects cannot adopt its proof.
                target = next(
                    (child for child in sequential if child.controller is controller), None
                )
                if target is None or isinstance(target, SingleAddressSideCoordinator):
                    raise invalid("bed_changed")
                parent = sequential[target]
                cycle = parent.sequential_cycle
                generation = checked[target][2]
                if (
                    cycle is None
                    or cycle.task is not call_task
                    or not parent.cycle_is_current(cycle)
                    or target.connection_creator_task is not cycle.task
                    or not isinstance(generation, int)
                    or _connection_generation(target) != generation + 1
                ):
                    raise invalid("bed_changed")
                session = await controller.check_settings(request)
            await controller.execute_settings(request, checked_session=session)

        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(SleepFunctionController, "SleepFunction settings", apply),
            cancel_running=False,
            resource="configuration",
            admissions=admissions,
        )


def async_register_sleepfunction_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, "sleepfunction_settings", handle_sleepfunction_settings, schema=vol.Schema(FIELDS)
    )
