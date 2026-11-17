"""Bed-local alarms with all-target admission captured before the first await."""

from __future__ import annotations

from typing import TypedDict

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _preflight_and_execute,
)


class AlarmFields(TypedDict):
    enabled: bool
    hour: int
    minute: int
    repeat: int
    kind: int


def _integer(value: object) -> int:
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as error:
            raise vol.Invalid("Expected an integer") from error
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid("Expected an integer")
    return value


async def handle_alarm(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.ore_ultramatic.controller")
    from ...profiles import ore_ultramatic as app
    from .controller import OreUltramaticController

    time = call.data["time"]
    if time.second or time.microsecond:
        raise ServiceValidationError("Ultramatic alarms use minute precision")
    fields: AlarmFields = {
        "enabled": call.data["enabled"],
        "hour": time.hour,
        "minute": time.minute,
        "repeat": call.data["repeat"],
        "kind": call.data["alarm_type"],
    }

    def validate(controller: OreUltramaticController) -> None:
        if controller._route is None:
            raise ValueError("Connect ORE Ultramatic once to discover its bed route")
        app.alarm(controller._route, dt_util.now(), **fields)

    async def execute(controller: OreUltramaticController) -> None:
        validate(controller)
        await controller.set_alarm(**fields)

    await _preflight_and_execute(
        targets,
        OreUltramaticController,
        "ORE Ultramatic bed alarms",
        execute,
        validate=validate,
        admit=True,
        resource="*",
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "ore_ultramatic_set_alarm",
        handle_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Required("time"): cv.time,
                vol.Optional("repeat", default=0): vol.All(_integer, vol.Range(min=-128, max=255)),
                vol.Optional("alarm_type", default=0): vol.All(_integer, vol.In((0, 1, 2, 3))),
                **SIDE_FIELD,
            }
        ),
    )
