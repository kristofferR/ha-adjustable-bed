"""MLILY Remote's finite BED actions with STOP admission before lazy imports."""

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN, SIDE_BOTH, SIDE_LEFT, SIDE_RIGHT
from ...errors import invalid, rejected
from ...import_executor import async_import_modules
from ...paired_coordinator import SingleAddressPairedCoordinator
from ..casper_base.protocol import ALARM_MODES, Request


async def handle(call: ServiceCall) -> None:
    from ...services import _call_targets, _capture_command_admission

    targets = _call_targets(call)
    if call.data["operation"] == "anti_snore":
        for parent, side in targets:
            if isinstance(parent, SingleAddressPairedCoordinator) and side == SIDE_RIGHT:
                raise invalid("left_side_only")
        # This callback has no side operand. Bind parent/Both to its one physical
        # left owner before STOP admission, rather than fan it out to both children.
        targets = [
            (parent, SIDE_LEFT if isinstance(parent, SingleAddressPairedCoordinator) else side)
            for parent, side in targets
        ]
    else:
        # The countdown alarm belongs to the one receiver both sides share:
        # target the bed itself and run once, never once per side.
        for parent, side in targets:
            if isinstance(parent, SingleAddressPairedCoordinator) and side != SIDE_BOTH:
                raise invalid("whole_bed_only")
        targets = [
            (parent, SIDE_LEFT if isinstance(parent, SingleAddressPairedCoordinator) else side)
            for parent, side in targets
        ]
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.mlily_remote.controller")
    from .controller import MlilyRemoteController

    request = Request(
        call.data["operation"],
        hour=call.data["hour"],
        minute=call.data["minute"],
        mode=ALARM_MODES.get(call.data["mode"], ""),
    )
    from ...paired_coordinator import BedChild, PairedBedCoordinator
    from ...services import (
        _command_targets,
        _execute_preflighted,
        _family_command,
        _preflight_capability,
        _release_preflighted,
    )
    from ..base import BedController

    preflighted = await _preflight_capability(
        targets,
        MlilyRemoteController,
        "MLILY Remote",
        None,
        lambda controller: controller.validate_casper_base_request(request),
    )
    try:
        # No selected receiver changes its alarm until every receiver has passed
        # both the static product gate and this session's capability query.
        for parent, side in targets:
            for child in _command_targets(parent, side):

                async def query(controller: BedController) -> bool:
                    if not isinstance(controller, MlilyRemoteController):
                        raise invalid("bed_changed")
                    try:
                        await controller.async_prepare_request(request)
                    except ValueError as error:
                        raise rejected(error) from error
                    return True

                async def inspect(target: BedChild) -> None:
                    if not await target.async_execute_controller_query(query, cancel_running=False):
                        raise invalid("action_stopped")

                if isinstance(parent, PairedBedCoordinator):
                    child_side = next(
                        key for key, value in parent.children.items() if value is child
                    )
                    await parent.async_run_child_operation(
                        "MLILY Remote preflight",
                        inspect,
                        side=child_side,
                        cancel_running=False,
                    )
                else:
                    await inspect(child)
                preflighted.append((parent, child))
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(
                MlilyRemoteController,
                "MLILY Remote",
                lambda controller: controller.async_execute_casper_base_request(request),
            ),
            admissions=admissions,
            resource=None,
            cancel_running=True,
        )
    finally:
        await _release_preflighted(preflighted)


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD

    hass.services.async_register(
        DOMAIN,
        "mlily_remote",
        handle,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                **SIDE_FIELD,
                vol.Required("operation"): vol.In(("alarm", "alarm_cancel", "anti_snore")),
                vol.Optional("hour", default=6): vol.All(cv.positive_int, vol.Range(max=23)),
                vol.Optional("minute", default=30): vol.All(cv.positive_int, vol.Range(max=59)),
                vol.Optional("mode", default="zero_g"): vol.In(tuple(ALARM_MODES)),
            }
        ),
    )
