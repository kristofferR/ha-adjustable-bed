"""BF and Cherish bed alarm action with all-target preflight."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .beds.base import BedController, SideBoundController
from .const import BED_TYPE_BF, BED_TYPE_CHERISH, DOMAIN


def register_services(hass: HomeAssistant) -> None:
    from .services import (
        SIDE_FIELD,
        _command_targets,
        _execute_sided,
        _missing_device_error,
        _preflight_capability,
        _release_preflighted,
        _resolve_sided_targets,
    )

    async def set_alarm(call: ServiceCall) -> None:
        from homeassistant.util import dt as dt_util

        from .beds.bf_cherish import BfCherishController, alarm_frame

        enabled = call.data["enabled"]
        time = call.data.get("time")
        if enabled and time is None:
            raise ServiceValidationError("Choose an alarm time")
        if time is not None and (time.second or time.microsecond):
            raise ServiceValidationError("BF and Cherish alarms use minute precision")
        hour, minute = (time.hour, time.minute) if time else (0, 0)
        memory = call.data["memory"]
        targets, missing = _resolve_sided_targets(
            call.hass, call.data["device_id"], call.data.get("side")
        )
        if missing:
            raise _missing_device_error(missing[0])
        for owner, side in targets:
            for target in _command_targets(owner, side):
                if target.bed_type not in (BED_TYPE_BF, BED_TYPE_CHERISH):
                    raise ServiceValidationError("Select only BF or Cherish app beds")

        def controller(value: BedController | SideBoundController) -> BfCherishController:
            physical = value._controller if isinstance(value, SideBoundController) else value
            if not isinstance(physical, BfCherishController):
                raise ServiceValidationError("Requires a BF or Cherish app profile")
            return physical

        def validate(value: BedController | SideBoundController) -> None:
            alarm_frame(
                controller(value).cherish,
                dt_util.now(),
                enabled=enabled,
                hour=hour,
                minute=minute,
                memory=memory,
            )

        preflighted = await _preflight_capability(
            targets, "supports_clock_alarm", "BF/Cherish alarms", validate
        )

        async def program(value: BedController | SideBoundController) -> None:
            await controller(value).configure_clock_alarm(
                enabled=enabled, hour=hour, minute=minute, preset=memory
            )

        try:
            for owner, side in targets:
                await _execute_sided(
                    owner, side, program, cancel_running=False, resource="configuration"
                )
        except BaseException:
            await _release_preflighted(preflighted)
            raise

    hass.services.async_register(
        DOMAIN,
        "bf_cherish_set_alarm",
        set_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("memory", default="none"): vol.In(("none", "memory_1", "memory_2")),
                **SIDE_FIELD,
            }
        ),
    )
