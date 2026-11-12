"""N32's three app-supported bed alarm slots, with all-target admission."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.n32_motion_bed import ALARM_MODES, alarm_week
from .state import AlarmRow


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        SOLACE_WEEKDAY_OPTIONS,
        _call_targets,
        _execute_sided,
        _family_command,
        _preflight_capability,
        _release_preflighted,
    )

    async def alarm(call: ServiceCall) -> None:
        await async_import_modules(call.hass, "beds.n32_motion_bed.controller")
        from .controller import N32MotionBedController

        operation, slot = call.data["operation"], call.data["slot"]
        row = None
        if operation == "set":
            time, mode, days = (call.data.get(key) for key in ("time", "mode", "weekdays"))
            if time is None or mode is None or days is None:
                raise ServiceValidationError(
                    "N32 set requires time, weekdays (empty for once), and mode"
                )
            if time.second or time.microsecond:
                raise ServiceValidationError("N32 alarms use minute precision")
            week = alarm_week(tuple(SOLACE_WEEKDAY_OPTIONS.index(day) for day in days))
            row = AlarmRow(time.hour, time.minute, week, ALARM_MODES[mode], 1)
        elif any(key in call.data for key in ("time", "mode", "weekdays")):
            raise ServiceValidationError(
                "Alarm fields apply only to set; disable preserves the reported slot"
            )

        targets, label = _call_targets(call), "N32 Motion Bed alarms"
        preflighted = await _preflight_capability(
            targets,
            N32MotionBedController,
            label,
            validate=lambda c: c.validate_alarm(slot, operation, row),
        )

        async def check(c: N32MotionBedController) -> None:
            await c.check_alarm(slot, operation, row)

        async def apply(c: N32MotionBedController) -> None:
            await c.apply_alarm(slot, operation, row)

        try:
            # Every target passes live session/query checks before the first
            # requested mutation. Execution repeats them after any reconnect.
            for run in (check, apply):
                for parent, side in targets:
                    await _execute_sided(
                        parent,
                        side,
                        _family_command(N32MotionBedController, label, run),
                        cancel_running=False,
                        resource="configuration",
                    )
        except BaseException:
            await _release_preflighted(preflighted)
            raise

    hass.services.async_register(
        DOMAIN,
        "n32_motion_bed_alarm",
        alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("slot"): vol.All(vol.Coerce(int), vol.In((1, 2, 3))),
                vol.Required("operation"): vol.In(("set", "disable", "delete", "query")),
                vol.Optional("time"): cv.time,
                vol.Optional("mode"): vol.In(tuple(ALARM_MODES)),
                vol.Optional("weekdays"): vol.All(cv.ensure_list, [vol.In(SOLACE_WEEKDAY_OPTIONS)]),
                **SIDE_FIELD,
            }
        ),
    )
