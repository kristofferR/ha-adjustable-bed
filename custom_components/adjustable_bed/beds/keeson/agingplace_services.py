"""Dawn House direct BLE actions, with admission before any import or connect."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...command_scheduler import ALL_COMMAND_RESOURCES, PreparedCommandInvalidated
from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...paired_coordinator import SingleAddressPairedCoordinator
from ...profiles import agingplace as app
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _preflight_and_execute,
)

ACTIONS = tuple(name for name, action in app.ACTIONS.items() if not action.held) + (
    "device_info",
    "cancel",
)
SETTINGS = ("brightness", "massage_minutes", "motion_minutes")


def _admit(call: ServiceCall, resource: str | None):
    """Freeze physical owners and STOP epochs before any import/connect await."""
    targets = _call_targets(call)
    if any(isinstance(parent, SingleAddressPairedCoordinator) for parent, _side in targets):
        raise ServiceValidationError(
            "Dawn House has no command-side selector; configure one standalone bed"
        )
    resources = (resource,) if resource else ALL_COMMAND_RESOURCES
    admissions = [_capture_command_admission(parent, side, resources) for parent, side in targets]
    owners = [
        tuple(id(child) for child in _command_targets(parent, side)) for parent, side in targets
    ]

    def verify(_controller: object) -> None:
        for (parent, side), before, physical in zip(targets, admissions, owners, strict=True):
            now = _capture_command_admission(parent, side, resources)
            if (
                now.expected_pair_generations != before.expected_pair_generations
                or now.expected_stop_epochs != before.expected_stop_epochs
                or tuple(id(child) for child in _command_targets(parent, side)) != physical
            ):
                raise PreparedCommandInvalidated(
                    "Dawn House targets or STOP changed during admission"
                )

    return targets, admissions, verify


def _integer(value: object) -> int:
    if type(value) is not int:
        raise vol.Invalid("Expected a whole number")
    return value


async def handle_action(call: ServiceCall) -> None:
    name = call.data["action"]
    resource = "configuration" if name == "device_info" else None
    targets, admissions, verify = _admit(call, resource)
    await async_import_modules(call.hass, "beds.keeson.agingplace")
    from .agingplace import AgingPlaceController

    async def run(controller: AgingPlaceController) -> None:
        if name == "device_info":
            await controller.query_device_info()
        else:
            await controller.run_action("flat" if name == "cancel" else name)

    await _preflight_and_execute(
        targets,
        AgingPlaceController,
        "Dawn House actions",
        run,
        resource=resource,
        cancel_running=resource is None,
        admit=True,
        admissions=admissions,
        validate=verify,
    )


async def handle_setting(call: ServiceCall) -> None:
    targets, admissions, verify = _admit(call, "configuration")
    name, value = call.data["setting"], call.data["value"]
    # Validate the entire parameter before a target can connect or write.
    try:
        app.setting(name, value, None)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    await async_import_modules(call.hass, "beds.keeson.agingplace")
    from .agingplace import AgingPlaceController

    async def run(controller: AgingPlaceController) -> None:
        await controller.set_setting(name, value)

    await _preflight_and_execute(
        targets,
        AgingPlaceController,
        "Dawn House settings",
        run,
        admit=True,
        admissions=admissions,
        validate=verify,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "agingplace_action",
        handle_action,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(ACTIONS),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "agingplace_set_setting",
        handle_setting,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("setting"): vol.In(SETTINGS),
                vol.Required("value"): _integer,
                **SIDE_FIELD,
            }
        ),
    )
