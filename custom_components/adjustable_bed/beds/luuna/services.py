"""Live Luuna capability admission through the physical receiver's query lane."""

from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...paired_coordinator import BedChild, PairedBedCoordinator
from ..base import BedController
from ..casper_base.protocol import Request
from .controller import LuunaController


async def async_handle_request(call: ServiceCall, request: Request) -> None:
    """Validate all selected live receivers before executing any user command."""
    from ...services import (
        _call_targets,
        _command_targets,
        _execute_preflighted,
        _family_command,
    )

    targets = _call_targets(call)
    for parent, side in targets:
        for target in _command_targets(parent, side):

            async def query(controller: BedController) -> bool:
                if not isinstance(controller, LuunaController):
                    raise ServiceValidationError("Select a Luuna + product for this action")
                try:
                    await controller.async_prepare_request(request)
                except ValueError as error:
                    raise ServiceValidationError(str(error)) from error
                return True

            async def inspect(child: BedChild) -> None:
                if not await child.async_execute_controller_query(query, cancel_running=False):
                    raise ServiceValidationError("Luuna capability preflight was interrupted")

            if isinstance(parent, PairedBedCoordinator):
                child_side = next(key for key, child in parent.children.items() if child is target)
                await parent.async_run_child_operation(
                    "Luuna live preflight",
                    inspect,
                    side=child_side,
                    cancel_running=False,
                )
            else:
                await inspect(target)

    # Queries release their idle/paired links normally. Execution revalidates
    # the live announcement if a sequential pair or idle handoff reconnects.
    await _execute_preflighted(
        targets,
        [],
        _family_command(
            LuunaController,
            "Luuna + controls",
            lambda controller: controller.async_execute_casper_base_request(request),
        ),
    )
