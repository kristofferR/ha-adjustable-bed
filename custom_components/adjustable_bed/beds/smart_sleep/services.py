"""Smart Sleep alarm action, with whole-selection admission before any writes."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

    async def set_alarm(call: ServiceCall) -> None:
        await async_import_modules(hass, "beds.smart_sleep.controller")
        from .controller import SmartSleepController

        enabled, time = call.data["enabled"], call.data.get("time")
        if enabled and time is None:
            raise ServiceValidationError("Choose a Smart Sleep alarm time")
        if time is not None and (time.second or time.microsecond):
            raise ServiceValidationError("Smart Sleep alarms use minute precision")
        args = {
            "enabled": enabled,
            "weekdays": tuple(call.data["weekdays"]),
            "hour": time.hour if time else 0,
            "minute": time.minute if time else 0,
            "preset": call.data["action"],
            "flexible": call.data["flexible_wake"],
            "week_mask": call.data.get("week_mask"),
        }

        def validate(ctrl: SmartSleepController) -> None:
            ctrl.alarm_frame(**args)

        async def execute(ctrl: SmartSleepController) -> None:
            await ctrl.configure_clock_alarm(**args)

        await _preflight_and_execute(
            _call_targets(call),
            SmartSleepController,
            "OKIN Smart Sleep alarms",
            execute,
            validate=validate,
            cancel_running=True,
            resource=None,
        )

    hass.services.async_register(
        DOMAIN,
        "smart_sleep_set_alarm",
        set_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("weekdays", default=[]): [
                    vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
                ],
                vol.Optional("week_mask"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
                vol.Optional("action", default="memory_1"): cv.string,
                vol.Optional("flexible_wake", default=False): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
