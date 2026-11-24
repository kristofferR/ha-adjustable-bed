"""Native settings and confirmed maintenance actions for SleepIQ."""

from collections.abc import Mapping

from ..base import BedController, controller_as
from ..entity_specs import MotorCommandCallable
from .commands import SleepNumberActions


def action(command: str, parameters: Mapping[str, object]) -> MotorCommandCallable:
    async def execute(controller: BedController) -> None:
        actions = controller_as(controller, SleepNumberActions)
        if actions is None:
            raise ValueError("Sleep Number action is not supported by this controller")
        await actions.async_execute_sleep_number_command(command, parameters)

    return execute

