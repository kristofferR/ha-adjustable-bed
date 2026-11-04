"""Device-scoped command admission for adjustable beds.

The scheduler deliberately treats controller operations as opaque. It orders
them, scopes replacement to the resources they control, and provides an atomic
prepare/commit gate for paired coordinators, but it never slices or interleaves
protocol coroutines. Protocol-specific concurrency can be added behind a
different execution strategy once its wire behaviour is proven.

A held intent (``CommandKind.HOLD``, #483) also carries a lease: an owner, a
generation and a monotonic deadline. Renewing a live lease replaces its
deadline without touching the wire. When the deadline passes, the scheduler
cancels the hold through its own cancel event, so the controller runs the same
cleanup a STOP or replacement would. A generation that has ended is never
admitted or renewed again, and leases live only in memory.

The merged-stream strategy (#516) is the one exception to opaque operations.
It is used only for motors a controller declares in
``ExecutionCapabilities.concurrent``. One streamer per device owns the wire as
a single ``CommandKind.STREAM`` intent, and holds and timed moves on disjoint
motors join it as members. Each tick the controller composes the live members
into its frames; a member that ends gets its own cleanup, and the last one out
runs the profile release.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Collection, Coroutine
from contextvars import Context, ContextVar, Token, copy_context
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final, Protocol
from uuid import uuid4

_LOGGER = logging.getLogger(__name__)

ALL_COMMAND_RESOURCES: Final = frozenset({"*"})
MAX_RECENT_COMMAND_RECORDS: Final = 20
# Ended lease generations are remembered so a late renewal cannot restart a
# hold. Live and reserved leases are never evicted.
MAX_HOLD_LEASE_RECORDS: Final = 128


class CommandKind(StrEnum):
    """Broad command category used by diagnostics and future strategies."""

    COMMAND = "command"
    SEEK = "seek"
    GROUP = "group"
    STOP = "stop"
    HOLD = "hold"
    STREAM = "stream"


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
    EXPIRED = "expired"
    DISCONNECTED = "disconnected"


class PreparedCommandInvalidated(RuntimeError):
    """Raised when a linked command loses its reservation before completion."""


class StaleHoldLease(RuntimeError):
    """Raised when a hold names a generation that has ended or been superseded."""


class HoldClaim(StrEnum):
    """What a hold lease request may do on one device."""

    RENEW = "renew"
    """A live or reserved lease of this generation takes the new deadline."""
    START = "start"
    """No live lease of this generation exists; a new hold may be admitted."""
    STALE = "stale"
    """The generation has ended, was superseded, or names another action."""


@dataclass(frozen=True, slots=True)
class HoldLease:
    """One caller's claim on a held motion, renewable until it ends."""

    owner: str
    generation: int
    action: str
    """The held motion within the resources, such as a direction or control."""
    duration_s: float
    """How long the hold lasts after this request unless renewed again."""

    def __post_init__(self) -> None:
        if not self.owner or not self.action:
            raise ValueError("A hold lease needs an owner and an action")
        if isinstance(self.generation, bool) or self.generation < 0:
            raise ValueError("A hold lease generation must be a non-negative integer")
        if not self.duration_s > 0:
            raise ValueError("A hold lease must last a positive duration")


@dataclass(slots=True, eq=False)
class _LeaseRecord:
    """Scheduler-side state of one owner's lease on one resource set."""

    generation: int
    action: str
    resources: frozenset[str]
    deadline: float
    handle: CommandHandle | None = None
    member: StreamMember | None = None
    ended: bool = False
    timer: asyncio.TimerHandle | None = None


@dataclass(slots=True, eq=False)
class StreamMember:
    """One motor's held or timed motion inside a merged stream (#516)."""

    motor: str
    """The controller's motor key, for composing frames."""
    resource: str
    """The scheduler resource this member owns; one member per resource."""
    action: str
    """The direction or control being held."""
    deadline: float
    """Event-loop time at which the member ends unless its lease is renewed."""
    duration_s: float | None = None
    """A timed move's budget, counted from its first written tick, like the
    serial path's budget after connection. ``deadline`` applies until then."""
    lease: HoldLease | None = None
    ceiling: float | None = None
    """Event-loop time no renewal can extend the member past."""
    outcome: CommandOutcome | None = None
    error: BaseException | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    on_wire: Callable[[], None] | None = None
    """Called once, as the first write carrying this member starts."""
    on_left: Callable[[float | None], None] | None = None
    """Called once when the member settles, if it reached the wire: the
    seconds from its first write to its retirement, or None when it failed."""
    wire_started: float | None = None
    left_at: float | None = None

    def settle(self) -> None:
        """Resolve the caller and report how long the motion ran."""
        if self.done.is_set():
            return
        self.done.set()
        if self.on_left is None or self.wire_started is None:
            return
        failed = self.error is not None or self.outcome is CommandOutcome.FAILED
        left_at = self.left_at if self.left_at is not None else asyncio.get_running_loop().time()
        try:
            self.on_left(None if failed else max(0.0, left_at - self.wire_started))
        except Exception:
            _LOGGER.exception("Stream member timing observer failed")


class StreamDriver(Protocol):
    """What a merged stream needs from a controller that composes members."""

    @property
    def stream_tick_s(self) -> float:
        """Refresh interval of the composed frames."""
        ...

    async def write_stream_tick(self, members: tuple[StreamMember, ...]) -> None:
        """Write one composed refresh carrying every live member."""
        ...

    async def end_stream_member(
        self, member: StreamMember, remaining: tuple[StreamMember, ...]
    ) -> None:
        """Run one ending member's own cleanup while ``remaining`` keep moving."""
        ...

    async def release_stream(self) -> None:
        """Run the profile release after the last member has ended."""
        ...


StreamRunner = Callable[[Callable[[StreamDriver], Awaitable[None]]], Awaitable[None]]
"""Runs the stream body with the live controller, inside the device's wire lane."""


class _MergedStream:
    """One streamer that owns the wire for members on disjoint motors."""

    def __init__(self, scheduler: DeviceCommandScheduler, resources: frozenset[str]) -> None:
        self.scheduler = scheduler
        self.resources = resources
        self.members: dict[str, StreamMember] = {}
        self.ending: deque[StreamMember] = deque()
        self.handle: CommandHandle | None = None
        self.membership_changed = False
        self.wake = asyncio.Event()
        self.closing = False
        self.awaiting_release: list[StreamMember] = []
        self.cleaning: StreamMember | None = None

    @property
    def accepting(self) -> bool:
        handle = self.handle
        return (
            handle is not None
            and not self.closing
            and not handle.future.done()
            and not handle.context.cancel_event.is_set()
        )

    def join(self, member: StreamMember) -> None:
        previous = self.members.get(member.resource)
        if previous is not None:
            # Same-motor replacement is atomic: the stream never looks empty.
            self.retire(previous, CommandOutcome.REPLACED, close_if_empty=False)
        self.members[member.resource] = member
        self.membership_changed = True
        self.wake.set()

    def retire(
        self, member: StreamMember, outcome: CommandOutcome, *, close_if_empty: bool = True
    ) -> None:
        """Remove a live member; its cleanup runs on the streamer's next pass.

        Removing the last member closes admission at once, whoever removed it,
        so a newcomer starts a fresh stream behind this one's release.
        """
        if self.members.get(member.resource) is not member:
            return
        del self.members[member.resource]
        member.outcome = outcome
        member.left_at = asyncio.get_running_loop().time()
        self.ending.append(member)
        self.scheduler._end_member_lease(member)
        self.membership_changed = True
        if close_if_empty and not self.members:
            self.closing = True
        self.wake.set()

    def abandon(self, outcome: CommandOutcome, error: BaseException | None = None) -> None:
        """Resolve every member still waiting, with the stream's failure if any."""
        cleaning = (self.cleaning,) if self.cleaning is not None else ()
        for member in (*self.members.values(), *self.ending, *cleaning, *self.awaiting_release):
            if member.done.is_set():
                continue
            member.outcome = member.outcome or outcome
            if error is not None and member.error is None:
                member.error = error
            self.scheduler._end_member_lease(member)
            member.settle()
        self.members.clear()
        self.ending.clear()
        self.scheduler._forget_stream(self)

    async def run(self, context: CommandContext, runner: StreamRunner) -> None:
        try:
            await runner(lambda driver: self._stream(context, driver))
        except asyncio.CancelledError:
            self.abandon(context.cancel_reason or CommandOutcome.CALLER_CANCELLED)
            raise
        except BaseException as err:
            # A connection, tick or release failure reaches every member it ended.
            self.abandon(CommandOutcome.FAILED, err)
            raise
        else:
            # A runner that returned without running the body (preempted while
            # waiting for the link) ends its members as cancelled.
            self.abandon(context.cancel_reason or CommandOutcome.STOPPED)

    async def _stream(self, context: CommandContext, driver: StreamDriver) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        failure: BaseException | None = None
        try:
            while True:
                # Cleanup awaits the wire, so recheck deadlines until none is
                # overdue: an expired member must never reach another tick.
                while True:
                    now = loop.time()
                    for member in tuple(self.members.values()):
                        if member.deadline <= now:
                            self.retire(member, CommandOutcome.EXPIRED)
                    if not self.ending:
                        break
                    if not self.members:
                        # Close before yielding to the cleanup task, so a ready
                        # newcomer cannot join a stream that is ending.
                        self.closing = True
                    await _settled(self._clean_up(driver))
                if not self.members or context.cancel_event.is_set():
                    break
                self.wake.clear()
                if self.membership_changed or loop.time() >= next_tick:
                    self.membership_changed = False
                    members = tuple(self.members.values())
                    # A timed move's budget starts as its first write starts,
                    # like the serial path's timeout around its write loop.
                    started = loop.time()
                    for member in members:
                        if member.duration_s is not None:
                            member.deadline = started + member.duration_s
                            member.duration_s = None
                        if member.wire_started is None:
                            member.wire_started = started
                            if member.on_wire is not None:
                                try:
                                    member.on_wire()
                                except Exception:
                                    _LOGGER.exception("Stream member timing observer failed")
                    await self._write_tick(driver, members, context)
                    next_tick = started + driver.stream_tick_s
                if self.membership_changed:
                    continue
                earliest = min(member.deadline for member in self.members.values())
                timeout = max(0.0, min(next_tick, earliest) - loop.time())
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(timeout):
                        await _first_set(self.wake, context.cancel_event)
        except BaseException as err:
            failure = err
            raise
        finally:
            # STOP, replacement, shutdown or a failure: every member ends here,
            # each with its own cleanup, then the profile release. New members
            # start a fresh stream behind this one.
            self.closing = True
            outcome = (
                CommandOutcome.FAILED
                if failure is not None and not isinstance(failure, asyncio.CancelledError)
                else context.cancel_reason or CommandOutcome.STOPPED
            )
            for member in tuple(self.members.values()):
                self.retire(member, outcome)
                if outcome is CommandOutcome.FAILED and failure is not None:
                    member.error = failure
            # A STOP arriving now cancels this task; the cleanup and release
            # still finish before the wire lane is handed on.
            await _settled(self._close(driver))

    async def _write_tick(
        self,
        driver: StreamDriver,
        members: tuple[StreamMember, ...],
        context: CommandContext,
    ) -> None:
        """Write one composed tick, abandoning it once a member in it ends.

        Deadlines and lease expiry keep running while the write is in flight;
        a write that outlives a member's deadline, or a member stopped
        meanwhile, is cancelled as the serial path's timeout cancels its write.
        """
        loop = asyncio.get_running_loop()
        tick = asyncio.ensure_future(driver.write_stream_tick(members))
        try:
            while not tick.done():
                live = [m for m in members if self.members.get(m.resource) is m]
                if len(live) < len(members) or any(m.deadline <= loop.time() for m in live):
                    break
                if context.cancel_event.is_set():
                    break
                self.wake.clear()
                timeout = max(0.0, min(m.deadline for m in live) - loop.time())
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(timeout):
                        await _first_set_or_done(tick, self.wake, context.cancel_event)
        finally:
            if not tick.done():
                tick.cancel()
            # Never hand the wire on while this write is still running, even
            # when a STOP cancels the streamer meanwhile.
            interrupted = False
            while not tick.done():
                try:
                    await asyncio.wait({tick})
                except asyncio.CancelledError:
                    interrupted = True
            if interrupted:
                raise asyncio.CancelledError
        error = None if tick.cancelled() else tick.exception()
        if error is not None:
            raise error

    async def _close(self, driver: StreamDriver) -> None:
        try:
            await self._clean_up(driver)
        finally:
            try:
                await driver.release_stream()
            except BaseException as err:
                for member in self.awaiting_release:
                    member.error = member.error or err
                    member.outcome = CommandOutcome.FAILED
                raise
            finally:
                # The last members out return after the release, as a
                # serial move returns after its STOP.
                for member in self.awaiting_release:
                    member.settle()

    async def _clean_up(self, driver: StreamDriver) -> None:
        """Run every ending member's cleanup, then raise the first failure."""
        first_error: BaseException | None = None
        while self.ending:
            if not self.members:
                # Last ones out: newcomers queue behind this release instead
                # of joining while it is under way.
                self.closing = True
            member = self.ending.popleft()
            # Held until finalized, so no exit path can lose its caller.
            self.cleaning = member
            cancelled = False
            try:
                await driver.end_stream_member(member, tuple(self.members.values()))
            except asyncio.CancelledError as err:
                # An awaited write was cancelled under the cleanup: the cleanup
                # did not complete, which is a failure for this member.
                task = asyncio.current_task()
                cancelled = task is not None and task.cancelling() > 0
                failure = RuntimeError(f"{member.motor} cleanup was cancelled")
                failure.__cause__ = err
                member.error = failure
                member.outcome = CommandOutcome.FAILED
                first_error = first_error or failure
            except Exception as err:
                member.error = err
                member.outcome = CommandOutcome.FAILED
                first_error = first_error or err
            finally:
                self.cleaning = None
                if self.members:
                    member.settle()
                else:
                    # The last members out settle after the release runs.
                    self.closing = True
                    self.awaiting_release.append(member)
            if cancelled:
                raise asyncio.CancelledError
        if first_error is not None:
            raise first_error


async def _settled(cleanup: Coroutine[Any, Any, None]) -> None:
    """Finish ``cleanup`` even when the caller is cancelled meanwhile."""
    task = asyncio.ensure_future(cleanup)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(task)
        if not task.cancelled():
            task.exception()  # members already carry a cleanup failure
        raise


async def _first_set_or_done(task: asyncio.Future[None], *events: asyncio.Event) -> None:
    waiters = [asyncio.ensure_future(event.wait()) for event in events]
    try:
        await asyncio.wait({task, *waiters}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


async def _first_set(*events: asyncio.Event) -> None:
    waiters = [asyncio.ensure_future(event.wait()) for event in events]
    try:
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


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
    # A protocol cleanup frame belongs to the operation that is leaving the
    # lane. The immediately admitted replacement can use this acknowledgement
    # to avoid sending a duplicate STOP after it acquires the lane.
    preempted_contexts: tuple[CommandContext, ...] = ()
    cleanup_stop_sent: bool = False
    active: bool = True
    defer_disconnect: bool = False
    lease: HoldLease | None = None
    hold_deadline: float | None = None
    """Event-loop time at which a held command's lease expires, if any."""


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
    lease: HoldLease | None = None
    intent_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        if (self.lease is None) != (self.kind is not CommandKind.HOLD):
            raise ValueError("A HOLD intent carries a lease, and only a HOLD intent does")


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
    lease_record: _LeaseRecord | None = None
    stream: _MergedStream | None = None


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


def _consume_failure(future: asyncio.Future[None]) -> None:
    if not future.cancelled():
        future.exception()


def _clamp(deadline: float, ceiling: float | None) -> float:
    return deadline if ceiling is None else min(deadline, ceiling)


def _strategy(handle: CommandHandle) -> str:
    return "merged_stream" if handle.stream is not None else "serial_opaque"


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
        self._leases: OrderedDict[tuple[str, frozenset[str]], _LeaseRecord] = OrderedDict()
        self._streams: dict[frozenset[str], _MergedStream] = {}

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
            "scheduler_strategy": _strategy(handle),
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
            "hold_generation": (
                handle.context.lease.generation if handle.context.lease is not None else None
            ),
            "hold_remaining_seconds": (
                round(handle.context.hold_deadline - asyncio.get_running_loop().time(), 3)
                if handle.context.hold_deadline is not None
                else None
            ),
        }

    async def execute(
        self, intent: CommandIntent, *, expected_stop_epoch: int | None = None
    ) -> None:
        """Admit an ordinary intent and wait for its terminal result.

        A HOLD intent whose lease renews the live hold returns at once: the
        live hold keeps running with the new deadline.
        """
        handle = await self.enqueue(intent, expected_stop_epoch=expected_stop_epoch)
        if handle.intent is not intent:
            return
        try:
            await asyncio.shield(handle.future)
        except asyncio.CancelledError:
            await self.cancel(handle, CommandOutcome.CALLER_CANCELLED)
            raise

    async def enqueue(
        self,
        intent: CommandIntent,
        *,
        prepared: bool = False,
        expected_stop_epoch: int | None = None,
    ) -> CommandHandle:
        """Admit an intent and return its handle without waiting for execution.

        A HOLD intent that renews a live hold of its generation returns that
        live handle instead; one naming an ended generation raises
        ``StaleHoldLease``.
        """
        if intent.lease is not None and prepared:
            raise ValueError("A held command cannot join a prepared group")
        handle = self._new_handle(
            intent,
            prepared=prepared,
            admitted_stop_epoch=expected_stop_epoch,
        )

        async with self._lock:
            if self._closed:
                raise RuntimeError(f"Command scheduler for {self._name} is shut down")
            if expected_stop_epoch is not None and expected_stop_epoch != self._stop_epoch:
                self._finish_locked(
                    handle,
                    CommandOutcome.STOPPED,
                    invalidated_stop_epoch=self._stop_epoch,
                )
                return handle
            if intent.lease is not None:
                live = self._bind_lease_locked(handle, intent.lease)
                if live is not None:
                    return live
                if handle.future.done():
                    return handle
            self._admit_locked(handle)
        return handle

    def _admit_locked(self, handle: CommandHandle) -> None:
        replaces_active = False
        if handle.intent.cancel_running:
            active = self._active
            if active is not None and self._handles_conflict(active, handle):
                handle.context.preempted_contexts = (active.context,)
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

    # ---------------------------------------------------------- merged stream
    async def execute_stream_member(
        self,
        member: StreamMember,
        resources: Collection[str],
        runner: StreamRunner,
        *,
        expected_stop_epoch: int | None = None,
    ) -> CommandOutcome | None:
        """Join ``member`` to the live stream over ``resources``, or start one.

        ``resources`` are the controller's concurrent motors. A member on a
        motor that already streams replaces it. Returns the member's outcome,
        or None when a lease renewed the live member instead; raises the
        member's cleanup failure.
        """
        stream_resources = command_resources(*resources)
        if member.resource not in stream_resources:
            raise ValueError(f"{member.resource} is not a concurrent resource")
        async with self._lock:
            if self._closed:
                raise RuntimeError(f"Command scheduler for {self._name} is shut down")
            if expected_stop_epoch is not None and expected_stop_epoch != self._stop_epoch:
                return CommandOutcome.STOPPED
            if member.lease is not None:
                bound = self._bind_member_lease(member)
                if bound == "renewed":
                    return None
                if bound == "expired":
                    return CommandOutcome.EXPIRED
            stream = self._streams.get(stream_resources)
            if stream is None or not stream.accepting:
                stream = _MergedStream(self, stream_resources)
                self._streams[stream_resources] = stream

                async def operation(context: CommandContext) -> None:
                    await stream.run(context, runner)

                handle = self._new_handle(
                    CommandIntent(operation, resources=stream_resources, kind=CommandKind.STREAM),
                    prepared=False,
                )
                handle.stream = stream
                stream.handle = handle
                # Members carry the failure; nobody awaits the streamer itself.
                handle.future.add_done_callback(_consume_failure)
                stream.join(member)
                self._admit_locked(handle)
            else:
                stream.join(member)
        try:
            await member.done.wait()
        except asyncio.CancelledError:
            stream.retire(member, CommandOutcome.CALLER_CANCELLED)
            raise
        if member.error is not None:
            raise member.error
        return member.outcome

    def _bind_member_lease(self, member: StreamMember) -> str:
        """Bind a member to its lease: "bound", "renewed" (a live hold) or "expired"."""
        assert member.lease is not None
        key = (member.lease.owner, frozenset({member.resource}))
        record = self._leases.get(key)
        claim = self._classify_lease(record, member.lease)
        if claim is HoldClaim.STALE:
            raise StaleHoldLease(
                f"Hold generation {member.lease.generation} of {member.lease.owner!r} has ended"
            )
        if claim is HoldClaim.RENEW and record is not None and (
            record.member is not None or record.handle is not None
        ):
            self._set_lease_deadline(record, member.lease)
            return "renewed"
        if record is None or claim is HoldClaim.START:
            record = self._new_lease_record(key, member.lease)
        if record.timer is not None:
            # The streamer enforces member deadlines itself.
            record.timer.cancel()
            record.timer = None
        if record.deadline <= asyncio.get_running_loop().time():
            # Reserved, then waited out its lease before admission.
            self._end_lease(record)
            return "expired"
        record.member = member
        member.deadline = _clamp(record.deadline, member.ceiling)
        return "bound"

    def _end_member_lease(self, member: StreamMember) -> None:
        if member.lease is None:
            return
        record = self._leases.get((member.lease.owner, frozenset({member.resource})))
        if record is not None and record.member is member:
            self._end_lease(record)

    def _forget_stream(self, stream: _MergedStream) -> None:
        if self._streams.get(stream.resources) is stream:
            del self._streams[stream.resources]

    def stream_owns(self, resources: Collection[str]) -> bool:
        """Return whether an accepting stream owns any of ``resources``.

        True even when that motor's member already ended, so a repeated motor
        STOP stays member-scoped instead of replacing the whole stream.
        """
        return any(
            stream.accepting and _resources_overlap(stream.resources, resources)
            for stream in self._streams.values()
        )

    def _stop_stream_members(self, resources: Collection[str], stop_epoch: int) -> None:
        """End only the members a motor-scoped STOP names.

        A stream still queued keeps its other members: it is re-admitted at
        this STOP's epoch, or finished without writing once it has none left.
        """
        for stream in tuple(self._streams.values()):
            for member in tuple(stream.members.values()):
                if _resources_overlap((member.resource,), resources):
                    stream.retire(member, CommandOutcome.STOPPED)
            handle = stream.handle
            if handle is None or handle.started_at is not None or handle.future.done():
                continue
            # Nothing reached the wire yet, so there is nothing to clean up.
            while stream.ending:
                stream.ending.popleft().settle()
            if stream.members:
                handle.context.admitted_stop_epoch = stop_epoch
            elif handle in self._queue:
                self._queue.remove(handle)
                self._finish_locked(
                    handle, CommandOutcome.STOPPED, invalidated_stop_epoch=stop_epoch
                )

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
        active = self._active
        preempted_contexts = (
            (active.context,)
            if active is not None
            and _resources_overlap(active.intent.resources, normalized_resources)
            else ()
        )
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
        handle.context.preempted_contexts = preempted_contexts
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
            lease=intent.lease,
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
        # A lease running out is how a held member normally ends.
        if handle.outcome not in (CommandOutcome.COMPLETED, CommandOutcome.EXPIRED):
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
        self._end_leases_overlapping(resources)
        # A motor-scoped STOP ends only its stream member; a side or bed-wide
        # STOP cancels the whole streamer below.
        wide = self._is_wide(resources)
        if not wide:
            self._stop_stream_members(resources, self._stop_epoch)
        self._cancel_matching(
            resources,
            outcome=CommandOutcome.STOPPED,
            invalidated_stop_epoch=self._stop_epoch,
            spare_streams=not wide,
        )
        return self._stop_epoch

    @staticmethod
    def _is_wide(resources: Collection[str]) -> bool:
        return any(item == "*" or item.endswith(":*") for item in resources)

    def finish_stop(self, stop_epoch: int) -> None:
        """Release commands only after the newest STOP operation finishes."""
        if stop_epoch == self._stop_epoch:
            self._stop_barrier.set()

    async def async_shutdown(self) -> None:
        """Invalidate every command and drain the worker during entry unload."""
        self._closed = True
        self._stop_barrier.set()
        self._stop_epoch += 1
        for record in self._leases.values():
            self._end_lease(record)
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

    # ------------------------------------------------------------ hold leases
    def claim_hold(
        self, lease: HoldLease, resources: Collection[str], *, reserve: bool = True
    ) -> HoldClaim:
        """Classify a hold request without awaiting, and apply it.

        ``RENEW`` replaces the live or reserved lease's deadline and writes no
        frame. ``START`` reserves the generation (unless ``reserve`` is False)
        so concurrent requests renew the reservation and a STOP before
        admission ends it. ``STALE`` changes nothing.
        """
        if self._closed:
            return HoldClaim.STALE
        normalized = command_resources(*resources)
        key = (lease.owner, normalized)
        record = self._leases.get(key)
        claim = self._classify_lease(record, lease)
        if claim is HoldClaim.RENEW and record is not None:
            self._set_lease_deadline(record, lease)
        elif claim is HoldClaim.START and reserve:
            self._new_lease_record(key, lease)
        return claim

    def release_hold_claim(self, lease: HoldLease, resources: Collection[str]) -> None:
        """End a reservation that was never admitted, for example after preflight failed."""
        record = self._leases.get((lease.owner, command_resources(*resources)))
        if (
            record is not None
            and record.generation == lease.generation
            and record.handle is None
        ):
            self._end_lease(record)

    def end_holds(self, outcome: CommandOutcome) -> None:
        """End every hold and reservation now, without replay, for example on disconnect."""
        for record in tuple(self._leases.values()):
            self._expire_record(record, outcome)
        # A superseded generation can still be running after a newer one
        # replaced its record; reach it through its handle.
        for handle in (self._active, *self._queue):
            if handle is not None and handle.lease_record is not None:
                self._expire_record(handle.lease_record, outcome)
        for stream in tuple(self._streams.values()):
            handle = stream.handle
            if handle is not None and not handle.future.done():
                handle.context.cancel_reason = outcome
                handle.context.cancel_event.set()
                if handle in self._queue:
                    self._queue.remove(handle)
                    self._finish_locked(handle, outcome)

    def _classify_lease(self, record: _LeaseRecord | None, lease: HoldLease) -> HoldClaim:
        if (
            record is not None
            and not record.ended
            and record.deadline <= asyncio.get_running_loop().time()
        ):
            # The timer callback may not have run yet; a late renewal must
            # not revive an overdue lease.
            self._expire_record(record, CommandOutcome.EXPIRED)
        if record is None or lease.generation > record.generation:
            return HoldClaim.START
        if (
            lease.generation < record.generation
            or record.ended
            or record.action != lease.action
            or (record.handle is not None and record.handle.context.cancel_event.is_set())
            or (record.member is not None and record.member.outcome is not None)
        ):
            return HoldClaim.STALE
        return HoldClaim.RENEW

    def _new_lease_record(
        self, key: tuple[str, frozenset[str]], lease: HoldLease
    ) -> _LeaseRecord:
        previous = self._leases.pop(key, None)
        if previous is not None and previous.handle is None:
            # A newer generation supersedes an unadmitted reservation. A live
            # hold is replaced through ordinary resource conflict on admission.
            self._end_lease(previous)
        record = _LeaseRecord(
            generation=lease.generation,
            action=lease.action,
            resources=key[1],
            deadline=0.0,
        )
        self._leases[key] = record
        self._set_lease_deadline(record, lease)
        self._prune_leases()
        return record

    def _prune_leases(self) -> None:
        excess = len(self._leases) - MAX_HOLD_LEASE_RECORDS
        if excess <= 0:
            return
        for key in [key for key, record in self._leases.items() if record.ended][:excess]:
            del self._leases[key]

    def _set_lease_deadline(self, record: _LeaseRecord, lease: HoldLease) -> None:
        loop = asyncio.get_running_loop()
        record.deadline = loop.time() + lease.duration_s
        if record.timer is not None:
            record.timer.cancel()
            record.timer = None
        if record.member is not None:
            # Wake the streamer to recompute its wait; no frame is written.
            record.member.deadline = _clamp(record.deadline, record.member.ceiling)
            stream = next(
                (s for s in self._streams.values() if s.members.get(record.member.resource)
                 is record.member),
                None,
            )
            if stream is not None:
                stream.wake.set()
            return
        record.timer = loop.call_at(record.deadline, self._on_lease_deadline, record)
        if record.handle is not None:
            record.handle.context.hold_deadline = record.deadline

    def _on_lease_deadline(self, record: _LeaseRecord) -> None:
        record.timer = None
        if not record.ended:
            self._expire_record(record, CommandOutcome.EXPIRED)

    def _expire_record(self, record: _LeaseRecord, outcome: CommandOutcome) -> None:
        """End a lease and cancel its hold; the controller's cleanup still runs."""
        handle = record.handle
        self._end_lease(record)
        if record.member is not None:
            for stream in tuple(self._streams.values()):
                stream.retire(record.member, outcome)
            return
        if handle is None or handle.future.done():
            return
        handle.context.cancel_reason = outcome
        handle.context.cancel_event.set()
        if handle in self._queue:
            self._queue.remove(handle)
            self._finish_locked(handle, outcome)

    def _end_lease(self, record: _LeaseRecord) -> None:
        record.ended = True
        if record.timer is not None:
            record.timer.cancel()
            record.timer = None

    def _end_leases_overlapping(self, resources: Collection[str]) -> None:
        """A STOP ends reservations it overlaps, so their admission cannot follow it."""
        for record in tuple(self._leases.values()):
            if record.handle is None and _resources_overlap(record.resources, resources):
                self._end_lease(record)

    def _bind_lease_locked(
        self, handle: CommandHandle, lease: HoldLease
    ) -> CommandHandle | None:
        """Attach an admitted hold to its lease, or renew the live one."""
        key = (lease.owner, handle.intent.resources)
        record = self._leases.get(key)
        claim = self._classify_lease(record, lease)
        if claim is HoldClaim.STALE:
            raise StaleHoldLease(
                f"Hold generation {lease.generation} of {lease.owner!r} has ended"
            )
        if claim is HoldClaim.RENEW and record is not None and record.handle is not None:
            self._set_lease_deadline(record, lease)
            return record.handle
        if record is None or claim is HoldClaim.START:
            record = self._new_lease_record(key, lease)
        record.handle = handle
        handle.lease_record = record
        handle.context.hold_deadline = record.deadline
        if record.deadline <= asyncio.get_running_loop().time():
            # Reserved, then waited out its lease before admission.
            self._end_lease(record)
            self._finish_locked(handle, CommandOutcome.EXPIRED)
        return None

    def bind_hold_inline(
        self, context: CommandContext, lease: HoldLease, resources: Collection[str]
    ) -> bool:
        """Make the running reservation that owns ``context`` the held command.

        Paired groups run each side inside a prepared reservation, so a held
        start there binds its lease to that reservation instead of queueing a
        nested command. Returns False when there is nothing to run: the call
        renewed a live hold, or its reservation already expired.
        """
        handle = self._active
        if handle is None or handle.context is not context:
            raise ValueError("A held command can only bind to the running reservation")
        key = (lease.owner, command_resources(*resources))
        record = self._leases.get(key)
        claim = self._classify_lease(record, lease)
        if claim is HoldClaim.STALE:
            raise StaleHoldLease(
                f"Hold generation {lease.generation} of {lease.owner!r} has ended"
            )
        if claim is HoldClaim.RENEW and record is not None and record.handle is not None:
            self._set_lease_deadline(record, lease)
            return False
        if record is None or claim is HoldClaim.START:
            record = self._new_lease_record(key, lease)
        if record.deadline <= asyncio.get_running_loop().time():
            self._end_lease(record)
            return False
        record.handle = handle
        handle.lease_record = record
        context.lease = lease
        context.hold_deadline = record.deadline
        return True

    def _replace_conflicts_locked(self, incoming: CommandHandle) -> bool:
        """Cancel conflicts and report whether the active handle was replaced."""
        active = self._active
        replaces_active = False
        if active is not None and self._handles_conflict(active, incoming):
            replaces_active = True
            # A streamer already ending at a STOP keeps that reason for its members.
            if active.stream is None or not active.context.cancel_event.is_set():
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
        spare_streams: bool = False,
    ) -> None:
        active = self._active
        if (
            active is not None
            and _resources_overlap(active.intent.resources, resources)
            and not (spare_streams and active.stream is not None)
        ):
            active.context.cancel_reason = outcome
            active.context.cancel_event.set()
            active.invalidated_stop_epoch = invalidated_stop_epoch
        for queued in tuple(self._queue):
            if not _resources_overlap(queued.intent.resources, resources) or (
                spare_streams and queued.stream is not None
            ):
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
        if handle.lease_record is not None:
            self._end_lease(handle.lease_record)
        if handle.stream is not None and handle.started_at is None:
            handle.stream.abandon(outcome)
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
                scheduler_strategy=_strategy(handle),
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
