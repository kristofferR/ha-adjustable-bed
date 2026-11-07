"""Malouf app alarm action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .services import (
    ATTR_ENABLED,
    ATTR_PRESET,
    ATTR_TIME,
    ATTR_WEEKDAYS,
    DEVICE_IDS,
    SIDE_FIELD,
    SOLACE_WEEKDAY_OPTIONS,
    _call_targets,
    _preflight_and_execute,
)

SERVICE_MALOUF_SET_ALARM = "malouf_set_alarm"
MALOUF_ALARM_PRESETS = ("zero_g", "lounge", "tv", "anti_snore", "memory_1", "memory_2")


async def handle_malouf_set_alarm(call: ServiceCall) -> None:
    """Set or clear the app profile's clock alarm through its command lock."""
    from .beds.malouf_app import MaloufAppController

    alarm_time = call.data[ATTR_TIME]
    if alarm_time.second or alarm_time.microsecond:
        raise ServiceValidationError("Malouf alarms use minute precision")
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])

    def validate_alarm(controller: MaloufAppController) -> None:
        if (
            call.data[ATTR_ENABLED]
            and call.data[ATTR_PRESET] not in controller.clock_alarm_preset_options
        ):
            raise ServiceValidationError("The selected alarm preset is unavailable on this model")

    async def program(controller: MaloufAppController) -> None:
        await controller.configure_clock_alarm(
            enabled=call.data[ATTR_ENABLED],
            weekdays=weekdays,
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            preset=call.data[ATTR_PRESET],
        )

    await _preflight_and_execute(
        _call_targets(call),
        MaloufAppController,
        "Malouf clock alarms",
        program,
        supported=lambda controller: controller.supports_clock_alarm,
        validate=validate_alarm,
    )


def async_register_malouf_app_services(hass: HomeAssistant) -> None:
    """Register the Malouf app alarm action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_MALOUF_SET_ALARM,
        handle_malouf_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]
                ),
                vol.Optional(ATTR_PRESET, default="zero_g"): vol.In(MALOUF_ALARM_PRESETS),
                **SIDE_FIELD,
            }
        ),
    )
