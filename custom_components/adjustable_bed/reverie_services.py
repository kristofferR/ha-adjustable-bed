"""Reverie and PairLink comfort, routine and test actions."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .beds.base import BedController, controller_as, require_controller
from .beds.reverie_comfort import (
    PairlinkComfortActions,
    ReverieComfortActions,
    ReverieComfortRequest,
    RoutineSteps,
)
from .command_scheduler import CommandHandle, PreparedCommandInvalidated
from .const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_PAIRLINK,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
)
from .paired_coordinator import BedChild, PairedBedCoordinator, PairedSideError
from .services import (
    ATTR_SIDE,
    SIDE_FIELD,
    BedTarget,
    PreflightedSides,
    _capture_command_admission,
    _command_targets,
    _CommandAdmission,
    _execute_sided,
    _missing_device_error,
    _release_preflighted,
    _resolve_sided_targets,
    _target_stop_epoch,
    _validation_controller,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.reverie_pairlink_runtime import PairlinkComfortPlan


SERVICE_REVERIE_SET_COMFORT = "reverie_set_comfort"
SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT = "reverie_pairlink_alarm_comfort"
SERVICE_REVERIE_RUN_ROUTINE = "reverie_run_routine"
SERVICE_REVERIE_TEST = "reverie_test"


@dataclass(frozen=True, slots=True)
class _ReverieComfortPhysicalTarget:
    """One physical coordinator selected by a Reverie comfort service call."""

    target: BedChild
    parent: PairedBedCoordinator | None
    side: str | None


def _reverie_comfort_request(
    data: dict[str, Any], *, force: bool = False
) -> ReverieComfortRequest:
    return ReverieComfortRequest(
        head_position=data.get("head_position"),
        foot_position=data.get("foot_position"),
        lumbar_position=data.get("lumbar_position"),
        head_massage=data.get("head_massage"),
        foot_massage=data.get("foot_massage"),
        timer_byte=data.get("timer_byte"),
        mode=data.get("mode"),
        force=force,
    )


def _strict_int_range(minimum: int, maximum: int | None = None) -> Callable[[object], int]:
    def validate(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise vol.Invalid("expected integer")
        if value < minimum or (maximum is not None and value > maximum):
            raise vol.Invalid("integer is outside the allowed range")
        return value

    return validate


_REVERIE_COMFORT_SCHEMA = vol.Schema(
    {
        vol.Optional("head_position"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("foot_position"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("lumbar_position"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("head_massage"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("foot_massage"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("timer_byte"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("mode"): _strict_int_range(-(2**31), 2**31 - 1),
    }
)
_REVERIE_ALARM_COMFORT_SCHEMA = vol.Schema(
    {
        vol.Required("head_position"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Required("foot_position"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Optional("lumbar_position"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Required("head_massage"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Required("foot_massage"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Required("timer_byte"): _strict_int_range(-(2**31), 2**31 - 1),
        vol.Required("mode"): _strict_int_range(-(2**31), 2**31 - 1),
    }
)


def _reverie_comfort_controller(
    coordinator: BedChild,
    controller: BedController,
) -> ReverieComfortActions:
    reverie = controller_as(controller, ReverieComfortActions)
    if reverie is None:
        raise ServiceValidationError(
            f"Device '{coordinator.name}' is not a supported Reverie protocol target"
        )
    return reverie


async def _prepare_reverie_comfort_target(
    parent: BedTarget,
    target: BedChild,
    request: ReverieComfortRequest,
    preflighted: PreflightedSides,
    pairlink_plans: dict[object, PairlinkComfortPlan],
) -> None:
    """Validate one physical target and prepare P4 against its live generation."""
    if target.bed_type != BED_TYPE_REVERIE_PAIRLINK:
        controller = await _validation_controller(parent, target, preflighted)
        if target.bed_type == BED_TYPE_REVERIE:
            _validate_reverie_deferred_target(parent, controller)
        reverie = _reverie_comfort_controller(target, controller)
        try:
            reverie.validate_comfort_request(request)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        return

    controller = target.controller or target.capability_controller
    if controller is not None and controller.requires_disconnected_transport:
        if not controller.disconnected_transport_ready:
            raise ServiceValidationError(
                f"Device '{target.name}' local Pairlink session is not ready"
            )
    elif not target.is_connected or target.controller is None:
        connected = await target.async_ensure_connected(reset_timer=False)
        if not connected or target.controller is None:
            raise ServiceValidationError(
                f"Device '{target.name}' cannot prepare a current Pairlink session"
            )
        preflighted.append((parent, target))
        controller = target.controller

    if controller is None:
        raise ServiceValidationError(
            f"Device '{target.name}' has no active Pairlink controller"
        )
    pairlink = controller_as(controller, PairlinkComfortActions)
    if pairlink is None:
        raise ServiceValidationError(
            f"Device '{target.name}' has no active Pairlink controller"
        )
    try:
        pairlink.validate_comfort_request(request)
        plan = pairlink.prepare_comfort(request)
    except (ValueError, RuntimeError, PermissionError, ConnectionError) as err:
        raise ServiceValidationError(str(err)) from err
    pairlink_plans[pairlink.comfort_runtime_identity()] = plan


def _reverie_comfort_physical_targets(
    targets: list[tuple[BedTarget, str]],
) -> list[_ReverieComfortPhysicalTarget]:
    """Expand selected HA devices to their actual physical command lanes."""
    physical: list[_ReverieComfortPhysicalTarget] = []
    seen: set[tuple[int, str | None]] = set()
    for coordinator, side in targets:
        if isinstance(coordinator, PairedBedCoordinator):
            sides = coordinator.sides if side == SIDE_BOTH else (side,)
            for physical_side in sides:
                target = coordinator.child_for_side(physical_side)
                if target is None:
                    continue
                key = (id(target), physical_side)
                if key not in seen:
                    seen.add(key)
                    physical.append(
                        _ReverieComfortPhysicalTarget(target, coordinator, physical_side)
                    )
            continue
        key = (id(coordinator), None)
        if key not in seen:
            seen.add(key)
            physical.append(_ReverieComfortPhysicalTarget(coordinator, None, None))
    return physical


@contextlib.asynccontextmanager
async def _reverie_comfort_pair_lanes(
    targets: list[_ReverieComfortPhysicalTarget],
) -> AsyncIterator[None]:
    """Acquire paired side lanes in stable order around reservation and commit."""
    grouped: dict[PairedBedCoordinator, list[tuple[str, BedChild]]] = {}
    for target in targets:
        if target.parent is not None and target.side is not None:
            grouped.setdefault(target.parent, []).append((target.side, target.target))
    async with contextlib.AsyncExitStack() as stack:
        for parent in sorted(grouped, key=id):
            await stack.enter_async_context(parent._locked_target_sides(grouped[parent]))
        yield


async def _execute_prepared_reverie_comfort(
    targets: list[tuple[BedTarget, str]],
    request: ReverieComfortRequest,
    pairlink_plans: dict[object, PairlinkComfortPlan],
    admissions: dict[tuple[int, str], _CommandAdmission],
) -> bool:
    """Reserve every selected command lane before dispatching comfort frames.

    Returns false only for lightweight coordinator doubles without the
    production scheduler reservation API. Pairlink plans are revalidated after
    all reservations are ready and immediately before the first dispatched
    controller action enters its command lock.
    """
    physical = _reverie_comfort_physical_targets(targets)
    if not physical or not pairlink_plans:
        return False
    if not all(
        callable(getattr(target.target, "async_prepare_command_operation", None))
        for target in physical
    ):
        return False
    by_parent: dict[PairedBedCoordinator, set[str]] = {}
    for target in physical:
        if target.parent is not None and target.side is not None:
            by_parent.setdefault(target.parent, set()).add(target.side)
    if any(
        parent.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL and len(sides) > 1
        for parent, sides in by_parent.items()
    ):
        raise ServiceValidationError(
            "Pairlink comfort requires all selected pair sides to remain live for preflight; "
            "use concurrent paired connection mode"
        )

    def admission_for(target: _ReverieComfortPhysicalTarget) -> _CommandAdmission:
        key = (id(target.parent or target.target), target.side or SIDE_BOTH)
        if key not in admissions:
            key = (key[0], SIDE_BOTH)
        return admissions[key]

    def stop_epoch_for(target: _ReverieComfortPhysicalTarget) -> int | None:
        return admission_for(target).expected_stop_epochs.get(target.side or SIDE_BOTH)

    def validate_pairlink_plans() -> None:
        for coordinator, side in targets:
            admission = admissions[(id(coordinator), side)]
            if isinstance(coordinator, PairedBedCoordinator):
                invalidated = coordinator._pair_admission_was_cancelled(
                    coordinator._targets_for(side),
                    admission.resources,
                    admission.expected_pair_generations,
                    admission.expected_stop_epochs,
                )
            else:
                epoch = admission.expected_stop_epochs.get(SIDE_BOTH)
                invalidated = epoch is not None and _target_stop_epoch(coordinator) != epoch
            if invalidated:
                raise PreparedCommandInvalidated("Comfort request was stopped during preflight")
        for target in physical:
            pairlink = controller_as(
                target.target.controller or target.target.capability_controller,
                PairlinkComfortActions,
            )
            if pairlink is None:
                continue
            plan = pairlink_plans.get(pairlink.comfort_runtime_identity())
            if plan is None or not pairlink.comfort_plan_is_current(request, plan):
                raise ServiceValidationError(
                    f"Device '{target.target.name}' Pairlink comfort state changed during preflight"
                )

    dispatch_checked = False

    async def execute_target(target: _ReverieComfortPhysicalTarget) -> None:
        async def apply(controller: BedController) -> None:
            nonlocal dispatch_checked
            if not dispatch_checked:
                validate_pairlink_plans()
                dispatch_checked = True
            pairlink = controller_as(controller, PairlinkComfortActions)
            if pairlink is not None:
                plan = pairlink_plans.get(pairlink.comfort_runtime_identity())
                if plan is None or not pairlink.comfort_plan_is_current(request, plan):
                    raise ServiceValidationError(
                        f"Device '{target.target.name}' Pairlink comfort state is no longer current"
                    )
                await pairlink.async_set_comfort(request, prepared_plan=plan)
                return
            await require_controller(controller, ReverieComfortActions).async_set_comfort(request)

        await target.target.async_execute_controller_command(
            apply,
            cancel_running=False,
            resource="reverie:comfort",
            read_positions_after_operation=False,
            expected_stop_epoch=stop_epoch_for(target),
        )

    group_id = uuid4().hex
    prepared: list[tuple[_ReverieComfortPhysicalTarget, CommandHandle]] = []
    result_tasks: list[asyncio.Task[None]] = []
    committed = False
    stop_attempted = False
    try:
        async with _reverie_comfort_pair_lanes(physical):
            for target in physical:
                validate_pairlink_plans()
                handle = await target.target.async_prepare_command_operation(
                    lambda target=target: execute_target(target),
                    resource="reverie:comfort",
                    cancel_running=True,
                    group_id=group_id,
                    expected_stop_epoch=stop_epoch_for(target),
                )
                prepared.append((target, handle))

        ready = await asyncio.gather(
            *(
                target.target.async_wait_prepared_command(handle)
                for target, handle in prepared
            ),
            return_exceptions=True,
        )
        error = next(
            (result for result in ready if isinstance(result, BaseException)),
            None,
        )
        if error is not None:
            raise error

        async with _reverie_comfort_pair_lanes(physical):
            revalidated = await asyncio.gather(
                *(
                    target.target.async_wait_prepared_command(handle)
                    for target, handle in prepared
                ),
                return_exceptions=True,
            )
            error = next(
                (result for result in revalidated if isinstance(result, BaseException)),
                None,
            )
            if error is not None:
                raise error
            validate_pairlink_plans()
            for target, handle in prepared:
                target.target.commit_prepared_command(handle)
            committed = True

            result_tasks = [
                asyncio.create_task(
                    target.target.async_wait_prepared_command_result(handle)
                )
                for target, handle in prepared
            ]
            done, pending = await asyncio.wait(
                result_tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            failures: list[BaseException] = []
            for task in done:
                if task.cancelled():
                    continue
                error = task.exception()
                if error is not None:
                    failures.append(error)
            if failures:
                paired_both = [
                    parent for parent, sides in by_parent.items() if len(sides) > 1
                ]
                stop_errors: dict[str, BaseException] = {}
                for parent in paired_both:
                    try:
                        await parent.async_stop_command(side=SIDE_BOTH)
                    except BaseException as stop_error:
                        stop_errors[f"pair-{id(parent)}"] = stop_error
                stop_attempted = bool(paired_both)
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                if paired_both:
                    side_errors = {
                        f"target-{index}": error
                        for index, error in enumerate(failures)
                    }
                    side_errors.update(
                        {f"{key} (stop)": error for key, error in stop_errors.items()}
                    )
                    raise PairedSideError("Reverie comfort", side_errors)
                raise failures[0]
            if pending:
                await asyncio.gather(*pending)
    except BaseException:
        if not committed:
            await asyncio.gather(
                *(
                    target.target.async_abort_prepared_command(handle)
                    for target, handle in prepared
                ),
                return_exceptions=True,
            )
        else:
            if not stop_attempted:
                for parent in (
                    parent for parent, sides in by_parent.items() if len(sides) > 1
                ):
                    try:
                        await parent.async_stop_command(side=SIDE_BOTH)
                    except BaseException:
                        pass
            for task in result_tasks:
                if not task.done():
                    task.cancel()
            if result_tasks:
                await asyncio.gather(*result_tasks, return_exceptions=True)
        raise
    return True


async def handle_reverie_set_comfort(call: ServiceCall) -> None:
    """Validate every selected target, then send one typed Reverie comfort request."""
    request = _reverie_comfort_request(call.data["comfort"])
    explicit_side = call.data.get(ATTR_SIDE)
    targets, missing = _resolve_sided_targets(
        call.hass, call.data.get(CONF_DEVICE_ID, []), explicit_side
    )
    if missing:
        raise _missing_device_error(missing[0])

    admissions = {
        (id(coordinator), side): _capture_command_admission(
            coordinator, side, ("reverie:comfort",)
        )
        for coordinator, side in targets
    }
    preflighted: PreflightedSides = []
    pairlink_plans: dict[object, PairlinkComfortPlan] = {}
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                await _prepare_reverie_comfort_target(
                    coordinator,
                    target,
                    request,
                    preflighted,
                    pairlink_plans,
                )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise

    async def set_comfort(controller: BedController) -> None:
        pairlink = controller_as(controller, PairlinkComfortActions)
        if pairlink is not None:
            plan = pairlink_plans.get(pairlink.comfort_runtime_identity())
            if plan is None:
                raise ServiceValidationError("Pairlink comfort plan is missing for this target")
            await pairlink.async_set_comfort(request, prepared_plan=plan)
            return
        await require_controller(controller, ReverieComfortActions).async_set_comfort(request)

    try:
        if pairlink_plans and await _execute_prepared_reverie_comfort(
            targets,
            request,
            pairlink_plans,
            admissions,
        ):
            return
        for coordinator, side in targets:
            async def apply_comfort(
                controller: BedController,
                parent: BedTarget = coordinator,
                selected_side: str = side,
            ) -> None:
                if any(
                    target.bed_type == BED_TYPE_REVERIE
                    for target in _command_targets(parent, selected_side)
                ):
                    _validate_reverie_deferred_target(parent, controller)
                await set_comfort(controller)

            await _execute_sided(
                coordinator,
                side,
                apply_comfort,
                resource="reverie:comfort",
                admission=admissions[(id(coordinator), side)],
            )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


async def handle_reverie_pairlink_alarm_comfort(call: ServiceCall) -> None:
    """Send the accepted complete Pairlink alarm setting after all-target preflight."""
    request = _reverie_comfort_request(call.data["comfort"], force=True)
    explicit_side = call.data.get(ATTR_SIDE)
    targets, missing = _resolve_sided_targets(
        call.hass, call.data.get(CONF_DEVICE_ID, []), explicit_side
    )
    if missing:
        raise _missing_device_error(missing[0])

    admissions = {
        (id(coordinator), side): _capture_command_admission(
            coordinator, side, ("reverie:comfort",)
        )
        for coordinator, side in targets
    }
    preflighted: PreflightedSides = []
    pairlink_plans: dict[object, PairlinkComfortPlan] = {}
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                if target.bed_type != BED_TYPE_REVERIE_PAIRLINK:
                    raise ServiceValidationError(
                        "Pairlink alarm comfort requires a Pairlink target"
                    )
                await _prepare_reverie_comfort_target(
                    coordinator,
                    target,
                    request,
                    preflighted,
                    pairlink_plans,
                )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise

    async def send_alarm_comfort(controller: BedController) -> None:
        pairlink = controller_as(controller, PairlinkComfortActions)
        if pairlink is None:
            raise ServiceValidationError("Pairlink alarm comfort received a non-Pairlink target")
        plan = pairlink_plans.get(pairlink.comfort_runtime_identity())
        if plan is None:
            raise ServiceValidationError("Pairlink comfort plan is missing for this target")
        await pairlink.async_set_comfort(request, prepared_plan=plan)

    try:
        if pairlink_plans and await _execute_prepared_reverie_comfort(
            targets,
            request,
            pairlink_plans,
            admissions,
        ):
            return
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                send_alarm_comfort,
                resource="reverie:comfort",
                admission=admissions[(id(coordinator), side)],
            )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


def _validate_reverie_deferred_target(
    coordinator: BedTarget, controller: BedController
) -> None:
    """Deferred work must survive the paired command's connection policy."""
    if (
        isinstance(coordinator, PairedBedCoordinator)
        and coordinator.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
        and not controller.requires_disconnected_transport
    ):
        raise ServiceValidationError(
            "Deferred Reverie actions require concurrent paired connection mode "
            "for central Bluetooth receivers"
        )


async def handle_reverie_run_routine(call: ServiceCall) -> None:
    """Preflight all routine rows on every target before starting any queue."""
    explicit_side = call.data.get(ATTR_SIDE)
    raw_steps = call.data["steps"]
    steps: RoutineSteps = []
    for item in raw_steps:
        request_data = item.get("comfort")
        request = _reverie_comfort_request(request_data) if request_data is not None else None
        steps.append((request, item.get("duration_minutes")))

    targets, missing = _resolve_sided_targets(
        call.hass, call.data.get(CONF_DEVICE_ID, []), explicit_side
    )
    if missing:
        raise _missing_device_error(missing[0])

    admissions = {
        (id(coordinator), side): _capture_command_admission(
            coordinator, side, ("reverie:routine",)
        )
        for coordinator, side in targets
    }
    preflighted: PreflightedSides = []
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(coordinator, target, preflighted)
                _validate_reverie_deferred_target(coordinator, controller)
                reverie = _reverie_comfort_controller(target, controller)
                try:
                    reverie.validate_routine(steps)
                except ValueError as err:
                    raise ServiceValidationError(str(err)) from err
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise

    try:
        for coordinator, side in targets:
            async def start_routine(
                controller: BedController, parent: BedTarget = coordinator
            ) -> None:
                _validate_reverie_deferred_target(parent, controller)
                await require_controller(controller, ReverieComfortActions).async_start_routine(
                    steps
                )

            await _execute_sided(
                coordinator,
                side,
                start_routine,
                resource="reverie:routine",
                admission=admissions[(id(coordinator), side)],
            )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


async def handle_reverie_test(call: ServiceCall) -> None:
    """Validate every selected target before starting its timed direct test."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data.get(CONF_DEVICE_ID, []), call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])

    admissions = {
        (id(coordinator), side): _capture_command_admission(
            coordinator, side, ("reverie:diagnostic",)
        )
        for coordinator, side in targets
    }
    preflighted: PreflightedSides = []
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(coordinator, target, preflighted)
                _validate_reverie_deferred_target(coordinator, controller)
                reverie = _reverie_comfort_controller(target, controller)
                try:
                    reverie.validate_diagnostic()
                except ValueError as err:
                    raise ServiceValidationError(str(err)) from err
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise

    try:
        for coordinator, side in targets:
            async def start_diagnostic(
                controller: BedController, parent: BedTarget = coordinator
            ) -> None:
                _validate_reverie_deferred_target(parent, controller)
                await require_controller(
                    controller, ReverieComfortActions
                ).async_start_diagnostic()

            await _execute_sided(
                coordinator,
                side,
                start_diagnostic,
                resource="reverie:diagnostic",
                admission=admissions[(id(coordinator), side)],
            )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


def async_register_reverie_services(hass: HomeAssistant) -> None:
    """Register the Reverie comfort, routine and test actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVERIE_SET_COMFORT,
        handle_reverie_set_comfort,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required("comfort"): _REVERIE_COMFORT_SCHEMA,
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
        handle_reverie_pairlink_alarm_comfort,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required("comfort"): _REVERIE_ALARM_COMFORT_SCHEMA,
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVERIE_RUN_ROUTINE,
        handle_reverie_run_routine,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required("steps"): [
                    {
                        vol.Optional("duration_minutes"): _strict_int_range(
                            -(2**31), 2**31 - 1
                        ),
                        vol.Optional("comfort"): vol.Any(None, _REVERIE_COMFORT_SCHEMA),
                    }
                ],
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVERIE_TEST,
        handle_reverie_test,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                **SIDE_FIELD,
            }
        ),
    )
