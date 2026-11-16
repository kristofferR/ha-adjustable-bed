"""Sophie bed alarm programming, with all-target admission before lazy imports."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.sophie import ALARM_MODES


async def handle_sophie_set_alarm(call: ServiceCall) -> None:
    from ...services import (
        SOLACE_WEEKDAY_OPTIONS,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    targets = _call_targets(call)
    admissions = [
        _capture_command_admission(parent, side, ("configuration",)) for parent, side in targets
    ]
    await async_import_modules(call.hass, "beds.solace.sophie")
    from .sophie import SophieController

    time = call.data["time"]
    if time.second or time.microsecond:
        raise ServiceValidationError("Sophie alarms use minute precision")
    days = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) + 1 for day in call.data["weekdays"])
    mode, massage = call.data["mode"], call.data["massage"]

    async def program(controller: SophieController) -> None:
        await controller.set_alarm(
            enabled=call.data["enabled"],
            hour=time.hour,
            minute=time.minute,
            weekdays=days,
            mode=mode,
            massage=massage,
            ring=call.data["ring"],
        )

    await _preflight_and_execute(
        targets,
        SophieController,
        "Sophie alarm",
        program,
        validate=lambda controller: controller.validate_alarm(mode, massage),
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD, SOLACE_WEEKDAY_OPTIONS

    hass.services.async_register(
        DOMAIN,
        "sophie_set_alarm",
        handle_sophie_set_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time", default="00:00:00"): cv.time,
                vol.Optional("weekdays", default=[]): vol.All(
                    cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]
                ),
                vol.Optional("mode", default="no_action"): vol.In(tuple(ALARM_MODES)),
                vol.Optional("massage", default=False): cv.boolean,
                vol.Optional("ring", default=False): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
