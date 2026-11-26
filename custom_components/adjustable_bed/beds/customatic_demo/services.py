"""Confirmed Independence demonstration on a single physical receiver."""

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _preflight_and_execute,
    )

    async def run_demo(call: ServiceCall) -> None:
        if not call.data["confirm"]:
            raise invalid("confirmation_required", action="run the Independence demo")
        targets = _call_targets(call)
        if len(targets) != 1 or len(_command_targets(*targets[0])) != 1:
            raise invalid("one_bed_only")
        parent, side = targets[0]
        admission = _capture_command_admission(parent, side)
        still_admitted = None
        if isinstance(parent, PairedBedCoordinator):
            physical_side, _ = parent.targets_for(side)[0]
            stop_epoch = parent.stop_count(physical_side)

            def pair_stop_unchanged() -> bool:
                return parent.stop_count(physical_side) == stop_epoch

            still_admitted = pair_stop_unchanged
        await async_import_modules(call.hass, "beds.customatic_demo.controller")
        from .controller import CustomaticDemoController

        async def run(controller: CustomaticDemoController) -> None:
            await controller.run_demo(still_admitted=still_admitted)

        await _preflight_and_execute(
            targets,
            CustomaticDemoController,
            run,
            cancel_running=True,
            resource=None,
            admissions=[admission],
        )

    hass.services.async_register(
        DOMAIN,
        "customatic_demo_run",
        run_demo,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                **SIDE_FIELD,
                vol.Optional("confirm", default=False): cv.boolean,
            }
        ),
    )
