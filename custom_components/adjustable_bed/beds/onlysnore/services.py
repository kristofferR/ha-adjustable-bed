"""All-target Snore Monitor alarm admission before the lazy import awaits."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import CONF_PRODUCT_TYPE, DOMAIN, PAIR_CONNECTION_MODE_CONCURRENT
from ...import_executor import async_import_modules
from ...profile_id import profile_route_from_data

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...command_scheduler import CommandHandle, CommandRecord
    from ...coordinator import AdjustableBedCoordinator
    from ..base import BedController


def _route(receiver: AdjustableBedCoordinator) -> tuple[str, str, str, object]:
    return (
        receiver.address,
        receiver.bed_type,
        profile_route_from_data(receiver.entry.data).profile_id,
        receiver.entry.data.get(CONF_PRODUCT_TYPE),
    )


@dataclass(frozen=True)
class _Session:
    client: BleakClient | None
    controller: BedController | None
    generation: int
    notifications: object

    @classmethod
    def capture(cls, receiver: AdjustableBedCoordinator) -> _Session:
        return cls(
            receiver.client,
            receiver.controller,
            receiver._position_connection_generation,
            getattr(receiver.controller, "_generation", None),
        )

    def matches(self, receiver: AdjustableBedCoordinator) -> bool:
        current = self.capture(receiver)
        return (
            current.client is self.client
            and current.controller is self.controller
            and current.generation == self.generation
            and current.notifications == self.notifications
        )


@dataclass
class _Owner:
    receiver: AdjustableBedCoordinator
    route: tuple[str, str, str, object]
    token: object
    stop_epoch: int
    records: tuple[CommandRecord, ...]
    active: CommandHandle | None
    initial: _Session
    connected: _Session | None = None

    @classmethod
    def capture(cls, receiver: AdjustableBedCoordinator) -> _Owner:
        scheduler = receiver._command_scheduler
        return cls(
            receiver,
            _route(receiver),
            scheduler.token,
            receiver.stop_epoch,
            scheduler.recent_records,
            scheduler._active,
            _Session.capture(receiver),
        )

    def check_route(self) -> None:
        if (
            _route(self.receiver) != self.route
            or self.receiver._command_scheduler.token is not self.token
            or self.receiver.stop_epoch != self.stop_epoch
        ):
            raise ServiceValidationError("BED route, product or STOP ownership changed")

    def check_session(self) -> None:
        self.check_route()
        expected = self.connected or self.initial
        if expected.matches(self.receiver):
            return
        # An admitted offline receiver can construct its first live session.
        # Once bound, later reconnects/replacements are not the admitted owner.
        if (
            self.initial.controller is None
            and self.connected is None
            and self.receiver.controller is not None
            and self.receiver.client is not None
            and self.receiver.client.is_connected
            and self.receiver._position_connection_generation == self.initial.generation + 1
        ):
            self.connected = _Session.capture(self.receiver)
            return
        raise ServiceValidationError("BED controller or connection changed after alarm preflight")


def register_services(hass: HomeAssistant) -> None:
    from ...coordinator import AdjustableBedCoordinator
    from ...paired_coordinator import PairedBedCoordinator
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _command_targets,
        _preflight_and_execute,
    )

    async def alarm(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [_capture_command_admission(parent, side) for parent, side in targets]
        # Capture every physical connection/controller before the first await.
        owners: dict[AdjustableBedCoordinator, _Owner] = {}
        roster = []
        linked = []
        for parent, side in targets:
            physical = tuple(_command_targets(parent, side))
            for child in physical:
                if not isinstance(child, AdjustableBedCoordinator):
                    raise ServiceValidationError(
                        "Snore Monitor alarms require physical BED receivers"
                    )
                owners.setdefault(child, _Owner.capture(child))
            roster.append(physical)
            if (
                isinstance(parent, PairedBedCoordinator)
                and parent.connection_mode == PAIR_CONNECTION_MODE_CONCURRENT
                and len(physical) > 1
            ):
                linked.append((parent, physical, asyncio.Event()))
        await async_import_modules(hass, "beds.onlysnore.controller")
        from .controller import AlarmArguments, OnlySnoreController

        def check_roster() -> None:
            if any(
                tuple(_command_targets(parent, side)) != admitted
                for (parent, side), admitted in zip(targets, roster, strict=True)
            ):
                raise ServiceValidationError("BED target roster changed during alarm admission")
            if any(
                parent.connection_mode != PAIR_CONNECTION_MODE_CONCURRENT
                for parent, _physical, _ready in linked
            ):
                raise ServiceValidationError(
                    "BED connection topology changed during alarm admission"
                )

        check_roster()
        for owner in owners.values():
            owner.check_route()
            if (
                not owner.initial.matches(owner.receiver)
                or owner.receiver._command_scheduler.recent_records != owner.records
                or owner.receiver._command_scheduler._active is not owner.active
            ):
                raise ServiceValidationError("BED ownership changed during alarm admission")
        if any(
            _capture_command_admission(parent, side) != admission
            for (parent, side), admission in zip(targets, admissions, strict=True)
        ):
            raise ServiceValidationError(
                "BED STOP or pair ownership changed during alarm admission"
            )
        time = call.data["time"]
        if time.second or time.microsecond:
            raise ServiceValidationError("BED alarms use minute precision")
        args: AlarmArguments = {
            "slot": call.data["slot"],
            "enabled": call.data["enabled"],
            "hour": time.hour,
            "minute": time.minute,
            "week": call.data["week_mask"],
            "type_index": call.data["action_index"],
            "soft": call.data["soft_wake"],
        }
        validated: dict[AdjustableBedCoordinator, OnlySnoreController] = {}
        prepared: set[AdjustableBedCoordinator] = set()
        mutation_started = False

        def owner_for(ctrl: OnlySnoreController) -> _Owner:
            owner = owners.get(ctrl._coordinator)
            if owner is None:
                raise ServiceValidationError("BED controller belongs to another physical receiver")
            owner.check_session()
            product = owner.route[3]
            if isinstance(product, str) and ctrl.model != product:
                raise ServiceValidationError("BED controller product changed after alarm admission")
            return owner

        def validate(ctrl: OnlySnoreController) -> None:
            owner = owner_for(ctrl)
            ctrl.alarm_frame(**args)
            validated[owner.receiver] = ctrl

        async def execute(ctrl: OnlySnoreController) -> None:
            nonlocal mutation_started
            check_roster()
            owner = owner_for(ctrl)
            if owner.receiver.controller is not ctrl:
                raise ServiceValidationError("BED controller changed after alarm preflight")
            prepared.add(owner.receiver)
            for _parent, physical, ready in linked:
                if owner.receiver not in physical:
                    continue
                # Both physical schedulers must finish their own connection
                # preparation before either checks peer sessions or mutates.
                if all(child in prepared for child in physical):
                    ready.set()
                await ready.wait()
            check_roster()
            owner_for(ctrl)
            if not mutation_started:
                # Recheck the whole immutable selection after scheduler/connect
                # waits, before the first requested mutation on any receiver.
                for admitted in owners.values():
                    admitted.check_session()
                    candidate = admitted.receiver.controller or validated.get(admitted.receiver)
                    if not isinstance(candidate, OnlySnoreController):
                        raise ServiceValidationError("BED alarm preflight is incomplete")
                    if candidate._coordinator is not admitted.receiver:
                        raise ServiceValidationError(
                            "BED controller belongs to another physical receiver"
                        )
                    owner_for(candidate)
                    candidate.alarm_frame(**args)
            mutation_started = True
            await ctrl.set_alarm(**args)

        await _preflight_and_execute(
            targets,
            OnlySnoreController,
            "Snore Monitor BED alarms",
            execute,
            validate=validate,
            cancel_running=True,
            resource=None,
            admissions=admissions,
        )

    hass.services.async_register(
        DOMAIN,
        "onlysnore_set_alarm",
        alarm,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("time"): cv.time,
                vol.Optional("slot", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
                vol.Optional("enabled", default=True): cv.boolean,
                vol.Optional("week_mask", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=255)
                ),
                vol.Optional("action_index", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=4)
                ),
                vol.Optional("soft_wake", default=False): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
