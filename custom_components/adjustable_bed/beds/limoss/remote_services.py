"""Limoss remote memory names, calibration, features and held controls."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...command_scheduler import HoldLease
from ...const import BED_TYPE_LIMOSS_REMOTE, DOMAIN
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild, PairedBedCoordinator
from ...position_estimate import track_held_control
from ...services import (
    ATTR_DURATION,
    ATTR_NAME,
    ATTR_PRESET,
    DEVICE_IDS,
    SIDE_FIELD,
    BedTarget,
    _call_targets,
    _command_targets,
    _execute_sided,
    _hold_seconds,
    _leggett_integer,
    _preflight_capability,
    _release_preflighted,
)

if TYPE_CHECKING:
    from ..base import BedController
    from .remote import LimossRemoteController


SERVICE_LIMOSS_REMOTE_RENAME_MEMORY = "limoss_remote_rename_memory"
SERVICE_LIMOSS_REMOTE_CALIBRATE = "limoss_remote_calibrate"
SERVICE_LIMOSS_REMOTE_FEATURES = "limoss_remote_features"


def _limoss_boolean(value: object) -> bool:
    if type(value) is not bool:
        raise vol.Invalid("Select true or false")
    return value


async def _hold_limoss_remote(
    call: ServiceCall,
    control: str,
    duration_ms: int,
    *,
    targets: list[tuple[BedTarget, str]] | None = None,
    lease: HoldLease | None = None,
) -> None:
    """Hold a rendered literal app action using its five-frame release.

    With a ``lease`` the hold streams until the lease ends (#483).
    """

    def validate(controller: LimossRemoteController) -> None:
        if control not in controller.held_control_options:
            raise ValueError(f"The selected profile does not support combination '{control}'")
        if lease is not None and controller.execution.hold is None:
            raise ValueError("This profile does not support renewable holds")

    async def hold(controller: BedController) -> None:
        await controller.hold_control(control, duration_ms)

    # One tracked movement per hold: renewals extend the running command.
    tracked = track_held_control(call.hass, control, hold)

    async def execute(controller: LimossRemoteController) -> None:
        await tracked(controller)

    await _execute_limoss_remote(call, validate, execute, targets=targets, lease=lease)


def _limoss_remote_controller(
    controller: BedController,
) -> LimossRemoteController:
    from .remote import LimossRemoteController

    if isinstance(controller, LimossRemoteController):
        return controller
    raise ServiceValidationError("This action requires the explicit Limoss Remote profile")


@contextlib.asynccontextmanager
async def _limoss_remote_reload_transaction(
    targets: list[tuple[BedTarget, str]],
) -> AsyncIterator[None]:
    """Defer selected receivers' entity reloads through all service phases."""
    from ...coordinator import AdjustableBedCoordinator

    async with contextlib.AsyncExitStack() as stack:
        physical: dict[int, BedChild] = {}
        for coordinator, side in targets:
            selected = [
                target
                for target in _command_targets(coordinator, side)
                if target.bed_type == BED_TYPE_LIMOSS_REMOTE
            ]
            if selected and isinstance(coordinator, PairedBedCoordinator):
                # Any child's capability update reloads this same parent entry.
                selected = list(coordinator.children.values())
            physical.update((id(target), target) for target in selected)
        for _, target in sorted(physical.items()):
            if not isinstance(target, AdjustableBedCoordinator):
                raise ServiceValidationError("Limoss Remote requires a physical receiver target")
            await stack.enter_async_context(target.async_defer_capability_reload())
        yield


async def _preflight_live_limoss_remote(
    targets: list[tuple[BedTarget, str]],
    validate: Callable[[LimossRemoteController], object],
) -> None:
    """Require each receiver's completed live startup before selected movement.

    Cached layouts remain useful offline, but do not establish a new receiver
    session. Paired routing releases each sequential validation link normally.
    """
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_LIMOSS_REMOTE:
                continue
            refreshed: list[LimossRemoteController] = []

            async def query(
                controller: BedController,
            ) -> LimossRemoteController:
                selected = _limoss_remote_controller(controller)
                await selected.start_notify()
                return selected

            async def inspect(
                child: BedChild,
                results: list[LimossRemoteController] = refreshed,
            ) -> None:
                selected = await child.async_execute_controller_query(query, cancel_running=False)
                if selected is not None:
                    results.append(selected)

            if isinstance(coordinator, PairedBedCoordinator):
                child_side = next(
                    key for key, child in coordinator.children.items() if child is target
                )
                await coordinator.async_run_child_operation(
                    "Limoss Remote preflight",
                    inspect,
                    side=child_side,
                    cancel_running=False,
                )
            else:
                await inspect(target)
            if not refreshed:
                raise ServiceValidationError("Limoss Remote capability preflight was interrupted")
            try:
                validate(refreshed[0])
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error


async def _execute_limoss_remote(
    call: ServiceCall,
    validate: Callable[[LimossRemoteController], object],
    execute: Callable[[LimossRemoteController], Coroutine[Any, Any, None]],
    *,
    targets: list[tuple[BedTarget, str]] | None = None,
    lease: HoldLease | None = None,
) -> None:
    await async_import_modules(call.hass, "beds.limoss.remote")
    from .remote import LimossRemoteController

    targets = _limoss_remote_targets(call) if targets is None else targets

    def check(controller: BedController) -> None:
        try:
            validate(_limoss_remote_controller(controller))
        except ValueError as error:
            raise ServiceValidationError(str(error)) from error

    async with _limoss_remote_reload_transaction(targets):
        await _preflight_live_limoss_remote(targets, validate)
        preflighted = await _preflight_capability(
            targets,
            LimossRemoteController,
            "Limoss Remote",
            supported=lambda controller: controller.requires_notification_channel,
            validate=check,
        )
        completed = 0

        async def run(controller: BedController) -> None:
            nonlocal completed
            selected = _limoss_remote_controller(controller)
            check(selected)
            await execute(selected)
            if selected._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            completed += 1

        try:
            for coordinator, side in targets:
                before = completed
                await _execute_sided(coordinator, side, run, cancel_running=True, lease=lease)
                # A renewable hold normally ends by expiry, release or STOP.
                if lease is None and completed - before != len(
                    _command_targets(coordinator, side)
                ):
                    raise ServiceValidationError(
                        "Limoss Remote action was interrupted before completion"
                    )
        except Exception, asyncio.CancelledError:
            await _release_preflighted(preflighted)
            raise


def _limoss_remote_targets(call: ServiceCall) -> list[tuple[BedTarget, str]]:
    targets = _call_targets(call)
    for coordinator, side in targets:
        if any(
            target.bed_type != BED_TYPE_LIMOSS_REMOTE
            for target in _command_targets(coordinator, side)
        ):
            raise ServiceValidationError("This action requires the explicit Limoss Remote profile")
    return targets


async def handle_limoss_remote_rename_memory(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.limoss.remote")
    slot, name = call.data[ATTR_PRESET], call.data[ATTR_NAME]
    controllers: list[LimossRemoteController] = []
    for coordinator, side in _limoss_remote_targets(call):
        for target in _command_targets(coordinator, side):
            controller = target.capability_controller
            if controller is None:
                raise ServiceValidationError("This receiver has no cached memory capacity")
            local = _limoss_remote_controller(controller)
            try:
                local._slot(slot)
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error
            controllers.append(local)
    # No receiver access or suspension occurs during this local edit.
    for controller in controllers:
        await controller.rename_memory(slot, name)


async def handle_limoss_remote_calibrate(call: ServiceCall) -> None:
    def validate(controller: LimossRemoteController) -> None:
        if call.data["confirmed"] is not True or controller.memory_slot_count == 0:
            raise ValueError(
                "Calibration requires explicit confirmation and a memory-capable profile"
            )

    await _execute_limoss_remote(
        call,
        validate,
        lambda ctrl: ctrl.hold_calibration(int(call.data[ATTR_DURATION] * 1000), confirmed=True),
    )


async def handle_limoss_remote_features(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.limoss.remote")

    light, massage = call.data["underbed_light"], call.data["massage"]
    targets = _limoss_remote_targets(call)
    async with _limoss_remote_reload_transaction(targets):
        touched: list[tuple[LimossRemoteController, bool, bool]] = []
        online: list[tuple[BedTarget, str]] = []
        local: list[BedChild] = []
        for coordinator, side in targets:
            physical_targets = _command_targets(coordinator, side)
            disabling: list[BedChild] = []
            for target in physical_targets:
                cached = target.capability_controller
                if cached is None:
                    raise ServiceValidationError("This receiver has no cached app profile")
                physical = _limoss_remote_controller(cached)
                if (physical.underbed_light and not light) or (physical.massage and not massage):
                    disabling.append(target)
                else:
                    local.append(target)
            if len(disabling) == len(physical_targets):
                online.append((coordinator, side))
            elif isinstance(coordinator, PairedBedCoordinator):
                online.extend(
                    (coordinator, child_side)
                    for child_side, child in coordinator.children.items()
                    if child in disabling
                )

        async def apply(controller: LimossRemoteController) -> None:
            touched.append((controller, controller.underbed_light, controller.massage))
            await controller.set_optional_features(light, massage, persist=False)

        try:
            # Only disabling an enabled feature has native OFF frames to deliver.
            if online:
                await _execute_limoss_remote(call, lambda ctrl: None, apply, targets=online)
            async with contextlib.AsyncExitStack() as stack:
                # Shared guards use one process-local order across multi-target calls.
                owners = {id(coordinator): coordinator for coordinator, _ in targets}
                for _, coordinator in sorted(owners.items()):
                    guard = (
                        coordinator.async_capability_reload_guard()
                        if isinstance(coordinator, PairedBedCoordinator)
                        else coordinator.async_command_operation_guard()
                    )
                    await stack.enter_async_context(guard)
                for target in local:
                    cached = target.capability_controller
                    if cached is None:
                        raise ServiceValidationError("This receiver has no cached app profile")
                    selected = _limoss_remote_controller(cached)
                    if (selected.underbed_light and not light) or (
                        selected.massage and not massage
                    ):
                        raise ServiceValidationError(
                            "The local feature selection changed; retry the action"
                        )
                    await apply(selected)
                for controller, _, _ in touched:
                    controller._coordinator.remember_limoss_remote_features(light, massage)
        except Exception, asyncio.CancelledError:
            # Flags describe the selected local layout, not a hardware acknowledgement.
            for controller, previous_light, previous_massage in touched:
                controller.underbed_light, controller.massage = previous_light, previous_massage
            raise


def async_register_limoss_remote_services(hass: HomeAssistant) -> None:
    """Register the Limoss remote memory, calibration and feature actions."""
    device_fields = {
        vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
        **SIDE_FIELD,
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIMOSS_REMOTE_RENAME_MEMORY,
        handle_limoss_remote_rename_memory,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required(ATTR_PRESET): vol.All(_leggett_integer, vol.Range(min=1, max=8)),
                vol.Required(ATTR_NAME): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIMOSS_REMOTE_CALIBRATE,
        handle_limoss_remote_calibrate,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required("confirmed"): _limoss_boolean,
                vol.Required(ATTR_DURATION): _hold_seconds,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIMOSS_REMOTE_FEATURES,
        handle_limoss_remote_features,
        schema=vol.Schema(
            {
                **device_fields,
                vol.Required("underbed_light"): _limoss_boolean,
                vol.Required("massage"): _limoss_boolean,
            }
        ),
    )
