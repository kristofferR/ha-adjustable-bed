"""Validated Sleep Number controls with optional structured responses."""

from __future__ import annotations

import math

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util.json import JsonValueType

from .beds.base import BedController
from .const import DOMAIN
from .paired_coordinator import PairedBedCoordinator
from .services import (
    SIDE_FIELD,
    PreflightedSides,
    _command_targets,
    _execute_sided,
    _missing_device_error,
    _release_preflighted,
    _resolve_sided_targets,
    _validation_controller,
)

SERVICE_SLEEP_NUMBER_COMMAND = "sleep_number_command"
MOTION_COMMANDS = frozenset(
    {
        "set_actuator_target_position",
        "set_actuator_target_position_with_timer",
        "set_target_preset_with_timer",
        "set_target_preset_without_timer",
        "cancel_target_preset",
        "halt_all_actuators",
        "starts_actuator_homing",
        "start_sleep_number_adjustment",
        "interrupt_sleep_number_adjustment",
        "position",
        "preset_timer",
        "stop",
        "head_tilt",
    }
)
SLEEP_NUMBER_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required("command"): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("parameters", default=dict): dict,
        **SIDE_FIELD,
    }
)


def _json_value(value: object) -> JsonValueType:
    """Keep controller responses within Home Assistant's JSON service contract."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, JsonValueType] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Sleep Number response field names must be strings")
            result[key] = _json_value(item)
        return result
    raise ValueError("Sleep Number response contains a non-JSON value")


async def handle_sleep_number_command(call: ServiceCall) -> ServiceResponse:
    """Validate every selected side before issuing any requested commands."""
    targets, missing = _resolve_sided_targets(
        call.hass, [call.data[CONF_DEVICE_ID]], call.data.get("side")
    )
    if missing:
        raise _missing_device_error(missing[0])
    command = call.data["command"]
    parameters = call.data.get("parameters", {})
    preflighted: PreflightedSides = []
    results: dict[str, JsonValueType] = {}
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(coordinator, target, preflighted)
                physical_side = (
                    next(
                        child_side for child_side, child in coordinator.children.items()
                        if child is target
                    )
                    if isinstance(coordinator, PairedBedCoordinator)
                    else None
                )
                with controller.side_scope(physical_side):
                    if command not in controller.sleep_number_command_names:
                        raise ServiceValidationError(
                            f"Sleep Number command {command!r} is not supported by {target.name}"
                        )
                    controller.validate_sleep_number_command(command, parameters)

        for coordinator, side in targets:
            address_sides = (
                {
                    child.address.upper(): physical_side
                    for physical_side, child in coordinator.children.items()
                }
                if isinstance(coordinator, PairedBedCoordinator)
                else {}
            )

            async def control(
                controller: BedController, address_sides: dict[str, str] = address_sides
            ) -> None:
                # Single-address children arrive bound; ordinary paired children
                # need their physical side applied after connection as well.
                physical_side = controller.command_side or address_sides.get(
                    controller._coordinator.address.upper()
                )
                with controller.side_scope(physical_side):
                    controller.validate_sleep_number_command(command, parameters)
                    key = physical_side or "single"
                    results[key] = _json_value(
                        await controller.async_execute_sleep_number_command(command, parameters)
                    )

            await _execute_sided(
                coordinator, side, control, resource="*", cancel_running=command in MOTION_COMMANDS
            )
    except ValueError as err:
        await _release_preflighted(preflighted)
        raise ServiceValidationError(str(err)) from err
    except BaseException:
        await _release_preflighted(preflighted)
        raise
    return {"command": command, "results": results}


def async_register_sleep_number_services(hass: HomeAssistant) -> None:
    """Register semantic commands; controllers own their finite parameter schemas."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SLEEP_NUMBER_COMMAND,
        handle_sleep_number_command,
        schema=SLEEP_NUMBER_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
