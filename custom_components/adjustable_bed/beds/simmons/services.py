"""SIMMONS app alarm action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...services import (
    ATTR_CONFIRM_CUSTOM_MODE,
    ATTR_ENABLED,
    ATTR_MODE,
    ATTR_SLOT,
    ATTR_TIME,
    ATTR_WEEKDAYS,
    DEVICE_IDS,
    SIDE_FIELD,
    SOLACE_WEEKDAY_OPTIONS,
    _call_targets,
    _execute_sided,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)

SERVICE_SIMMONS_SET_ALARM = "simmons_set_alarm"


async def handle_simmons_set_alarm(call: ServiceCall) -> None:
    """Program or disable one of the two SIMMONS alarms through the command queue."""
    from .controller import SimmonsController

    alarm_time = call.data[ATTR_TIME]
    if alarm_time.second or alarm_time.microsecond:
        raise ServiceValidationError("SIMMONS alarms use minute precision")
    weekdays = tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in call.data[ATTR_WEEKDAYS])
    options = {
        "slot": call.data[ATTR_SLOT],
        "enabled": call.data[ATTR_ENABLED],
        "mode": call.data.get(ATTR_MODE),
        "confirm_custom_mode": call.data[ATTR_CONFIRM_CUSTOM_MODE],
    }
    label = "SIMMONS alarms"
    targets = _call_targets(call)
    preflighted = await _preflight_capability(
        targets,
        SimmonsController,
        label,
        supported=lambda controller: controller.supports_clock_sync,
        validate=lambda controller: controller.validate_simmons_alarm(**options),
    )

    fields = {**options, "hour": alarm_time.hour, "minute": alarm_time.minute, "weekdays": weekdays}

    async def check(controller: SimmonsController) -> None:
        await controller.check_simmons_alarm(**fields)

    async def program(controller: SimmonsController) -> None:
        await controller.configure_simmons_alarm(**fields)

    try:
        # All-or-nothing: every bed reports its records and passes the peer
        # rules before the first bed is programmed.
        for step in (check, program):
            for coordinator, side in targets:
                await _execute_sided(
                    coordinator,
                    side,
                    _family_command(SimmonsController, label, step),
                    cancel_running=False,
                    resource="configuration",
                )
    except BaseException:
        # Includes cancellation: beds connected only for preflight still need
        # their normal idle disconnect.
        await _release_preflighted(preflighted)
        raise


def async_register_simmons_services(hass: HomeAssistant) -> None:
    """Register the SIMMONS alarm action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SIMMONS_SET_ALARM,
        handle_simmons_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_SLOT): vol.All(vol.Coerce(int), vol.In((1, 2))),
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]
                ),
                vol.Optional(ATTR_MODE): vol.In(("custom_mode", "flat", "anti_snore")),
                vol.Optional(ATTR_CONFIRM_CUSTOM_MODE, default=False): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
