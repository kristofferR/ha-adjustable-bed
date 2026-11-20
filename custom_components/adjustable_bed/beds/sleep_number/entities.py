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


async def automatic_light(controller: BedController, enabled: bool) -> None:
    actions = controller_as(controller, SleepNumberActions)
    if actions is None:
        raise ValueError("Automatic lighting is not supported by this controller")
    state = await actions.async_execute_sleep_number_command(
        "get_underbed_light_auto_mode_status", {}
    )
    await actions.async_execute_sleep_number_command(
        "set_underbed_light_auto_mode",
        {
            "underbed_light_auto_mode_enable_status": "true" if enabled else "false",
            "underbed_light_auto_mode_intensity_level": state[
                "underbed_light_auto_mode_intensity_level"
            ],
        },
    )
