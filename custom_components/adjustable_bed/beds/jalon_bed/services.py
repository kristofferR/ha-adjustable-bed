"""OkinComfortBed Ⅱ's bed-local weekly/next-occurrence wake alarm."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

    async def set_alarm(call: ServiceCall) -> None:
        await async_import_modules(call.hass, "beds.jalon_bed.controller")
        from .controller import JalonBedController, alarm_frame

        enabled, time = call.data["enabled"], call.data.get("time")
        if enabled and time is None:
            raise ServiceValidationError("Choose a Jalon alarm time")
        if time is not None and (time.second or time.microsecond):
            raise ServiceValidationError("Jalon alarms use minute precision")
        weekdays = tuple(call.data["weekdays"])
        hour, minute = (time.hour, time.minute) if time else (0, 0)
        preset = call.data["wake_mode"]

        def validate(controller: JalonBedController) -> None:
            alarm_frame(
                enabled=enabled,
                weekdays=weekdays,
                hour=hour,
                minute=minute,
                preset=preset,
                now=dt_util.now(),
            )

        async def program(controller: JalonBedController) -> None:
            await controller.configure_clock_alarm(
                enabled=enabled, weekdays=weekdays, hour=hour, minute=minute, preset=preset
            )

        await _preflight_and_execute(
            _call_targets(call),
            JalonBedController,
            "OkinComfortBed Ⅱ (Jalon) alarms",
            program,
            validate=validate,
            cancel_running=True,
            resource=None,
        )

    hass.services.async_register(
        DOMAIN,
        "jalon_set_alarm",
        set_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("weekdays", default=[]): [
                    vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
                ],
                vol.Optional("wake_mode", default="none"): vol.In(
                    ("none", "memory_1", "memory_2", "massage")
                ),
                **SIDE_FIELD,
            }
        ),
    )
