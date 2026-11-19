"""Physical cohort and one-use sequential session transfers for app services."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bleak import BleakClient
from homeassistant.exceptions import ServiceValidationError

from ...command_scheduler import CommandContext, _first_set, current_command_context
from ...const import DOMAIN
from ...coordinator import AdjustableBedCoordinator
from ...paired_coordinator import PairedBedCoordinator
from ...paired_topology import SequentialTwoLinkTopology
from ...services import BedTarget, _CommandAdmission
from ..base import BedController
from .betterliving2_admission import SELECTION

if TYPE_CHECKING:
    from .betterliving2 import BetterLiving2Controller


def _selection_error(reason: str) -> ServiceValidationError:
    return ServiceValidationError(
        reason,
        translation_domain=DOMAIN,
        translation_key="betterliving2_selection_changed",
        translation_placeholders={"reason": reason},
    )


class PreparationCancelled(asyncio.CancelledError):
    """Retire a captured operation through the native cancellation cleanup path."""

    def __init__(self, selection: Selection, child: AdjustableBedCoordinator) -> None:
        super().__init__("Captured BetterLiving2 preparation cancelled")
        self.selection = selection
        self.child = child


@dataclass(slots=True)
class Batch:
    parent: AdjustableBedCoordinator | PairedBedCoordinator
    side: str
    admission: _CommandAdmission
    data: Mapping[str, object]
    roster: tuple[tuple[str, AdjustableBedCoordinator], ...]
    topology: object | None
    sequential: bool
    preemption_admitted: bool = False
    dispatched: bool = False
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    aborted: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(slots=True)
class Owner:
    child: AdjustableBedCoordinator
    batch: Batch
    data: Mapping[str, object]
    address: str
    stop_epoch: int
    scheduler_token: object
    controller: BedController | None
    client: BleakClient | None
    link: object | None
    binding_allowed: bool
    retiring: tuple[BedController, BleakClient] | None = None
    started: bool = False
    preparing: bool = False
    ready: bool = False
    context: CommandContext | None = None


class Selection:
    """Capture without awaiting; no session may replace a queued live link."""

    def __init__(
        self,
        targets: list[tuple[BedTarget, str]],
        admissions: Sequence[_CommandAdmission],
        *,
        required_wire: str | None = None,
    ) -> None:
        self.active = True
        self.invalid = False
        self.batches: list[Batch] = []
        self.owners: dict[int, Owner] = {}
        for (parent, side), admission in zip(targets, admissions, strict=True):
            if not isinstance(parent, (AdjustableBedCoordinator, PairedBedCoordinator)):
                raise _selection_error("BetterLiving2 requires physical receiver targets")
            paired = isinstance(parent, PairedBedCoordinator)
            members = parent._targets_for(side) if paired else [("both", parent)]
            roster = tuple(parent.children.items()) if paired else (("both", parent),)
            if any(not isinstance(child, AdjustableBedCoordinator) for _, child in roster):
                raise _selection_error("BetterLiving2 requires physical receiver targets")
            physical = tuple(
                (name, child)
                for name, child in roster
                if isinstance(child, AdjustableBedCoordinator)
            )
            batch = Batch(
                parent,
                side,
                admission,
                deepcopy(dict(parent.entry.data)),
                physical,
                parent._topology if paired else None,
                paired and isinstance(parent._topology, SequentialTwoLinkTopology),
            )
            self.batches.append(batch)
            for _, child in members:
                if not isinstance(child, AdjustableBedCoordinator):
                    raise _selection_error("BetterLiving2 has no one-address side selector")
                data = deepcopy(dict(child.entry.data))
                wire = data.get("protocol_variant")
                if (
                    child.bed_type != "betterliving2"
                    or not isinstance(wire, str)
                    or wire not in {"p1", "p2", "p3"}
                    or str(data.get("product_type")) not in {"2", "3"}
                    or required_wire is not None
                    and wire != required_wire
                ):
                    raise _selection_error("Choose an exact supported BetterLiving2 profile")
                controller, client = child._controller, child.client
                self.owners[id(child)] = Owner(
                    child,
                    batch,
                    data,
                    child.address.upper(),
                    child.stop_epoch,
                    child._command_scheduler.token,
                    controller,
                    client,
                    getattr(controller, "_link", None),
                    not child.is_connected,
                )
        self.check()

    @contextmanager
    def scope(self) -> Iterator[None]:
        token = SELECTION.set(self)
        try:
            yield
        finally:
            self.active = False
            SELECTION.reset(token)

    @contextmanager
    def bind_operation(self) -> Iterator[None]:
        """Bind this admission in the actual scheduler worker, without retiring it."""
        token = SELECTION.set(self)
        try:
            yield
        finally:
            SELECTION.reset(token)

    def begin(self, child: AdjustableBedCoordinator) -> None:
        owner = self.owners.get(id(child))
        if owner is None or not self._owned(owner.batch):
            raise _selection_error("BetterLiving2 preparation was not admitted")
        context = current_command_context()
        if context is None or context.scheduler_token is not owner.scheduler_token:
            raise _selection_error("BetterLiving2 preparation has no owned reservation")
        if owner.context is not None and owner.context is not context:
            raise _selection_error("BetterLiving2 preparation reservation changed")
        owner.context = context
        self.check()
        if not owner.batch.sequential:
            peers = [other for other in self.owners.values() if other.batch is owner.batch]
            if len(peers) > 1:
                # Native Both has reserved every worker before committing any.
                # Capture even a peer whose operation callback has not run yet.
                for peer in peers:
                    handle = peer.child._command_scheduler._active
                    if (
                        handle is None
                        or context.group_id is None
                        or handle.context.group_id != context.group_id
                        or handle.context.scheduler_token is not peer.scheduler_token
                        or peer.context is not None
                        and peer.context is not handle.context
                    ):
                        raise _selection_error("BetterLiving2 peer reservation changed")
                    peer.context = handle.context
        owner.preparing = True

    def finished(self, child: AdjustableBedCoordinator) -> None:
        owner = self.owners.get(id(child))
        if owner is not None and not owner.ready:
            owner.batch.aborted.set()

    def _pair_generations(
        self, batch: Batch
    ) -> tuple[dict[str, tuple[int, ...]], dict[str, tuple[int, ...]]]:
        before = batch.admission.expected_pair_generations
        parent = batch.parent
        if not isinstance(parent, PairedBedCoordinator):
            return {}, before
        current = {
            side: parent._pair_cancel_generation(side, batch.admission.resources) for side in before
        }
        admitted = {side: (value[0] + 1,) for side, value in before.items()}
        if not batch.preemption_admitted and current == admitted and self._owned(batch):
            batch.preemption_admitted = True
        return current, admitted if batch.preemption_admitted else before

    def _owner_cancelled(self, owner: Owner) -> bool:
        if owner.child.stop_epoch != owner.stop_epoch or (
            owner.context is not None and owner.context.cancel_event.is_set()
        ):
            return True
        current, expected = self._pair_generations(owner.batch)
        return any(
            child is owner.child and side in expected and current.get(side) != expected[side]
            for side, child in owner.batch.roster
        )

    def _cohort_cancelled(self, batch: Batch) -> bool:
        return batch.aborted.is_set() or any(
            other.batch is batch and self._owner_cancelled(other) for other in self.owners.values()
        )

    def _dispatch_cancelled(self, owner: Owner) -> bool:
        return self._owner_cancelled(owner) or (
            not self._dispatched(owner) and self._cohort_cancelled(owner.batch)
        )

    def _dispatched(self, owner: Owner) -> bool:
        return owner.started if owner.batch.sequential else owner.batch.dispatched

    async def prepared(self, controller: BetterLiving2Controller) -> bool:
        """Complete the current cohort's owned startup before any user write."""
        owner = self.owners.get(id(controller._coordinator))
        if owner is not None and not owner.batch.sequential:
            if self._dispatch_cancelled(owner):
                # An expected peer STOP must not become a linked-operation failure.
                return False
        self.check(controller)
        owner = self.owners[id(controller._coordinator)]
        owner.ready = True
        owner.preparing = False
        batch = owner.batch
        if not batch.sequential:
            peers = [other for other in self.owners.values() if other.batch is batch]
            if all(other.ready for other in peers):
                batch.ready.set()
            cancel_events = [
                other.context.cancel_event for other in peers if other.context is not None
            ]
            await _first_set(batch.ready, batch.aborted, *cancel_events)
            if self._dispatch_cancelled(owner):
                return False
        self.check(controller)
        return True

    def _owned(self, batch: Batch) -> bool:
        context = current_command_context()
        selected = [owner.child for owner in self.owners.values() if owner.batch is batch]
        if context is not None and any(
            context.scheduler_token is child._command_scheduler.token for child in selected
        ):
            return True
        parent = batch.parent
        topology = parent._topology if isinstance(parent, PairedBedCoordinator) else None
        return (
            batch.sequential
            and isinstance(parent, PairedBedCoordinator)
            and isinstance(topology, SequentialTwoLinkTopology)
            and parent._admission.active_children == set(selected)
            and topology.command_lock.locked()
        )

    def _check(
        self,
        binding: Owner | None = None,
        receiver: Owner | None = None,
        *,
        releasing: bool = False,
        completed: bool = False,
    ) -> bool:
        if not self.active or self.invalid:
            raise _selection_error("BetterLiving2 selection was retired")
        context = current_command_context()
        current_owner = next(
            (
                owner
                for owner in self.owners.values()
                if context is not None and owner.context is context
            ),
            None,
        )
        if not completed and current_owner is not None and self._dispatch_cancelled(current_owner):
            raise PreparationCancelled(self, current_owner.child)
        scoped_stop = current_owner is not None and self._dispatched(current_owner)
        startup = receiver or binding
        execution_owner = current_owner or startup
        stop_batch = execution_owner.batch if execution_owner is not None else None
        cancelled_startup = None
        if (
            context is None
            and startup is not None
            and (releasing or startup.context is None and not startup.started)
            and startup.batch.sequential
            and self._owned(startup.batch)
            and self._cohort_cancelled(startup.batch)
        ):
            # The sequential native cycle connects before entering its child
            # worker. Let its post-connect cancellation check release this link.
            cancelled_startup = startup.batch
        # Completion checks only structure and sessions. Native admission and
        # dispatch guards enforce STOP, including for batches still queued.
        for batch in self.batches:
            parent = batch.parent
            if (
                parent.hass.data.get(DOMAIN, {}).get(parent.entry.entry_id) is not parent
                or dict(parent.entry.data) != batch.data
            ):
                raise _selection_error("BetterLiving2 entry/roster changed")
            if isinstance(parent, PairedBedCoordinator):
                if (
                    parent._topology is not batch.topology
                    or tuple(parent.children) != tuple(side for side, _ in batch.roster)
                    or any(parent.children.get(side) is not child for side, child in batch.roster)
                ):
                    raise _selection_error("BetterLiving2 physical roster changed")
                generations, expected = (
                    ({}, {})
                    if completed or stop_batch is not None and batch is not stop_batch
                    else self._pair_generations(batch)
                )
                sides = (
                    [
                        side
                        for side, child in batch.roster
                        if current_owner is not None and child is current_owner.child
                    ]
                    if scoped_stop
                    else ([] if batch is cancelled_startup else list(expected))
                )
                if any(generations.get(side) != expected.get(side) for side in sides):
                    raise _selection_error("BetterLiving2 paired admission changed")
        for owner in self.owners.values():
            child = owner.child
            if (
                child.address.upper() != owner.address
                or dict(child.entry.data) != owner.data
                or child._command_scheduler.token is not owner.scheduler_token
            ):
                raise _selection_error("BetterLiving2 physical owner/profile/STOP changed")
            if (
                not completed
                and (stop_batch is None or owner.batch is stop_batch)
                and owner.batch is not cancelled_startup
                and (not scoped_stop or owner is current_owner)
                and (
                    child.stop_epoch != owner.stop_epoch
                    or owner.context is not None
                    and owner.context.cancel_event.is_set()
                )
            ):
                raise _selection_error("BetterLiving2 physical STOP changed")
            if owner is binding:
                continue
            # An initially offline peer may still be establishing transport
            # during the native concurrent prepare barrier. It has no granted
            # controller session yet; every session must bind in connected().
            # No user action is dispatched until start() checks the whole set.
            if (
                owner.preparing
                and owner.binding_allowed
                and owner.controller is None
                and child._controller is None
            ):
                continue
            if owner.retiring is not None:
                old_controller, old_client = owner.retiring
                if child._controller is old_controller and child.client is old_client:
                    continue
                if (
                    not old_client.is_connected
                    and child._controller is None
                    and child.client is None
                ):
                    continue
                raise _selection_error("Unowned BetterLiving2 reconnect during selection")
            if (
                child._controller is not owner.controller
                or child.client is not owner.client
                or getattr(child._controller, "_link", None) is not owner.link
            ):
                raise _selection_error("BetterLiving2 captured session changed")
        return cancelled_startup is not None

    def completed(self, parent: PairedBedCoordinator, side: str) -> None:
        """Validate the recorded physical releases after native cleanup awaits."""
        batch = next(
            batch for batch in self.batches if batch.parent is parent and batch.side == side
        )
        if batch.sequential:
            self._check(completed=True)

    def check(self, controller: BetterLiving2Controller | None = None) -> None:
        cancelled_startup = self._check(
            receiver=self.owners.get(id(controller._coordinator))
            if controller is not None
            else None
        )
        if controller is not None:
            owner = self.owners.get(id(controller._coordinator))
            if (
                owner is None
                or owner.controller is not controller
                or owner.link is not controller._link
            ):
                raise _selection_error("BetterLiving2 dispatch session was not admitted")
            if cancelled_startup and controller._startup_cancel is not None:
                controller._startup_cancel.set()

    def stopped_before_preflight(self) -> bool:
        """Retain the native service contract for a STOP during its lazy import."""
        return any(owner.child.stop_epoch != owner.stop_epoch for owner in self.owners.values())

    def connected(self, controller: BetterLiving2Controller) -> None:
        owner = self.owners.get(id(controller._coordinator))
        if owner is None or not owner.binding_allowed or not self._owned(owner.batch):
            raise _selection_error("Unowned BetterLiving2 session replacement")
        if owner.retiring is not None and owner.retiring[1].is_connected:
            raise _selection_error("BetterLiving2 old physical link was not released")
        self._check(binding=owner)
        owner.controller, owner.client, owner.link = controller, controller.client, controller._link
        owner.retiring = None
        owner.binding_allowed = False
        self.check(controller)

    def releasing(self, controller: BetterLiving2Controller, reason: str) -> None:
        owner = self.owners.get(id(controller._coordinator))
        if owner is None or owner.controller is not controller or owner.client is None:
            return  # The coordinator also releases its offline capability copy.
        try:
            self._check(receiver=owner, releasing=True)
        except PreparationCancelled:
            return  # Expected owned cancellation must not retire the peer's cleanup.
        except ServiceValidationError:
            self.invalid = True
            return  # Never prevent physical disconnect/cleanup.
        if (
            reason != "sequential_switch"
            or not owner.batch.sequential
            or not self._owned(owner.batch)
        ):
            self.invalid = True
            return
        owner.retiring = (controller, owner.client)
        owner.binding_allowed = not owner.started

    def start(self, controller: BetterLiving2Controller) -> None:
        owner = self.owners[id(controller._coordinator)]
        if not owner.ready:
            raise _selection_error("BetterLiving2 session preparation is incomplete")
        self.check(controller)
        owner.started = True
        # Services call start immediately before dispatching the controller action.
        owner.batch.dispatched = True
