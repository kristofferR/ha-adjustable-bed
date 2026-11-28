"""Finite Thrive Sleep controls with all-target live preflight before writes."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...const import DOMAIN
from ...errors import invalid, rejected
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild, PairedBedCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _release_preflighted,
    _Selection,
    _whole_number,
)
from ..base import BedController

if TYPE_CHECKING:
    from .controller import ThriveSleepController


@dataclass(frozen=True, slots=True)
class Request:
    operation: Literal["light_rgb", "delete_alarm", "query_alarms", "query_snore"]
    rgb: tuple[int, int, int] = (255, 255, 255)
    alarm_id: int = 1


def validate(controller: ThriveSleepController, request: Request) -> None:
    controller._live()
    if request.operation == "light_rgb":
        controller.validate_light()
        if len(request.rgb) != 3 or any(
            type(c) is not int or not 0 <= c <= 255 for c in request.rgb
        ):
            raise ValueError("Supply three RGB bytes")
    elif request.operation in ("query_alarms", "delete_alarm"):
        if (
            "clock" not in controller.features
            or type(request.alarm_id) is not int
            or not 1 <= request.alarm_id <= 7
        ):
            raise ValueError("Choose an app alarm ID 1 to 7 on an alarm-capable bed")
    elif request.operation == "query_snore":
        if controller.profile.key != "level5" or not controller.sleep_name:
            raise ValueError("Level 5 anti-snore requires a returned sleep device name")
    else:
        raise ValueError("Unsupported Thrive Sleep action")


async def execute(controller: ThriveSleepController, request: Request) -> None:
    validate(controller, request)
    match request.operation:
        case "light_rgb":
            await controller.light_rgb(request.rgb)
        case "delete_alarm":
            await controller.delete_alarm(request.alarm_id)
        case "query_alarms":
            await controller.query_alarms()
        case "query_snore":
            controller._snore_requested = False
            await controller.read_positions()


async def handle(call: ServiceCall) -> None:
    data = call.data
    request = Request(data["operation"], tuple(data["rgb_color"]), data["alarm_id"])
    targets = _call_targets(call)
    selection = _Selection.capture(targets)
    admissions = [
        _capture_command_admission(parent, side, ("configuration",)) for parent, side in targets
    ]
    await async_import_modules(call.hass, "beds.thrivesleep.controller")
    from .controller import ThriveSleepController

    def require_batch() -> None:
        selection.require_unchanged(call)
        if selection.stopped():
            raise invalid("action_stopped")

    async def write(controller: ThriveSleepController) -> None:
        require_batch()
        await execute(controller, request)

    preflighted = []
    try:
        with ExitStack() as connections:
            held: set[int] = set()
            for parent, side in targets:
                if (
                    isinstance(parent, PairedBedCoordinator)
                    and parent.connection_mode == "sequential"
                ):
                    continue
                for child in _command_targets(parent, side):
                    if id(child) not in held:
                        held.add(id(child))
                        connections.enter_context(child.hold_command_connection())
            for (parent, side), admission in zip(targets, admissions, strict=True):
                for child in _command_targets(parent, side):
                    require_batch()
                    results: list[bool | ValueError | ServiceValidationError] = []

                    async def query(
                        controller: BedController,
                    ) -> bool | ValueError | ServiceValidationError:
                        if not isinstance(controller, ThriveSleepController):
                            return ValueError("Choose a Thrive Sleep bed")
                        try:
                            require_batch()
                            validate(controller, request)
                        except (ValueError, ServiceValidationError) as error:
                            return error
                        return True

                    async def inspect(
                        target: BedChild,
                        results: list[bool | ValueError | ServiceValidationError] = results,
                    ) -> None:
                        result = await target.async_execute_controller_query(
                            query, cancel_running=False
                        )
                        if result is not None:
                            results.append(result)

                    if isinstance(parent, PairedBedCoordinator):
                        child_side = next(
                            key for key, value in parent.children.items() if value is child
                        )
                        await parent.async_inspect_child_operation(
                            inspect,
                            side=child_side,
                            resource="configuration",
                            expected_pair_generations=admission.expected_pair_generations,
                            expected_stop_epochs=admission.expected_stop_epochs,
                        )
                    else:
                        await inspect(child)
                    preflighted.append((parent, child))
                    if not results or results[0] is not True:
                        if results and isinstance(results[0], ServiceValidationError):
                            raise results[0]
                        if results and isinstance(results[0], ValueError):
                            raise rejected(results[0])
                        raise invalid("action_stopped")
            require_batch()
            await _execute_preflighted(
                targets,
                preflighted,
                _family_command(ThriveSleepController, write),
                resource="configuration",
                admissions=admissions,
            )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def register_services(hass: HomeAssistant) -> None:
    byte = vol.All(_whole_number, vol.Range(min=0, max=255))
    hass.services.async_register(
        DOMAIN,
        "thrivesleep",
        handle,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("operation"): vol.In(
                    ("light_rgb", "delete_alarm", "query_alarms", "query_snore")
                ),
                vol.Optional("rgb_color", default=[255, 255, 255]): vol.ExactSequence((byte,) * 3),
                vol.Optional("alarm_id", default=1): vol.All(
                    _whole_number, vol.Range(min=1, max=7)
                ),
                **SIDE_FIELD,
            }
        ),
    )
