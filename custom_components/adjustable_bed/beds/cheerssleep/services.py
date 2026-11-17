"""CheersSleep's direct bed and conditional exported-screen actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules

OPERATIONS = (
    "query",
    "query_shared",
    "position_light_toggle",
    "color_light_toggle",
    "massage_head",
    "massage_foot",
    "massage_mode",
    "sonic_back",
    "sonic_foot",
    "sonic_toggle",
    "sonic_mode_1",
    "sonic_mode_2",
    "sonic_switch",
    "sonic_increase",
    "sonic_decrease",
    "sonic_level",
    "rgb_preview",
    "rgb2_preview",
    "rgb_commit",
    "rgb2_commit",
    "snore_setting",
    "out_of_bed_setting",
    "yb_massage",
    "seven_motion",
    "ten_motion",
    "ten_recall",
    "ten_save",
    "newten_motion",
    "newten_recall",
    "newten_save",
)


async def handle_request(call: ServiceCall) -> None:
    from ...services import (
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _preflight_and_execute,
    )

    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    physical = [
        (child.capability_controller, getattr(child.capability_controller, "_link", None))
        for parent, side in targets
        for child in _command_targets(parent, side)
    ]
    # STOP/pair/physical generations are captured before even lazy imports await.
    await async_import_modules(call.hass, "beds.cheerssleep.controller")
    from .controller import CheersSleepController, Request

    rgb = call.data["rgb"]
    request = Request(
        call.data["operation"],
        call.data["value"],
        (rgb[0], rgb[1], rgb[2]),
        call.data["brightness"],
        call.data["duration_ms"],
        call.data["axis"],
        call.data["up"],
        call.data["position"],
        call.data.get("sleeper"),
    )

    def validate(controller: CheersSleepController) -> None:
        for previous, link in physical:
            if (
                link is not None
                and previous is not None
                and previous._coordinator is controller._coordinator
            ):
                if previous is not controller or controller._link is not link:
                    raise ServiceValidationError(
                        "CheersSleep physical link changed during admission"
                    )
        controller.validate_request(request)

    executed: set[int] = set()

    async def execute(controller: CheersSleepController) -> None:
        validate(controller)
        # Both child lanes share the color light on one physical receiver.
        receiver = id(controller._coordinator)
        if request.operation == "color_light_toggle" and receiver in executed:
            return
        await controller.execute_request(request)
        executed.add(receiver)

    await _preflight_and_execute(
        targets,
        CheersSleepController,
        "CheersSleep bed controls",
        execute,
        validate=validate,
        cancel_running=True,
        resource=None,
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD

    hass.services.async_register(
        DOMAIN,
        "cheerssleep",
        handle_request,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("operation"): vol.In(OPERATIONS),
                vol.Optional("value", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=120)
                ),
                vol.Optional("rgb", default=[255, 255, 255]): vol.All(
                    [vol.All(vol.Coerce(int), vol.Range(min=0, max=255))], vol.Length(min=3, max=3)
                ),
                vol.Optional("brightness", default=255): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=255)
                ),
                vol.Optional("duration_ms", default=1000): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=30000)
                ),
                vol.Optional("axis", default="all"): vol.In(("all", "back", "legs", "lumbar")),
                vol.Optional("up", default=True): cv.boolean,
                vol.Optional("position", default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=4)
                ),
                vol.Optional("sleeper"): vol.In(("left", "right")),
                **SIDE_FIELD,
            }
        ),
    )
