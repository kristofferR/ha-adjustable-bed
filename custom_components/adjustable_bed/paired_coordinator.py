"""Paired-bed coordinator (Dual Bed 4.0).

A thin parent that owns the two per-side child coordinators behind one uniform
side-routing API (``left`` / ``right`` / ``both``). It holds **no BleakClient of
its own** — every per-link invariant (command lock, cancel/STOP, idle/reconnect
timers, keepalive) lives unchanged in the children. The parent only fans a
command out to the right child(ren) and, for ``both``, guarantees the
partial-failure contract: if one side fails, the other is stopped and a single
aggregated error is raised.

Children are injected (built from child descriptors in production, recording
doubles in tests), so this module never imports the heavy coordinator and is
fully unit-testable. See ``docs/design/dual-bed-4.0-plan.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Collection, Coroutine, Mapping
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo

from .command_scheduler import (
    CommandHandle,
    CommandKind,
    CommandOutcome,
    PreparedCommandInvalidated,
    command_resources,
)
from .const import (
    BED_TYPE_OKIN_CB24,
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    DEFAULT_PAIR_CONNECTION_MODE,
    DOMAIN,
    PAIR_CONNECTION_MODE_AUTO,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_SIDES,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    requires_sequential_pairing,
)

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

CommandFn = Callable[[Any], Coroutine[Any, Any, None]]


def _merge_stop_errors(
    errors: Mapping[str, BaseException],
    stop_errors: Mapping[str, BaseException],
) -> dict[str, BaseException]:
    """Merge command errors with cleanup-STOP failures under distinct keys, so a
    combined failure surfaces both — a dropped STOP can leave a side moving."""
    merged: dict[str, BaseException] = dict(errors)
    for side, err in stop_errors.items():
        merged.setdefault(f"{side} (stop)", err)
    return merged


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


class PairedBedCoordinator:
    """Routes left/right/both commands across two child coordinators."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        children: Mapping[str, AdjustableBedCoordinator],
        *,
        connection_mode: str | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._pair_id: str = entry.data[CONF_PAIR_ID]
        self._name: str = entry.data.get("name", "Adjustable Bed")
        # Ordered {side: child}, left first. A side may be absent only in
        # degraded/test setups; normally both are present (a disconnected child
        # is still present, just not is_connected).
        self._children: dict[str, AdjustableBedCoordinator] = {
            side: children[side] for side in PAIR_SIDES if side in children
        }
        if not self._children:
            raise ValueError("PairedBedCoordinator requires at least one child")
        # Resolve "auto" to a concrete mode from the bed type: single-connection
        # beds (Octo) get the sequential active-connection profile; everything
        # else stays concurrent. An explicit concurrent/sequential choice is
        # honoured as-is. Resolving here (not at pair-build) auto-upgrades any
        # pre-existing "auto" pair on the next load; entry.data stays "auto".
        raw_mode = connection_mode or entry.data.get(
            CONF_PAIR_CONNECTION_MODE, DEFAULT_PAIR_CONNECTION_MODE
        )
        if raw_mode == PAIR_CONNECTION_MODE_AUTO:
            raw_mode = (
                PAIR_CONNECTION_MODE_SEQUENTIAL
                if requires_sequential_pairing(entry.data.get(CONF_BED_TYPE))
                else PAIR_CONNECTION_MODE_CONCURRENT
            )
        self._connection_mode: str = raw_mode
        # Orders connection switching in sequential mode; unused when concurrent.
        self._pair_command_lock = asyncio.Lock()
        # Concurrent pairs use one parent lane per physical side. Independent
        # sides overlap. Linked groups serialize with each other but release the
        # side lanes while waiting for both physical schedulers to become ready.
        self._pair_side_locks = {side: asyncio.Lock() for side in PAIR_SIDES}
        self._pair_group_lock = asyncio.Lock()
        # Preemption: STOP bumps this so a movement still queued on the lock is
        # dropped instead of starting after the stop; _active_children are the
        # sides executing under the lock, so a cancel_running command can cancel
        # them before queueing and preempt instead of waiting out the pulse window.
        self._pair_cancel_counter: dict[str, int] = {SIDE_LEFT: 0, SIDE_RIGHT: 0}
        self._pair_global_cancel_counter: dict[str, int] = {
            SIDE_LEFT: 0,
            SIDE_RIGHT: 0,
        }
        self._pair_resource_cancel_counter: dict[str, dict[str, int]] = {
            SIDE_LEFT: {},
            SIDE_RIGHT: {},
        }
        self._active_children: set[AdjustableBedCoordinator] = set()
        self._active_group_resources: frozenset[str] = frozenset()
        self._connection_state_callbacks: set[Callable[[bool], None]] = set()
        self._child_unsubs: list[Callable[[], None]] = []
        self._wire_child_connection_callbacks()

    # ------------------------------------------------------------------ identity
    @property
    def pair_id(self) -> str:
        return self._pair_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def connection_mode(self) -> str:
        return self._connection_mode

    @property
    def sides(self) -> tuple[str, ...]:
        """Sides that have a child, in stable order."""
        return tuple(self._children)

    @property
    def children(self) -> dict[str, AdjustableBedCoordinator]:
        return dict(self._children)

    def child_for_side(self, side: str) -> AdjustableBedCoordinator | None:
        return self._children.get(side)

    @contextlib.asynccontextmanager
    async def async_capability_reload_guard(self) -> AsyncIterator[None]:
        """Wait for every side to become idle before reloading the pair."""
        targets = list(self._children.items())
        async with contextlib.AsyncExitStack() as stack:
            if self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
                await stack.enter_async_context(self._pair_command_lock)
            else:
                await stack.enter_async_context(self._locked_target_sides(targets))
            for _, child in targets:
                await stack.enter_async_context(child.async_command_operation_guard())
            yield

    async def async_remove_child(self, side: str) -> None:
        """Drop a side whose standalone entry could not be absorbed safely."""
        child = self._children.pop(side, None)
        if child is None:
            return
        # Rebuild the aggregate connection callbacks without the removed child.
        for unsubscribe in self._child_unsubs:
            unsubscribe()
        self._child_unsubs.clear()
        self._wire_child_connection_callbacks()
        await child.async_shutdown()

    @property
    def is_connected(self) -> bool:
        """True if *any* side is connected (a half-available pair is usable)."""
        return any(child.is_connected for child in self._children.values())

    @property
    def device_info(self) -> DeviceInfo:
        """Synthetic parent device; children nest under it via ``via_device``."""
        first = next(iter(self._children.values()))
        child_info = first.device_info
        manufacturer = (
            child_info.get("manufacturer") if isinstance(child_info, dict) else None
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self._pair_id)},
            name=self._name,
            manufacturer=manufacturer,
            model="Adjustable Bed (paired)",
        )

    def entity_unique_id(self, key: str) -> str:
        """Return a stable unique id for a combined parent entity."""
        return f"{self._pair_id}_{key}"

    # ------------------------------------------------------------------ routing
    def _validate_side(self, side: str) -> None:
        if side not in (SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH):
            raise ValueError(f"Unknown side {side!r}")
        if side in (SIDE_LEFT, SIDE_RIGHT) and side not in self._children:
            raise ValueError(f"Paired bed has no {side} side")

    def _targets_for(self, side: str) -> list[tuple[str, AdjustableBedCoordinator]]:
        self._validate_side(side)
        if side == SIDE_BOTH:
            return [(s, self._children[s]) for s in PAIR_SIDES if s in self._children]
        return [(side, self._children[side])]

    def _bump_pair_cancel_generation(
        self, side: str, resources: Collection[str]
    ) -> None:
        """Invalidate queued commands whose resources overlap a newer request."""
        self._pair_cancel_counter[side] += 1
        if "*" in resources:
            self._pair_global_cancel_counter[side] += 1
            return
        resource_counters = self._pair_resource_cancel_counter[side]
        for resource in resources:
            resource_counters[resource] = resource_counters.get(resource, 0) + 1

    def _pair_cancel_generation(
        self, side: str, resources: Collection[str]
    ) -> tuple[int, ...]:
        """Snapshot cancellation state relevant to queued resources."""
        if "*" in resources:
            return (self._pair_cancel_counter[side],)
        return (
            self._pair_global_cancel_counter[side],
            *(
                self._pair_resource_cancel_counter[side].get(resource, 0)
                for resource in sorted(resources)
            ),
        )

    def _pair_command_was_cancelled(
        self,
        side: str,
        resources: Collection[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
    ) -> bool:
        """Return whether a newer overlapping command invalidated this request."""
        return self._pair_cancel_generation(side, resources) != entry_cancel[side]

    # ------------------------------------------------------------------ commands
    async def async_execute_controller_command(
        self,
        command_fn: CommandFn,
        *,
        side: str = SIDE_BOTH,
        cancel_running: bool = True,
        skip_disconnect: bool = False,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None:
        """Run ``command_fn`` on the targeted side(s) with the both-failure contract."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")

        async def op(child: AdjustableBedCoordinator) -> None:
            if resource is None and resources is None:
                await child.async_execute_controller_command(
                    command_fn,
                    cancel_running=cancel_running,
                    skip_disconnect=skip_disconnect,
                )
            else:
                await child.async_execute_controller_command(
                    command_fn,
                    cancel_running=cancel_running,
                    skip_disconnect=skip_disconnect,
                    resource=resource,
                    resources=resources,
                )

        await self._run(
            "command",
            side,
            op,
            cancel_running=cancel_running,
            resource=resource,
            resources=resources,
        )

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: CommandFn,
        move_down_fn: CommandFn,
        move_stop_fn: CommandFn,
        *,
        side: str = SIDE_BOTH,
    ) -> None:
        """Seek a target position on the targeted side(s)."""

        async def op(child: AdjustableBedCoordinator) -> None:
            await child.async_seek_position(
                position_key, target_angle, move_up_fn, move_down_fn, move_stop_fn
            )

        await self._run("seek", side, op, resource=f"motor:{position_key}")

    async def async_run_child_operation(
        self,
        action: str,
        operation: Callable[
            [AdjustableBedCoordinator], Coroutine[Any, Any, None]
        ],
        *,
        side: str = SIDE_BOTH,
        cancel_running: bool = True,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None:
        """Run a child-specific operation with the paired failure contract."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        await self._run(
            action,
            side,
            operation,
            cancel_running=cancel_running,
            resource=resource,
            resources=resources,
        )

    async def _run(
        self,
        action: str,
        side: str,
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
        *,
        cancel_running: bool = True,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None:
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        targets = self._targets_for(side)
        target_sides = [target_side for target_side, _ in targets]
        sequential = self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL

        # Preempt: invalidate any OLDER movement still queued on the lock AND
        # cancel the in-flight command on THIS command's own target sides, so a
        # reverse wins instead of waiting out the pulse window or letting a stale
        # queued movement run first. Both the cancel and the counter bump are
        # per-side — a left command must not abort or invalidate an independent
        # right movement (and vice versa).
        if cancel_running:
            for target_side in target_sides:
                self._bump_pair_cancel_generation(target_side, command_scope)
            target_children = {child for _, child in targets}
            # If this command overlaps the in-flight one, preempt the WHOLE
            # in-flight command (all its children), not just the shared side: a
            # whole-bed command holds the pair lock until BOTH its children
            # finish, so cancelling only the shared side would leave the other
            # still moving AND keep the lock held until its pulse window ends,
            # delaying this command. A NON-overlapping command (e.g. a right
            # command while an independent left-only move runs) leaves the other
            # side alone — it just waits its turn on the lock.
            active_group_overlaps = (
                not self._active_group_resources
                or "*" in self._active_group_resources
                or "*" in command_scope
                or not command_scope.isdisjoint(self._active_group_resources)
            )
            if any(child in target_children for child in self._active_children) and (
                sequential or active_group_overlaps
            ):
                cancel_scope = self._active_group_resources or command_scope
                for child in list(self._active_children):
                    child.request_command_cancel(resources=cancel_scope)
        entry_cancel = {
            s: self._pair_cancel_generation(s, command_scope) for s in target_sides
        }

        if not sequential:
            if len(targets) == 1:
                target_side, child = targets[0]
                await self._run_single_concurrent(
                    action,
                    target_side,
                    child,
                    op,
                    cancel_running=cancel_running,
                    resources=command_scope,
                    entry_cancel=entry_cancel,
                )
                return

            # Only one linked group may coordinate the two device schedulers at
            # a time. The group itself briefly takes the side lanes for enqueue
            # and takes them again for commit/execution, but releases them while
            # waiting for READY so a command for the active motor can preempt.
            async with self._pair_group_lock:
                if any(
                    self._pair_command_was_cancelled(s, command_scope, entry_cancel)
                    for s in target_sides
                ):
                    return

                active_children = {child for _, child in targets}
                self._active_children = active_children
                self._active_group_resources = command_scope
                try:
                    await self._run_both_concurrent(
                        action,
                        targets,
                        op,
                        cancel_running=cancel_running,
                        resources=command_scope,
                        entry_cancel=entry_cancel,
                    )
                finally:
                    self._active_children = set()
                    self._active_group_resources = frozenset()
            return

        # Sequential pairs share a one-link connection lane. Keep the existing
        # lock and disconnect dead-man sequencing for that hardware profile.
        async with self._pair_command_lock:
            # A STOP (or newer command) bumped one of OUR target sides while we
            # waited — drop this now-stale movement instead of starting it right
            # after the safety stop.
            if any(
                self._pair_command_was_cancelled(s, command_scope, entry_cancel)
                for s in target_sides
            ):
                return

            self._active_children = {child for _, child in targets}
            try:
                try:
                    await self._run_both_sequential(
                        action, targets, op, entry_cancel, command_scope
                    )
                except asyncio.CancelledError:
                    # The parent command was cancelled (service cancellation or
                    # config-entry unload) while a side may still be moving.
                    # Cancelling the child TASKS is not the same as a STOP write,
                    # so explicitly STOP the still-connected side(s) before
                    # propagating — otherwise a motor can be left running. In
                    # sequential mode _stop_children only targets a side that is
                    # still connected (a disconnected side already halted on its
                    # link drop). _stop_children never raises and we re-raise the
                    # cancellation regardless, so this is best-effort cleanup.
                    await self._stop_children(targets)
                    raise
            finally:
                self._active_children = set()

    @contextlib.asynccontextmanager
    async def _locked_target_sides(
        self, targets: Collection[tuple[str, AdjustableBedCoordinator]]
    ) -> AsyncIterator[None]:
        """Lock selected physical side lanes in stable order."""
        target_by_side = dict(targets)
        async with contextlib.AsyncExitStack() as stack:
            for side in PAIR_SIDES:
                if side in target_by_side:
                    await stack.enter_async_context(self._pair_side_locks[side])
            yield

    async def _run_single_concurrent(
        self,
        action: str,
        side: str,
        child: AdjustableBedCoordinator,
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
    ) -> None:
        """Admit one side without holding pair metadata across its operation."""
        prepare = getattr(child, "async_prepare_command_operation", None)
        prepare_owner = getattr(child, "_single_inner", child)
        if not callable(prepare) or not callable(
            getattr(prepare_owner, "async_prepare_command_operation", None)
        ):
            # Compatibility for coordinator doubles. Separate side locks still
            # allow left and right to overlap while serializing one fake child.
            async with self._pair_side_locks[side]:
                if self._pair_command_was_cancelled(side, resources, entry_cancel):
                    return
                await op(child)
            return

        handle: CommandHandle | None = None
        async with self._pair_side_locks[side]:
            if self._pair_command_was_cancelled(side, resources, entry_cancel):
                return
            handle = await child.async_prepare_command_operation(
                lambda: op(child),
                resources=resources,
                cancel_running=cancel_running,
                group_id=uuid4().hex,
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
        async with self._pair_side_locks[side]:
            try:
                await child.async_wait_prepared_command(handle)
                if self._pair_command_was_cancelled(side, resources, entry_cancel):
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

    async def _run_both_concurrent(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
    ) -> None:
        """Prepare every physical scheduler, then commit the linked command."""
        del entry_cancel
        if not all(
            callable(getattr(child, "async_prepare_command_operation", None))
            for _, child in targets
        ):
            # Compatibility for third-party/test coordinator doubles. Production
            # children always expose the scheduler reservation API.
            async with self._locked_target_sides(targets):
                await self._run_both_concurrent_legacy(action, targets, op)
            return

        group_id = uuid4().hex
        child_by_side = dict(targets)
        prepared: dict[str, tuple[AdjustableBedCoordinator, CommandHandle]] = {}
        committed = False
        result_tasks: dict[str, asyncio.Task[None]] = {}

        def collect_enqueues(
            enqueue_tasks: Mapping[str, asyncio.Task[CommandHandle]],
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
                    prepared[side] = (child_by_side[side], handle)
            return errors

        def is_expected_invalidation(side: str, error: BaseException | None) -> bool:
            return isinstance(error, PreparedCommandInvalidated) and (
                prepared[side][1].outcome
                in {CommandOutcome.REPLACED, CommandOutcome.STOPPED}
            )

        try:
            async with self._locked_target_sides(targets):
                enqueue_tasks = {
                    side: asyncio.create_task(
                        child.async_prepare_command_operation(
                            lambda child=child: op(child),
                            resources=resources,
                            cancel_running=cancel_running,
                            group_id=group_id,
                        )
                    )
                    for side, child in targets
                }
                try:
                    await asyncio.gather(
                        *enqueue_tasks.values(), return_exceptions=True
                    )
                except asyncio.CancelledError:
                    for task in enqueue_tasks.values():
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        *enqueue_tasks.values(), return_exceptions=True
                    )
                    collect_enqueues(enqueue_tasks)
                    raise
                enqueue_errors = collect_enqueues(enqueue_tasks)
                if enqueue_errors:
                    raise PairedSideError(action, enqueue_errors)

            # Do not hold the side lanes while an older operation is ahead of a
            # group reservation. A newer replacement for that active resource
            # can now enter its child scheduler and run before this disjoint group.
            ready_tasks = {
                side: asyncio.create_task(child.async_wait_prepared_command(handle))
                for side, (child, handle) in prepared.items()
            }
            ready_results = await asyncio.gather(
                *ready_tasks.values(), return_exceptions=True
            )
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
            async with self._locked_target_sides(targets):
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
                if revalidation_invalidated:
                    return

                # No controller coroutine has run before this point. Commit every
                # ready handle synchronously so neither side can observe a partial
                # group caused by another await between releases.
                for child, handle in prepared.values():
                    child.commit_prepared_command(handle)
                committed = True

                result_tasks = {
                    side: asyncio.create_task(
                        child.async_wait_prepared_command_result(handle)
                    )
                    for side, (child, handle) in prepared.items()
                }
                try:
                    await asyncio.wait(
                        result_tasks.values(), return_when=asyncio.FIRST_EXCEPTION
                    )
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
                        stop_errors = await self._stop_children(targets)
                        raise PairedSideError(
                            action, _merge_stop_errors(errors, stop_errors)
                        )

                    if expected_invalidations:
                        settled = await asyncio.gather(
                            *result_tasks.values(), return_exceptions=True
                        )
                        late_errors = {
                            side: result
                            for side, result in zip(
                                result_tasks, settled, strict=True
                            )
                            if isinstance(result, BaseException)
                            and not is_expected_invalidation(side, result)
                        }
                        if late_errors:
                            stop_errors = await self._stop_children(targets)
                            raise PairedSideError(
                                action,
                                _merge_stop_errors(late_errors, stop_errors),
                            )
                    else:
                        await asyncio.gather(*result_tasks.values())
                except asyncio.CancelledError:
                    await self._stop_children(targets)
                    raise
                finally:
                    for task in result_tasks.values():
                        if not task.done():
                            task.cancel()
                    if result_tasks:
                        await asyncio.gather(
                            *result_tasks.values(), return_exceptions=True
                        )
        finally:
            if not committed:
                await asyncio.gather(
                    *(
                        child.async_abort_prepared_command(handle)
                        for child, handle in prepared.values()
                    ),
                    return_exceptions=True,
                )

    async def _run_both_concurrent_legacy(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
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
                stop_errors = await self._stop_children(targets)
                raise PairedSideError(action, _merge_stop_errors(errors, stop_errors))
        except asyncio.CancelledError:
            await self._stop_children(targets)
            raise
        finally:
            # Never let a child task outlive this call (e.g. if the parent
            # coroutine is cancelled mid-wait): cancel any still-running task and
            # settle them all so none keep writing outside the parent lock.
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def _run_both_sequential(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
        entry_cancel: Mapping[str, tuple[int, ...]],
        resources: frozenset[str],
    ) -> None:
        """Run each side in turn holding only ONE BLE link at a time: connect the
        side, run its op, then disconnect it before moving to the next.

        Used for single-connection beds (Octo) whose firmware allows only one
        concurrent link. Dropping the link halts that side's motors (verified
        dead-man model — the bed only moves while a command stream arrives), so a
        side that has been disconnected needs no separate STOP. On failure the
        loop stops at the first failing side; every side that was connected is
        disconnected (the ``finally``), so nothing is left connected or moving.

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
                self._pair_command_was_cancelled(s, resources, entry_cancel)
                for s, _ in targets
            )

        for side, child in targets:
            if cycle_cancelled():
                # A STOP / newer command landed mid-cycle — abort before
                # connecting this side (the earlier side already disconnected).
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
                connected = await child.async_connect()
            except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                errors[side] = err
                break
            if not connected:
                errors[side] = HomeAssistantError(
                    f"{side} side of the pair could not be connected"
                )
                break

            # A STOP (or newer command) may have landed WHILE we were connecting —
            # _stop_children couldn't reach this side then (it wasn't connected
            # yet), so re-check now and bail (releasing the link) instead of
            # starting a motor command after the STOP was accepted.
            if cycle_cancelled():
                if not await self._safe_disconnect(side, child):
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
                await self._safe_disconnect(side, child)
                raise
            except Exception as err:  # noqa: BLE001
                op_error = err

            # Disconnecting is BOTH the one-link guard and the halt for this side,
            # so a disconnect failure is fatal: abort rather than connect the next
            # side onto a possibly-still-live/moving link.
            disconnected = await self._safe_disconnect(side, child)
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

    async def _release_other_sides(self, keep: AdjustableBedCoordinator) -> bool:
        """Disconnect every side except ``keep`` (the one-link guard before a
        sequential connect). Returns False if any disconnect failed, so the caller
        can abort rather than risk opening a second link."""
        ok = True
        for side, child in self._children.items():
            if child is not keep and child.is_connected:
                if not await self._safe_disconnect(side, child):
                    ok = False
        return ok

    async def _safe_disconnect(
        self, side: str, child: AdjustableBedCoordinator
    ) -> bool:
        """Disconnect one side, swallowing failures. Returns True on success — a
        disconnect error must not mask the command outcome, but callers that rely
        on the link actually being down (sequential switching) check the result.

        The child returns False when Bleak reports that the physical link remains
        active after a failed disconnect. Older test doubles return None, which is
        treated as success for backward compatibility.
        """
        try:
            disconnected = await child.async_disconnect("sequential_switch")
        except Exception as err:  # noqa: BLE001 - CancelledError must propagate
            _LOGGER.warning(
                "Disconnect failed on %s side (%s): %s", side, child.address, err
            )
            return False
        return disconnected is not False and not child.is_connected

    async def async_stop_command(self, *, side: str = SIDE_BOTH) -> None:
        """Stop the targeted side(s); never let one side's failure skip another."""
        targets = self._targets_for(side)
        # Bump each targeted side's counter so a movement still queued on the pair
        # lock for that side drops instead of starting right after this safety stop.
        for target_side, _ in targets:
            self._bump_pair_cancel_generation(target_side, command_resources("*"))
        errors = await self._stop_children(targets)
        if errors:
            raise PairedSideError("stop", errors)

    async def _stop_children(
        self, targets: list[tuple[str, AdjustableBedCoordinator]]
    ) -> dict[str, BaseException]:
        """Send STOP to every target, swallowing individual failures.

        Returns the per-side errors (if any). Always attempts every side — a STOP
        failure on one must never prevent stopping another.

        In sequential mode only a side that is still CONNECTED is stopped: a
        disconnected side already halted when its link dropped (dead-man model),
        and stopping it would reconnect it (async_stop_command ensures a link),
        momentarily creating the two-link state the sequential profile avoids.
        """
        if self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
            targets = [(side, child) for side, child in targets if child.is_connected]
        results = await asyncio.gather(
            *(child.async_stop_command() for _, child in targets),
            return_exceptions=True,
        )
        errors: dict[str, BaseException] = {}
        for (side, child), result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                errors[side] = result
                _LOGGER.warning(
                    "STOP failed on %s side (%s): %s", side, child.address, result
                )
        return errors

    # ------------------------------------------------------------------ lifecycle
    async def async_connect(self) -> bool:
        """Connect the children; succeed if *at least one* connects (half-available)."""
        items = list(self._children.items())
        if self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
            # Single-connection beds hold one link at a time, so don't keep either
            # side connected after setup. Connect each side once to verify it is
            # reachable (this is also where a capability snapshot is captured),
            # then release it; commands reconnect the targeted side on demand.
            any_connected = False
            for side, child in items:
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
                    if not await self._safe_disconnect(side, child):
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

        results = await asyncio.gather(
            *(child.async_connect() for _, child in items), return_exceptions=True
        )
        for (side, _), result in zip(items, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Connect failed on %s side: %s", side, result)
        return any(result is True for result in results)

    async def async_disconnect(self, reason: str = "intentional") -> None:
        await asyncio.gather(
            *(child.async_disconnect(reason) for child in self._children.values()),
            return_exceptions=True,
        )

    async def async_shutdown(self) -> None:
        for unsub in self._child_unsubs:
            unsub()
        self._child_unsubs.clear()
        await asyncio.gather(
            *(child.async_shutdown() for child in self._children.values()),
            return_exceptions=True,
        )

    def consume_internal_entry_update(self, entry: ConfigEntry) -> bool:
        """Let the side that changed bond state claim the parent entry update.

        A separate-address pair persists a child's runtime bond markers by
        updating the one real parent entry. The update listener therefore sees
        this wrapper, not the child that armed the internal-update marker.
        Forwarding the check prevents a successful verification or confirmed
        removal from unnecessarily reloading and disconnecting both sides.
        """
        # Each parent write queues its own listener invocation. Consume exactly
        # one marker per pass so concurrent child writes can each claim theirs.
        return any(
            child.consume_internal_entry_update(entry)
            for child in self._children.values()
        )

    # --------------------------------------------------- connection-state relay
    def _wire_child_connection_callbacks(self) -> None:
        for child in self._children.values():
            self._child_unsubs.append(
                child.register_connection_state_callback(
                    self._on_child_connection_change
                )
            )

    def _on_child_connection_change(self, _connected: bool) -> None:
        aggregate = self.is_connected
        for callback_fn in list(self._connection_state_callbacks):
            try:
                callback_fn(aggregate)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Paired connection state callback error: %s", err)

    def register_connection_state_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register for aggregate (any-side) connection-state changes."""
        self._connection_state_callbacks.add(callback_fn)

        def unregister() -> None:
            self._connection_state_callbacks.discard(callback_fn)

        return unregister


class SingleAddressSideCoordinator:
    """Logical left/right coordinator view over one physical BLE coordinator."""

    def __init__(
        self,
        inner: AdjustableBedCoordinator,
        side: str,
        hydration_owner: SingleAddressPairedCoordinator,
    ) -> None:
        object.__setattr__(self, "_single_inner", inner)
        object.__setattr__(self, "_single_side", side)
        object.__setattr__(self, "_single_hydration_owner", hydration_owner)
        object.__setattr__(self, "_single_position_data", {})
        object.__setattr__(self, "_single_position_callbacks", set())
        # CB24 reports one shared set of axes, so reconnect hydration can relay
        # it to both views. Other single-address protocols use the same axis
        # keys per side, where an unbound response would overwrite the other
        # side's state.
        if inner.bed_type == BED_TYPE_OKIN_CB24:
            object.__setattr__(
                self,
                "_single_unregister_position_callback",
                inner.register_position_callback(
                    lambda _positions: self._sync_position_state()
                ),
            )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_single_"):
            raise AttributeError(name)
        return getattr(self._single_inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_single_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._single_inner, name, value)

    def __hash__(self) -> int:
        return hash(id(self._single_inner))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SingleAddressSideCoordinator) and (
            self._single_inner is other._single_inner
        )

    @property
    def side(self) -> str:
        return self._single_side

    @property
    def entity_side(self) -> str:
        """Logical side exposed to entity state and the Lovelace card."""
        return self._single_side

    @property
    def operation_identity(self) -> int:
        """Shared key used by preflight plans for left/right/native-both views."""
        return id(self._single_inner)

    @property
    def position_data(self) -> dict[str, float]:
        return dict(self._single_position_data)

    def _sync_position_state(self) -> None:
        self._single_position_data.clear()
        self._single_position_data.update(self._single_inner.position_data)
        for callback_fn in list(self._single_position_callbacks):
            callback_fn(dict(self._single_position_data))

    def _set_position_state(self, position_key: str, target_angle: float) -> None:
        """Publish a successful direct-position target to this logical side."""
        self._single_position_data[position_key] = target_angle
        for callback_fn in list(self._single_position_callbacks):
            callback_fn(dict(self._single_position_data))

    def _unregister_inner_position_callback(self) -> None:
        """Release the shared-position relay registered by CB24 views."""
        unregister = getattr(self, "_single_unregister_position_callback", None)
        if unregister is not None:
            unregister()
            object.__setattr__(self, "_single_unregister_position_callback", None)

    def register_position_callback(
        self, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]:
        self._single_position_callbacks.add(callback_fn)
        if self._single_position_data:
            callback_fn(dict(self._single_position_data))

        def unregister() -> None:
            self._single_position_callbacks.discard(callback_fn)

        return unregister

    @property
    def controller(self) -> Any | None:
        controller = self._single_inner.controller
        return controller.bind_side(self._single_side) if controller is not None else None

    @property
    def capability_controller(self) -> Any | None:
        controller = self._single_inner.capability_controller
        return controller.bind_side(self._single_side) if controller is not None else None

    def entity_unique_id(self, key: str) -> str:
        suffix = f"_{self._single_side}"
        sided_key = key if key.endswith(suffix) else f"{key}{suffix}"
        return f"{self._single_inner.address}_{sided_key}"

    def entity_translation_key(self, key: str) -> str:
        suffix = f"_{self._single_side}"
        return key if key.endswith(suffix) else f"{key}{suffix}"

    def _scoped_command_resources(
        self,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> frozenset[str]:
        """Namespace scheduler resources by logical side on the shared link."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        raw_resources = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        sides = PAIR_SIDES if self._single_side == SIDE_BOTH else (self._single_side,)
        return frozenset(
            f"side:{side}:{item}" for side in sides for item in raw_resources
        )

    def request_command_cancel(
        self,
        resource: str | None = None,
        *,
        resources: Collection[str] | None = None,
    ) -> None:
        """Cancel only this logical side's resources on the shared scheduler."""
        self._single_inner.request_command_cancel(
            resources=self._scoped_command_resources(resource, resources)
        )

    async def async_prepare_command_operation(
        self,
        operation: Callable[[], Coroutine[Any, Any, None]],
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reserve this logical side without colliding with the other side."""
        return await self._single_inner.async_prepare_command_operation(
            operation,
            resources=self._scoped_command_resources(resource, resources),
            **kwargs,
        )

    async def async_execute_controller_command(
        self, command_fn: CommandFn, **kwargs: Any
    ) -> None:
        async def bound(controller: Any) -> None:
            await command_fn(controller.bind_side(self._single_side))

        resource = kwargs.pop("resource", None)
        resources = kwargs.pop("resources", None)
        await self._single_inner.async_execute_controller_command(
            bound,
            resources=self._scoped_command_resources(resource, resources),
            **kwargs,
        )
        self._sync_position_state()

    async def async_execute_command_group(
        self,
        operations: Collection[Callable[[], Coroutine[Any, Any, None]]],
        *,
        resources: Collection[str],
        **kwargs: Any,
    ) -> None:
        """Run a logical-side command group on side-scoped resources."""
        await self._single_inner.async_execute_command_group(
            operations,
            resources=self._scoped_command_resources(resources=resources),
            **kwargs,
        )

    async def async_execute_controller_query(
        self, query_fn: Callable[[Any], Coroutine[Any, Any, Any]], **kwargs: Any
    ) -> Any:
        async def bound(controller: Any) -> Any:
            return await query_fn(controller.bind_side(self._single_side))

        result = await self._single_inner.async_execute_controller_query(bound, **kwargs)
        self._sync_position_state()
        return result

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: CommandFn,
        move_down_fn: CommandFn,
        move_stop_fn: CommandFn,
    ) -> None:
        controller = self.capability_controller
        if controller is not None and controller.supports_direct_position_control:

            async def set_direct(live_controller: Any) -> None:
                bound = live_controller.bind_side(self._single_side)
                native = bound.angle_to_native_position(position_key, target_angle)
                await bound.set_motor_position(position_key, native)

            await self._single_inner.async_execute_controller_command(
                set_direct,
                resources=self._scoped_command_resources(
                    resource=f"motor:{position_key}"
                ),
            )
            self._set_position_state(position_key, target_angle)
            return

        def bind(fn: CommandFn) -> CommandFn:
            async def bound(controller: Any) -> None:
                await fn(controller.bind_side(self._single_side))

            return bound

        await self._single_inner.async_seek_position(
            position_key,
            target_angle,
            bind(move_up_fn),
            bind(move_down_fn),
            bind(move_stop_fn),
            resources=self._scoped_command_resources(
                resource=f"motor:{position_key}"
            ),
        )
        self._sync_position_state()

    async def async_read_initial_positions(self) -> None:
        if self._single_inner.disable_angle_sensing:
            return

        async def read(controller: Any) -> None:
            bound = controller.bind_side(self._single_side)
            await bound.prepare_for_position_read()
            await bound.read_positions(self._single_inner.motor_count)

        await self._single_inner.async_execute_controller_query(
            read, skip_disconnect=True
        )
        self._sync_position_state()

    async def async_pause_position_hydration(self) -> None:
        """Pause both physical and logical hydration through the paired owner."""
        await self._single_hydration_owner.async_pause_position_hydration()

    def resume_position_hydration(self) -> None:
        """Resume both physical and logical hydration through the paired owner."""
        self._single_hydration_owner.resume_position_hydration()

    async def async_stop_command(
        self, *, cancel_running: bool = True, **_kwargs: Any
    ) -> None:
        if cancel_running:
            self.request_command_cancel()

        async def stop(controller: Any) -> None:
            await controller.bind_side(self._single_side).stop_all()

        await self._single_inner.async_execute_controller_command(
            stop,
            cancel_running=False,
            resources=self._scoped_command_resources(),
            kind=CommandKind.STOP,
        )


class SingleAddressPairedCoordinator(PairedBedCoordinator):
    """Paired surface backed by one coordinator and one physical BLE link."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        inner: AdjustableBedCoordinator,
    ) -> None:
        self._single_inner = inner
        self._single_native_both = entry.data.get(CONF_BED_TYPE) != BED_TYPE_SLEEP_NUMBER
        self._single_position_hydration_task: asyncio.Task[None] | None = None
        self._single_position_hydration_pause_count = 0
        children = {
            SIDE_LEFT: SingleAddressSideCoordinator(inner, SIDE_LEFT, self),
            SIDE_RIGHT: SingleAddressSideCoordinator(inner, SIDE_RIGHT, self),
        }
        self._single_both = SingleAddressSideCoordinator(inner, SIDE_BOTH, self)
        self._single_side_coordinators = (*children.values(), self._single_both)
        super().__init__(
            hass,
            entry,
            children,  # type: ignore[arg-type]
            connection_mode=PAIR_CONNECTION_MODE_CONCURRENT,
        )

    @property
    def is_connected(self) -> bool:
        return self._single_inner.is_connected

    @property
    def device_info(self) -> DeviceInfo:
        return self._single_inner.device_info

    def entity_unique_id(self, key: str) -> str:
        return f"{self._single_inner.address}_{key}"

    def _targets_for(self, side: str) -> list[tuple[str, AdjustableBedCoordinator]]:
        self._validate_side(side)
        if side == SIDE_BOTH and self._single_native_both:
            return [
                (SIDE_LEFT, self._single_both),
                (SIDE_RIGHT, self._single_both),
            ]  # type: ignore[list-item]
        return super()._targets_for(side)

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: CommandFn,
        move_down_fn: CommandFn,
        move_stop_fn: CommandFn,
        *,
        side: str = SIDE_BOTH,
    ) -> None:
        """Seek a logical side and mirror native-both direct targets to both views."""
        await super().async_seek_position(
            position_key,
            target_angle,
            move_up_fn,
            move_down_fn,
            move_stop_fn,
            side=side,
        )
        controller = self._single_both.capability_controller
        if (
            side == SIDE_BOTH
            and self._single_native_both
            and controller is not None
            and controller.supports_direct_position_control
        ):
            for child in self._children.values():
                if isinstance(child, SingleAddressSideCoordinator):
                    child._set_position_state(position_key, target_angle)

    async def _run_both_concurrent(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
        *,
        cancel_running: bool,
        resources: frozenset[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
    ) -> None:
        """Serialize non-native both over the one physical command lock."""
        del cancel_running
        try:
            if self._single_native_both and len({child for _, child in targets}) == 1:
                await op(targets[0][1])
                return

            errors: dict[str, BaseException] = {}
            for side, child in targets:
                if any(
                    self._pair_command_was_cancelled(
                        target_side, resources, entry_cancel
                    )
                    for target_side, _ in targets
                ):
                    return
                try:
                    await op(child)
                except Exception as err:  # noqa: BLE001
                    errors[side] = err
                    break
            if errors:
                stop_targets = [
                    (side, self._children[side])
                    for side in PAIR_SIDES
                    if side in self._children
                ]
                stop_errors = await self._stop_children(stop_targets)
                raise PairedSideError(
                    action, _merge_stop_errors(errors, stop_errors)
                )
        except asyncio.CancelledError:
            await self._stop_children(targets)
            raise
        except Exception as err:  # noqa: BLE001
            if self._single_native_both and len({child for _, child in targets}) == 1:
                stop_errors = await self._stop_children(
                    [(SIDE_BOTH, targets[0][1])]
                )
                raise PairedSideError(
                    action,
                    _merge_stop_errors({SIDE_BOTH: err}, stop_errors),
                ) from err
            raise

    async def _stop_children(
        self, targets: list[tuple[str, AdjustableBedCoordinator]]
    ) -> dict[str, BaseException]:
        if (
            self._single_native_both
            and len(targets) > 1
            and len({child for _, child in targets}) == 1
        ):
            targets = [(SIDE_BOTH, targets[0][1])]
        elif len(targets) > 1 and all(
            isinstance(child, SingleAddressSideCoordinator)
            for _, child in targets
        ):
            # The logical sides share one scheduler. Cancel its existing work
            # once, then preserve and serialize both side-bound STOP writes.
            # Letting each wrapper cancel independently can remove the STOP that
            # the previous wrapper just queued.
            self._single_inner.request_command_cancel()
            errors: dict[str, BaseException] = {}
            for side, child in targets:
                assert isinstance(child, SingleAddressSideCoordinator)
                logical_child: Any = child
                try:
                    await logical_child.async_stop_command(cancel_running=False)
                except BaseException as err:
                    errors[side] = err
                    _LOGGER.warning(
                        "STOP failed on %s logical side (%s): %s",
                        side,
                        child.address,
                        err,
                    )
            return errors
        return await super()._stop_children(targets)

    async def async_connect(self) -> bool:
        return await self._single_inner.async_connect()

    def _on_child_connection_change(self, connected: bool) -> None:
        super()._on_child_connection_change(connected)
        if not connected:
            task = self._single_position_hydration_task
            if task is not None and not task.done():
                task.cancel()
            return
        if self._single_inner.bed_type != BED_TYPE_SLEEP_NUMBER:
            return
        self._schedule_single_position_hydration()

    def _schedule_single_position_hydration(self) -> None:
        """Refresh logical sides unless diagnostics currently own the BLE link."""
        if self._single_position_hydration_pause_count:
            return
        previous_task = self._single_position_hydration_task
        if previous_task is not None and not previous_task.done():
            previous_task.cancel()
        else:
            previous_task = None
        self._single_position_hydration_task = self.entry.async_create_background_task(
            self.hass,
            self._async_hydrate_logical_positions(previous_task),
            name=f"adjustable_bed_single_address_position_hydration_{self.entry.entry_id}",
        )

    async def _async_hydrate_logical_positions(
        self, previous_task: asyncio.Task[None] | None = None
    ) -> None:
        """Refresh each logical side without mixing same-named position axes."""
        current_task = asyncio.current_task()
        retry_after_preemption = False
        try:
            if previous_task is not None:
                try:
                    await previous_task
                except asyncio.CancelledError:
                    if current_task is not None and current_task.cancelling():
                        raise
            # The inner coordinator schedules an unbound read during connect.
            # Replace it with side-bound reads for protocols whose two logical
            # sides report the same axis names.
            await self._single_inner._async_cancel_position_hydration()
            if current_task is not None and current_task.cancelling():
                raise asyncio.CancelledError
            results = await asyncio.gather(
                *(
                    child.async_read_initial_positions()
                    for child in self._children.values()
                ),
                return_exceptions=True,
            )
            for side, result in zip(self._children, results, strict=True):
                if isinstance(result, asyncio.CancelledError):
                    retry_after_preemption = True
                if isinstance(result, BaseException):
                    _LOGGER.debug(
                        "Single-address position hydration failed for %s side: %s",
                        side,
                        result,
                    )
        finally:
            if self._single_position_hydration_task is current_task:
                self._single_position_hydration_task = None
            if (
                retry_after_preemption
                and (current_task is None or not current_task.cancelling())
                and not self._single_position_hydration_pause_count
                and self._single_inner.is_connected
                and self._single_inner.bed_type == BED_TYPE_SLEEP_NUMBER
            ):
                self._schedule_single_position_hydration()

    async def _async_cancel_single_position_hydration(self) -> None:
        """Cancel and await logical-side hydration."""
        task = self._single_position_hydration_task
        try:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
        finally:
            if self._single_position_hydration_task is task:
                self._single_position_hydration_task = None

    async def async_pause_position_hydration(self) -> None:
        """Pause physical and logical hydration during diagnostics."""
        self._single_position_hydration_pause_count += 1
        await self._single_inner.async_pause_position_hydration()
        await self._async_cancel_single_position_hydration()

    def resume_position_hydration(self) -> None:
        """Resume physical and logical hydration after diagnostics."""
        if self._single_position_hydration_pause_count == 0:
            return
        self._single_position_hydration_pause_count -= 1
        self._single_inner.resume_position_hydration()
        if (
            self._single_position_hydration_pause_count == 0
            and self._single_inner.is_connected
            and self._single_inner.bed_type == BED_TYPE_SLEEP_NUMBER
        ):
            self._schedule_single_position_hydration()

    async def async_disconnect(self, reason: str = "intentional") -> None:
        await self._single_inner.async_disconnect(reason)

    @contextlib.asynccontextmanager
    async def async_transport_operation(self, operation: str) -> AsyncIterator[None]:
        """Hold the one physical link still for a whole transport operation.

        This surface keeps the entry's own address, so it is offered the bond
        actions. The locks and the link both live on the inner coordinator, so
        the gate has to be its gate rather than a second one that guards
        nothing.
        """
        async with self._single_inner.async_transport_operation(operation):
            yield

    def apply_confirmed_bond_removal(self) -> None:
        """Clear the bond state held by the coordinator that owns the link."""
        self._single_inner.apply_confirmed_bond_removal()

    def begin_internal_bond_update(
        self,
        bond_established: bool,
        *,
        marker_unreliable: bool | None = None,
    ) -> None:
        """Tag the next bond write on the coordinator that owns the link."""
        self._single_inner.begin_internal_bond_update(
            bond_established,
            marker_unreliable=marker_unreliable,
        )

    async def async_shutdown(self) -> None:
        # Suppress reconnect-driven hydration before awaiting cancellation:
        # connection callbacks can otherwise replace the task being drained.
        self._single_position_hydration_pause_count += 1
        for unsub in self._child_unsubs:
            unsub()
        self._child_unsubs.clear()
        try:
            await self._async_cancel_single_position_hydration()
        finally:
            try:
                # Also drain any task queued by a callback that was already in
                # flight when shutdown disabled future scheduling.
                await self._async_cancel_single_position_hydration()
            finally:
                for side_coordinator in self._single_side_coordinators:
                    side_coordinator._unregister_inner_position_callback()
                await self._single_inner.async_shutdown()

    def _wire_child_connection_callbacks(self) -> None:
        self._child_unsubs.append(
            self._single_inner.register_connection_state_callback(
                self._on_child_connection_change
            )
        )


class PairedSideProxy:
    """A child coordinator as seen by its per-side entities, with writes routed
    through the parent so they take the pair command lock.

    Per-side cover/button/number/switch entities are built against this proxy:
    reads and identity (device, unique_id, controller, positions, listeners)
    come straight from the wrapped child, while movement/command writes go
    through the parent with this side. That way a side command waits for an
    in-flight whole-bed command instead of starting concurrently and
    desyncing the pair. (Connect/disconnect stay per-child — they're connection
    management, not motion, and don't need the pair lock.)
    """

    def __init__(
        self,
        parent: PairedBedCoordinator,
        child: AdjustableBedCoordinator,
        side: str,
    ) -> None:
        """Wrap ``child`` (on ``side``) with writes routed through ``parent``."""
        self._pair_parent = parent
        self._pair_child = child
        self._pair_side = side

    def __getattr__(self, name: str) -> Any:
        # Everything not overridden below delegates to the wrapped child. Guard
        # the proxy's own attrs so a miss before __init__ can't infinitely recurse.
        if name.startswith("_pair_"):
            raise AttributeError(name)
        return getattr(self._pair_child, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # The proxy's own wiring stays local; everything else delegates to the
        # child so existing entity and coordinator state surfaces stay compatible.
        if name.startswith("_pair_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._pair_child, name, value)

    async def async_execute_controller_command(
        self, command_fn: CommandFn, **kwargs: Any
    ) -> None:
        """Route a side command through the parent (takes the pair lock)."""
        await self._pair_parent.async_execute_controller_command(
            command_fn, side=self._pair_side, **kwargs
        )

    async def async_seek_position(self, *args: Any, **kwargs: Any) -> None:
        """Route a side seek through the parent (takes the pair lock)."""
        await self._pair_parent.async_seek_position(
            *args, side=self._pair_side, **kwargs
        )

    async def async_stop_command(self, **kwargs: Any) -> None:
        """Stop just this side via the parent's resilient stop contract."""
        await self._pair_parent.async_stop_command(side=self._pair_side)
