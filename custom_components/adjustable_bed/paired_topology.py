"""Topology strategies behind the paired-bed coordinator (#524).

``PairedBedCoordinator`` is the public facade. It composes one strategy per
physical topology, and that strategy owns target admission, locking,
prepare/commit, connection switching and STOP fan-out:

- ``ConcurrentTwoLinkTopology``: two receivers on two live links. Each side has
  its own lane, linked commands reserve both schedulers before either starts,
  and automatic mode can adopt sequential switching when one adapter slot
  cannot hold both links.
- ``SequentialTwoLinkTopology``: two receivers sharing one link lane. One side
  is connected, operated and disconnected before the next.
- ``SingleLinkSideAwareTopology``: one receiver serving logical left/right
  sides. A native Both stays one physical operation; otherwise the side frames
  run in turn on the one link.

Cancellation generations and the active group are shared by every strategy of
one pair (``PairAdmission``), so a command rerouted after a mode change keeps
the STOP ownership it captured. Child coordinators keep their BLE clients,
schedulers, authentication, timers and protocol controllers.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Collection, Coroutine, Iterator, Mapping
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError

from .command_scheduler import (
    CommandHandle,
    CommandOutcome,
    PreparedCommandInvalidated,
    command_resources,
)
from .const import (
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_SIDES,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .paired_coordinator import BedChild, PairedBedCoordinator, SingleAddressPairedCoordinator

_LOGGER = logging.getLogger(__name__)

type PairTarget = tuple[str, BedChild]
type ChildOperation = Callable[[BedChild], Coroutine[Any, Any, None]]
type ChildCommand = Callable[[BedController], Coroutine[Any, Any, None]]
type ConnectionAttemptCursor = tuple[int | None, Mapping[str, object] | None]
type GuardedDisconnect = Callable[[str], Coroutine[Any, Any, bool | None]]


class ConnectionModeChanged(Exception):
    """Signal that a command queued in concurrent mode must be rerouted."""


class PairedSideError(HomeAssistantError):
    """A side-targeted paired command failed.

    Carries the per-side outcomes so the service layer can surface a clean,
    translated message. By the time this is raised, the coordinator has already
    stopped every started side.
    """

    def __init__(self, action: str, side_errors: Mapping[str, BaseException]) -> None:
        self.action = action
        self.side_errors = dict(side_errors)
        sides = ", ".join(sorted(side_errors))
        super().__init__(f"Paired {action} failed on side(s): {sides}")


def merge_stop_errors(
    errors: Mapping[str, BaseException],
    stop_errors: Mapping[str, BaseException],
) -> dict[str, BaseException]:
    """Merge command errors with cleanup-STOP failures under distinct keys, so a
    combined failure surfaces both — a dropped STOP can leave a side moving."""
    merged: dict[str, BaseException] = dict(errors)
    for side, err in stop_errors.items():
        merged.setdefault(f"{side} (stop)", err)
    return merged


class PairAdmission:
    """Cancellation generations and the active group shared by one pair.

    Preemption: STOP bumps a side's generation so a movement still queued for
    that side is dropped instead of starting after the stop. ``active_children``
    are the sides executing a group or sequential cycle, so a ``cancel_running``
    command can cancel them before queueing instead of waiting out the pulse
    window.
    """

    def __init__(self) -> None:
        self.cancel_counter: dict[str, int] = {SIDE_LEFT: 0, SIDE_RIGHT: 0}
        self.global_cancel_counter: dict[str, int] = {SIDE_LEFT: 0, SIDE_RIGHT: 0}
        self.resource_cancel_counter: dict[str, dict[str, int]] = {
            SIDE_LEFT: {},
            SIDE_RIGHT: {},
        }
        self.active_children: set[BedChild] = set()
        self.active_group_resources: frozenset[str] = frozenset()

    def bump(self, side: str, resources: Collection[str]) -> None:
        """Invalidate queued commands whose resources overlap a newer request."""
        self.cancel_counter[side] += 1
        if "*" in resources:
            self.global_cancel_counter[side] += 1
            return
        resource_counters = self.resource_cancel_counter[side]
        for resource in resources:
            resource_counters[resource] = resource_counters.get(resource, 0) + 1

    def generation(self, side: str, resources: Collection[str]) -> tuple[int, ...]:
        """Snapshot cancellation state relevant to queued resources."""
        if "*" in resources:
            return (self.cancel_counter[side],)
        return (
            self.global_cancel_counter[side],
            *(
                self.resource_cancel_counter[side].get(resource, 0)
                for resource in sorted(resources)
            ),
        )

    def was_cancelled(
        self,
        side: str,
        resources: Collection[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
    ) -> bool:
        """Return whether a newer overlapping command invalidated this request."""
        return self.generation(side, resources) != entry_cancel[side]

    @staticmethod
    def stop_epochs_match(
        targets: Collection[PairTarget],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> bool:
        """Check the physical STOP epochs captured before paired hold admission."""
        if expected_stop_epochs is None:
            return True
        for side, child in targets:
            expected_epoch = expected_stop_epochs.get(side)
            if expected_epoch is None:
                continue
            owner = getattr(child, "_single_inner", child)
            scheduler = getattr(owner, "_command_scheduler", None)
            if getattr(scheduler, "stop_epoch", None) != expected_epoch:
                return False
        return True

    def admission_was_cancelled(
        self,
        targets: Collection[PairTarget],
        resources: Collection[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> bool:
        """Revalidate a linked request after it has waited for an admission lane."""
        return any(
            self.was_cancelled(side, resources, entry_cancel) for side, _child in targets
        ) or not self.stop_epochs_match(targets, expected_stop_epochs)


# ---------------------------------------------------------------------------
# Child capability probes shared by the strategies
# ---------------------------------------------------------------------------


def linked_readiness_required(targets: Collection[PairTarget]) -> bool:
    """Return whether a linked group needs every physical receiver live first."""
    return any(
        child.capability_controller is not None
        and getattr(child.capability_controller, "requires_linked_live_readiness", False) is True
        for _, child in targets
    )


def ready_disconnected_transport(child: BedChild) -> bool:
    """Recognize an explicitly selected, already-ready non-Bleak role."""
    controller = child.controller or child.capability_controller
    return bool(
        controller is not None
        and getattr(controller, "requires_disconnected_transport", False)
        and controller.disconnected_transport_ready
    )


def selects_disconnected_transport(child: BedChild) -> bool:
    """Return whether a side is served by a local transport rather than Bleak."""
    controller = child.controller or child.capability_controller
    return bool(
        controller is not None and getattr(controller, "requires_disconnected_transport", False)
    )


def manual_disconnect_would_strand(child: BedChild) -> bool:
    """Return whether sequential switching is unsafe for this child."""
    controller = getattr(child, "controller", None) or getattr(
        child, "capability_controller", None
    )
    return bool(
        controller is not None
        and getattr(controller, "manual_disconnect_strands_connection", False)
    )


@contextlib.contextmanager
def hold_command_connections(targets: Collection[PairTarget]) -> Iterator[None]:
    """Keep early-finishing sides available through combined action cleanup."""
    with contextlib.ExitStack() as stack:
        for _, child in targets:
            stack.enter_context(child.hold_command_connection())
        yield


async def safe_disconnect(
    side: str,
    child: BedChild,
    *,
    disconnect: GuardedDisconnect | None = None,
) -> bool:
    """Disconnect one side, swallowing failures. Returns True on success — a
    disconnect error must not mask the command outcome, but callers that rely
    on the link actually being down (sequential switching) check the result.

    The child returns False when Bleak reports that the physical link remains
    active after a failed disconnect. Older test doubles return None, which is
    treated as success for backward compatibility.
    """
    try:
        disconnect_fn = disconnect or child.async_disconnect
        disconnected = await disconnect_fn("sequential_switch")
    except Exception as err:  # noqa: BLE001 - CancelledError must propagate
        _LOGGER.warning("Disconnect failed on %s side (%s): %s", side, child.address, err)
        return False
    return disconnected is not False and not child.is_connected


async def stop_targets(targets: list[PairTarget]) -> dict[str, BaseException]:
    """Send STOP to every target at once, collecting individual failures.

    Always attempts every side — a STOP failure on one must never prevent
    stopping another.
    """
    with hold_command_connections(targets):
        results = await asyncio.gather(
            *(child.async_stop_command() for _, child in targets),
            return_exceptions=True,
        )
    errors: dict[str, BaseException] = {}
    for (side, child), result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            errors[side] = result
            _LOGGER.warning("STOP failed on %s side (%s): %s", side, child.address, result)
    return errors


async def stop_motor_targets(
    targets: list[PairTarget], stop_fn: ChildCommand, resource: str
) -> dict[str, BaseException]:
    """Stop one motor on every target, never letting one side skip another.

    Each receiver pre-empts the motion holding that side's writer, so the stop
    never waits behind another motor's move (#516).
    """
    with hold_command_connections(targets):
        results = await asyncio.gather(
            *(
                child.async_stop_motor(stop_fn, resource, stream_member=False)
                for _, child in targets
            ),
            return_exceptions=True,
        )
    errors: dict[str, BaseException] = {}
    for (side, child), result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            errors[side] = result
            _LOGGER.warning("Motor STOP failed on %s side (%s): %s", side, child.address, result)
    return errors


# ---------------------------------------------------------------------------
# Connection-slot evidence for automatic fallback
# ---------------------------------------------------------------------------


def connection_attempts(child: BedChild) -> tuple[Mapping[str, object], ...]:
    """Return a child's structured connection attempts when it exposes them."""
    attempts = getattr(child, "connection_attempt_details", ())
    if not isinstance(attempts, (list, tuple)):
        return ()
    return tuple(attempt for attempt in attempts if isinstance(attempt, Mapping))


def connection_attempt_cursor(child: BedChild) -> ConnectionAttemptCursor:
    """Return a stable cursor into a child's bounded attempt history."""
    count = getattr(child, "connection_attempt_count", None)
    attempts = connection_attempts(child)
    return (
        count if isinstance(count, int) else None,
        attempts[-1] if attempts else None,
    )


def connection_attempts_since(
    child: BedChild, cursor: ConnectionAttemptCursor
) -> tuple[Mapping[str, object], ...]:
    """Return attempts recorded after a cursor, despite deque eviction."""
    attempts = connection_attempts(child)
    previous_count, previous_tail = cursor
    if previous_tail is not None:
        for index in range(len(attempts) - 1, -1, -1):
            if attempts[index] is previous_tail:
                return attempts[index + 1 :]
    current_count = getattr(child, "connection_attempt_count", None)
    if previous_count is not None and isinstance(current_count, int):
        added = max(0, current_count - previous_count)
        if added == 0:
            return ()
        return attempts[-added:]
    return attempts


def connection_slot_exhausted(
    child: BedChild,
    result: object,
    attempt_cursor: ConnectionAttemptCursor,
) -> bool:
    """Return whether this connect failed because its transport had no slot."""
    if result is True:
        return False
    if isinstance(result, BaseException) and "connection slot" in str(result).lower():
        return True
    return any(
        "connection slot" in str(attempt.get("error", "")).lower()
        for attempt in connection_attempts_since(child, attempt_cursor)
    )


def connection_slot_exhausted_sources(
    child: BedChild,
    result: object,
    attempt_cursor: ConnectionAttemptCursor,
) -> set[str]:
    """Return transports that reported slot exhaustion in this operation."""
    if result is True:
        return set()
    sources: set[str] = set()
    for attempt in connection_attempts_since(child, attempt_cursor):
        if "connection slot" not in str(attempt.get("error", "")).lower():
            continue
        source = attempt.get("actual_source") or attempt.get("selected_source")
        if isinstance(source, str) and source:
            sources.add(source)
    return sources


def shared_connection_slot_pressure(
    items: Collection[PairTarget],
    results: Mapping[str, object],
    attempt_cursors: Mapping[str, ConnectionAttemptCursor],
) -> bool:
    """Return whether a live sibling occupies an exhausted transport."""
    for failed_side, failed_child in items:
        result = results.get(failed_side)
        cursor = attempt_cursors.get(failed_side, (None, None))
        if failed_child.is_connected or not connection_slot_exhausted(
            failed_child, result, cursor
        ):
            continue
        exhausted_sources = connection_slot_exhausted_sources(failed_child, result, cursor)
        for live_side, live_child in items:
            if live_side == failed_side or not live_child.is_connected:
                continue
            live_source = getattr(live_child, "connection_source", None)
            if live_source in exhausted_sources:
                return True
    return False


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class PairTopology(ABC):
    """Routing, locking and STOP fan-out for one physical pair topology."""

    def __init__(self, pair: PairedBedCoordinator) -> None:
        self._pair = pair
        self._admission = pair._admission

    @property
    def _children(self) -> dict[str, BedChild]:
        # Live view: a side the parent drops after setup leaves every strategy.
        return self._pair._children

    def targets_for(self, side: str) -> list[PairTarget]:
        """Resolve a logical side to the children it reaches, left first."""
        if side not in (SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH):
            raise ValueError(f"Unknown side {side!r}")
        if side in (SIDE_LEFT, SIDE_RIGHT) and side not in self._children:
            raise ValueError(f"Paired bed has no {side} side")
        if side == SIDE_BOTH:
            return [(s, self._children[s]) for s in PAIR_SIDES if s in self._children]
        return [(side, self._children[side])]

    def check_admission(self, targets: Collection[PairTarget]) -> None:
        """Reject a request this topology can never execute."""
        del targets

    @abstractmethod
    def preempts_active(self, command_scope: frozenset[str]) -> bool:
        """Return whether a request overlapping the active children cancels them."""

    @abstractmethod
    def capability_reload_guard(
        self, targets: Collection[PairTarget]
    ) -> contextlib.AbstractAsyncContextManager[None]:
        """Hold every lane a capability reload must wait for."""

    @abstractmethod
    async def run(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> None:
        """Admit and execute one command on its target sides."""

    @abstractmethod
    async def stop_children(self, targets: list[PairTarget]) -> dict[str, BaseException]:
        """Send STOP to every target, collecting individual failures."""

    async def stop_motor(
        self, targets: list[PairTarget], stop_fn: ChildCommand, resource: str
    ) -> dict[str, BaseException]:
        """Stop one motor on every target, collecting individual failures (#516)."""
        return await stop_motor_targets(targets, stop_fn, resource)

    @abstractmethod
    async def connect_children(self, *, started_local_sides: Collection[str] = ()) -> bool:
        """Connect the sides ready for ordinary control."""


class _SideLaneTopology(PairTopology):
    """Admission shared by topologies that give each logical side its own lane.

    Independent sides overlap. Linked groups serialize with each other but
    release the side lanes while waiting for the physical schedulers to become
    ready, so a command for the active motor can preempt.
    """

    def __init__(self, pair: PairedBedCoordinator) -> None:
        super().__init__(pair)
        self.side_locks = {side: asyncio.Lock() for side in PAIR_SIDES}
        self.group_lock = asyncio.Lock()

    def _is_active(self) -> bool:
        return self._pair._connection_mode == PAIR_CONNECTION_MODE_CONCURRENT

    def preempts_active(self, command_scope: frozenset[str]) -> bool:
        # A whole-bed command holds its lanes until BOTH children finish, so an
        # overlapping command preempts all of it. A command on disjoint
        # resources leaves the active group alone and waits its turn.
        active = self._admission.active_group_resources
        return (
            not active
            or "*" in active
            or "*" in command_scope
            or not command_scope.isdisjoint(active)
        )

    @contextlib.asynccontextmanager
    async def locked_target_sides(self, targets: Collection[PairTarget]) -> AsyncIterator[None]:
        """Lock selected physical side lanes in stable order."""
        target_by_side = dict(targets)
        async with contextlib.AsyncExitStack() as stack:
            for side in PAIR_SIDES:
                if side in target_by_side:
                    await stack.enter_async_context(self.side_locks[side])
            yield

    def capability_reload_guard(
        self, targets: Collection[PairTarget]
    ) -> contextlib.AbstractAsyncContextManager[None]:
        return self.locked_target_sides(targets)

    async def run(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> None:
        """Run one lane command without connection-mode fallback."""
        if len(targets) == 1:
            target_side, child = targets[0]
            await self._run_single(
                action,
                target_side,
                child,
                op,
                cancel_running=cancel_running,
                resources=resources,
                entry_cancel=entry_cancel,
                expected_stop_epoch=(
                    expected_stop_epochs.get(target_side)
                    if expected_stop_epochs is not None
                    else None
                ),
            )
            return

        # Only one linked group may coordinate the device schedulers at a time.
        # The group itself briefly takes the side lanes for enqueue and takes
        # them again for commit/execution, but releases them while waiting for
        # READY so a command for the active motor can preempt.
        async with self.group_lock:
            if not self._is_active():
                raise ConnectionModeChanged
            if any(
                self._admission.was_cancelled(side, resources, entry_cancel)
                for side, _ in targets
            ):
                return

            self._admission.active_children = {child for _, child in targets}
            self._admission.active_group_resources = resources
            try:
                with hold_command_connections(targets):
                    await self._run_linked(
                        action,
                        targets,
                        op,
                        cancel_running=cancel_running,
                        resources=resources,
                        entry_cancel=entry_cancel,
                        expected_stop_epochs=expected_stop_epochs,
                    )
            finally:
                self._admission.active_children = set()
                self._admission.active_group_resources = frozenset()

    async def _run_single(
        self,
        action: str,
        side: str,
        child: BedChild,
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epoch: int | None = None,
    ) -> None:
        """Admit one side without holding pair metadata across its operation."""
        del action
        admission = self._admission
        expected = {side: expected_stop_epoch} if expected_stop_epoch is not None else None
        prepare = getattr(child, "async_prepare_command_operation", None)
        prepare_owner = getattr(child, "_single_inner", child)
        if not callable(prepare) or not callable(
            getattr(prepare_owner, "async_prepare_command_operation", None)
        ):
            # Compatibility for coordinator doubles. Separate side locks still
            # allow left and right to overlap while serializing one fake child.
            async with self.side_locks[side]:
                if not self._is_active():
                    raise ConnectionModeChanged
                if admission.was_cancelled(
                    side, resources, entry_cancel
                ) or not admission.stop_epochs_match([(side, child)], expected):
                    return
                await op(child)
            return

        handle: CommandHandle | None = None
        async with self.side_locks[side]:
            if not self._is_active():
                raise ConnectionModeChanged
            if admission.was_cancelled(
                side, resources, entry_cancel
            ) or not admission.stop_epochs_match([(side, child)], expected):
                return
            if expected_stop_epoch is None:
                handle = await child.async_prepare_command_operation(
                    lambda: op(child),
                    resources=resources,
                    cancel_running=cancel_running,
                    group_id=uuid4().hex,
                )
            else:
                handle = await child.async_prepare_command_operation(
                    lambda: op(child),
                    resources=resources,
                    cancel_running=cancel_running,
                    group_id=uuid4().hex,
                    expected_stop_epoch=expected_stop_epoch,
                )
        try:
            await child.async_wait_prepared_command(handle)
        except PreparedCommandInvalidated:
            await child.async_abort_prepared_command(handle)
            return
        except BaseException:
            await child.async_abort_prepared_command(handle)
            raise

        # Waiting behind an earlier prepared group must not retain this side
        # lane, because that group needs the lane to commit. Reacquire only for
        # the synchronous validation/commit transition.
        async with self.side_locks[side]:
            if not self._is_active():
                await child.async_abort_prepared_command(handle)
                raise ConnectionModeChanged
            try:
                await child.async_wait_prepared_command(handle)
                if admission.was_cancelled(
                    side, resources, entry_cancel
                ) or not admission.stop_epochs_match([(side, child)], expected):
                    await child.async_abort_prepared_command(handle)
                    return
            except PreparedCommandInvalidated:
                await child.async_abort_prepared_command(handle)
                return
            except BaseException:
                await child.async_abort_prepared_command(handle)
                raise
            child.commit_prepared_command(handle)

        try:
            await child.async_wait_prepared_command_result(handle)
        except PreparedCommandInvalidated:
            # Replacement and STOP are successful cancellation outcomes for an
            # ordinary side command. Operation failures still arrive as their
            # original exception and continue to propagate.
            return
        except asyncio.CancelledError:
            await child.async_abort_prepared_command(handle)
            raise

    @abstractmethod
    async def _run_linked(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None = None,
    ) -> None:
        """Run one command across several sides under the group lock."""


class ConcurrentTwoLinkTopology(_SideLaneTopology):
    """Two receivers, each on its own live link."""

    async def run(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> None:
        attempt_cursors = {
            target_side: connection_attempt_cursor(child)
            for target_side, child in self._children.items()
        }
        try:
            await super().run(
                action,
                targets,
                op,
                cancel_running=cancel_running,
                resources=resources,
                entry_cancel=entry_cancel,
                expected_stop_epochs=expected_stop_epochs,
            )
        except ConnectionModeChanged:
            raise
        except Exception as err:
            await self.fallback_after_connection_slot_exhaustion(err, attempt_cursors)
            raise

    async def _run_linked(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None = None,
    ) -> None:
        """Prepare every physical scheduler, then commit the linked command."""
        admission = self._admission
        if admission.admission_was_cancelled(
            targets, resources, entry_cancel, expected_stop_epochs
        ):
            return
        if not all(
            callable(getattr(child, "async_prepare_command_operation", None))
            for _, child in targets
        ):
            # Compatibility for third-party/test coordinator doubles. Production
            # children always expose the scheduler reservation API.
            async with self.locked_target_sides(targets):
                if admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ):
                    return
                await self._run_linked_unscheduled(action, targets, op)
            return

        group_id = uuid4().hex
        child_by_side = dict(targets)
        prepared: dict[str, tuple[BedChild, CommandHandle]] = {}
        committed = False
        result_tasks: dict[str, asyncio.Task[None]] = {}

        def collect_enqueues(
            enqueue_tasks: Mapping[str, asyncio.Task[CommandHandle | None]],
        ) -> dict[str, BaseException]:
            """Recover every completed reservation, including during cancellation."""
            errors: dict[str, BaseException] = {}
            for side, task in enqueue_tasks.items():
                if not task.done() or task.cancelled():
                    continue
                try:
                    handle = task.result()
                except BaseException as err:
                    errors[side] = err
                else:
                    if handle is not None:
                        prepared[side] = (child_by_side[side], handle)
            return errors

        def is_expected_invalidation(side: str, error: BaseException | None) -> bool:
            return isinstance(error, PreparedCommandInvalidated) and (
                prepared[side][1].outcome in {CommandOutcome.REPLACED, CommandOutcome.STOPPED}
            )

        try:
            async with self.locked_target_sides(targets):
                if admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ):
                    return

                async def prepare_side(side: str, child: BedChild) -> CommandHandle | None:
                    # STOP or newer side work may run before this task's first turn.
                    if admission.admission_was_cancelled(
                        targets, resources, entry_cancel, expected_stop_epochs
                    ):
                        return None
                    expected_stop_epoch = (
                        expected_stop_epochs.get(side)
                        if expected_stop_epochs is not None
                        else None
                    )
                    if expected_stop_epoch is None:
                        return await child.async_prepare_command_operation(
                            lambda child=child: op(child),
                            resources=resources,
                            cancel_running=cancel_running,
                            group_id=group_id,
                        )
                    return await child.async_prepare_command_operation(
                        lambda child=child: op(child),
                        resources=resources,
                        cancel_running=cancel_running,
                        group_id=group_id,
                        expected_stop_epoch=expected_stop_epoch,
                    )

                enqueue_tasks = {
                    side: asyncio.create_task(prepare_side(side, child))
                    for side, child in targets
                }
                try:
                    await asyncio.gather(*enqueue_tasks.values(), return_exceptions=True)
                except asyncio.CancelledError:
                    for task in enqueue_tasks.values():
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*enqueue_tasks.values(), return_exceptions=True)
                    collect_enqueues(enqueue_tasks)
                    raise
                enqueue_errors = collect_enqueues(enqueue_tasks)
                if enqueue_errors:
                    raise PairedSideError(action, enqueue_errors)
                if admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ) or any(task.result() is None for task in enqueue_tasks.values()):
                    return

            # Do not hold the side lanes while an older operation is ahead of a
            # group reservation. A newer replacement for that active resource
            # can now enter its child scheduler and run before this disjoint group.
            ready_tasks = {
                side: asyncio.create_task(child.async_wait_prepared_command(handle))
                for side, (child, handle) in prepared.items()
            }
            ready_results = await asyncio.gather(*ready_tasks.values(), return_exceptions=True)
            ready_errors: dict[str, BaseException] = {}
            ready_invalidated = False
            for side, result in zip(ready_tasks, ready_results, strict=True):
                if not isinstance(result, BaseException):
                    continue
                if is_expected_invalidation(side, result):
                    ready_invalidated = True
                else:
                    ready_errors[side] = result
            if ready_errors:
                raise PairedSideError(action, ready_errors)
            if ready_invalidated:
                return

            # Reacquire both lanes and revalidate reservations. From commit until
            # result/STOP cleanup completes, overlapping commands wait here.
            async with self.locked_target_sides(targets):
                if admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ):
                    return
                revalidation_errors: dict[str, BaseException] = {}
                revalidation_invalidated = False
                for side, (child, handle) in prepared.items():
                    try:
                        await child.async_wait_prepared_command(handle)
                    except Exception as err:  # noqa: BLE001 - collect both sides
                        if is_expected_invalidation(side, err):
                            revalidation_invalidated = True
                        else:
                            revalidation_errors[side] = err
                if revalidation_errors:
                    raise PairedSideError(action, revalidation_errors)
                if revalidation_invalidated or admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ):
                    for child, handle in prepared.values():
                        await child.async_abort_prepared_command(handle)
                    return

                if linked_readiness_required(targets):
                    await self._async_validate_linked_readiness(targets)
                    # STOP or replacement may invalidate a reservation while its
                    # receiver connects. Recheck before releasing either side.
                    for child, handle in prepared.values():
                        await child.async_wait_prepared_command(handle)
                    if admission.admission_was_cancelled(
                        targets, resources, entry_cancel, expected_stop_epochs
                    ):
                        for child, handle in prepared.values():
                            await child.async_abort_prepared_command(handle)
                        return

                if admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ):
                    return

                # No controller command coroutine has run before this point. Commit every
                # ready handle synchronously so neither side can observe a partial
                # group caused by another await between releases.
                for child, handle in prepared.values():
                    child.commit_prepared_command(handle)
                committed = True

                result_tasks = {
                    side: asyncio.create_task(child.async_wait_prepared_command_result(handle))
                    for side, (child, handle) in prepared.items()
                }
                try:
                    await asyncio.wait(result_tasks.values(), return_when=asyncio.FIRST_EXCEPTION)
                    errors: dict[str, BaseException] = {}
                    expected_invalidations = False
                    for side, task in result_tasks.items():
                        if task.done() and not task.cancelled():
                            error = task.exception()
                            if is_expected_invalidation(side, error):
                                expected_invalidations = True
                            elif error is not None:
                                errors[side] = error
                    if errors:
                        stop_errors = await self._pair._stop_children(targets)
                        raise PairedSideError(action, merge_stop_errors(errors, stop_errors))

                    if expected_invalidations:
                        settled = await asyncio.gather(
                            *result_tasks.values(), return_exceptions=True
                        )
                        late_errors = {
                            side: result
                            for side, result in zip(result_tasks, settled, strict=True)
                            if isinstance(result, BaseException)
                            and not is_expected_invalidation(side, result)
                        }
                        if late_errors:
                            stop_errors = await self._pair._stop_children(targets)
                            raise PairedSideError(
                                action, merge_stop_errors(late_errors, stop_errors)
                            )
                    else:
                        await asyncio.gather(*result_tasks.values())
                except asyncio.CancelledError:
                    await self._pair._stop_children(targets)
                    raise
                finally:
                    for task in result_tasks.values():
                        if not task.done():
                            task.cancel()
                    if result_tasks:
                        await asyncio.gather(*result_tasks.values(), return_exceptions=True)
        finally:
            if not committed:
                await asyncio.gather(
                    *(
                        child.async_abort_prepared_command(handle)
                        for child, handle in prepared.values()
                    ),
                    return_exceptions=True,
                )

    async def _async_validate_linked_readiness(self, targets: Collection[PairTarget]) -> None:
        from .coordinator import AdjustableBedCoordinator

        if not self._is_active():
            raise ValueError("Linked readiness cannot use sequential fallback")
        physical: dict[str, AdjustableBedCoordinator] = {}
        for side, child in targets:
            controller = child.capability_controller
            if (
                not isinstance(child, AdjustableBedCoordinator)
                or controller is None
                or controller.requires_linked_live_readiness is not True
            ):
                raise ValueError("Link only independently configured compatible physical receivers")
            physical[side] = child
        outcomes = await asyncio.gather(
            *(child.async_validate_linked_command_readiness() for child in physical.values()),
            return_exceptions=True,
        )
        errors = {
            side: outcome
            for side, outcome in zip(physical, outcomes, strict=True)
            if isinstance(outcome, BaseException)
        }
        if errors:
            raise PairedSideError("linked readiness", errors)
        if not self._is_active() or not all(child.is_connected for child in physical.values()):
            raise ConnectionError("Both linked receivers must remain concurrently connected")

    async def _run_linked_unscheduled(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
    ) -> None:
        """Run the b3 concurrent contract for coordinator test doubles."""
        tasks: dict[str, asyncio.Task[None]] = {
            side: asyncio.ensure_future(op(child)) for side, child in targets
        }
        try:
            # Return as soon as the FIRST side fails (or all complete), so the
            # stop-the-other cleanup fires immediately instead of waiting for the
            # healthy side to finish its full send window.
            await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_EXCEPTION)

            errors: dict[str, BaseException] = {}
            for side, task in tasks.items():
                if task.done() and not task.cancelled():
                    exc = task.exception()
                    if exc is not None:
                        errors[side] = exc

            if errors:
                # STOP every side now (this also makes each child's in-flight
                # command exit early). Surface any cleanup-STOP failure too, so a
                # caller knows the "healthy" side may still be moving.
                stop_errors = await self._pair._stop_children(targets)
                raise PairedSideError(action, merge_stop_errors(errors, stop_errors))
        except asyncio.CancelledError:
            await self._pair._stop_children(targets)
            raise
        finally:
            # Never let a child task outlive this call (e.g. if the parent
            # coroutine is cancelled mid-wait): cancel any still-running task and
            # settle them all so none keep writing outside the parent lock.
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def stop_children(self, targets: list[PairTarget]) -> dict[str, BaseException]:
        return await stop_targets(targets)

    async def connect_children(self, *, started_local_sides: Collection[str] = ()) -> bool:
        """Connect both links at once; automatic mode may adopt sequential switching."""
        pair = self._pair
        items = list(self._children.items())
        attempt_cursors = {side: connection_attempt_cursor(child) for side, child in items}

        async def connect_and_cache(side: str, child: BedChild) -> bool:
            if selects_disconnected_transport(child):
                # Startup owns a registered local server before any peer joins.
                # Command admission still requires authenticated readiness.
                connected = side in started_local_sides or ready_disconnected_transport(child)
            else:
                connected = await child.async_connect()
            if connected:
                # Cache as soon as this side completes. The other side may take
                # longer than this receiver's idle disconnect grace period.
                child.cache_capability_controller()
            return connected

        results = await asyncio.gather(
            *(connect_and_cache(side, child) for side, child in items), return_exceptions=True
        )
        results_by_side = {side: result for (side, _), result in zip(items, results, strict=True)}
        for (side, _), result in zip(items, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Connect failed on %s side: %s", side, result)
        if pair._automatic_connection_mode and shared_connection_slot_pressure(
            items, results_by_side, attempt_cursors
        ):
            async with contextlib.AsyncExitStack() as stack:
                guarded_disconnects: dict[str, GuardedDisconnect] = {}
                for _, child in items:
                    await stack.enter_async_context(child.async_command_operation_guard())
                for side, child in items:
                    guarded_disconnects[side] = await stack.enter_async_context(
                        child.async_connection_operation_guard()
                    )

                if not shared_connection_slot_pressure(items, results_by_side, attempt_cursors):
                    return any(result is True for result in results)
                if any(manual_disconnect_would_strand(child) for _, child in items):
                    _LOGGER.warning(
                        "Automatic paired connection cannot fall back to sequential "
                        "mode because disconnecting a pairing-only receiver would "
                        "strand it; retaining the usable concurrent link"
                    )
                    return any(result is True for result in results)
                _LOGGER.warning(
                    "Automatic paired connection fell back to sequential mode because "
                    "the concurrent connect exhausted an adapter's connection slots"
                )
                for side, child in items:
                    if not child.is_connected:
                        continue
                    child.cache_capability_controller()
                    if not await safe_disconnect(
                        side, child, disconnect=guarded_disconnects[side]
                    ):
                        return True
                pair._adopt_connection_mode(PAIR_CONNECTION_MODE_SEQUENTIAL)
            return await pair._async_connect_children(started_local_sides=started_local_sides)
        return any(result is True for result in results)

    async def fallback_after_connection_slot_exhaustion(
        self,
        error: BaseException,
        attempt_cursors: Mapping[str, ConnectionAttemptCursor],
    ) -> None:
        """Adopt sequential mode after a command-time connection-slot failure.

        The failing command remains failed because another side may already have
        acted. The next command uses the safe one-link path.
        """
        pair = self._pair
        if not pair._automatic_connection_mode or not self._is_active():
            return

        items = list(self._children.items())
        side_errors = error.side_errors if isinstance(error, PairedSideError) else {}
        results = {side: side_errors.get(side, error) for side, _ in items}
        if not any(
            connection_slot_exhausted(
                child, results[side], attempt_cursors.get(side, (None, None))
            )
            for side, child in items
        ):
            return

        # Quiesce both parent lanes and child command lanes before changing the
        # connection contract or releasing a live link. This also rechecks the
        # pairing-only safety property after any in-flight reconnect completed.
        async with (
            pair._connection_mode_transition_lock,
            self.group_lock,
            self.locked_target_sides(items),
            contextlib.AsyncExitStack() as stack,
        ):
            guarded_disconnects: dict[str, GuardedDisconnect] = {}
            for _, child in items:
                await stack.enter_async_context(child.async_command_operation_guard())
            for side, child in items:
                guarded_disconnects[side] = await stack.enter_async_context(
                    child.async_connection_operation_guard()
                )

            if not self._is_active():
                return
            if not shared_connection_slot_pressure(items, results, attempt_cursors):
                return
            if any(manual_disconnect_would_strand(child) for _, child in items):
                _LOGGER.warning(
                    "Automatic paired command cannot fall back to sequential "
                    "mode because disconnecting a pairing-only receiver would "
                    "strand it; retaining the usable concurrent link"
                )
                return

            for side, child in items:
                if not child.is_connected:
                    continue
                child.cache_capability_controller()
                if not await safe_disconnect(side, child, disconnect=guarded_disconnects[side]):
                    _LOGGER.warning(
                        "Automatic paired command could not release the %s "
                        "side, so concurrent mode remains active",
                        side,
                    )
                    return

            pair._adopt_connection_mode(PAIR_CONNECTION_MODE_SEQUENTIAL)
            _LOGGER.warning(
                "Automatic paired connection fell back to sequential mode "
                "after a command reconnect exhausted an adapter's connection slots"
            )


class SequentialTwoLinkTopology(PairTopology):
    """Two receivers sharing one link lane: connect, operate, then disconnect.

    Dropping the link halts that side's motors (verified dead-man model — the
    bed only moves while a command stream arrives), so a disconnected side
    needs no separate STOP.
    """

    def __init__(self, pair: PairedBedCoordinator) -> None:
        super().__init__(pair)
        # Orders connection switching; one command cycle owns the link lane.
        self.command_lock = asyncio.Lock()

    def check_admission(self, targets: Collection[PairTarget]) -> None:
        if len(targets) > 1 and linked_readiness_required(targets):
            raise ValueError("This linked profile requires concurrent ready physical receivers")

    def preempts_active(self, command_scope: frozenset[str]) -> bool:
        # The cycle holds the one link lane until every side finishes, so any
        # request on an active side preempts the whole cycle.
        del command_scope
        return True

    def capability_reload_guard(
        self, targets: Collection[PairTarget]
    ) -> contextlib.AbstractAsyncContextManager[None]:
        del targets
        return self.command_lock

    async def run(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> None:
        del cancel_running
        admission = self._admission
        async with self.command_lock:
            # A STOP (or newer command) bumped one of OUR target sides while we
            # waited — drop this now-stale movement instead of starting it right
            # after the safety stop.
            if any(
                admission.was_cancelled(s, resources, entry_cancel) for s, _ in targets
            ) or not admission.stop_epochs_match(targets, expected_stop_epochs):
                return

            admission.active_children = {child for _, child in targets}
            try:
                try:
                    await self._run_cycle(action, targets, op, entry_cancel, resources)
                except asyncio.CancelledError:
                    # The parent command was cancelled (service cancellation or
                    # config-entry unload) while a side may still be moving.
                    # Cancelling the child TASKS is not the same as a STOP write,
                    # so explicitly STOP the still-connected side(s) before
                    # propagating — otherwise a motor can be left running.
                    # stop_children only targets a side that is still connected
                    # (a disconnected side already halted on its link drop). It
                    # never raises and we re-raise the cancellation regardless,
                    # so this is best-effort cleanup.
                    await self._pair._stop_children(targets)
                    raise
            finally:
                admission.active_children = set()

    async def _run_cycle(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        entry_cancel: Mapping[str, tuple[int, ...]],
        resources: frozenset[str],
    ) -> None:
        """Run each side in turn holding only ONE BLE link at a time: connect the
        side, run its op, then disconnect it before moving to the next.

        On failure the loop stops at the first failing side; every side that was
        connected is disconnected, so nothing is left connected or moving.

        ``entry_cancel`` is the per-side cancel counter captured at command entry:
        a STOP (or newer command) bumps it, so before starting each side we re-check
        and abort the rest of the cycle — otherwise a STOP during side A would still
        let side B connect and move.
        """
        errors: dict[str, BaseException] = {}

        def cycle_cancelled() -> bool:
            # A STOP / newer command for ANY targeted side supersedes the whole
            # cycle — checking only the side about to run would let a later side
            # connect after an earlier side of a both-cycle was already cancelled.
            return any(
                self._admission.was_cancelled(s, resources, entry_cancel) for s, _ in targets
            )

        for side, child in targets:
            if cycle_cancelled():
                # A STOP / newer command landed mid-cycle — abort before
                # connecting this side (the earlier side already disconnected).
                break

            local_role = selects_disconnected_transport(child)
            if local_role and not ready_disconnected_transport(child):
                errors[side] = ConnectionError(f"{side} local transport is selected but not ready")
                break

            # One-link guard: release any OTHER side that is still connected (it
            # may have been connected out-of-band, e.g. a per-side diagnostic
            # Connect button) before opening this link, so we never hold two.
            if not await self._release_other_sides(child):
                errors[side] = HomeAssistantError(
                    "could not release the other side before switching"
                )
                break

            try:
                connected = True if local_role else await child.async_connect()
            except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                errors[side] = err
                break
            if not connected:
                errors[side] = HomeAssistantError(f"{side} side of the pair could not be connected")
                break

            # A STOP (or newer command) may have landed WHILE we were connecting —
            # stop_children couldn't reach this side then (it wasn't connected
            # yet), so re-check now and bail (releasing the link) instead of
            # starting a motor command after the STOP was accepted.
            if cycle_cancelled():
                if not local_role and not await safe_disconnect(side, child):
                    # The post-cancel release raised — surface it; the one-link
                    # guard may have failed.
                    errors[side] = HomeAssistantError(
                        f"{side} side failed to disconnect after cancellation "
                        "— aborting to keep one link"
                    )
                break

            op_error: BaseException | None = None
            try:
                await op(child)
            except asyncio.CancelledError:
                # Release this side (halts it) before propagating the cancellation.
                if not local_role:
                    await safe_disconnect(side, child)
                raise
            except Exception as err:  # noqa: BLE001
                op_error = err

            # Disconnecting is BOTH the one-link guard and the halt for this side,
            # so a disconnect failure is fatal: abort rather than connect the next
            # side onto a possibly-still-live/moving link.
            disconnected = local_role or await safe_disconnect(side, child)
            if op_error is not None or not disconnected:
                if op_error is not None and not disconnected:
                    # Both failed: the command erred AND the release that should
                    # have halted/released the side also failed — surface both, as
                    # the link may still be live/moving (the more critical fact).
                    err = HomeAssistantError(
                        f"{side} side command failed and its release also failed "
                        f"— the link may still be live"
                    )
                    err.__cause__ = op_error
                    errors[side] = err
                elif op_error is not None:
                    errors[side] = op_error
                else:
                    errors[side] = HomeAssistantError(
                        f"{side} side failed to disconnect — aborting to keep one link"
                    )
                break
        if errors:
            raise PairedSideError(action, errors)

    async def _release_other_sides(self, keep: BedChild) -> bool:
        """Disconnect every side except ``keep`` (the one-link guard before a
        sequential connect). Returns False if any disconnect failed, so the caller
        can abort rather than risk opening a second link."""
        ok = True
        for side, child in self._children.items():
            if child is not keep and child.is_connected:
                if not await safe_disconnect(side, child):
                    ok = False
        return ok

    async def stop_children(self, targets: list[PairTarget]) -> dict[str, BaseException]:
        """STOP connected central receivers and ready local transports.

        A disconnected central side already halted on link drop, and stopping it
        would reconnect it (``async_stop_command`` ensures a link), momentarily
        creating the two-link state this topology avoids.
        """
        return await stop_targets(
            [
                (side, child)
                for side, child in targets
                if child.is_connected or ready_disconnected_transport(child)
            ]
        )

    async def stop_motor(
        self, targets: list[PairTarget], stop_fn: ChildCommand, resource: str
    ) -> dict[str, BaseException]:
        """Stop one motor on connected sides only, never reconnecting one.

        A side moves only inside a cycle, which releases its link once the
        command ends, and the drop halts it. A cycling side's running command
        is pre-empted instead: its own release goes out, then the cycle drops
        the link. A STOP frame of its own would race that drop, or reopen the
        second link this topology avoids. A connected side outside a cycle gets
        the motor's stop; a disconnected one already halted.
        """
        cycling = self._admission.active_children
        scope = command_resources("motor:*" if resource.startswith("motor:") else resource)
        for _, child in targets:
            if child in cycling:
                child.request_command_cancel(resources=scope)
        return await stop_motor_targets(
            [
                (side, child)
                for side, child in targets
                if child not in cycling
                and (child.is_connected or ready_disconnected_transport(child))
            ],
            stop_fn,
            resource,
        )

    async def connect_children(self, *, started_local_sides: Collection[str] = ()) -> bool:
        """Verify each side once, then release it; commands reconnect on demand.

        This is also where a capability snapshot is captured.
        """
        any_connected = False
        for side, child in list(self._children.items()):
            if selects_disconnected_transport(child):
                if side not in started_local_sides and not ready_disconnected_transport(child):
                    raise ConnectionError(f"{side} local transport is selected but not ready")
                child.cache_capability_controller()
                any_connected = True
                continue
            if not await self._release_other_sides(child):
                break
            try:
                connected = await child.async_connect()
            except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                _LOGGER.warning("Connect failed on %s side: %s", side, err)
                continue
            if connected:
                any_connected = True
                # Keep the just-discovered live controller as this side's
                # offline capability source BEFORE releasing the link, so its
                # per-side entities still build after this disconnect (which
                # drops the live controller).
                child.cache_capability_controller()
                if not await safe_disconnect(side, child):
                    # Releasing the just-verified side raised: opening the next
                    # side now could hold two links at once, which the single-
                    # connection profile must never do (the reference app
                    # strictly disconnects-before-connect and aborts on a
                    # genuine disconnect error). Stop verifying the rest — one
                    # side left up beats two — commands reconnect on demand.
                    _LOGGER.warning(
                        "Could not release %s side after verify; skipping the "
                        "remaining side(s) to keep a single BLE link",
                        side,
                    )
                    break
        return any_connected


class SingleLinkSideAwareTopology(_SideLaneTopology):
    """One receiver serving logical left and right sides on one link."""

    def __init__(self, pair: SingleAddressPairedCoordinator, *, native_both: bool) -> None:
        super().__init__(pair)
        self._single = pair
        self.native_both = native_both

    def targets_for(self, side: str) -> list[PairTarget]:
        targets = super().targets_for(side)
        if side == SIDE_BOTH and self.native_both:
            both = self._single._single_both
            return [(SIDE_LEFT, both), (SIDE_RIGHT, both)]
        return targets

    def _is_native_group(self, targets: Collection[PairTarget]) -> bool:
        return self.native_both and len({child for _, child in targets}) == 1

    async def _run_linked(
        self,
        action: str,
        targets: list[PairTarget],
        op: ChildOperation,
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None = None,
    ) -> None:
        """Serialize non-native both over the one physical command lock."""
        del cancel_running
        admission = self._admission
        if not admission.stop_epochs_match(targets, expected_stop_epochs):
            return
        try:
            if self._is_native_group(targets):
                if admission.admission_was_cancelled(
                    targets, resources, entry_cancel, expected_stop_epochs
                ):
                    return
                await op(targets[0][1])
                return

            errors: dict[str, BaseException] = {}
            for side, child in targets:
                if any(
                    admission.was_cancelled(target_side, resources, entry_cancel)
                    for target_side, _ in targets
                ) or not admission.stop_epochs_match(targets, expected_stop_epochs):
                    return
                try:
                    await op(child)
                except Exception as err:  # noqa: BLE001
                    errors[side] = err
                    break
            if errors:
                stop_targets = [
                    (side, self._children[side]) for side in PAIR_SIDES if side in self._children
                ]
                stop_errors = await self._pair._stop_children(stop_targets)
                raise PairedSideError(action, merge_stop_errors(errors, stop_errors))
        except asyncio.CancelledError:
            await self._pair._stop_children(targets)
            raise
        except Exception as err:  # noqa: BLE001
            if self._is_native_group(targets):
                stop_errors = await self._pair._stop_children([(SIDE_BOTH, targets[0][1])])
                raise PairedSideError(
                    action, merge_stop_errors({SIDE_BOTH: err}, stop_errors)
                ) from err
            raise

    async def stop_children(self, targets: list[PairTarget]) -> dict[str, BaseException]:
        from .paired_coordinator import SingleAddressSideCoordinator

        if self.native_both and len(targets) > 1 and len({child for _, child in targets}) == 1:
            targets = [(SIDE_BOTH, targets[0][1])]
        elif len(targets) > 1 and all(
            isinstance(child, SingleAddressSideCoordinator) for _, child in targets
        ):
            # The logical sides share one scheduler. Cancel its existing work
            # once, then preserve and serialize both side-bound STOP writes.
            # Letting each wrapper cancel independently can remove the STOP that
            # the previous wrapper just queued.
            self._single._single_inner.request_command_cancel()
            errors: dict[str, BaseException] = {}
            for side, child in targets:
                assert isinstance(child, SingleAddressSideCoordinator)
                try:
                    await child.async_stop_command(cancel_running=False)
                except BaseException as err:
                    errors[side] = err
                    _LOGGER.warning(
                        "STOP failed on %s logical side (%s): %s",
                        side,
                        child.address,
                        err,
                    )
            return errors
        return await stop_targets(targets)

    async def connect_children(self, *, started_local_sides: Collection[str] = ()) -> bool:
        """Connect the one physical link shared by both logical sides."""
        del started_local_sides
        return await self._single._single_inner.async_connect()
