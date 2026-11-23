"""All-target Snore Monitor alarm admission before the lazy import awaits."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...alarm import WEEKDAYS
from ...command_scheduler import current_command_context
from ...const import (
    CONF_PRODUCT_TYPE,
    DOMAIN,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
)
from ...errors import invalid
from ...import_executor import async_import_modules
from ...profile_id import profile_route_from_data

# The app's alarm action list sends one of five codes, whose physical effects
# are not established. Only the first, the app's default, is offered.
DEFAULT_ALARM_ACTION = 0


def week_mask(weekdays: list[str]) -> int:
    """The app's repeat bits: 1 Sunday, 2 Monday ... 64 Saturday; none is a one-time alarm."""
    return sum(1 << ((WEEKDAYS.index(day) + 1) % 7) for day in set(weekdays))

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...command_scheduler import CommandHandle, CommandRecord
    from ...coordinator import AdjustableBedCoordinator
    from ...paired_topology import SequentialCycle
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
    live: bool

    @classmethod
    def capture(cls, receiver: AdjustableBedCoordinator) -> _Session:
        return cls(
            receiver.client,
            receiver.controller,
            receiver.connection_generation,
            getattr(receiver.controller, "_generation", None),
            receiver.client is not None and receiver.client.is_connected,
        )

    def matches(self, receiver: AdjustableBedCoordinator) -> bool:
        current = self.capture(receiver)
        return (
            current.client is self.client
            and current.controller is self.controller
            and current.generation == self.generation
            and current.notifications == self.notifications
            and current.live == self.live
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
    released: _Session | None = None

    @classmethod
    def capture(cls, receiver: AdjustableBedCoordinator) -> _Owner:
        scheduler = receiver.command_scheduler
        return cls(
            receiver,
            _route(receiver),
            scheduler.token,
            receiver.stop_epoch,
            scheduler.recent_records,
            scheduler.active,
            _Session.capture(receiver),
        )

    def check_route(self) -> None:
        if (
            _route(self.receiver) != self.route
            or self.receiver.command_scheduler.token is not self.token
            or self.receiver.stop_epoch != self.stop_epoch
        ):
            raise invalid("bed_changed")

    def check_session(
        self,
        *,
        planned_switch: bool = False,
        bind_switch: bool = False,
        switch_task: asyncio.Task[object] | None = None,
    ) -> None:
        self.check_route()
        expected = self.connected or self.released or self.initial
        if expected.matches(self.receiver):
            return
        if (
            planned_switch
            and self.released is None
            and self.connected is None
            and expected.live
            and expected.client is not None
            and not expected.client.is_connected
            and expected.controller is not None
            and isinstance(expected.notifications, int)
            and getattr(expected.controller, "_generation", 0) > expected.notifications
            and self.receiver.client is None
            and self.receiver.controller is None
            and self.receiver.connection_generation == expected.generation
            and self.receiver.last_disconnect_reason == "sequential_switch"
        ):
            # Only the native one-link cycle may retire this captured session.
            self.released = _Session.capture(self.receiver)
            return
        baseline = self.released or self.initial
        context = current_command_context()
        prepared_switch = (
            bind_switch
            and self.released is not None
            and context is not None
            and context.scheduler_token is self.token
            and switch_task is not None
            and self.receiver.connection_creator_task is switch_task
        )
        # An admitted offline receiver can construct its first live session.
        # Once bound, later reconnects/replacements are not the admitted owner.
        if (
            (self.initial.controller is None or prepared_switch)
            and self.connected is None
            and self.receiver.controller is not None
            and self.receiver.client is not None
            and self.receiver.client.is_connected
            and self.receiver.connection_generation == baseline.generation + 1
        ):
            self.connected = _Session.capture(self.receiver)
            return
        raise invalid("bed_changed")


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
        call_task = asyncio.current_task()
        targets = _call_targets(call)
        admissions = [_capture_command_admission(parent, side) for parent, side in targets]
        # Capture every physical connection/controller before the first await.
        owners: dict[AdjustableBedCoordinator, _Owner] = {}
        roster = []
        linked = []
        sequential = {}
        for parent, side in targets:
            physical = tuple(_command_targets(parent, side))
            for child in physical:
                if not isinstance(child, AdjustableBedCoordinator):
                    raise invalid("action_for_other_beds", beds="Snore Monitor beds")
                owners.setdefault(child, _Owner.capture(child))
            roster.append(physical)
            if (
                isinstance(parent, PairedBedCoordinator)
                and parent.connection_mode == PAIR_CONNECTION_MODE_CONCURRENT
                and len(physical) > 1
            ):
                linked.append((parent, physical, asyncio.Event()))
            elif (
                isinstance(parent, PairedBedCoordinator)
                and parent.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
                and len(physical) > 1
            ):
                sequential.update((child, parent) for child in physical)
        await async_import_modules(hass, "beds.onlysnore.controller")
        from .controller import AlarmArguments, OnlySnoreController

        def check_roster() -> None:
            if any(
                tuple(_command_targets(parent, side)) != admitted
                for (parent, side), admitted in zip(targets, roster, strict=True)
            ):
                raise invalid("bed_changed")
            if any(
                parent.connection_mode != PAIR_CONNECTION_MODE_CONCURRENT
                for parent, _physical, _ready in linked
            ):
                raise invalid("bed_changed")
            if any(
                parent.connection_mode != PAIR_CONNECTION_MODE_SEQUENTIAL
                for parent in sequential.values()
            ):
                raise invalid("bed_changed")

        check_roster()
        for owner in owners.values():
            owner.check_route()
            if (
                not owner.initial.matches(owner.receiver)
                or owner.receiver.command_scheduler.recent_records != owner.records
                or owner.receiver.command_scheduler.active is not owner.active
            ):
                raise invalid("bed_changed")
        if any(
            _capture_command_admission(parent, side) != admission
            for (parent, side), admission in zip(targets, admissions, strict=True)
        ):
            raise invalid("bed_changed")
        time = call.data["time"]
        if time.second or time.microsecond:
            raise invalid("alarm_time_whole_minutes")
        args: AlarmArguments = {
            "slot": call.data["slot"],
            "enabled": call.data["enabled"],
            "hour": time.hour,
            "minute": time.minute,
            "week": week_mask(call.data["weekdays"]),
            "type_index": DEFAULT_ALARM_ACTION,
            "soft": call.data["soft_wake"],
        }
        validated: dict[AdjustableBedCoordinator, OnlySnoreController] = {}
        prepared: set[AdjustableBedCoordinator] = set()
        mutation_started = False

        def cycle_for(owner: _Owner) -> SequentialCycle | None:
            parent = sequential.get(owner.receiver)
            if parent is None:
                return None
            cycle = parent.sequential_cycle
            if cycle is None or cycle.task is not call_task:
                return None
            if not parent.cycle_is_current(cycle):
                raise invalid("bed_changed")
            return cycle

        def owner_for(ctrl: OnlySnoreController, *, bind_switch: bool = False) -> _Owner:
            owner = owners.get(ctrl._coordinator)
            if owner is None:
                raise invalid("bed_changed")
            parent = sequential.get(owner.receiver)
            cycle = cycle_for(owner)
            owner.check_session(
                planned_switch=cycle is not None
                and parent is not None
                and parent.is_admitted_child(owner.receiver),
                bind_switch=bind_switch,
                switch_task=cycle.task if cycle is not None else None,
            )
            product = owner.route[3]
            if isinstance(product, str) and ctrl.model != product:
                raise invalid("bed_changed")
            return owner

        def validate(ctrl: OnlySnoreController) -> None:
            owner = owner_for(ctrl)
            ctrl.alarm_frame(**args)
            validated[owner.receiver] = ctrl

        def recheck(admitted: _Owner, *, bind_switch: bool = False) -> None:
            candidate = admitted.receiver.controller or validated.get(admitted.receiver)
            if not isinstance(candidate, OnlySnoreController):
                raise invalid("bed_changed")
            if candidate._coordinator is not admitted.receiver:
                raise invalid("bed_changed")
            owner_for(candidate, bind_switch=bind_switch)
            candidate.alarm_frame(**args)

        async def execute(ctrl: OnlySnoreController) -> None:
            nonlocal mutation_started
            check_roster()
            owner = owner_for(ctrl, bind_switch=True)
            if owner.receiver.controller is not ctrl:
                raise invalid("bed_changed")
            parent = sequential.get(owner.receiver)
            if parent is not None and cycle_for(owner) is not None:
                for peer in owners.values():
                    if sequential.get(peer.receiver) is parent and peer.receiver not in prepared:
                        recheck(peer, bind_switch=peer is owner)
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
            owner_for(ctrl, bind_switch=True)
            if not mutation_started:
                # Recheck the whole immutable selection after scheduler/connect
                # waits, before the first requested mutation on any receiver.
                for admitted in owners.values():
                    recheck(admitted)
            mutation_started = True
            await ctrl.set_alarm(**args)

        await _preflight_and_execute(
            targets,
            OnlySnoreController,
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
                vol.Optional("weekdays", default=[]): vol.All(
                    cv.ensure_list, [vol.In(WEEKDAYS)]
                ),
                vol.Optional("soft_wake", default=False): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
