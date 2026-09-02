"""Bounded launcher contract for history-free analysis contexts."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from tools.phase4_v2.queue import (
    Lease,
    Queue,
    StaleLeaseError,
    TerminalOutcome,
    WorkUnitSnapshot,
    WorkUnitStatus,
)

from .model import FollowUp, WorkStage, route_follow_up

_MAX_PROMPT_BYTES = 256 * 1024
_MAX_RUNTIME_SECONDS = 24 * 60 * 60


class ContextExit(StrEnum):
    """Terminal state reported by a launched context."""

    EXITED = "EXITED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """Complete handoff to an adapter, intentionally without conversation history."""

    lease: Lease
    stage: WorkStage
    cluster_id: str
    workspace: Path
    prompt: str
    max_runtime_seconds: float
    inherit_conversation: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.lease, Lease) or not isinstance(self.stage, WorkStage):
            raise ValueError("launch request requires a typed lease and stage")
        if self.inherit_conversation is not False:
            raise ValueError("orchestration contexts must not inherit conversation history")
        if not isinstance(self.workspace, Path) or self.workspace != self.lease.workspace:
            raise ValueError("launch workspace must be the leased attempt workspace")
        if not isinstance(self.cluster_id, str) or not self.cluster_id:
            raise ValueError("orchestration work requires a cluster")
        if (
            not isinstance(self.prompt, str)
            or not self.prompt
            or len(self.prompt.encode("utf-8")) > _MAX_PROMPT_BYTES
        ):
            raise ValueError("launch prompt must be non-empty and bounded")
        if any(character == "\x00" for character in self.prompt):
            raise ValueError("launch prompt contains a NUL byte")
        if (
            isinstance(self.max_runtime_seconds, bool)
            or not isinstance(self.max_runtime_seconds, (int, float))
            or not math.isfinite(self.max_runtime_seconds)
            or not 0 < self.max_runtime_seconds <= _MAX_RUNTIME_SECONDS
        ):
            raise ValueError("max runtime must be positive and at most 24 hours")


class FreshContextHandle(Protocol):
    """Running context controlled without model polling turns."""

    def wait(self, timeout_seconds: float) -> ContextExit | None: ...

    def terminate(self) -> None: ...


class FreshContextAdapter(Protocol):
    """Host adapter that must start a new context with no inherited history."""

    def start(self, request: LaunchRequest) -> FreshContextHandle: ...


@dataclass(frozen=True, slots=True)
class LaunchReceipt:
    """Result of supervising one bounded fresh context."""

    lease: Lease
    stage: WorkStage
    context_exit: ContextExit
    queue_status: WorkUnitStatus
    follow_up: FollowUp | None


PromptFactory = Callable[[Lease, WorkUnitSnapshot], str]


def launch_one(
    queue: Queue,
    *,
    owner: str,
    adapter: FreshContextAdapter,
    prompt_factory: PromptFactory,
    ttl_seconds: int = 1_800,
    heartbeat_seconds: float = 60.0,
    max_runtime_seconds: float = 6 * 60 * 60,
) -> LaunchReceipt | None:
    """Claim and supervise one typed unit while the worker owns all output writes."""
    if (
        type(ttl_seconds) is not int
        or ttl_seconds < 1
        or isinstance(heartbeat_seconds, bool)
        or not isinstance(heartbeat_seconds, (int, float))
        or not math.isfinite(heartbeat_seconds)
        or heartbeat_seconds <= 0
        or heartbeat_seconds >= ttl_seconds
    ):
        raise ValueError("heartbeat must be positive and shorter than the lease TTL")
    if (
        isinstance(max_runtime_seconds, bool)
        or not isinstance(max_runtime_seconds, (int, float))
        or not math.isfinite(max_runtime_seconds)
        or not 0 < max_runtime_seconds <= _MAX_RUNTIME_SECONDS
    ):
        raise ValueError("max runtime must be positive and at most 24 hours")
    lease = queue.claim(
        owner,
        ttl_seconds=ttl_seconds,
        allowed_kinds=tuple(stage.value for stage in WorkStage),
    )
    if lease is None:
        return None
    unit = _leased_unit(queue, lease)
    try:
        stage = WorkStage(unit.kind)
    except ValueError as error:  # pragma: no cover - allowed_kinds closes this path
        queue.finish(lease, TerminalOutcome.FAILED)
        raise RuntimeError("queue returned a non-orchestration unit") from error
    if unit.cluster_id is None:
        queue.finish(lease, TerminalOutcome.FAILED)
        raise RuntimeError("orchestration unit has no cluster")

    try:
        request = LaunchRequest(
            lease=lease,
            stage=stage,
            cluster_id=unit.cluster_id,
            workspace=lease.workspace,
            prompt=prompt_factory(lease, unit),
            max_runtime_seconds=max_runtime_seconds,
        )
        handle = adapter.start(request)
    except Exception:
        queue.finish(lease, TerminalOutcome.FAILED)
        raise

    started = time.monotonic()
    context_exit: ContextExit | None = None
    try:
        while context_exit is None:
            remaining = max_runtime_seconds - (time.monotonic() - started)
            if remaining <= 0:
                handle.terminate()
                context_exit = ContextExit.TIMED_OUT
                break
            context_exit = handle.wait(min(heartbeat_seconds, remaining))
            if context_exit is None:
                try:
                    lease = queue.renew(lease, ttl_seconds=ttl_seconds)
                except StaleLeaseError:
                    unit = _leased_unit(queue, lease)
                    if unit.status is WorkUnitStatus.LEASED:
                        raise
                    context_exit = ContextExit.FAILED
    except Exception:
        handle.terminate()
        unit = _leased_unit(queue, lease)
        if unit.status is WorkUnitStatus.LEASED:
            try:
                queue.finish(lease, TerminalOutcome.FAILED)
            except StaleLeaseError:
                pass
        raise

    if not isinstance(context_exit, ContextExit):
        handle.terminate()
        unit = _leased_unit(queue, lease)
        if unit.status is WorkUnitStatus.LEASED:
            try:
                queue.finish(lease, TerminalOutcome.FAILED)
            except StaleLeaseError:
                pass
        raise RuntimeError("fresh-context adapter returned an invalid exit state")

    queue_status = queue.status(lease.unit_id)
    if queue_status is WorkUnitStatus.LEASED:
        try:
            queue.finish(lease, TerminalOutcome.FAILED)
        except StaleLeaseError:
            pass
        queue_status = queue.status(lease.unit_id)
        if context_exit is ContextExit.EXITED:
            context_exit = ContextExit.FAILED
    outcome = queue.attempt_outcome(lease.attempt_id)
    if outcome is None:
        raise RuntimeError("worker exited without an immutable terminal")
    if outcome is TerminalOutcome.ABANDONED:
        return LaunchReceipt(
            lease=lease,
            stage=stage,
            context_exit=ContextExit.FAILED,
            queue_status=queue_status,
            follow_up=None,
        )
    return LaunchReceipt(
        lease=lease,
        stage=stage,
        context_exit=context_exit,
        queue_status=queue_status,
        follow_up=route_follow_up(stage, outcome),
    )


def _leased_unit(queue: Queue, lease: Lease) -> WorkUnitSnapshot:
    for unit in queue.snapshot().units:
        if unit.unit_id == lease.unit_id:
            return unit
    raise StaleLeaseError(f"leased unit disappeared: {lease.unit_id}")
