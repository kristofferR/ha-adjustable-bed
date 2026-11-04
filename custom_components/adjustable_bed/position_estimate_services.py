"""Actions for estimated positions and saved positions (#601)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SIDE_BOTH
from .paired_coordinator import PairedBedCoordinator
from .position_estimate import (
    MAX_POSITION_NAME_LENGTH,
    BedEstimate,
    EstimateReason,
    PositionEstimates,
    async_lower_to_flat,
    async_recall_position,
    position_estimates,
)
from .services import SIDE_FIELD, _missing_device_error, _resolve_sided_targets

SERVICE_SAVE_POSITION = "save_position"
SERVICE_RENAME_POSITION = "rename_position"
SERVICE_UPDATE_POSITION = "update_position"
SERVICE_DELETE_POSITION = "delete_position"
SERVICE_RECALL_POSITION = "recall_position"
SERVICE_SET_POSITION_REFERENCE = "set_position_reference"
SERVICE_CONFIRM_POSITION_UNCHANGED = "confirm_position_unchanged"
SERVICE_MARK_POSITION_UNKNOWN = "mark_position_unknown"
SERVICE_LOWER_TO_FLAT = "lower_to_flat"

ATTR_NAME = "name"
ATTR_POSITION = "position"
ATTR_CREATE_BUTTON = "create_button"
ATTR_MOTORS = "motors"
ESTIMATED_MOTORS = ("back", "legs", "head", "feet")

_DEVICE = {vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1, max=1))}
_NAME = vol.All(cv.string, vol.Length(min=1, max=MAX_POSITION_NAME_LENGTH))
_MOTORS = {vol.Optional(ATTR_MOTORS): vol.All(cv.ensure_list, [vol.In(ESTIMATED_MOTORS)])}

BED_SCHEMA = vol.Schema({**_DEVICE, **SIDE_FIELD})
MOTORS_SCHEMA = vol.Schema({**_DEVICE, **SIDE_FIELD, **_MOTORS})
SAVE_SCHEMA = vol.Schema(
    {
        **_DEVICE,
        **SIDE_FIELD,
        vol.Required(ATTR_NAME): _NAME,
        vol.Optional(ATTR_CREATE_BUTTON, default=True): cv.boolean,
    }
)
POSITION_SCHEMA = vol.Schema({**_DEVICE, vol.Required(ATTR_POSITION): cv.string})
RENAME_SCHEMA = vol.Schema(
    {
        **_DEVICE,
        vol.Required(ATTR_POSITION): cv.string,
        vol.Required(ATTR_NAME): _NAME,
        vol.Optional(ATTR_CREATE_BUTTON): cv.boolean,
    }
)


def _selection(call: ServiceCall) -> tuple[PositionEstimates, list[BedEstimate]]:
    """Resolve one bed device, and its side for a pair, to its estimates."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get("side")
    )
    if missing:
        raise _missing_device_error(missing[0])
    coordinator, side = targets[0]
    manager = position_estimates(call.hass, coordinator.entry.entry_id)
    if manager is None or not manager.active:
        raise ServiceValidationError(
            "Estimated positions are not enabled for this bed",
            translation_domain=DOMAIN,
            translation_key="position_estimate_not_enabled",
        )
    if isinstance(coordinator, PairedBedCoordinator) and side != SIDE_BOTH:
        beds = [bed for bed in manager.beds.values() if bed.side == side]
    else:
        beds = list(manager.beds.values())
    beds = [bed for bed in beds if bed.motors]
    if not beds:
        raise ServiceValidationError(
            "Estimated positions are not enabled for this side",
            translation_domain=DOMAIN,
            translation_key="position_estimate_not_enabled",
        )
    return manager, beds


async def handle_save_position(call: ServiceCall) -> ServiceResponse:
    manager, beds = _selection(call)
    position = manager.save_position(
        call.data[ATTR_NAME], beds, button=call.data[ATTR_CREATE_BUTTON]
    )
    return {"position_id": position.id, "name": position.name}


async def handle_rename_position(call: ServiceCall) -> None:
    manager, _beds = _selection(call)
    manager.rename_position(
        manager.position(call.data[ATTR_POSITION]),
        call.data[ATTR_NAME],
        button=call.data.get(ATTR_CREATE_BUTTON),
    )


async def handle_update_position(call: ServiceCall) -> None:
    manager, _beds = _selection(call)
    manager.update_position(manager.position(call.data[ATTR_POSITION]))


async def handle_delete_position(call: ServiceCall) -> None:
    manager, _beds = _selection(call)
    manager.delete_position(manager.position(call.data[ATTR_POSITION]))


async def handle_recall_position(call: ServiceCall) -> None:
    manager, _beds = _selection(call)
    await async_recall_position(call.hass, manager, manager.position(call.data[ATTR_POSITION]))


async def handle_set_position_reference(call: ServiceCall) -> None:
    _manager, beds = _selection(call)
    for bed in beds:
        bed.set_reference(call.data.get(ATTR_MOTORS))


async def handle_confirm_position_unchanged(call: ServiceCall) -> None:
    _manager, beds = _selection(call)
    for bed in beds:
        bed.confirm_unchanged()


async def handle_mark_position_unknown(call: ServiceCall) -> None:
    _manager, beds = _selection(call)
    for bed in beds:
        bed.invalidate(EstimateReason.REMOTE)


async def handle_lower_to_flat(call: ServiceCall) -> None:
    manager, beds = _selection(call)
    for bed in beds:
        await async_lower_to_flat(call.hass, manager, bed, call.data.get(ATTR_MOTORS))


def async_register_position_estimate_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_POSITION,
        handle_save_position,
        schema=SAVE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    handlers: tuple[tuple[str, Callable[[ServiceCall], Awaitable[None]], vol.Schema], ...] = (
        (SERVICE_RENAME_POSITION, handle_rename_position, RENAME_SCHEMA),
        (SERVICE_UPDATE_POSITION, handle_update_position, POSITION_SCHEMA),
        (SERVICE_DELETE_POSITION, handle_delete_position, POSITION_SCHEMA),
        (SERVICE_RECALL_POSITION, handle_recall_position, POSITION_SCHEMA),
        (SERVICE_SET_POSITION_REFERENCE, handle_set_position_reference, MOTORS_SCHEMA),
        (SERVICE_CONFIRM_POSITION_UNCHANGED, handle_confirm_position_unchanged, BED_SCHEMA),
        (SERVICE_MARK_POSITION_UNKNOWN, handle_mark_position_unknown, BED_SCHEMA),
        (SERVICE_LOWER_TO_FLAT, handle_lower_to_flat, MOTORS_SCHEMA),
    )
    for name, handler, schema in handlers:
        hass.services.async_register(DOMAIN, name, handler, schema=schema)
