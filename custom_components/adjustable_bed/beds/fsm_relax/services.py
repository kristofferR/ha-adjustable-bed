"""FSM Relax calibration action."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute
from .controller import FsmRelaxController

SERVICE_FSM_RELAX_CALIBRATE = "fsm_relax_calibrate"


async def handle_fsm_relax_calibrate(call: ServiceCall) -> None:
    """Send exactly one positively confirmed calibration write."""
    targets = _call_targets(call)
    if call.data.get("confirmed") is not True:
        raise ServiceValidationError("Calibration requires explicit confirmation")

    async def execute(controller: FsmRelaxController) -> None:
        await controller.calibrate(confirmed=True)

    await _preflight_and_execute(
        targets,
        FsmRelaxController,
        "FSM Relax local action",
        execute,
        cancel_running=True,
        resource=None,
    )


def async_register_fsm_relax_services(hass: HomeAssistant) -> None:
    """Register the FSM Relax calibration action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_FSM_RELAX_CALIBRATE,
        handle_fsm_relax_calibrate,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("confirmed"): vol.All(cv.boolean, vol.In((True,))),
                **SIDE_FIELD,
            }
        ),
    )
