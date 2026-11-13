"""Public SonicSleep alarm, clock and link actions with all-target admission."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.sonicsleep import PRESETS


async def handle_request(call: ServiceCall) -> None:
    from ...paired_coordinator import PairedBedCoordinator
    from ...services import (
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _execute_preflighted,
        _family_command,
        _release_preflighted,
    )

    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    # Capture every physical STOP/pair generation before even the lazy import.
    await async_import_modules(call.hass, "beds.sonicsleep.controller")
    from .controller import PreparedRequest, Request, SonicSleepController

    request = Request(
        call.data["operation"], call.data.get("alarm_id"), call.data["hour"],
        call.data["minute"], call.data["mode"], tuple(call.data["weekdays"]), call.data["enabled"],
    )
    for parent, side in targets:
        for child in _command_targets(parent, side):
            controller = child.capability_controller
            if not isinstance(controller, SonicSleepController):
                raise ServiceValidationError("Select SonicSleep for this action")
            try:
                controller.validate_request(request)
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error
    # Only after every local child/ID/form constraint passes may live queries run.
    preflighted = []
    plans: dict[SonicSleepController, PreparedRequest] = {}
    try:
        for parent, side in targets:
            for child in _command_targets(parent, side):
                async def query(controller):
                    if not isinstance(controller, SonicSleepController):
                        raise ServiceValidationError("SonicSleep controller ownership changed")
                    try:
                        plans[controller] = await controller.prepare_plan(request)
                    except ValueError as error:
                        raise ServiceValidationError(str(error)) from error
                    return True

                async def inspect(target):
                    if not await target.async_execute_controller_query(query, cancel_running=False):
                        raise ServiceValidationError("SonicSleep preflight was interrupted")

                if isinstance(parent, PairedBedCoordinator):
                    child_side = next(key for key, value in parent.children.items() if value is child)
                    await parent.async_run_child_operation("SonicSleep preflight", inspect, side=child_side, cancel_running=False)
                else:
                    await inspect(child)
                preflighted.append((parent, child))
        # A sequential pair may have released an earlier receiver. Refuse
        # stale read/modify/write plans before touching ANY target's settings.
        for controller, plan in plans.items():
            controller.validate_plan(plan)

        async def execute(controller: SonicSleepController) -> None:
            if controller not in plans:
                raise ServiceValidationError("SonicSleep controller changed after preflight")
            await controller.execute_prepared(plans[controller])

        await _execute_preflighted(
            targets, preflighted,
            _family_command(SonicSleepController, "SonicSleep", execute),
            admissions=admissions,
        )
    finally:
        await _release_preflighted(preflighted)


def async_register_sonicsleep_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD

    hass.services.async_register(
        DOMAIN, "sonicsleep", handle_request,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required("operation"): vol.In(("list", "new", "edit", "toggle", "delete", "link_name", "sync_clock")),
            vol.Optional("alarm_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            vol.Optional("hour", default=6): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
            vol.Optional("minute", default=30): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
            vol.Optional("mode", default="zero_gravity"): vol.In(PRESETS),
            vol.Optional("weekdays", default=[]): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
            vol.Optional("enabled", default=True): cv.boolean,
            **SIDE_FIELD,
        }),
    )
