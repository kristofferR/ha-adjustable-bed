"""BF and Cherish bed alarm action with all-target preflight."""

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
        from homeassistant.util import dt as dt_util

        await async_import_modules(call.hass, "beds.bf_cherish.controller")
        from .controller import BfCherishController, alarm_frame

        enabled = call.data["enabled"]
        time = call.data.get("time")
        if enabled and time is None:
            raise ServiceValidationError("Choose an alarm time")
        if time is not None and (time.second or time.microsecond):
            raise ServiceValidationError("BF and Cherish alarms use minute precision")
        hour, minute = (time.hour, time.minute) if time else (0, 0)
        memory = call.data["memory"]

        def validate(controller: BfCherishController) -> None:
            alarm_frame(
                controller.cherish,
                dt_util.now(),
                enabled=enabled,
                hour=hour,
                minute=minute,
                memory=memory,
            )

        async def program(controller: BfCherishController) -> None:
            await controller.configure_clock_alarm(
                enabled=enabled, hour=hour, minute=minute, preset=memory
            )

        await _preflight_and_execute(
            _call_targets(call),
            BfCherishController,
            "BF/Cherish alarms",
            program,
            supported=lambda controller: controller.supports_clock_alarm,
            validate=validate,
        )

    hass.services.async_register(
        DOMAIN,
        "bf_cherish_set_alarm",
        set_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("memory", default="none"): vol.In(("none", "memory_1", "memory_2")),
                **SIDE_FIELD,
            }
        ),
    )
