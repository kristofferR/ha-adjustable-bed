"""Finite app-labelled gestures and dedicated saves, with batch admission."""

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
    _require_hold_topology,
)


async def handle_request(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    # Reject unsupported single-address scopes and sequential holds before any
    # lazy import, connection, local selector change or other target effect.
    _require_hold_topology(targets)
    from ...paired_coordinator import SingleAddressPairedCoordinator

    if any(isinstance(parent, SingleAddressPairedCoordinator) for parent, _ in targets):
        raise invalid("side_not_supported")
    await async_import_modules(call.hass, "beds.richmat_legacy.controller")
    from .controller import RichmatLegacyController

    control = call.data["control"]
    duration = call.data["duration_ms"]
    program = call.data["operation"] == "program"

    def validate(controller: RichmatLegacyController) -> None:
        controller.validate_request(control, duration, program)

    preflighted = await _preflight_capability(
        targets,
        RichmatLegacyController,
        "SleepEvolution / W.Silver 3.x",
        None,
        validate,
    )

    async def execute(controller: RichmatLegacyController) -> None:
        # Automatic link-slot fallback can change topology while queued.
        _require_hold_topology(targets)
        await controller.action(control, duration_ms=duration, program=program)

    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(
            RichmatLegacyController,
            "Fixed ASCII app",
            execute,
        ),
        cancel_running=True,
        admissions=admissions,
        resource=None,
    )


def async_register_richmat_legacy_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "richmat_legacy",
        handle_request,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("control"): cv.string,
                vol.Optional("operation", default="gesture"): vol.In(("gesture", "program")),
                vol.Optional("duration_ms", default=1000): vol.All(
                    cv.positive_int, vol.Range(min=1, max=60000)
                ),
                **SIDE_FIELD,
            }
        ),
    )
