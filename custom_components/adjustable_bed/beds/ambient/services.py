"""Side-explicit M3 Ambient actions for complete position and heat targets."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...codec.ambient import Coordinates
from ...command_scheduler import ALL_COMMAND_RESOURCES
from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles import ambient as app
from ...services import (
    DEVICE_IDS,
    _call_targets,
    _capture_command_admission,
    _preflight_and_execute,
    _whole_number,
)


def _level(maximum: int) -> vol.All:
    return vol.All(_whole_number, vol.Range(min=0, max=maximum))


async def handle_position(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [
        _capture_command_admission(parent, side, ALL_COMMAND_RESOURCES) for parent, side in targets
    ]
    await async_import_modules(call.hass, "beds.ambient.controller")
    from .controller import AmbientController

    side = app.SIDES.get(call.data.get("position_side", ""))
    coordinates = Coordinates(call.data["head"], call.data["feet"], call.data["neck"])

    async def execute(controller: AmbientController) -> None:
        await controller.set_position(side, coordinates)

    await _preflight_and_execute(
        targets,
        AmbientController,
        execute,
        validate=lambda controller: controller.validate_position_side(side),
        resource=None,
        admissions=admissions,
    )


async def handle_heat(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [
        _capture_command_admission(parent, side, ALL_COMMAND_RESOURCES) for parent, side in targets
    ]
    timer = call.data.get("timer_hours")
    zones = {index: call.data[zone] for index, zone in enumerate(("shoulder", "torso", "legs"))}
    await async_import_modules(call.hass, "beds.ambient.controller")
    from .controller import AmbientController

    side = app.SIDES[call.data["heat_side"]]

    async def execute(controller: AmbientController) -> None:
        await controller.set_heat(side, zones, timer_hours=timer)

    await _preflight_and_execute(targets, AmbientController, execute, resource=None, admissions=admissions)


async def handle_rgb(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [
        _capture_command_admission(parent, side, ALL_COMMAND_RESOURCES) for parent, side in targets
    ]
    await async_import_modules(call.hass, "beds.ambient.controller")
    from .controller import AmbientController

    async def execute(controller: AmbientController) -> None:
        await controller.set_raw_rgb((call.data["red"], call.data["green"], call.data["blue"]))

    await _preflight_and_execute(targets, AmbientController, execute, resource=None, admissions=admissions)


def async_register_ambient_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "ambient_set_position",
        handle_position,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Optional("position_side"): vol.In(app.SIDES),
                **{vol.Required(axis): _level(limit) for axis, limit in app.AXIS_LIMITS.items()},
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "ambient_set_heat",
        handle_heat,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("heat_side"): vol.In(app.SIDES),
                **{
                    vol.Required(zone): _level(app.HEAT_LEVEL_MAX)
                    for zone in ("shoulder", "torso", "legs")
                },
                vol.Optional("timer_hours"): vol.All(
                    _whole_number, vol.In((app.HEAT_TIMER_HOURS,))
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "ambient_set_rgb",
        handle_rgb,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                **{vol.Required(channel): _level(255) for channel in ("red", "green", "blue")},
            }
        ),
    )
