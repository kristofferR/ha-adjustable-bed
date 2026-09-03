"""Tests for typed, bounded Phase 4 v2 orchestration."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.orchestration.completion as stage_completion
from tools.phase4_v2.orchestration import (
    STAGE_AUTHORITY_REVISION,
    ContextExit,
    FollowUpAction,
    LaunchRequest,
    SyntheticAcceptanceConfig,
    WorkStage,
    launch_one,
    route_follow_up,
    run_synthetic_acceptance,
)
from tools.phase4_v2.queue import (
    MAX_ACTIVE_ORCHESTRATION_CLUSTERS,
    MAX_ACTIVE_ORCHESTRATION_LEASES_PER_CLUSTER,
    Lease,
    Queue,
    TerminalOutcome,
    WorkUnitStatus,
)


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    result = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    result.initialize()
    return result


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


_AUTHORITY_KEYS: dict[str, Ed25519PrivateKey] = {}
_AUTHORITY_DOCUMENTS: dict[str, bytes] = {}


@pytest.fixture(autouse=True)
def _protected_stage_authorities(monkeypatch: pytest.MonkeyPatch) -> None:
    _AUTHORITY_KEYS.clear()
    _AUTHORITY_DOCUMENTS.clear()
    config: dict[str, tuple[str, int]] = {}
    for stage in ("audit", "reconciliation", "implementation", "publication"):
        key = Ed25519PrivateKey.from_private_bytes(
            hashlib.sha256(f"synthetic-stage-key:{stage}".encode()).digest()
        )
        public = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        document = _canonical(
            {
                "authority_id": f"synthetic-{stage}",
                "generation": 1,
                "public_key": public.hex(),
                "revision": STAGE_AUTHORITY_REVISION,
                "stage": stage,
            }
        )
        _AUTHORITY_KEYS[stage] = key
        _AUTHORITY_DOCUMENTS[stage] = document
        config[stage] = (hashlib.sha256(b"phase4-v2:stage-authority\0" + document).hexdigest(), 1)
    monkeypatch.setattr(stage_completion, "_load_stage_authority_config", lambda: config)


def _enqueue_stage(
    queue: Queue,
    unit_id: str,
    stage: WorkStage,
    cluster: str,
    *,
    priority: int = 0,
) -> None:
    queue.enqueue(
        unit_id,
        kind=stage.value,
        cluster_id=cluster,
        input_digest=_digest(f"input:{unit_id}"),
        priority=priority,
    )


def _accept(queue: Queue, lease: Lease, marker: str) -> None:
    unit = next(item for item in queue.snapshot().units if item.unit_id == lease.unit_id)
    assert unit.cluster_id is not None
    stage = unit.kind.rsplit("-", 1)[-1]
    authority = stage_completion.load_stage_authority(_AUTHORITY_DOCUMENTS[stage])
    common: dict[str, object] = {
        "accepted": True,
        "authority_sha256": authority.authority_sha256,
        "cluster_id": unit.cluster_id,
        "diagnostics": [],
        "graph_sha256": _digest(f"graph:{marker}"),
        "stage": stage,
        "stage_input_sha256": lease.input_digest,
    }
    if stage == "audit":
        payload = {
            **common,
            "analysis_completion_revision": "test-v1",
            "analysis_completion_sha256": _digest("analysis"),
            "package_ref_id": _digest(marker),
            "revision": stage_completion.PACKAGE_AUDIT_COMPLETION_REVISION,
        }
    elif stage == "reconciliation":
        payload = {
            **common,
            "package_audit_receipts": [],
            "reconciliation_result_sha256": _digest(marker),
            "completeness_receipt_sha256": _digest("complete"),
            "disposition_ledger_sha256": _digest("ledger"),
            "revision": stage_completion.CLUSTER_RECONCILIATION_COMPLETION_REVISION,
        }
    elif stage == "implementation":
        payload = {
            **common,
            "reconciliation_receipt_sha256": _digest("reconciliation"),
            "disposition_ledger_sha256": _digest("ledger"),
            "implementation_output_sha256": _digest(marker),
            "revision": stage_completion.CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
        }
    else:
        payload = {
            **common,
            "implementation_receipt_sha256": _digest("implementation"),
            "queue_generation_sha256": queue.snapshot().generation_id,
            "document_set_sha256": _digest("documents"),
            "publication_config_sha256": _digest("config"),
            "before_revision": "a" * 40,
            "after_revision": "a" * 40,
            "paths": ["issues/436.md"],
            "changed": False,
            "revision": stage_completion.TRACKER_PUBLICATION_COMPLETION_REVISION,
        }
    signing = f"phase4-v2:signed-stage-receipt:{stage}".encode() + b"\0" + _canonical(payload)
    canonical_receipt = _canonical(
        {"payload": payload, "signature": _AUTHORITY_KEYS[stage].sign(signing).hex()}
    )
    queue.finish_authenticated_orchestration_stage(
        lease, authority=authority, canonical_receipt=canonical_receipt
    )


@pytest.mark.parametrize(
    ("stage", "outcome", "action", "next_stage"),
    [
        (
            WorkStage.PACKAGE_ANALYSIS,
            TerminalOutcome.ACCEPTED,
            FollowUpAction.ADVANCE,
            WorkStage.PACKAGE_AUDIT,
        ),
        (
            WorkStage.PACKAGE_AUDIT,
            TerminalOutcome.ACCEPTED,
            FollowUpAction.ADVANCE,
            WorkStage.CLUSTER_RECONCILIATION,
        ),
        (
            WorkStage.CLUSTER_RECONCILIATION,
            TerminalOutcome.ACCEPTED,
            FollowUpAction.ADVANCE,
            WorkStage.CLUSTER_IMPLEMENTATION,
        ),
        (
            WorkStage.CLUSTER_IMPLEMENTATION,
            TerminalOutcome.ACCEPTED,
            FollowUpAction.ADVANCE,
            WorkStage.TRACKER_PUBLICATION,
        ),
        (
            WorkStage.TRACKER_PUBLICATION,
            TerminalOutcome.ACCEPTED,
            FollowUpAction.COMPLETE,
            None,
        ),
        (
            WorkStage.PACKAGE_AUDIT,
            TerminalOutcome.BLOCKED,
            FollowUpAction.WAIT_FOR_BLOCKER,
            None,
        ),
        (
            WorkStage.PACKAGE_AUDIT,
            TerminalOutcome.INPUT_MISMATCH,
            FollowUpAction.RETRY_REPAIR,
            WorkStage.PACKAGE_AUDIT,
        ),
        (
            WorkStage.PACKAGE_AUDIT,
            TerminalOutcome.PARTIAL,
            FollowUpAction.RETRY_REPAIR,
            WorkStage.PACKAGE_AUDIT,
        ),
        (
            WorkStage.PACKAGE_AUDIT,
            TerminalOutcome.FAILED,
            FollowUpAction.RETRY_REPAIR,
            WorkStage.PACKAGE_AUDIT,
        ),
        (
            WorkStage.PACKAGE_AUDIT,
            TerminalOutcome.ABANDONED,
            FollowUpAction.RETRY_REPAIR,
            WorkStage.PACKAGE_AUDIT,
        ),
    ],
)
def test_follow_up_routing_is_closed_and_deterministic(
    stage: WorkStage,
    outcome: TerminalOutcome,
    action: FollowUpAction,
    next_stage: WorkStage | None,
) -> None:
    routed = route_follow_up(stage, outcome)
    assert routed.action is action
    assert routed.next_stage is next_stage


def test_claim_filter_does_not_consume_unowned_work(queue: Queue) -> None:
    queue.enqueue("tracker", kind="tracker", input_digest="a" * 64, priority=100)
    _enqueue_stage(queue, "audit", WorkStage.PACKAGE_AUDIT, "cluster-001")

    lease = queue.claim(
        "orchestrator",
        allowed_kinds=(WorkStage.PACKAGE_AUDIT.value,),
    )

    assert lease is not None
    assert lease.unit_id == "audit"
    assert queue.status("tracker") is WorkUnitStatus.READY

    with pytest.raises(ValueError, match="collection"):
        queue.claim("invalid", allowed_kinds=WorkStage.PACKAGE_AUDIT.value)


def test_orchestration_stage_requires_cluster_identity(queue: Queue) -> None:
    with pytest.raises(ValueError, match="cluster_id"):
        queue.enqueue(
            "audit",
            kind=WorkStage.PACKAGE_AUDIT.value,
            input_digest="a" * 64,
        )


def test_database_bounds_simultaneously_leased_clusters(queue: Queue) -> None:
    for index in range(MAX_ACTIVE_ORCHESTRATION_CLUSTERS + 1):
        _enqueue_stage(
            queue,
            f"audit-{index}",
            WorkStage.PACKAGE_AUDIT,
            f"cluster-{index}",
        )

    leases = [queue.claim(f"worker-{index}") for index in range(MAX_ACTIVE_ORCHESTRATION_CLUSTERS)]
    assert all(lease is not None for lease in leases)
    assert queue.claim("one-too-many") is None

    assert leases[0] is not None
    queue.finish(leases[0], TerminalOutcome.FAILED)
    replacement = queue.claim("replacement")
    assert replacement is not None
    assert replacement.unit_id == f"audit-{MAX_ACTIVE_ORCHESTRATION_CLUSTERS}"


def test_database_bounds_leases_inside_one_cluster(queue: Queue) -> None:
    for index in range(MAX_ACTIVE_ORCHESTRATION_LEASES_PER_CLUSTER + 1):
        _enqueue_stage(queue, f"audit-{index}", WorkStage.PACKAGE_AUDIT, "cluster-001")

    leases = [
        queue.claim(f"worker-{index}")
        for index in range(MAX_ACTIVE_ORCHESTRATION_LEASES_PER_CLUSTER)
    ]
    assert all(lease is not None for lease in leases)
    assert queue.claim("one-too-many") is None


def test_reconciliation_waits_for_existing_implementation_debt(queue: Queue) -> None:
    _enqueue_stage(
        queue,
        "reconciliation-1",
        WorkStage.CLUSTER_RECONCILIATION,
        "cluster-001",
        priority=100,
    )
    _enqueue_stage(
        queue,
        "implementation-1",
        WorkStage.CLUSTER_IMPLEMENTATION,
        "cluster-001",
        priority=100,
    )
    _enqueue_stage(
        queue,
        "reconciliation-2",
        WorkStage.CLUSTER_RECONCILIATION,
        "cluster-002",
        priority=90,
    )
    _enqueue_stage(
        queue,
        "implementation-2",
        WorkStage.CLUSTER_IMPLEMENTATION,
        "cluster-002",
        priority=90,
    )

    assert (
        queue.claim("early-implementer", allowed_kinds=(WorkStage.CLUSTER_IMPLEMENTATION.value,))
        is None
    )

    first = queue.claim("reconciler", allowed_kinds=(WorkStage.CLUSTER_RECONCILIATION.value,))
    assert first is not None
    _accept(queue, first, "reconciliation-1")
    assert (
        queue.claim("second-reconciler", allowed_kinds=(WorkStage.CLUSTER_RECONCILIATION.value,))
        is None
    )

    implementation = queue.claim(
        "implementer",
        allowed_kinds=(WorkStage.CLUSTER_IMPLEMENTATION.value,),
    )
    assert implementation is not None
    _accept(queue, implementation, "implementation-1")
    second = queue.claim(
        "second-reconciler",
        allowed_kinds=(WorkStage.CLUSTER_RECONCILIATION.value,),
    )
    assert second is not None
    assert second.unit_id == "reconciliation-2"


def test_reconciliation_leases_are_serialized_across_clusters(queue: Queue) -> None:
    for index in range(2):
        _enqueue_stage(
            queue,
            f"reconciliation-{index}",
            WorkStage.CLUSTER_RECONCILIATION,
            f"cluster-{index}",
        )
        _enqueue_stage(
            queue,
            f"implementation-{index}",
            WorkStage.CLUSTER_IMPLEMENTATION,
            f"cluster-{index}",
        )
    first = queue.claim("reconciler-1")
    second = queue.claim("reconciler-2")
    assert first is not None
    assert second is None

    _accept(queue, first, "first")
    assert (
        queue.claim("reconciler-2", allowed_kinds=(WorkStage.CLUSTER_RECONCILIATION.value,)) is None
    )

    implementation = queue.claim(
        "implementer",
        allowed_kinds=(WorkStage.CLUSTER_IMPLEMENTATION.value,),
    )
    assert implementation is not None
    _accept(queue, implementation, "implementation-0")
    second = queue.claim(
        "reconciler-2",
        allowed_kinds=(WorkStage.CLUSTER_RECONCILIATION.value,),
    )
    assert second is not None
    assert second.unit_id == "reconciliation-1"


def test_reconciliation_can_create_bounded_implementation_debt(queue: Queue) -> None:
    _enqueue_stage(
        queue,
        "reconciliation",
        WorkStage.CLUSTER_RECONCILIATION,
        "cluster-001",
    )

    lease = queue.claim("reconciler")
    assert lease is not None
    assert lease.unit_id == "reconciliation"
    _accept(queue, lease, "reconciliation")
    _enqueue_stage(
        queue,
        "second-reconciliation",
        WorkStage.CLUSTER_RECONCILIATION,
        "cluster-002",
    )
    assert queue.claim("second-reconciler") is None


def test_tracker_publication_requires_accepted_implementation(queue: Queue) -> None:
    _enqueue_stage(
        queue,
        "publication",
        WorkStage.TRACKER_PUBLICATION,
        "cluster-001",
    )

    assert queue.claim("publisher") is None


class _CompletingHandle:
    def __init__(self, queue: Queue, request: LaunchRequest) -> None:
        self.queue = queue
        self.request = request

    def wait(self, timeout_seconds: float) -> ContextExit | None:
        assert timeout_seconds > 0
        _accept(self.queue, self.request.lease, self.request.lease.unit_id)
        return ContextExit.EXITED

    def terminate(self) -> None:
        pytest.fail("completed context was terminated")


class _CompletingAdapter:
    def __init__(self, queue: Queue) -> None:
        self.queue = queue
        self.request: LaunchRequest | None = None

    def start(self, request: LaunchRequest) -> _CompletingHandle:
        self.request = request
        return _CompletingHandle(self.queue, request)


def test_launcher_hands_off_only_a_bounded_fresh_context(queue: Queue) -> None:
    _enqueue_stage(queue, "audit", WorkStage.PACKAGE_AUDIT, "cluster-001")
    adapter = _CompletingAdapter(queue)

    receipt = launch_one(
        queue,
        owner="launcher",
        adapter=adapter,
        prompt_factory=lambda lease, unit: f"Process {unit.unit_id} in {lease.workspace}",
        heartbeat_seconds=1,
        ttl_seconds=5,
        max_runtime_seconds=10,
    )

    assert receipt is not None
    assert receipt.context_exit is ContextExit.EXITED
    assert receipt.queue_status is WorkUnitStatus.COMPLETED
    assert receipt.follow_up.next_stage is WorkStage.CLUSTER_RECONCILIATION
    assert adapter.request is not None
    assert adapter.request.inherit_conversation is False
    assert adapter.request.workspace == receipt.lease.workspace

    with pytest.raises(ValueError, match="must not inherit"):
        replace(adapter.request, inherit_conversation=True)  # type: ignore[arg-type]


class _UnfinishedHandle:
    def wait(self, timeout_seconds: float) -> ContextExit | None:
        assert timeout_seconds > 0
        return ContextExit.EXITED

    def terminate(self) -> None:
        pytest.fail("exited context was terminated")


class _UnfinishedAdapter:
    def start(self, request: LaunchRequest) -> _UnfinishedHandle:
        del request
        return _UnfinishedHandle()


def test_launcher_routes_exit_without_terminal_to_repair(queue: Queue) -> None:
    _enqueue_stage(queue, "audit", WorkStage.PACKAGE_AUDIT, "cluster-001")

    receipt = launch_one(
        queue,
        owner="launcher",
        adapter=_UnfinishedAdapter(),
        prompt_factory=lambda _lease, _unit: "synthetic task",
        heartbeat_seconds=1,
        ttl_seconds=5,
        max_runtime_seconds=10,
    )

    assert receipt is not None
    assert receipt.context_exit is ContextExit.FAILED
    assert receipt.queue_status is WorkUnitStatus.REPAIR_REQUIRED
    assert receipt.follow_up.action is FollowUpAction.RETRY_REPAIR


class _FencingHandle:
    def __init__(self, queue: Queue, request: LaunchRequest) -> None:
        self.queue = queue
        self.request = request
        self.replacement: Lease | None = None

    def wait(self, timeout_seconds: float) -> ContextExit | None:
        assert timeout_seconds > 0
        with closing(sqlite3.connect(self.queue.database)) as connection, connection:
            connection.execute(
                "UPDATE leases SET expires_at = 1 WHERE lease_id = ?",
                (self.request.lease.lease_id,),
            )
        assert self.queue.recover() == 1
        self.replacement = self.queue.claim(
            "replacement",
            allowed_kinds=(WorkStage.PACKAGE_AUDIT.value,),
        )
        assert self.replacement is not None
        return ContextExit.EXITED

    def terminate(self) -> None:
        pytest.fail("exited fenced context was terminated")


class _FencingAdapter:
    def __init__(self, queue: Queue) -> None:
        self.queue = queue
        self.handle: _FencingHandle | None = None

    def start(self, request: LaunchRequest) -> _FencingHandle:
        self.handle = _FencingHandle(self.queue, request)
        return self.handle


def test_launcher_never_routes_from_a_replacement_attempt(queue: Queue) -> None:
    _enqueue_stage(queue, "audit", WorkStage.PACKAGE_AUDIT, "cluster-001")
    adapter = _FencingAdapter(queue)

    receipt = launch_one(
        queue,
        owner="launcher",
        adapter=adapter,
        prompt_factory=lambda _lease, _unit: "synthetic task",
        heartbeat_seconds=1,
        ttl_seconds=5,
        max_runtime_seconds=10,
    )

    assert receipt is not None
    assert receipt.context_exit is ContextExit.FAILED
    assert receipt.follow_up is None
    assert queue.attempt_outcome(receipt.lease.attempt_id) is TerminalOutcome.ABANDONED
    assert adapter.handle is not None and adapter.handle.replacement is not None
    queue.finish(adapter.handle.replacement, TerminalOutcome.FAILED)


def test_seeded_synthetic_crash_harness_converges_and_fences(tmp_path: Path) -> None:
    report = run_synthetic_acceptance(
        tmp_path / "synthetic-run",
        SyntheticAcceptanceConfig(
            seed=436,
            clusters=3,
            units_per_cluster=4,
            workers=6,
            crash_probability=0.35,
            forced_initial_crashes=2,
        ),
    )

    assert report.unit_count == 45
    assert report.attempt_count >= report.unit_count
    assert report.injected_crashes > 0
    assert report.recovered_attempts == report.injected_crashes
    assert report.stale_writers_fenced == report.injected_crashes
    assert report.max_implementation_debt_clusters == 1
    assert report.published_clusters == 3
    assert len(report.final_generation) == 64
