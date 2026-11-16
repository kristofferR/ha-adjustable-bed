"""Whole-bank Nerum alarms, with STOP and pair ownership captured before import."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.nerum import WAKE, Alarm


def register_services(hass: HomeAssistant) -> None:
    from ...command_scheduler import ALL_COMMAND_RESOURCES
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    async def set_alarms(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [
            _capture_command_admission(parent, side, ALL_COMMAND_RESOURCES)
            for parent, side in targets
        ]
        await async_import_modules(hass, "beds.nerum.controller")
        from .controller import NerumController

        records = tuple(
            Alarm(row["hour"], row["minute"], row["repeat"], WAKE[row["action"]], row["enabled"])
            for row in call.data["alarms"]
        )
        bank = (records[0], records[1], records[2])
        await _preflight_and_execute(
            targets,
            NerumController,
            "Nerum alarms",
            lambda controller: controller.set_alarms(bank),
            validate=lambda controller: controller.validate_alarm_bank(bank),
            cancel_running=True,
            resource=None,
            admit=True,
            admissions=admissions,
        )

    alarm = vol.Schema(
        {
            vol.Required("hour"): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
            vol.Required("minute"): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
            vol.Required("repeat"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            vol.Required("enabled"): cv.boolean,
            vol.Required("action"): vol.In(WAKE),
        }
    )
    hass.services.async_register(
        DOMAIN,
        "nerum_set_alarms",
        set_alarms,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("alarms"): vol.All([alarm], vol.Length(min=3, max=3)),
                **SIDE_FIELD,
            }
        ),
    )
