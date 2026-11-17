"""Majestic Home alarms with physical, all-target admission before lazy import."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    CONF_PROFILE_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _release_preflighted,
)
from ..base import BedController
from .requests import Request

if TYPE_CHECKING:
    from .controller import Intent, MajesticHomeController, Plan


def selected(controller: BedController | None) -> MajesticHomeController:
    if (
        type(controller).__module__
        != "custom_components.adjustable_bed.beds.majestichome.controller"
        or type(controller).__name__ != "MajesticHomeController"
    ):
        raise ServiceValidationError("Select Majestic Home for this action")
    return cast("MajesticHomeController", controller)


async def handle_request(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    physical = [(parent, side, tuple(_command_targets(parent, side))) for parent, side in targets]
    request = Request(
        call.data["operation"],
        call.data.get("alarm_id"),
        call.data["hour"],
        call.data["minute"],
        call.data["preset"],
        tuple(call.data["weekdays"]),
        call.data["enabled"],
    )

    def route(child):
        return (
            child.address,
            *(
                child.entry.options.get(key, child.entry.data.get(key))
                for key in (
                    CONF_ADDRESS,
                    CONF_BED_TYPE,
                    CONF_PROTOCOL_VARIANT,
                    CONF_PROFILE_ID,
                    CONF_PRODUCT_TYPE,
                )
            ),
        )

    products, routes = {}, {}
    for _parent, _side, children in physical:
        for child in children:
            try:
                controller = selected(child.capability_controller)
                controller.validate_request(request)
                products[child] = controller.layout.key
                routes[child] = route(child)
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error
    # Every physical STOP generation and local target/form check was captured
    # before this first await, including both children of a native paired bed.
    await async_import_modules(call.hass, "beds.majestichome.controller")
    from ...paired_coordinator import PairedBedCoordinator
    from .controller import MajesticHomeController

    plans: dict[MajesticHomeController, Plan] = {}
    intents: list[Intent] = []
    preflighted = []
    connections = ExitStack()

    def validate_owners() -> None:
        for parent, side, children in physical:
            current = _command_targets(parent, side)
            if len(current) != len(children) or any(
                a is not b for a, b in zip(current, children, strict=True)
            ):
                raise ServiceValidationError(
                    "Majestic Home physical targets changed after admission"
                )
            for child in children:
                if (
                    route(child) != routes[child]
                    or selected(child.capability_controller).layout.key != products[child]
                ):
                    raise ServiceValidationError("Majestic Home product changed after admission")

    try:
        validate_owners()
        for parent, _side, children in physical:
            if not (
                isinstance(parent, PairedBedCoordinator)
                and parent.connection_mode == "sequential"
            ):
                for child in children:
                    connections.enter_context(child.hold_command_connection())
        for parent, _side, children in physical:
            for child in children:

                async def query(controller: BedController, parent=parent) -> bool:
                    try:
                        target = selected(controller)
                        sequential = (
                            isinstance(parent, PairedBedCoordinator)
                            and parent.connection_mode == "sequential"
                        )
                        plan = await target.prepare_live(request, refresh_alarm=sequential)
                        if sequential:
                            intents.append(target.capture_intent(plan))
                        else:
                            plans[target] = plan
                    except ValueError as error:
                        raise ServiceValidationError(str(error)) from error
                    return True

                async def inspect(target) -> None:
                    if not await target.async_execute_controller_query(query, cancel_running=False):
                        raise ServiceValidationError("Majestic Home preflight was interrupted")

                if isinstance(parent, PairedBedCoordinator):
                    child_side = next(
                        key for key, value in parent.children.items() if value is child
                    )
                    await parent.async_run_child_operation(
                        "Majestic Home preflight", inspect, side=child_side, cancel_running=False
                    )
                else:
                    await inspect(child)
                preflighted.append((parent, child))
        validate_owners()
        for controller, plan in plans.items():
            controller.validate_plan(plan)

        async def execute(controller: MajesticHomeController) -> None:
            validate_owners()
            intent = next((item for item in intents if item.owner.controller is controller), None)
            if intent is not None:
                # Sequential preflight deliberately closed its link. Re-read
                # the required live fields and build fresh bytes on this link.
                plan = await controller.prepare_intent(intent)
                validate_owners()
                await controller.execute_prepared(plan, validate_admission=validate_owners)
            elif controller in plans:
                await controller.execute_prepared(
                    plans[controller], validate_admission=validate_owners
                )
            else:
                raise ServiceValidationError("Majestic Home controller changed after preflight")

        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(MajesticHomeController, "Majestic Home", execute),
            admissions=admissions,
        )
    finally:
        try:
            await _release_preflighted(preflighted)
        finally:
            connections.close()


def async_register_majestichome_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "majestichome",
        handle_request,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("operation"): vol.In(
                    ("list", "new", "set", "toggle", "delete", "sync_clock")
                ),
                vol.Optional("alarm_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
                vol.Optional("hour", default=7): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Optional("minute", default=30): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=59)
                ),
                vol.Optional("preset", default="memory_1"): vol.In(
                    ("zero_gravity", "anti_snore", "memory_1", "memory_2")
                ),
                vol.Optional("weekdays", default=[]): [
                    vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
                ],
                vol.Optional("enabled", default=True): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
