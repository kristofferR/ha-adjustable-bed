"""Device-scoped command admission for adjustable beds.

The scheduler deliberately treats controller operations as opaque. It orders
them, scopes replacement to the resources they control, and provides an atomic
prepare/commit gate for paired coordinators, but it never slices or interleaves
protocol coroutines. Protocol-specific concurrency can be added behind a
different execution strategy once its wire behaviour is proven.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Awaitable, Callable, Collection
from contextvars import Context, ContextVar, Token, copy_context
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final
from uuid import uuid4

ALL_COMMAND_RESOURCES: Final = frozenset({"*"})
MAX_RECENT_COMMAND_RECORDS: Final = 20


class CommandKind(StrEnum):
    """Broad command category used by diagnostics and future strategies."""

    COMMAND = "command"
    SEEK = "seek"
    GROUP = "group"
    STOP = "stop"


class CommandState(StrEnum):
    """Lifecycle state of an admitted command."""

    QUEUED = "queued"
    PREPARED = "prepared"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CommandOutcome(StrEnum):
    """Terminal result of a command handle."""

    COMPLETED = "completed"
    REPLACED = "replaced"
    STOPPED = "stopped"
    CALLER_CANCELLED = "caller_cancelled"
    GROUP_ABORTED = "group_aborted"
    SHUTDOWN = "shutdown"
    TIMEOUT = "timeout"
    FAILED = "failed"


class PreparedCommandInvalidated(RuntimeError):
    """Raised when a linked command loses its reservation before completion."""


@dataclass(slots=True)
class CommandContext:
    """Task-local state for one controller operation."""

    scheduler_token: object
    cancel_event: asyncio.Event
    admitted_stop_epoch: int
    intent_id: str
    kind: CommandKind
    group_id: str | None
    resources: frozenset[str]
    pulse_count: int | None = None
    pulse_delay_ms: int | None = None
    cancel_reason: CommandOutcome | None = None
    active: bool = True
    defer_disconnect: bool = False


CommandOperation = Callable[[CommandContext], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CommandIntent:
    """A unit of requested bed behaviour."""

    operation: CommandOperation
    resources: frozenset[str] = ALL_COMMAND_RESOURCES
    kind: CommandKind = CommandKind.COMMAND
    replacement_key: str | None = None
    cancel_running: bool = True
    group_id: str | None = None
    pulse_count: int | None = None
    pulse_delay_ms: int | None = None
    intent_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class CommandRecord:
    """Immutable terminal snapshot of one admitted command."""

    intent_id: str
    kind: CommandKind
    group_id: str | None
    resources: tuple[str, ...]
    scheduler_strategy: str
    stop_epoch: int
    invalidated_stop_epoch: int | None
    admitted_at: datetime
    started_at: datetime | None
    finished_at: datetime
    outcome: CommandOutcome
    queue_wait_seconds: float
    active_duration_seconds: float | None

    def as_dict(self) -> dict[str, Any]:
        """Return the shared JSON shape used by diagnostics and support bundles."""
        return {
            "intent_id": self.intent_id,
            "kind": self.kind.value,
            "group_id": self.group_id,
            "resources": list(self.resources),
            "scheduler_strategy": self.scheduler_strategy,
            "stop_epoch": self.stop_epoch,
            "invalidated_stop_epoch": self.invalidated_stop_epoch,
            "admitted_at": self.admitted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat(),
            "outcome": self.outcome.value,
            "queue_wait_seconds": self.queue_wait_seconds,
            "active_duration_seconds": self.active_duration_seconds,
        }


@dataclass(slots=True)
class CommandHandle:
    """Observable state for one admitted intent."""

    intent: CommandIntent
    context: CommandContext
    future: asyncio.Future[None]
    prepared: bool
    state: CommandState = CommandState.QUEUED
    outcome: CommandOutcome | None = None
    admitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    admitted_monotonic: float = field(default_factory=time.monotonic)
    started_at: datetime | None = None
    started_monotonic: float | None = None
    finished_at: datetime | None = None
    finished_monotonic: float | None = None
    invalidated_stop_epoch: int | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    commit: asyncio.Event = field(default_factory=asyncio.Event)


_CURRENT_COMMAND_CONTEXT: ContextVar[CommandContext | None] = ContextVar(
    "adjustable_bed_command_context", default=None
)


def current_command_context() -> CommandContext | None:
    """Return the command context bound to the current task, if any."""
    context = _CURRENT_COMMAND_CONTEXT.get()
    return context if context is None or context.active else None


def copy_context_without_command() -> Context:
    """Keep tracing and HA context, without a parent's command reservation."""
    context = copy_context()
    context.run(_CURRENT_COMMAND_CONTEXT.set, None)
    return context


def command_resources(*resources: str) -> frozenset[str]:
    """Normalize a resource declaration, defaulting to the whole command link."""
    normalized = frozenset(resource for resource in resources if resource)
    return normalized or ALL_COMMAND_RESOURCES


def _resources_overlap(left: Collection[str], right: Collection[str]) -> bool:
    if "*" in left or "*" in right:
        return True

    def matches(pattern: str, resource: str) -> bool:
        return pattern.endswith(":*") and resource.startswith(pattern[:-1])

    return any(
        left_resource == right_resource
        or matches(left_resource, right_resource)
        or matches(right_resource, left_resource)
        for left_resource in left
        for right_resource in right
    )


class DeviceCommandScheduler:
    """Serialize opaque operations for one physical command channel."""

    strategy_name: Final = "serial_opaque"

    def __init__(self, name: str) -> None:
        self._name = name
        self._token = object()
        self._lock = asyncio.Lock()
        self._queue: deque[CommandHandle] = deque()
        self._active: CommandHandle | None = None
        self._active_stops: dict[
            str, tuple[CommandHandle, asyncio.Task[None]]
        ] = {}
        self._recent_records: deque[CommandRecord] = deque(
            maxlen=MAX_RECENT_COMMAND_RECORDS
        )
        self._worker: asyncio.Task[None] | None = None
        self._stop_epoch = 0
        self._stop_barrier = asyncio.Event()
        self._stop_barrier.set()
        self._closed = False

    @property
    def token(self) -> object:
        """Identity used to recognize safe scheduler re-entry."""
        return self._token

    @property
    def has_pending(self) -> bool:
        """Return whether another command is queued behind the active one."""
        return bool(self._queue)

    @property
    def stop_epoch(self) -> int:
        return self._stop_epoch

    @property
    def recent_records(self) -> tuple[CommandRecord, ...]:
        """Return the bounded immutable terminal history."""
        return tuple(self._recent_records)

    @property
    def diagnostics(self) -> dict[str, object]:
        """Return a bounded snapshot suitable for integration diagnostics."""
        active_handles = [handle for handle, _task in self._active_stops.values()]
        if self._active is not None:
            active_handles.append(self._active)
        active = active_handles[0] if active_handles else None
        return {
            "strategy": self.strategy_name,
            "stop_epoch": self._stop_epoch,
            "queue_depth": len(self._queue),
            "active_intent_id": active.intent.intent_id if active else None,
            "active_kind": active.intent.kind.value if active else None,
            "active_group_id": active.intent.group_id if active else None,
            "active_resources": sorted(active.intent.resources) if active else [],
            "active_state": active.state if active else None,
            "active_age_seconds": (
                round(time.monotonic() - active.started_monotonic, 3)
                if active is not None and active.started_monotonic is not None
                else None
            ),
            "active_intents": [
                self._active_diagnostics(handle) for handle in active_handles
            ],
            "recent_records": [record.as_dict() for record in self._recent_records],
        }

    def _active_diagnostics(self, handle: CommandHandle) -> dict[str, object]:
        now = time.monotonic()
        return {
            "intent_id": handle.intent.intent_id,
            "kind": handle.intent.kind.value,
            "group_id": handle.intent.group_id,
            "resources": sorted(handle.intent.resources),
            "scheduler_strategy": self.strategy_name,
            "stop_epoch": handle.context.admitted_stop_epoch,
            "state": handle.state.value,
            "admitted_at": handle.admitted_at.isoformat(),
            "started_at": (
                handle.started_at.isoformat() if handle.started_at is not None else None
            ),
            "queue_wait_seconds": round(
                (handle.started_monotonic or now) - handle.admitted_monotonic, 3
            ),
            "active_duration_seconds": (
                round(now - handle.started_monotonic, 3)
                if handle.started_monotonic is not None
                else None
            ),
        }

    async def execute(self, intent: CommandIntent) -> None:
        """Admit an ordinary intent and wait for its terminal result."""
        handle = await self.enqueue(intent)
        try:
            await asyncio.shield(handle.future)
        except asyncio.CancelledError:
            await self.cancel(handle, CommandOutcome.CALLER_CANCELLED)
            raise

    async def enqueue(self, intent: CommandIntent, *, prepared: bool = False) -> CommandHandle:
        """Admit an intent and return its handle without waiting for execution."""
        handle = self._new_handle(intent, prepared=prepared)

        async with self._lock:
            if self._closed:
                raise RuntimeError(f"Command scheduler for {self._name} is shut down")
            replaces_active = False
            if intent.cancel_running:
                replaces_active = self._replace_conflicts_locked(handle)
            # A replacement for the operation currently owning the link must be
            # next after that operation's cleanup. Otherwise an older,
            # unrelated prepared group can sit in front of a motor STOP/reverse
            # and prevent the replacement from ever reaching the active motor.
            if replaces_active:
                self._queue.appendleft(handle)
            else:
                self._queue.append(handle)
            if self._worker is None or self._worker.done():
                self._worker = asyncio.create_task(
                    self._run(), name=f"adjustable_bed_commands_{self._name}"
                )
        return handle

    def admit_stop(
        self,
        operation: CommandOperation,
        resources: Collection[str] = ALL_COMMAND_RESOURCES,
        *,
        group_id: str | None = None,
    ) -> asyncio.Task[None]:
        """Invalidate matching work and synchronously start a safety STOP."""
        if self._closed:
            raise RuntimeError(f"Command scheduler for {self._name} is shut down")
        normalized_resources = command_resources(*resources)
        stop_epoch = self.request_stop(normalized_resources)
        handle = self._new_handle(
            CommandIntent(
                operation,
                resources=normalized_resources,
                kind=CommandKind.STOP,
                cancel_running=False,
                group_id=group_id,
            ),
            prepared=False,
            admitted_stop_epoch=stop_epoch,
        )
        task = asyncio.create_task(
            self._execute_admitted_stop(handle),
            name=f"adjustable_bed_stop_{self._name}",
        )
        self._active_stops[handle.intent.intent_id] = (handle, task)
        return task

    async def _execute_admitted_stop(self, handle: CommandHandle) -> None:
        """Execute a synchronously admitted STOP outside the ordinary queue."""
        self._mark_started(handle)
        token: Token[CommandContext | None] = _CURRENT_COMMAND_CONTEXT.set(handle.context)
        try:
            await handle.intent.operation(handle.context)
        except asyncio.CancelledError:
            outcome = (
                CommandOutcome.SHUTDOWN
                if self._closed
                else CommandOutcome.CALLER_CANCELLED
            )
            self._finish(handle, outcome)
            raise
        except TimeoutError as err:
            self._finish(handle, CommandOutcome.TIMEOUT, error=err)
            handle.future.exception()
            raise
        except Exception as err:
            self._finish(handle, CommandOutcome.FAILED, error=err)
            handle.future.exception()
            raise
        else:
            self._finish(handle, CommandOutcome.COMPLETED)
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
            self._active_stops.pop(handle.intent.intent_id, None)
            self.finish_stop(handle.context.admitted_stop_epoch)

    def _new_handle(
        self,
        intent: CommandIntent,
        *,
        prepared: bool,
        admitted_stop_epoch: int | None = None,
    ) -> CommandHandle:
        loop = asyncio.get_running_loop()
        context = CommandContext(
            scheduler_token=self._token,
            cancel_event=asyncio.Event(),
            admitted_stop_epoch=(
                self._stop_epoch
                if admitted_stop_epoch is None
                else admitted_stop_epoch
            ),
            intent_id=intent.intent_id,
            kind=intent.kind,
            group_id=intent.group_id,
            resources=intent.resources,
            pulse_count=intent.pulse_count,
            pulse_delay_ms=intent.pulse_delay_ms,
        )
        handle = CommandHandle(
            intent=intent,
            context=context,
            future=loop.create_future(),
            prepared=prepared,
        )
        if not prepared:
            handle.commit.set()
        return handle

    async def wait_ready(self, handle: CommandHandle) -> None:
        """Wait until a prepared command owns the head of its device queue."""
        try:
            await asyncio.shield(handle.ready.wait())
        except asyncio.CancelledError:
            await self.cancel(handle, CommandOutcome.CALLER_CANCELLED)
            raise
        if handle.state is not CommandState.PREPARED:
            raise PreparedCommandInvalidated(
                f"Prepared command {handle.intent.intent_id} was {handle.outcome}"
            )

    def commit(self, handle: CommandHandle) -> None:
        """Release a prepared command from READY into execution."""
        if handle.state is CommandState.PREPARED:
            handle.commit.set()

    async def wait_prepared_result(self, handle: CommandHandle) -> None:
        """Wait for a linked member and reject non-success terminal outcomes."""
        try:
            await asyncio.shield(handle.future)
        except asyncio.CancelledError:
            await self.cancel(handle, CommandOutcome.CALLER_CANCELLED)
            raise
        if handle.outcome is not CommandOutcome.COMPLETED:
            raise PreparedCommandInvalidated(
                f"Prepared command {handle.intent.intent_id} was {handle.outcome}"
            )

    async def cancel(
        self, handle: CommandHandle, outcome: CommandOutcome = CommandOutcome.GROUP_ABORTED
    ) -> None:
        """Invalidate one handle and wait for active cleanup when necessary."""
        handle.context.cancel_reason = outcome
        handle.context.cancel_event.set()
        async with self._lock:
            if handle in self._queue:
                self._queue.remove(handle)
                self._finish_locked(handle, outcome)
        if not handle.future.done():
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(handle.future)

    def request_cancel(
        self,
        resources: Collection[str] = ALL_COMMAND_RESOURCES,
        *,
        outcome: CommandOutcome = CommandOutcome.REPLACED,
    ) -> None:
        """Synchronously invalidate matching active and queued commands."""
        self._cancel_matching(
            resources,
            outcome=outcome,
            invalidated_stop_epoch=(
                self._stop_epoch
                if outcome in {CommandOutcome.STOPPED, CommandOutcome.SHUTDOWN}
                else None
            ),
        )

    def request_stop(self, resources: Collection[str] = ALL_COMMAND_RESOURCES) -> int:
        """Invalidate matching work and advance the monotonic STOP epoch."""
        self._stop_barrier.clear()
        self._stop_epoch += 1
        self._cancel_matching(
            resources,
            outcome=CommandOutcome.STOPPED,
            invalidated_stop_epoch=self._stop_epoch,
        )
        return self._stop_epoch

    def finish_stop(self, stop_epoch: int) -> None:
        """Release commands only after the newest STOP operation finishes."""
        if stop_epoch == self._stop_epoch:
            self._stop_barrier.set()

    async def async_shutdown(self) -> None:
        """Invalidate every command and drain the worker during entry unload."""
        self._closed = True
        self._stop_barrier.set()
        self._stop_epoch += 1
        self._cancel_matching(
            ALL_COMMAND_RESOURCES,
            outcome=CommandOutcome.SHUTDOWN,
            invalidated_stop_epoch=self._stop_epoch,
        )
        worker = self._worker
        if worker is not None and not worker.done():
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker

        # STOP is admitted outside the ordinary worker so it can preempt an
        # active command. It is still scheduler-owned and must settle before
        # coordinator teardown disconnects the BLE link.
        stop_tasks = tuple(task for _handle, task in self._active_stops.values())
        if stop_tasks:
            stop_drain = asyncio.gather(*stop_tasks, return_exceptions=True)
            try:
                await asyncio.shield(stop_drain)
            except asyncio.CancelledError:
                await stop_drain
                raise

    def _replace_conflicts_locked(self, incoming: CommandHandle) -> bool:
        """Cancel conflicts and report whether the active handle was replaced."""
        active = self._active
        replaces_active = False
        if active is not None and self._handles_conflict(active, incoming):
            replaces_active = True
            active.context.cancel_reason = CommandOutcome.REPLACED
            active.context.cancel_event.set()

        for queued in tuple(self._queue):
            if not self._handles_conflict(queued, incoming):
                continue
            self._queue.remove(queued)
            queued.context.cancel_reason = CommandOutcome.REPLACED
            queued.context.cancel_event.set()
            self._finish_locked(queued, CommandOutcome.REPLACED)
        return replaces_active

    @staticmethod
    def _handles_conflict(existing: CommandHandle, incoming: CommandHandle) -> bool:
        existing_key = existing.intent.replacement_key
        incoming_key = incoming.intent.replacement_key
        if existing_key is not None and incoming_key is not None:
            return existing_key == incoming_key or _resources_overlap(
                existing.intent.resources, incoming.intent.resources
            )
        return _resources_overlap(existing.intent.resources, incoming.intent.resources)

    def _cancel_matching(
        self,
        resources: Collection[str],
        *,
        outcome: CommandOutcome,
        invalidated_stop_epoch: int | None = None,
    ) -> None:
        active = self._active
        if active is not None and _resources_overlap(active.intent.resources, resources):
            active.context.cancel_reason = outcome
            active.context.cancel_event.set()
            active.invalidated_stop_epoch = invalidated_stop_epoch
        for queued in tuple(self._queue):
            if not _resources_overlap(queued.intent.resources, resources):
                continue
            self._queue.remove(queued)
            queued.context.cancel_reason = outcome
            queued.context.cancel_event.set()
            self._finish_locked(
                queued,
                outcome,
                invalidated_stop_epoch=invalidated_stop_epoch,
            )

    async def _run(self) -> None:
        try:
            while True:
                async with self._lock:
                    if not self._queue:
                        self._worker = None
                        return
                    handle = self._queue.popleft()
                    self._active = handle

                if (
                    handle.context.cancel_event.is_set()
                    or handle.context.admitted_stop_epoch != self._stop_epoch
                ):
                    self._finish(handle, handle.context.cancel_reason or CommandOutcome.STOPPED)
                    async with self._lock:
                        if self._active is handle:
                            self._active = None
                    continue

                await self._stop_barrier.wait()
                if (
                    handle.context.cancel_event.is_set()
                    or handle.context.admitted_stop_epoch != self._stop_epoch
                ):
                    self._finish(handle, handle.context.cancel_reason or CommandOutcome.STOPPED)
                    async with self._lock:
                        if self._active is handle:
                            self._active = None
                    continue

                if handle.prepared:
                    handle.state = CommandState.PREPARED
                    handle.ready.set()
                    committed = await self._wait_for_commit(handle)
                    if not committed:
                        self._finish(
                            handle,
                            handle.context.cancel_reason or CommandOutcome.GROUP_ABORTED,
                        )
                        async with self._lock:
                            if self._active is handle:
                                self._active = None
                        continue

                if (
                    handle.context.cancel_event.is_set()
                    or handle.context.admitted_stop_epoch != self._stop_epoch
                ):
                    self._finish(handle, handle.context.cancel_reason or CommandOutcome.STOPPED)
                    async with self._lock:
                        if self._active is handle:
                            self._active = None
                    continue

                self._mark_started(handle)
                token: Token[CommandContext | None] = _CURRENT_COMMAND_CONTEXT.set(handle.context)
                try:
                    await handle.intent.operation(handle.context)
                except asyncio.CancelledError:
                    worker_task = asyncio.current_task()
                    worker_cancelled = bool(
                        worker_task is not None and worker_task.cancelling()
                    )
                    if not handle.context.cancel_event.is_set():
                        handle.context.cancel_reason = (
                            CommandOutcome.SHUTDOWN
                            if worker_cancelled
                            else CommandOutcome.CALLER_CANCELLED
                        )
                        handle.context.cancel_event.set()
                    self._finish(
                        handle,
                        handle.context.cancel_reason or CommandOutcome.CALLER_CANCELLED,
                    )
                    # A controller may raise CancelledError after observing its
                    # ticket event. That ends only this handle; the replacement
                    # queued behind it must still run. Re-raise solely when the
                    # scheduler worker task itself was externally cancelled.
                    if worker_cancelled:
                        raise
                except TimeoutError as err:
                    self._finish(handle, CommandOutcome.TIMEOUT, error=err)
                except Exception as err:
                    self._finish(handle, CommandOutcome.FAILED, error=err)
                else:
                    outcome = CommandOutcome.COMPLETED
                    if handle.context.cancel_event.is_set():
                        outcome = handle.context.cancel_reason or CommandOutcome.CALLER_CANCELLED
                    self._finish(
                        handle,
                        outcome,
                    )
                finally:
                    _CURRENT_COMMAND_CONTEXT.reset(token)
                    async with self._lock:
                        if self._active is handle:
                            self._active = None
        finally:
            active = self._active
            if active is not None and not active.future.done():
                self._finish(active, active.context.cancel_reason or CommandOutcome.SHUTDOWN)
            for queued in tuple(self._queue):
                self._queue.remove(queued)
                self._finish(queued, queued.context.cancel_reason or CommandOutcome.SHUTDOWN)
            self._worker = None

    async def _wait_for_commit(self, handle: CommandHandle) -> bool:
        commit_task = asyncio.create_task(handle.commit.wait())
        cancel_task = asyncio.create_task(handle.context.cancel_event.wait())
        try:
            done, pending = await asyncio.wait(
                {commit_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
            )
            return commit_task in done and not handle.context.cancel_event.is_set()
        finally:
            for task in (commit_task, cancel_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(commit_task, cancel_task, return_exceptions=True)

    def _finish(
        self,
        handle: CommandHandle,
        outcome: CommandOutcome,
        *,
        error: BaseException | None = None,
        invalidated_stop_epoch: int | None = None,
    ) -> None:
        self._finish_locked(
            handle,
            outcome,
            error=error,
            invalidated_stop_epoch=invalidated_stop_epoch,
        )

    def _mark_started(self, handle: CommandHandle) -> None:
        handle.state = CommandState.ACTIVE
        handle.started_at = datetime.now(UTC)
        handle.started_monotonic = time.monotonic()

    def _finish_locked(
        self,
        handle: CommandHandle,
        outcome: CommandOutcome,
        *,
        error: BaseException | None = None,
        invalidated_stop_epoch: int | None = None,
    ) -> None:
        if handle.finished_at is not None:
            return
        if invalidated_stop_epoch is not None:
            handle.invalidated_stop_epoch = invalidated_stop_epoch
        finished_at = datetime.now(UTC)
        finished_monotonic = time.monotonic()
        handle.context.active = False
        handle.outcome = outcome
        handle.finished_at = finished_at
        handle.finished_monotonic = finished_monotonic
        handle.state = (
            CommandState.COMPLETED
            if outcome is CommandOutcome.COMPLETED
            else (
                CommandState.FAILED
                if outcome in {CommandOutcome.FAILED, CommandOutcome.TIMEOUT}
                else CommandState.CANCELLED
            )
        )
        handle.ready.set()
        started_monotonic = handle.started_monotonic
        queue_finished_monotonic = started_monotonic or finished_monotonic
        self._recent_records.append(
            CommandRecord(
                intent_id=handle.intent.intent_id,
                kind=handle.intent.kind,
                group_id=handle.intent.group_id,
                resources=tuple(sorted(handle.intent.resources)),
                scheduler_strategy=self.strategy_name,
                stop_epoch=handle.context.admitted_stop_epoch,
                invalidated_stop_epoch=handle.invalidated_stop_epoch,
                admitted_at=handle.admitted_at,
                started_at=handle.started_at,
                finished_at=finished_at,
                outcome=outcome,
                queue_wait_seconds=round(
                    queue_finished_monotonic - handle.admitted_monotonic, 3
                ),
                active_duration_seconds=(
                    round(finished_monotonic - started_monotonic, 3)
                    if started_monotonic is not None
                    else None
                ),
            )
        )
        if not handle.future.done():
            if error is not None:
                handle.future.set_exception(error)
            else:
                handle.future.set_result(None)
