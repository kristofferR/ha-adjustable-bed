"""Layout-owned actions, with STOP admission captured before lazy imports."""

import asyncio
from contextlib import ExitStack

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
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
    _execute_preflighted,
    _family_command,
    _require_hold_topology,
    _Selection,
)
from ..base import BedController

FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("action"): cv.string,
    vol.Optional("keep", default=False): cv.boolean,
    vol.Optional("mode"): vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
    vol.Optional("confirm", default=False): cv.boolean,
    vol.Optional("long_press", default=False): cv.boolean,
    vol.Optional("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
    vol.Optional("aroma_times"): vol.All(
        vol.ExactSequence((cv.positive_int, cv.positive_int, cv.positive_int)), vol.Coerce(tuple)
    ),
    vol.Optional("duration_ms", default=1000): vol.All(
        cv.positive_int, vol.Range(min=1, max=60000)
    ),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_jerome(call: ServiceCall) -> None:
    caller = asyncio.current_task()
    targets = _call_targets(call)
    selection = _Selection.capture(targets)
    utility = call.data["action"] in ("light_color", "aroma_settings")
    resource = "configuration" if utility else "movement"
    admissions = [
        _capture_command_admission(coordinator, side, (resource,)) for coordinator, side in targets
    ]
    keep = call.data["keep"]
    if keep:
        _require_hold_topology(targets)
    await async_import_modules(call.hass, "beds.richmat_classic.jerome")
    from .jerome import JeromeController

    def require_batch(*, preparing: bool = False) -> None:
        selection.require_unchanged(call)
        if (
            selection.stopped()
            or preparing
            and any(
                _capture_command_admission(parent, side, (resource,)) != expected
                for (parent, side), expected in zip(targets, admissions, strict=True)
            )
        ):
            raise invalid("action_stopped")

    def validate(controller: JeromeController) -> None:
        if utility:
            controller.validate_utility(
                call.data["action"], call.data.get("rgb_color"), call.data.get("aroma_times")
            )
            return
        controller.validate_action(
            call.data["action"],
            keep=keep,
            mode=call.data.get("mode"),
            confirm=call.data["confirm"],
            long_press=call.data["long_press"],
        )

    async def execute(controller: JeromeController) -> None:
        require_batch()
        if utility:
            if call.data["action"] == "light_color":
                await controller.set_light_color(call.data["rgb_color"])
            else:
                await controller.configure_aroma(call.data["aroma_times"])
            return
        if keep:
            _require_hold_topology(targets)
        await controller.press(
            call.data["action"],
            keep=keep,
            mode=call.data.get("mode"),
            confirm=call.data["confirm"],
            duration_ms=call.data["duration_ms"],
            long_press=call.data["long_press"],
        )

    # Preserve inspected links through the batch, except where the native
    # topology deliberately permits only one physical connection at a time.
    with ExitStack() as connections:
        held: set[int] = set()
        preflighted = []
        for parent, side in targets:
            if isinstance(parent, PairedBedCoordinator) and parent.connection_mode == "sequential":
                continue
            for child in _command_targets(parent, side):
                physical = child.inner if isinstance(child, SingleAddressSideCoordinator) else child
                if id(physical) not in held:
                    held.add(id(physical))
                    connections.enter_context(physical.hold_command_connection())

        # A rejected parameter is a query result, not a failed paired command:
        # rejecting it must not cancel movement or send an unsolicited STOP.
        for (parent, side), admission in zip(targets, admissions, strict=True):
            for child in _command_targets(parent, side):
                require_batch(preparing=True)
                results: list[bool | ValueError | ServiceValidationError] = []

                async def query(
                    controller: BedController,
                ) -> bool | ValueError | ServiceValidationError:
                    if not isinstance(controller, JeromeController):
                        return invalid("action_for_other_beds", beds="Jerome's power base")
                    try:
                        require_batch(preparing=True)
                        validate(controller)
                    except (ValueError, ServiceValidationError) as error:
                        return error
                    return True

                async def inspect(
                    target: BedChild,
                    results: list[bool | ValueError | ServiceValidationError] = results,
                ) -> None:
                    try:
                        result = await target.async_execute_controller_query(
                            query, cancel_running=False
                        )
                    except asyncio.CancelledError:
                        if not (caller is not None and caller.cancelling()) and selection.stopped():
                            results.append(invalid("action_stopped"))
                            return
                        raise
                    if result is not None:
                        results.append(result)

                if isinstance(parent, PairedBedCoordinator):
                    child_side = next(
                        key for key, value in parent.children.items() if value is child
                    )
                    await parent.async_inspect_child_operation(
                        inspect,
                        side=child_side,
                        resource=resource,
                        expected_pair_generations=admission.expected_pair_generations,
                        expected_stop_epochs=admission.expected_stop_epochs,
                    )
                else:
                    await inspect(child)
                preflighted.append((parent, child))
                if not results or results[0] is not True:
                    if results and isinstance(results[0], (ValueError, ServiceValidationError)):
                        raise results[0]
                    raise invalid("action_stopped")

        require_batch(preparing=True)
        # Cached entity shapes are not revalidated as live permission here.
        # Execution reconnects via the native topology when necessary, and
        # each controller action checks that new session's proof before writing.
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(JeromeController, "Layout bed actions", execute),
            cancel_running=not utility,
            resource=resource,
            admissions=admissions,
        )


def async_register_jerome_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "jerome_bed", handle_jerome, schema=vol.Schema(FIELDS))
