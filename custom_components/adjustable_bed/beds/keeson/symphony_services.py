"""Symphony Sleep's single daily bed alarm, with all-target admission."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles import symphony_sleep as app
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute


async def handle_set_alarm(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.keeson.symphony_sleep")
    from .symphony_sleep import SymphonySleepController

    enabled = call.data["enabled"]
    time = call.data.get("time")
    if enabled and time is None:
        raise ServiceValidationError("Choose a Symphony Sleep alarm time")
    if time is not None and (time.second or time.microsecond):
        raise ServiceValidationError("Symphony Sleep alarms use minute precision")
    hour, minute = (time.hour, time.minute) if time else (0, 0)
    wake = call.data["wake_mode"]

    def validate(controller: SymphonySleepController) -> None:
        app.alarm(controller.route, enabled=enabled, hour=hour, minute=minute, wake=wake)
        controller.validate_clock_sync()

    async def configure(controller: SymphonySleepController) -> None:
        await controller.configure_clock_alarm(enabled=enabled, weekdays=(), hour=hour,
                                                minute=minute, preset=wake)

    await _preflight_and_execute(
        _call_targets(call), SymphonySleepController, "Symphony Sleep bed alarms", configure,
        validate=validate, cancel_running=True, resource=None, admit=True,
    )


def register_symphony_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "symphony_set_alarm", handle_set_alarm, schema=vol.Schema({
        vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
        vol.Required("enabled"): cv.boolean,
        vol.Optional("time"): cv.time,
        vol.Optional("wake_mode", default="none"): vol.In(tuple(app.WAKE)),
        **SIDE_FIELD,
    }))
