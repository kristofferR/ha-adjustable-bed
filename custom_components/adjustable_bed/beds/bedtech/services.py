"""BedTech's app sleeper selector, including the two-receiver shared-foot layout."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...const import DOMAIN, SIDE_BOTH
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    PreflightedSides,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_sided,
    _release_preflighted,
    _validation_controller,
)
from ..base import BedController, require_controller
from .routing import APP_ACTION_CHOICES, app_side


async def handle_app_command(call: ServiceCall) -> None:
    """Validate every receiver before executing an app action on its selected sleepers."""
    await async_import_modules(call.hass, "beds.bedtech.controller")
    from .controller import BedTechController

    action = call.data["action"]
    sleeper = call.data["sleeper"]
    preflighted: PreflightedSides = []
    plans = []
    try:
        targets = [
            (coordinator, side, _capture_command_admission(coordinator, side))
            for coordinator, side in _call_targets(call)
        ]
        for coordinator, target_side, admission in targets:
            controllers = [
                require_controller(
                    await _validation_controller(coordinator, child, preflighted), BedTechController
                )
                for child in _command_targets(coordinator, target_side)
            ]
            models = {controller.model for controller in controllers}
            if len(models) != 1 or not all(controller.app_model for controller in controllers):
                raise ValueError(
                    "BedTech app routing requires the same explicit model on every receiver"
                )
            selected = app_side(controllers[0].model, sleeper, action)
            if target_side != SIDE_BOTH and selected != target_side:
                raise ValueError(
                    "The app sleeper selector conflicts with the targeted child device"
                )
            if not isinstance(coordinator, PairedBedCoordinator):
                if not controllers[0].supports_single_address_pairing and selected == "right":
                    raise ValueError("The second sleeper needs a paired second receiver")
                selected = SIDE_BOTH
            logical = app_side(controllers[0].model, sleeper, action)
            for child in _command_targets(coordinator, selected):
                controller = require_controller(
                    await _validation_controller(coordinator, child, preflighted), BedTechController
                )
                with controller.side_scope(logical):
                    controller.validate_app_action(action)
            plans.append((coordinator, selected, logical, admission))
        for coordinator, selected, logical, admission in plans:
            if action == "stop":
                if isinstance(coordinator, PairedBedCoordinator):
                    await coordinator.async_stop_command(side=selected)
                else:
                    await coordinator.async_stop_command()
                continue

            async def scoped(controller: BedController, logical: str = logical) -> None:
                bed = require_controller(controller, BedTechController)
                with bed.side_scope(logical):
                    await bed.app_action(action)

            await _execute_sided(coordinator, selected, scoped, admission=admission)
    except (ValueError, NotImplementedError, TypeError) as err:
        raise ServiceValidationError(str(err)) from err
    finally:
        await _release_preflighted(preflighted)


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "bedtech_app_command",
        handle_app_command,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(APP_ACTION_CHOICES),
                vol.Optional("sleeper", default=3): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=5)
                ),
                **SIDE_FIELD,
            }
        ),
    )
