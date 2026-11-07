"""Svane Remote held controls and axis release."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_SVANE, DOMAIN
from .paired_coordinator import BedChild, PairedBedCoordinator
from .services import (
    ATTR_MOTOR,
    ATTR_SIDE,
    SIDE_FIELD,
    BedTarget,
    PreflightedSides,
    _command_targets,
    _execute_sided,
    _get_controller_for_service,
    _missing_device_error,
    _release_preflighted,
    _require_held_control,
    _resolve_sided_targets,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.svane import SvaneHoldAdmission


SERVICE_SVANE_RELEASE_AXIS = "svane_release_axis"


async def _preflight_live_svane(
    parent: BedTarget,
    target: BedChild,
    admission: SvaneHoldAdmission,
    control: str,
    duration_ms: int,
) -> None:
    """Validate the live role through the pair's guarded connection lane."""
    from .beds.svane import SvaneController

    validated = False

    async def inspect(child: BedChild) -> None:
        nonlocal validated
        controller = await _get_controller_for_service(child)
        if (
            not isinstance(controller, SvaneController)
            or controller.session is not admission.session
        ):
            raise ServiceValidationError("Svane physical session changed during preflight")
        try:
            controller.validate_svane_hold_control(control, duration_ms)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        validated = True

    if isinstance(parent, PairedBedCoordinator):
        side = next(key for key, child in parent.children.items() if child is target)
        await parent.async_run_child_operation(
            "Svane live preflight",
            inspect,
            side=side,
            cancel_running=False,
        )
    else:
        await inspect(target)
    if not validated:
        raise ServiceValidationError("Svane live preflight was interrupted")


async def _svane_live_targets(
    call: ServiceCall,
    control: str,
    duration_ms: int,
) -> tuple[list[tuple[BedTarget, str]], PreflightedSides, dict[int, SvaneHoldAdmission]]:
    """Capture all release boundaries, then validate each guarded live link."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])
    from .beds.svane import SvaneController

    admissions: dict[int, SvaneHoldAdmission] = {}
    for parent, side in targets:
        for target in _command_targets(parent, side):
            controller = target.capability_controller
            if (
                target.bed_type != BED_TYPE_SVANE
                or controller is None
                or not isinstance(controller, SvaneController)
            ):
                raise ServiceValidationError("Select a Svane Remote app profile")
            _require_held_control(target, controller, control)
            try:
                controller.validate_svane_hold_constraints(control, duration_ms)
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err
            admissions[id(controller.session)] = controller.prepare_svane_hold_admission()
    preflighted: PreflightedSides = []
    try:
        for parent, side in targets:
            for target in _command_targets(parent, side):
                preflighted.append((parent, target))
                controller = target.capability_controller
                if (
                    not isinstance(controller, SvaneController)
                    or id(controller.session) not in admissions
                ):
                    raise ServiceValidationError("Svane physical session changed during preflight")
                await _preflight_live_svane(
                    parent,
                    target,
                    admissions[id(controller.session)],
                    control,
                    duration_ms,
                )
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise
    return targets, preflighted, admissions


async def _hold_svane(call: ServiceCall, control: str, duration_ms: int) -> None:
    """Preflight exact roles on all sides before serialized source held writes."""
    targets, preflighted, admissions = await _svane_live_targets(call, control, duration_ms)
    try:

        async def hold(controller: BedController) -> None:
            from .beds.svane import SvaneController

            if not isinstance(controller, SvaneController):
                raise ValueError("Svane controller changed before held command admission")
            admission = admissions.get(id(controller.session))
            if admission is None:
                raise ValueError("Svane physical session changed before held command admission")
            with admission.activate(controller):
                await controller.hold_control(control, duration_ms)

        for parent, side in targets:
            await _execute_sided(parent, side, hold, cancel_running=True)
    except (Exception, asyncio.CancelledError) as error:
        await _release_preflighted(preflighted)
        if isinstance(error, ValueError):
            raise ServiceValidationError(str(error)) from error
        raise


async def handle_svane_release_axis(call: ServiceCall) -> None:
    """Signal only the active writer, allowing the other held axis to continue."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])
    controllers: list[BedController] = []
    for parent, side in targets:
        for target in _command_targets(parent, side):
            if target.bed_type != BED_TYPE_SVANE:
                raise ServiceValidationError("Select an active Svane Remote app profile")
            controller = target.controller or target.capability_controller
            if controller is None:
                continue
            if not controller.supports_held_control:
                raise ServiceValidationError("Select an active Svane Remote app profile")
            controllers.append(controller)
    for controller in controllers:
        controller.request_svane_axis_release(call.data[ATTR_MOTOR])
    # A streamed timed move (#516) on that axis ends alone; the other keeps going.
    from .coordinator import AdjustableBedCoordinator

    resource = "motor:back" if call.data[ATTR_MOTOR] == "head" else "motor:legs"
    for parent, side in targets:
        for target in _command_targets(parent, side):
            if isinstance(target, AdjustableBedCoordinator):
                target.stop_stream_member(resource)


def async_register_svane_services(hass: HomeAssistant) -> None:
    """Register the Svane axis release action."""
    device_fields = {
        vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
        **SIDE_FIELD,
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_SVANE_RELEASE_AXIS,
        handle_svane_release_axis,
        schema=vol.Schema({**device_fields, vol.Required(ATTR_MOTOR): vol.In(("head", "feet"))}),
    )
