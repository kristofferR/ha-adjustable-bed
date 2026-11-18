"""Ultramatic's one bed alarm, with all-target admission and session fences."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...const import BED_TYPE_ULTRAMATIC_SMART_BED, DOMAIN, PAIR_CONNECTION_MODE_SEQUENTIAL
from ...entity_runtime import controller_side_scope
from ...paired_coordinator import PairedBedCoordinator
from ...profiles import ultramatic as app
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)
from .state import AlarmSettings

if TYPE_CHECKING:
    from ...paired_coordinator import BedChild
    from ...services import BedTarget
    from .controller import AlarmPlan, Link, UltramaticController


@dataclass(frozen=True, slots=True)
class _Fence:
    controller: UltramaticController
    link: Link | None
    generation: int

    def check(self) -> None:
        if (
            self.controller.session_token is not self.link
            or self.controller.operation_generation != self.generation
        ):
            raise ServiceValidationError(
                "Ultramatic command or connection changed during alarm admission"
            )
        if self.link is not None:
            self.controller._live(self.link)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid("Expected a whole number")
    return value


def _alarm_targets(parent: BedTarget, side: str) -> list[BedChild]:
    """Validate logical owners and the topology's effective dispatch scopes."""
    children = _command_targets(parent, side)
    if isinstance(parent, PairedBedCoordinator):
        children.extend(child for _, child in parent._targets_for(side))
    return list({id(child): child for child in children}.values())


async def handle_alarm(call: ServiceCall) -> None:
    # Every target and generation is captured before the first await. Registration
    # loads only this light action module; target controllers already exist.
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    physical = [child for parent, side in targets for child in _command_targets(parent, side)]
    dispatches = [
        parent._targets_for(side) if isinstance(parent, PairedBedCoordinator) else [(side, parent)]
        for parent, side in targets
    ]
    # Native Both executes once on a combined view, while admission must still
    # validate both logical children. Keep identities: the side views compare equal.
    runtimes = list(
        {
            id(child): child for parent, side in targets for child in _alarm_targets(parent, side)
        }.values()
    )
    combined = [child for child in runtimes if not any(child is logical for logical in physical)]
    if not physical or any(
        child.bed_type != BED_TYPE_ULTRAMATIC_SMART_BED or child.capability_controller is None
        for child in runtimes
    ):
        raise ServiceValidationError("Every target must use the Ultramatic Smart Bed app profile")
    # A configured capability instance already loaded its class in the factory.
    # This cached import belongs to the call, never service registration.
    from .controller import UltramaticController

    initial: list[_Fence] = []
    modes = [
        parent.connection_mode if isinstance(parent, PairedBedCoordinator) else None
        for parent, _side in targets
    ]
    dispatch_index = -1
    plans: dict[tuple[UltramaticController, str], AlarmPlan] = {}
    ready: dict[UltramaticController, _Fence] = {}
    routes: dict[int, tuple[int, str]] = {}
    sequential = {
        id(child)
        for parent, side in targets
        if isinstance(parent, PairedBedCoordinator)
        and parent.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
        for child in _alarm_targets(parent, side)
    }
    for child in runtimes:
        controller = child.capability_controller
        if not isinstance(controller, UltramaticController):
            raise ServiceValidationError(
                "Every target must use the Ultramatic Smart Bed app profile"
            )
        initial.append(
            _Fence(controller, controller.session_token, controller.operation_generation)
        )
        with controller_side_scope(child):
            routes[id(child)] = (child.operation_identity, controller._side())

    def check_owners() -> None:
        if modes != [
            parent.connection_mode if isinstance(parent, PairedBedCoordinator) else None
            for parent, _side in targets
        ]:
            raise ServiceValidationError("Ultramatic alarm connection route changed")
        current = [child for parent, side in targets for child in _command_targets(parent, side)]
        if len(current) != len(physical) or any(
            before is not after for before, after in zip(physical, current, strict=True)
        ):
            raise ServiceValidationError("Ultramatic alarm target ownership changed")
        for (parent, side), captured in zip(targets, dispatches, strict=True):
            current_dispatch = (
                parent._targets_for(side)
                if isinstance(parent, PairedBedCoordinator)
                else [(side, parent)]
            )
            if len(current_dispatch) != len(captured) or any(
                old_side != new_side or before is not after
                for (old_side, before), (new_side, after) in zip(
                    captured, current_dispatch, strict=True
                )
            ):
                raise ServiceValidationError("Ultramatic alarm effective dispatch route changed")
        for child in runtimes:
            controller = child.capability_controller
            if not isinstance(controller, UltramaticController):
                raise ServiceValidationError("Ultramatic controller was replaced after validation")
            with controller_side_scope(child):
                route = (child.operation_identity, controller._side())
            if route != routes[id(child)]:
                raise ServiceValidationError("Ultramatic alarm physical owner or side changed")
        for index, ((parent, side), admission) in enumerate(zip(targets, admissions, strict=True)):
            current_admission = _capture_command_admission(parent, side)
            if current_admission.expected_stop_epochs != admission.expected_stop_epochs:
                raise ServiceValidationError("Ultramatic alarm was stopped during admission")
            # App commands reserve '*'. Paired admission advances its targeted
            # counter exactly once before releasing this group's child commands.
            # Predict that owned advance; never adopt a newer external epoch.
            expected_pair = {
                target_side: (generation[0] + int(index <= dispatch_index),)
                for target_side, generation in admission.expected_pair_generations.items()
            }
            if current_admission.expected_pair_generations != expected_pair:
                raise ServiceValidationError("Ultramatic pair admission was superseded")

    def check_initial() -> None:
        check_owners()
        for (parent, side), admission in zip(targets, admissions, strict=True):
            if _capture_command_admission(parent, side) != admission:
                raise ServiceValidationError("Ultramatic alarm admission was superseded")
        for fence in initial:
            if fence.link is not None:
                fence.check()
        for fence in ready.values():
            fence.check()

    operation = call.data["operation"]
    settings = None
    fields = ("time", "days", "wake", "enabled")
    if operation == "set":
        if any(key not in call.data for key in fields):
            raise ServiceValidationError("Set requires time, days, wake and enabled")
        time = call.data["time"]
        if time.second or time.microsecond:
            raise ServiceValidationError("Ultramatic alarms use minute precision")
        settings = AlarmSettings(
            time.hour,
            time.minute,
            call.data["days"],
            {"vibrate": 1, "zero_g": 2, "memory_1": 3}[call.data["wake"]],
            call.data["enabled"],
        )
        # Validate the complete parameter domain even when every target is offline.
        app.alarm(
            settings.hour,
            settings.minute,
            settings.days,
            settings.type_code,
            settings.enabled,
            now=dt_util.now(),
        )
    elif any(key in call.data for key in fields):
        raise ServiceValidationError("Alarm fields apply only to set")
    check_initial()
    # Toggle needs an existing current report. Refuse it on every offline target
    # before a preflight can open another connection and emit startup writes.
    if operation == "toggle":
        if len({child.operation_identity for child in physical if id(child) in sequential}) > 1:
            raise ServiceValidationError(
                "Toggle requires current reports on concurrently live receivers"
            )
        for child in runtimes:
            controller = child.capability_controller
            assert isinstance(controller, UltramaticController)
            with controller_side_scope(child):
                controller.prepare_alarm(None, toggle=True)

    def prepare(controller: UltramaticController) -> None:
        if operation != "query":
            plan = controller.prepare_alarm(settings, toggle=operation == "toggle")
            plans[controller, plan.side] = plan
        ready[controller] = _Fence(
            controller, controller.session_token, controller.operation_generation
        )

    # The one-link cycle intentionally drops the other live controller. Retain
    # its known capabilities for whole-selection ownership checks, not writes.
    for child in physical:
        if id(child) in sequential:
            child.cache_capability_controller()

    # Earlier targets must remain live while later targets execute. The shared
    # hold pauses only idle disconnects and restores normal timers on every exit.
    with ExitStack() as connections:
        held: set[int] = set()
        for child in physical:
            if id(child) not in sequential and child.operation_identity not in held:
                connections.enter_context(child.hold_command_connection())
                held.add(child.operation_identity)

        # Capability validation is offline-safe; link-bound plans must use the live
        # physical controller, never the client-free capability instance.
        preflighted = await _preflight_capability(
            targets, UltramaticController, "Ultramatic alarms"
        )
        try:
            check_initial()
            for parent, side in targets:
                for child in _command_targets(parent, side):
                    if id(child) in sequential:
                        continue  # The shared one-link topology connects each side in its turn.
                    check_initial()
                    preflighted.append((parent, child))
                    if not await child.async_ensure_connected(reset_timer=False):
                        raise ServiceValidationError("Ultramatic receiver is unavailable")
                    check_initial()
                    controller = child.controller
                    if not isinstance(controller, UltramaticController):
                        raise ServiceValidationError("Ultramatic live controller is unavailable")
                    await controller.async_validate_linked_readiness()
                    check_initial()
                    with controller_side_scope(child):
                        prepare(controller)
            for child in combined:
                check_initial()
                controller = child.controller
                if not isinstance(controller, UltramaticController) or controller not in ready:
                    raise ServiceValidationError("Ultramatic combined receiver was not validated")
                with controller_side_scope(child):
                    prepare(controller)
        except BaseException:
            await _release_preflighted(preflighted)
            raise

        def check_all() -> None:
            check_owners()
            for child in runtimes:
                if id(child) in sequential:
                    continue
                controller = child.controller
                if not isinstance(controller, UltramaticController) or controller not in ready:
                    raise ServiceValidationError(
                        "Ultramatic controller was replaced after validation"
                    )
                ready[controller].check()
                if operation != "query":
                    with controller_side_scope(child):
                        plan = plans.get((controller, controller._side()))
                        if plan is None:
                            raise ServiceValidationError(
                                "Ultramatic target side changed after validation"
                            )
                        controller.validate_plan(plan)

        async def apply(controller: UltramaticController) -> None:
            check_all()
            if controller not in ready:
                if not any(
                    id(child) in sequential and child.controller is controller for child in physical
                ):
                    raise ServiceValidationError(
                        "Ultramatic command reached an unvalidated receiver"
                    )
                await controller.async_validate_linked_readiness()
                check_all()
                prepare(controller)
            # _sequence advances once synchronously before its first await. Admit
            # precisely that increment so concurrent siblings cannot invalidate one
            # another, without adopting any external command's generation.
            fence = ready[controller]
            fence.check()
            ready[controller] = _Fence(controller, fence.link, fence.generation + 1)
            if operation == "query":
                await controller.query("alarm", validate=check_all)
            else:
                plan = plans.get((controller, controller._side()))
                if plan is None:
                    raise ServiceValidationError(
                        "Ultramatic alarm plan no longer matches the target"
                    )
                await controller.set_alarm(plan, validate=check_all)
            ready[controller].check()

        try:
            check_all()
        except BaseException:
            await _release_preflighted(preflighted)
            raise
        for index, (target, admission) in enumerate(zip(targets, admissions, strict=True)):
            dispatch_index = index
            await _execute_preflighted(
                [target],
                preflighted,
                _family_command(UltramaticController, "Ultramatic alarms", apply),
                cancel_running=True,
                resource="*",
                admissions=[admission],
            )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "ultramatic_alarm",
        handle_alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("operation"): vol.In(("set", "toggle", "query")),
                vol.Optional("time"): cv.time,
                vol.Optional("days"): vol.All(_integer, vol.Range(min=0, max=255)),
                vol.Optional("wake"): vol.In(("vibrate", "zero_g", "memory_1")),
                vol.Optional("enabled"): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
