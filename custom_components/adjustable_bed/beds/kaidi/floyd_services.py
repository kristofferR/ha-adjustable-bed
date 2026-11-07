"""Floyd preset, room and pairing actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    BedTarget,
    _call_targets,
    _execute_sided,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)

SERVICE_FLOYD_ACTION = "floyd_action"


async def handle_floyd_action(call: ServiceCall) -> None:
    """Run Floyd presets or explicitly assign one unassigned standalone node."""
    await async_import_modules(call.hass, "beds.kaidi.floyd")
    from ...coordinator import AdjustableBedCoordinator
    from .floyd import FloydController

    label = "Floyd Home actions"
    targets = _call_targets(call)
    action = call.data["action"]
    internal_side = call.data.get("internal_side", "first")
    confirm = call.data.get("confirm", False)
    room_id = call.data.get("room_id")
    if action == "assign_room" and (
        len(targets) != 1 or not isinstance(targets[0][0], AdjustableBedCoordinator)
    ):
        raise ServiceValidationError("Assign one standalone Floyd bed at a time")

    def validate(controller: FloydController) -> None:
        controller.validate_floyd_action(action, internal_side, confirm, room_id)

    preflighted = await _preflight_capability(targets, FloydController, label, validate=validate)
    try:
        for coordinator, side in targets:
            assignment_completed = False

            async def execute(
                controller: FloydController, *, target: BedTarget = coordinator,
            ) -> None:
                nonlocal assignment_completed
                await controller.floyd_action(action, internal_side, confirm, room_id)
                if action == "assign_room":
                    assert isinstance(target, AdjustableBedCoordinator)
                    assert isinstance(room_id, int)
                    target.remember_floyd_room(room_id)
                    assignment_completed = True

            try:
                await _execute_sided(
                    coordinator, side, _family_command(FloydController, label, execute),
                    resource="configuration" if action.startswith("save_") or action in {"assign_room", "confirm_add"} else None,
                )
            finally:
                if action == "assign_room":
                    await coordinator.async_disconnect()
            if action == "assign_room":
                if not assignment_completed:
                    raise ServiceValidationError("Floyd room assignment was cancelled before acknowledgement")
                await _execute_sided(
                    coordinator, side,
                    _family_command(
                        FloydController,
                        label,
                        lambda controller: controller.floyd_action("confirm_add", "first", True, None),
                    ),
                    resource="configuration",
                )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def async_register_floyd_services(hass: HomeAssistant) -> None:
    """Register the Floyd action."""
    hass.services.async_register(
        DOMAIN, SERVICE_FLOYD_ACTION, handle_floyd_action,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required("action"): vol.In((
                "zero_g", "flat", "anti_snore", "memory_1", "memory_2", "memory_3",
                "save_zero_g", "save_anti_snore", "assign_room", "confirm_add",
            )),
            vol.Optional("internal_side", default="first"): vol.In(("first", "both", "second")),
            vol.Optional("confirm", default=False): cv.boolean,
            vol.Optional("room_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=0xFFFFFFFF)),
            **SIDE_FIELD,
        }),
    )
