"""Customatic held memory and combined-motion actions."""

from __future__ import annotations

from collections.abc import Collection

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    DOMAIN,
)
from .services import (
    ATTR_ACTIONS,
    ATTR_DURATION,
    SIDE_FIELD,
    _call_targets,
    _command_targets,
    _hold_seconds,
    _hold_targets,
)

SERVICE_CUSTOMATIC_HOLD_MEMORY = "customatic_hold_memory"
SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY = "customatic_move_simultaneously"
CUSTOMATIC_MEMORY_ACTIONS = ("flat", "zg", "anti", "program", "incline")


def _customatic_memory_actions(value: object) -> list[str]:
    """Validate a nonempty subset before any bed receives a command."""
    if not isinstance(value, list) or not value or len(value) > 5:
        raise vol.Invalid("Select one to five memory actions")
    if any(
        not isinstance(action, str) or action not in CUSTOMATIC_MEMORY_ACTIONS for action in value
    ):
        raise vol.Invalid("Unknown Customatic memory action")
    if len(set(value)) != len(value):
        raise vol.Invalid("Memory actions must be unique")
    return [action for action in CUSTOMATIC_MEMORY_ACTIONS if action in value]


async def handle_customatic_hold_memory(call: ServiceCall) -> None:
    """Hold an artifact-proven memory subset on every validated physical target."""
    actions = _customatic_memory_actions(call.data[ATTR_ACTIONS])
    control = "+".join(actions)
    await _handle_customatic_hold(
        call, control, {BED_TYPE_CUSTOMATIC_CLARITY, BED_TYPE_CUSTOMATIC_REMEDY}
    )


def _customatic_movement_actions(value: object) -> dict[str, str]:
    """Allow one direction per physical axis, never contradictory motor bits."""
    if not isinstance(value, dict) or not 1 <= len(value) <= 3:
        raise vol.Invalid("Select one to three motor directions")
    if any(
        axis not in {"back", "legs", "lumbar"}
        or not isinstance(direction, str)
        or direction not in {"up", "down"}
        for axis, direction in value.items()
    ):
        raise vol.Invalid("Select back, legs or lumbar, with direction up or down")
    return {axis: value[axis] for axis in ("back", "legs", "lumbar") if axis in value}


async def handle_customatic_move_simultaneously(call: ServiceCall) -> None:
    """Move the selected safe axes using one native command mask."""
    movements = _customatic_movement_actions(call.data[ATTR_ACTIONS])
    control = "+".join(f"{axis}_{direction}" for axis, direction in movements.items())
    await _handle_customatic_hold(
        call,
        control,
        {BED_TYPE_CUSTOMATIC_CLARITY, BED_TYPE_CUSTOMATIC_JEROMES, BED_TYPE_CUSTOMATIC_REMEDY},
    )


async def _handle_customatic_hold(
    call: ServiceCall, control: str, bed_types: Collection[str]
) -> None:
    """Hold a Customatic combination after checking every target's profile."""
    duration_ms = int(call.data[ATTR_DURATION] * 1000)
    targets = _call_targets(call)
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type not in bed_types:
                raise ServiceValidationError(
                    f"Device '{target.name}' does not support this Customatic action"
                )
    await _hold_targets(targets, control, duration_ms)


def async_register_customatic_services(hass: HomeAssistant) -> None:
    """Register the Customatic held memory and combined-motion actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_CUSTOMATIC_HOLD_MEMORY,
        handle_customatic_hold_memory,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ACTIONS): _customatic_memory_actions,
                vol.Required(ATTR_DURATION): _hold_seconds,
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY,
        handle_customatic_move_simultaneously,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                vol.Required(ATTR_ACTIONS): _customatic_movement_actions,
                vol.Required(ATTR_DURATION): _hold_seconds,
                **SIDE_FIELD,
            }
        ),
    )
