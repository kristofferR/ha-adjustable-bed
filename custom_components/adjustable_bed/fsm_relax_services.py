"""FSM Relax calibration action."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_FSM_RELAX, DOMAIN
from .services import (
    SIDE_FIELD,
    _call_targets,
    _command_targets,
    _execute_sided,
    _preflight_capability,
)

if TYPE_CHECKING:
    from .beds.base import BedController


SERVICE_FSM_RELAX_CALIBRATE = "fsm_relax_calibrate"


async def handle_fsm_relax_calibrate(call: ServiceCall) -> None:
    """Send exactly one positively confirmed calibration write."""
    targets = _call_targets(call)
    if call.data.get("confirmed") is not True:
        raise ServiceValidationError("Calibration requires explicit confirmation")
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_FSM_RELAX:
                raise ServiceValidationError("This action requires the FSM Relax app profile")
    await _preflight_capability(targets, "supports_confirmed_calibration", "FSM Relax local action")

    async def execute(controller: BedController) -> None:
        await controller.calibrate(confirmed=True)

    for coordinator, side in targets:
        await _execute_sided(coordinator, side, execute, cancel_running=True)


def async_register_fsm_relax_services(hass: HomeAssistant) -> None:
    """Register the FSM Relax calibration action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_FSM_RELAX_CALIBRATE,
        handle_fsm_relax_calibrate,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required("confirmed"): vol.All(cv.boolean, vol.In((True,))),
                **SIDE_FIELD,
            }
        ),
    )
