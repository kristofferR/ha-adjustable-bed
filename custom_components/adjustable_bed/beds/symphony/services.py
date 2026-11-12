"""Typed Symphony actions, with live all-target admission before requested writes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypedDict

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...command_scheduler import PreparedCommandInvalidated
from ...const import DOMAIN, PAIR_CONNECTION_MODE_SEQUENTIAL, SIDE_BOTH
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator

if TYPE_CHECKING:
    from ...beds.base import BedController
    from ...paired_coordinator import BedChild
    from .controller import SymphonyController


class AlarmFields(TypedDict):
    enabled: bool
    hour: int
    minute: int
    week: int
    mode: str


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _execute_preflighted,
        _family_command,
        _get_controller_for_service,
        _release_preflighted,
        controller_side_scope,
    )

    async def dispatch(
        call: ServiceCall,
        validate: Callable[[SymphonyController], None],
        execute: Callable[[SymphonyController], Awaitable[None]],
        *,
        alarm: bool = False,
        alarm_sides: dict[str, tuple[int, ...]] | None = None,
    ) -> None:
        await async_import_modules(call.hass, "beds.symphony.controller")
        from .controller import SymphonyController

        targets = _call_targets(call)
        admissions = [
            _capture_command_admission(coordinator, side) for coordinator, side in targets
        ]
        opened = []
        physical = [
            target
            for coordinator, side in targets
            for target in _command_targets(coordinator, side)
        ]
        rehydrate: set[str] = set()
        completed: set[str] = set()

        def admit_all(*, check_pair: bool = True) -> bool:
            for (coordinator, side), admission in zip(targets, admissions, strict=True):
                if isinstance(coordinator, PairedBedCoordinator):
                    invalidated = check_pair and coordinator._pair_admission_was_cancelled(
                        coordinator._targets_for(side),
                        admission.resources,
                        admission.expected_pair_generations,
                        admission.expected_stop_epochs,
                    )
                    invalidated = invalidated or any(
                        child.stop_epoch != admission.expected_stop_epochs[target_side]
                        for target_side, child in coordinator._targets_for(side)
                    )
                else:
                    invalidated = (
                        coordinator.stop_epoch != admission.expected_stop_epochs[SIDE_BOTH]
                    )
                if invalidated:
                    raise PreparedCommandInvalidated(
                        "Symphony request was stopped during preflight"
                    )
            return True

        async def preflight(target: BedChild) -> None:
            admit_all()
            controller = await _get_controller_for_service(target)
            opened.append((target, target))
            if not isinstance(controller, SymphonyController):
                raise ValueError("Every target must use Symphony Sleep Sense")
            if alarm:
                assert alarm_sides is not None
                address = target.address.upper()
                alarm_sides[address] = tuple(
                    dict.fromkeys(
                        2
                        if member.controller_side == "right"
                        else 1
                        if member.controller_side == "left"
                        else controller.app.side
                        for member in physical
                        if member.address.upper() == address
                    )
                )

                async def prepare(current: BedController) -> None:
                    if not isinstance(current, SymphonyController):
                        raise ValueError("The Symphony profile changed")
                    await current.prepare_alarm()

                await target.async_execute_controller_query(
                    prepare, run_if=admit_all, skip_disconnect=True
                )
            with controller_side_scope(target):
                validate(controller)

        async def execute_current(controller: SymphonyController) -> None:
            address = controller._coordinator.address.upper()
            if alarm:
                if address in completed:
                    return
                if address in rehydrate:
                    # Sequential switching retired the preflight controller.
                    # Hydrate under the executing topology's connection lane.
                    await controller.prepare_alarm()
                admit_all(check_pair=False)
                validate(controller)
            await execute(controller)
            if alarm:
                completed.add(address)

        try:
            # Offline factory instances carry static models, not current alarm
            # caches or firmware. Connect each physical target before rejecting
            # a live capability, while preserving the original STOP admissions.
            for (coordinator, side), admission in zip(targets, admissions, strict=True):
                sequential = (
                    isinstance(coordinator, PairedBedCoordinator)
                    and coordinator.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
                )
                if sequential:
                    assert isinstance(coordinator, PairedBedCoordinator)
                    rehydrate.update(t.address.upper() for t in _command_targets(coordinator, side))
                    await coordinator.async_run_child_operation(
                        "symphony_preflight",
                        preflight,
                        side=side,
                        cancel_running=False,
                        resources=admission.resources,
                        expected_pair_generations=admission.expected_pair_generations,
                        expected_stop_epochs=admission.expected_stop_epochs,
                    )
                else:
                    for target in _command_targets(coordinator, side):
                        await preflight(target)
            admit_all()
            await _execute_preflighted(
                targets,
                opened,
                _family_command(SymphonyController, "Symphony Sleep Sense", execute_current),
                cancel_running=True,
                resource=None,
                admissions=admissions,
            )
        except ValueError as error:
            raise ServiceValidationError(str(error)) from error
        finally:
            await _release_preflighted(opened)

    async def set_alarm(call: ServiceCall) -> None:
        from ...profiles.symphony import alarm_week

        now = dt_util.now()
        time = call.data.get("time")
        enabled = call.data["enabled"]
        if enabled and time is None:
            raise ServiceValidationError("Choose the alarm time")
        if time is not None and (time.second or time.microsecond):
            raise ServiceValidationError("Symphony alarms use minute precision")
        hour, minute = (time.hour, time.minute) if time is not None else (0, 0)
        weekdays = call.data["weekdays"]
        mask = 128 | sum(1 << (day % 7) for day in set(weekdays)) if weekdays else 0
        requested = now.replace(hour=hour, minute=minute)
        week = alarm_week(mask, requested, now)
        sides: dict[str, tuple[int, ...]] = {}

        def fields(value: SymphonyController) -> AlarmFields:
            return {
                "enabled": enabled,
                "hour": hour,
                "minute": minute,
                "week": week,
                "mode": call.data.get("wake_mode", value.app.alarm_modes[0]),
            }

        def validate(value: SymphonyController) -> None:
            value.alarm_frames(sides=sides[value._coordinator.address.upper()], **fields(value))

        async def execute(value: SymphonyController) -> None:
            await value.set_alarm(sides=sides[value._coordinator.address.upper()], **fields(value))

        await dispatch(call, validate, execute, alarm=True, alarm_sides=sides)

    async def set_light(call: ServiceCall) -> None:
        def validate(value: SymphonyController) -> None:
            value.validate_light(call.data["color"], call.data["brightness"])

        async def execute(value: SymphonyController) -> None:
            await value.set_light(color=call.data["color"], brightness=call.data["brightness"])

        await dispatch(call, validate, execute)

    async def snore(call: ServiceCall) -> None:
        from ...profiles.symphony import anti_snore

        fields = {key: call.data[key] for key in ("enabled", "axis", "strength", "demo")}

        def validate(value: SymphonyController) -> None:
            value.validate_command()
            anti_snore(value.app, **fields)

        async def execute(value: SymphonyController) -> None:
            await value.configure_snore(**fields)

        await dispatch(call, validate, execute)

    async def preset(call: ServiceCall) -> None:
        from ...profiles.symphony import preset as preset_frame

        def validate(value: SymphonyController) -> None:
            value.validate_command()
            preset_frame(value.app, call.data["preset"], 1, save=call.data["save"])

        async def execute(value: SymphonyController) -> None:
            await value.recall(call.data["preset"], save=call.data["save"])

        await dispatch(call, validate, execute)

    base = {vol.Required("device_id"): DEVICE_IDS, **SIDE_FIELD}
    hass.services.async_register(
        DOMAIN,
        "symphony_set_alarm",
        set_alarm,
        schema=vol.Schema(
            {
                **base,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("weekdays", default=[]): [
                    vol.All(vol.Coerce(int), vol.Range(min=1, max=7))
                ],
                vol.Optional("wake_mode"): vol.In(
                    (
                        "zero_g",
                        "flat",
                        "memory_1",
                        "memory_2",
                        "massage",
                        "reading",
                        "tv",
                        "anti_snore",
                        "light",
                    )
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "symphony_set_light",
        set_light,
        schema=vol.Schema(
            {
                **base,
                vol.Required("color"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
                vol.Required("brightness"): vol.All(vol.Coerce(int), vol.Range(min=20, max=80)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "symphony_anti_snore",
        snore,
        schema=vol.Schema(
            {
                **base,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("axis", default="head"): vol.In(("head", "elevation")),
                vol.Optional("strength", default=1): vol.All(vol.Coerce(int), vol.In((1, 2, 3, 6))),
                vol.Optional("demo", default=False): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "symphony_preset",
        preset,
        schema=vol.Schema(
            {
                **base,
                vol.Required("preset"): vol.In(
                    ("zero_g", "flat", "memory_1", "memory_2", "reading", "tv", "anti_snore")
                ),
                vol.Optional("save", default=False): cv.boolean,
            }
        ),
    )
