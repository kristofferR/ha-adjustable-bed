"""The app's existing-alarm Confirm operation, without an inferred delete meaning."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...errors import invalid
from ...import_executor import async_import_modules


async def handle_confirm(call: ServiceCall) -> None:
    from ...services import (
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _execute_preflighted,
        _family_command,
        _release_preflighted,
        _validation_controller,
    )

    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.suta_king_koil.controller")
    from .controller import KingKoilController

    days, hour, minute = call.data["weekdays"], call.data["hour"], call.data["minute"]
    preflighted = []
    try:
        for parent, side in targets:
            for child in _command_targets(parent, side):
                if not isinstance(child.capability_controller, KingKoilController):
                    raise invalid("action_for_other_beds", beds="King Koil (SUTA) beds")
        for parent, side in targets:
            for child in _command_targets(parent, side):
                controller = await _validation_controller(parent, child, preflighted)
                if not isinstance(controller, KingKoilController):
                    raise invalid("bed_changed")
                if not controller.protocol_diagnostics["date_raw"]:
                    raise invalid("suta_king_koil_calibrate")
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(
                KingKoilController,
                lambda controller: controller.alarm_operation("DA", days, hour, minute),
            ),
            admissions=admissions,
        )
    finally:
        await _release_preflighted(preflighted)


def register_services(hass: HomeAssistant) -> None:
    from ...const import DOMAIN
    from ...services import DEVICE_IDS, SIDE_FIELD

    hass.services.async_register(
        DOMAIN,
        "suta_king_koil_confirm_alarm",
        handle_confirm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("weekdays"): vol.All(
                    [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))], vol.Length(min=1, max=7)
                ),
                vol.Required("hour"): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Required("minute"): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
                **SIDE_FIELD,
            }
        ),
    )
