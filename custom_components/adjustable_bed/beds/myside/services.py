"""Validated My Side repeat alarms and bed-side sleep-name query."""

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.myside import ALARM_MODES


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    async def handle(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [
            _capture_command_admission(c, side, ("configuration",)) for c, side in targets
        ]
        await async_import_modules(hass, "beds.myside.controller")
        from .controller import AlarmAdmission, MySideController

        data = call.data
        options = {
            "alarm_id": data["alarm_id"],
            "hour": data["hour"],
            "minute": data["minute"],
            "mode": data["mode"],
            "weekdays": tuple(data["weekdays"]),
        }
        prepared: dict[MySideController, AlarmAdmission] = {}
        mutation = data["operation"] in ("add", "edit", "delete", "enable")

        def validate(controller: MySideController) -> None:
            controller.validate_operation(data["operation"], **options)
            if mutation:
                prepared[controller] = controller.alarm_admission()

        async def execute(controller: MySideController) -> None:
            admission = prepared.get(controller)
            if mutation and admission is None:
                raise ValueError("The alarm connection changed; query alarms again")
            await controller.operation(
                data["operation"], **options, enabled=data["enabled"], admission=admission
            )

        await _preflight_and_execute(
            targets,
            MySideController,
            execute,
            validate=validate,
            admissions=admissions,
        )

    hass.services.async_register(
        DOMAIN,
        "myside",
        handle,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("operation"): vol.In(
                    ("query", "add", "edit", "delete", "enable", "sync", "name")
                ),
                vol.Optional("alarm_id", default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=7)
                ),
                vol.Optional("hour", default=7): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Optional("minute", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=59)
                ),
                vol.Optional("mode", default="zero_gravity"): vol.In(ALARM_MODES),
                vol.Optional("weekdays", default=[]): [vol.All(vol.Coerce(int), vol.In(range(7)))],
                vol.Optional("enabled", default=True): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
