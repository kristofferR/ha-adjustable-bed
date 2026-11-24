"""Automation actions for Sinca wake alarm, anti-snore and local history."""

from typing import Final

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _preflight_and_execute,
)

ACTIONS: Final = (
    "refresh_settings",
    "refresh_alarm",
    "disable_alarm",
    "anti_snore",
    "demo_anti_snore",
    "consume_history",
)
POSITIONS: Final = {"head": 1, "elevation": 2}
LEVELS: Final = {"low": 1, "medium": 3, "high": 6}


async def handle_command(call: ServiceCall) -> ServiceResponse:
    action = call.data["action"]
    targets = _call_targets(call)
    if action == "consume_history" and sum(len(_command_targets(p, s)) for p, s in targets) != 1:
        raise invalid("one_bed_only")
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.sinca_comfort.controller")
    from .controller import SincaComfortController

    result: ServiceResponse = {}

    def validate(controller: SincaComfortController) -> None:
        if action in ("anti_snore", "demo_anti_snore"):
            controller.require_sleep()

    async def execute(controller: SincaComfortController) -> None:
        validate(controller)
        match action:
            case "refresh_settings":
                await controller.settings_refresh()
            case "refresh_alarm":
                await controller.alarm_refresh()
            case "disable_alarm":
                await controller.disable_alarm()
            case "anti_snore" | "demo_anti_snore":
                await controller.set_anti_snore(
                    call.data["enabled"],
                    POSITIONS[call.data["position"]],
                    LEVELS[call.data["level"]],
                    demo=action == "demo_anti_snore",
                )
            case "consume_history":
                acknowledged, count = await controller.consume_history(
                    all_records=call.data["all_records"], confirmed=call.data["confirmed"]
                )
                result.update(acknowledged=acknowledged, records=count)

    await _preflight_and_execute(
        targets,
        SincaComfortController,
        execute,
        validate=validate,
        resource="*",
        admit=True,
        admissions=admissions,
    )
    return result


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "sinca_comfort_command",
        handle_command,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(ACTIONS),
                vol.Optional("enabled", default=True): bool,
                vol.Optional("position", default="head"): vol.In(POSITIONS),
                vol.Optional("level", default="low"): vol.In(LEVELS),
                vol.Optional("all_records", default=False): bool,
                vol.Optional("confirmed", default=False): bool,
                **SIDE_FIELD,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
