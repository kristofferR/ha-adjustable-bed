"""Read or modify Dorsal alarms, with an explicit action for an unreported slot."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonValueType

from ...alarm import OPTIONAL_FIELDS, WAKE_ACTIONS, WEEKDAYS, AlarmRequest
from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _check_alarm,
    _command_targets,
    _preflight_and_execute,
    _whole_number,
)


async def handle_alarm(call: ServiceCall) -> ServiceResponse | None:
    targets = _call_targets(call)
    if sum(len(_command_targets(parent, side)) for parent, side in targets) != 1:
        raise invalid("one_bed_only")
    operation = call.data["operation"]
    slot = call.data.get("slot")
    enabled = call.data.get("enabled")
    if (operation != "list" and slot is None) or (operation == "toggle" and enabled is None):
        raise invalid("dorsal_alarm_fields")
    alarm = None
    if operation == "create_or_replace":
        if enabled is not None:
            raise invalid("dorsal_alarm_create_enabled")
        time = call.data.get("time")
        wake_action = call.data.get("wake_action")
        if slot is None or time is None or wake_action is None:
            raise invalid("dorsal_alarm_create_fields")
        if time.second or time.microsecond:
            raise invalid("alarm_time_whole_minutes")
        alarm = AlarmRequest(
            enabled=True,
            slot=slot,
            hour=time.hour,
            minute=time.minute,
            weekdays=tuple(sorted({WEEKDAYS.index(day) for day in call.data.get("weekdays", ())})),
            wake_action=wake_action,
            confirm_custom_position=call.data.get("confirm_custom_position", False),
            reference_time=dt_util.now(),
        )
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.dorsal.controller")
    from .controller import DorsalController

    records: list[JsonValueType] = []

    def validate(controller: DorsalController) -> None:
        if alarm is not None:
            given = set(OPTIONAL_FIELDS).intersection(call.data)
            if not alarm.confirm_custom_position:
                given.discard("confirm_custom_position")
            _check_alarm("Dorsal", controller, alarm, given)

    async def execute(controller: DorsalController) -> None:
        if alarm is not None:
            validate(controller)
            await controller.create_or_replace_alarm(alarm)
            return
        if slot is not None and operation != "list":
            await controller.change_stored_alarm(slot, enabled if operation == "toggle" else None)
            return
        for number, stored in sorted((await controller.refresh_alarms()).items()):
            records.append(
                {
                    "slot": number,
                    "time": f"{stored.hour:02}:{stored.minute:02}",
                    "enabled": bool(stored.repeat & 1),
                    "weekdays": [
                        day for i, day in enumerate(WEEKDAYS) if stored.repeat & (1 << (7 - i))
                    ],
                }
            )

    await _preflight_and_execute(
        targets,
        DorsalController,
        execute,
        validate=validate,
        resource="*",
        admit=True,
        admissions=admissions,
    )
    return {"alarms": records} if call.return_response else None


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "dorsal_alarm",
        handle_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("operation"): vol.In(
                    ("list", "toggle", "delete", "create_or_replace")
                ),
                vol.Optional("slot"): vol.All(_whole_number, vol.Range(min=1, max=7)),
                vol.Optional("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("weekdays"): vol.All(cv.ensure_list, [vol.In(WEEKDAYS)]),
                vol.Optional("wake_action"): vol.In(WAKE_ACTIONS[1:]),
                vol.Optional("confirm_custom_position"): cv.boolean,
                **SIDE_FIELD,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
