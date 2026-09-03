"""Seeded production-path crash acceptance for the cluster stage graph."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.queue.core as queue_core
from tools.phase4_v2.equivalence.plan import (
    PACKAGE_EXECUTION_PLAN_REVISION,
    PREPARATION_QUEUE_UNIT_KIND,
    PREPARATION_RECEIPT_REVISION,
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    FrozenCapabilityPin,
    FrozenCompletionPin,
    FrozenPackageExecutionPlan,
    FrozenPreparationPlanBinding,
    PackagePlanStatus,
)
from tools.phase4_v2.queue import (
    CapabilityPin,
    Lease,
    Queue,
    StaleLeaseError,
    TerminalOutcome,
    TrackerDocument,
    TrackerDocumentSet,
    TrackerFormat,
    TrackerTarget,
    WorkUnitStatus,
    document_set_sha256,
    publish_tracker_fanout,
)

from .completion import (
    STAGE_AUTHORITY_REVISION,
    ActivatedStageAuthority,
    TrustedImplementationReceipt,
    TrustedReconciliationReceipt,
    _load_stage_authority_with_config,
    finish_cluster_implementation,
    finish_cluster_reconciliation,
    finish_package_audit,
    finish_tracker_publication,
    load_implementation_receipt,
    load_package_audit_receipt,
    load_publication_receipt,
    load_reconciliation_receipt,
    stage_authority_capability,
)
from .graph import (
    CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
    CLUSTER_RECONCILIATION_COMPLETION_REVISION,
    PACKAGE_AUDIT_COMPLETION_REVISION,
    TRACKER_PUBLICATION_COMPLETION_REVISION,
    ClusterGraphPlan,
    build_cluster_graph,
    materialize_cluster_graph,
    package_audit_unit_id,
)
from .model import WorkStage


@dataclass(frozen=True, slots=True)
class SyntheticAcceptanceConfig:
    seed: int
    clusters: int = 8
    units_per_cluster: int = 8
    workers: int = 8
    crash_probability: float = 0.2
    forced_initial_crashes: int = 1
    max_rounds: int = 10_000

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if type(self.clusters) is not int or not 1 <= self.clusters <= 100:
            raise ValueError("clusters must be between 1 and 100")
        if type(self.units_per_cluster) is not int or not 1 <= self.units_per_cluster <= 100:
            raise ValueError("units_per_cluster must be between 1 and 100")
        if type(self.workers) is not int or not 1 <= self.workers <= 64:
            raise ValueError("workers must be between 1 and 64")
        if (
            isinstance(self.crash_probability, bool)
            or not isinstance(self.crash_probability, (int, float))
            or not 0 <= self.crash_probability < 1
        ):
            raise ValueError("crash_probability must be at least zero and below one")
        maximum = self.clusters * (3 * self.units_per_cluster + 3)
        if type(self.forced_initial_crashes) is not int or not (
            0 <= self.forced_initial_crashes <= maximum
        ):
            raise ValueError("forced_initial_crashes must fit the production graph")
        if type(self.max_rounds) is not int or not 1 <= self.max_rounds <= 1_000_000:
            raise ValueError("max_rounds must be bounded and positive")


@dataclass(frozen=True, slots=True)
class SyntheticAcceptanceReport:
    seed: int
    unit_count: int
    attempt_count: int
    injected_crashes: int
    recovered_attempts: int
    stale_writers_fenced: int
    max_implementation_debt_clusters: int
    rounds: int
    final_generation: str
    published_clusters: int


@dataclass(slots=True)
class _ClusterState:
    graph: ClusterGraphPlan
    audit_receipts: dict[str, str]
    reconciliation: TrustedReconciliationReceipt | None = None
    implementation: TrustedImplementationReceipt | None = None


class _Gateway:
    def __init__(self) -> None:
        self.revision = "a" * 40
        self.documents: dict[str, bytes] = {}

    def read(self, paths: tuple[str, ...]) -> TrackerDocumentSet:
        return TrackerDocumentSet(
            self.revision,
            tuple(TrackerDocument(path, self.documents.get(path)) for path in paths),
        )

    def compare_and_replace(
        self,
        *,
        expected_revision: str,
        expected_documents_sha256: str,
        documents: tuple[TrackerDocument, ...],
    ) -> bool:
        current = tuple(
            TrackerDocument(item.path, self.documents.get(item.path)) for item in documents
        )
        if expected_revision != self.revision or expected_documents_sha256 != document_set_sha256(
            current
        ):
            return False
        self.documents = {item.path: item.body or b"" for item in documents}
        self.revision = hashlib.sha1(
            (self.revision + expected_documents_sha256).encode(), usedforsecurity=False
        ).hexdigest()
        return True


def run_synthetic_acceptance(
    root: Path, config: SyntheticAcceptanceConfig
) -> SyntheticAcceptanceReport:
    """Exercise materialization, signed adapters, recovery, debt fencing, and fanout."""

    if root.exists():
        raise ValueError("synthetic acceptance root must not already exist")
    database = root / "state" / "queue.sqlite3"
    attempts_root = root / "attempts"
    queue = Queue(database, attempts_root)
    queue.initialize()
    keys, authorities = _authorities()
    states = _build_graphs(queue, config, authorities)
    for state in states.values():
        materialize_cluster_graph(queue, state.graph)
    # Package report validation has its own exhaustive acceptance suite. This bounded
    # harness enters at its immutable completion revision, then exercises every
    # cluster-owned production adapter and the real fanout publisher.
    _complete_analysis_inputs(queue)

    generator = random.Random(config.seed)
    attempts = crashes = recovered = fenced = rounds = 0
    max_debt = 0
    gateway = _Gateway()
    targets = (
        TrackerTarget("issues/436.md", TrackerFormat.MARKDOWN),
        TrackerTarget("public/queue.html", TrackerFormat.HTML),
    )
    while True:
        for state in states.values():
            materialize_cluster_graph(queue, state.graph)
        snapshot = queue.snapshot()
        if all(unit.status is WorkUnitStatus.COMPLETED for unit in snapshot.units):
            break
        rounds += 1
        if rounds > config.max_rounds:
            raise RuntimeError("synthetic acceptance did not converge within max_rounds")
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            leases = tuple(
                lease
                for lease in executor.map(
                    lambda owner: Queue(database, attempts_root).claim(
                        owner,
                        allowed_kinds=tuple(
                            stage.value
                            for stage in WorkStage
                            if stage is not WorkStage.PACKAGE_ANALYSIS
                        ),
                    ),
                    (f"synthetic-worker:{index:02d}" for index in range(config.workers)),
                )
                if lease is not None
            )
        if not leases or len({lease.unit_id for lease in leases}) != len(leases):
            raise RuntimeError("synthetic queue stalled or issued overlapping leases")
        attempts += len(leases)
        crashed: list[Lease] = []
        for lease in sorted(leases, key=lambda item: item.unit_id):
            if (
                crashes < config.forced_initial_crashes
                or generator.random() < config.crash_probability
            ):
                crashes += 1
                crashed.append(lease)
                continue
            state = states[_cluster_for(queue, lease.unit_id)]
            _finish_stage(queue, lease, state, keys, authorities, gateway, targets)
            snapshot = queue.snapshot()
            reconciliation_done = {
                item.cluster_id
                for item in snapshot.units
                if item.kind == WorkStage.CLUSTER_RECONCILIATION.value
                and item.status is WorkUnitStatus.COMPLETED
            }
            implementation_done = {
                item.cluster_id
                for item in snapshot.units
                if item.kind == WorkStage.CLUSTER_IMPLEMENTATION.value
                and item.status is WorkUnitStatus.COMPLETED
            }
            max_debt = max(max_debt, len(reconciliation_done - implementation_done))
            if len(reconciliation_done - implementation_done) > 1:
                raise RuntimeError("multiple clusters accumulated implementation debt")
        if crashed:
            with closing(sqlite3.connect(database)) as connection, connection:
                updated = connection.executemany(
                    "UPDATE leases SET expires_at = 1 WHERE lease_id = ?",
                    ((lease.lease_id,) for lease in crashed),
                )
                if updated.rowcount != len(crashed):
                    raise RuntimeError("crash injection lost a live lease")
            recovered += queue.recover()
            for lease in crashed:
                try:
                    queue.finish(lease, TerminalOutcome.FAILED)
                except StaleLeaseError:
                    fenced += 1
                else:
                    raise RuntimeError("recovered worker was not fenced")

    final = queue.snapshot()
    expected_units = config.clusters * (3 * config.units_per_cluster + 3)
    if len(final.units) != expected_units:
        raise RuntimeError("production graph lost or added a work unit")
    workspace_count = sum(1 for unit in attempts_root.iterdir() for _child in unit.iterdir())
    setup_attempts = 2 * config.clusters * config.units_per_cluster
    if workspace_count != attempts + setup_attempts:
        raise RuntimeError("an attempt workspace was lost or overwritten")
    return SyntheticAcceptanceReport(
        config.seed,
        expected_units,
        attempts + setup_attempts,
        crashes,
        recovered,
        fenced,
        max_debt,
        rounds,
        final.generation_id,
        sum(state.implementation is not None for state in states.values()),
    )


def _finish_stage(
    queue: Queue,
    lease: Lease,
    state: _ClusterState,
    keys: dict[str, Ed25519PrivateKey],
    authorities: dict[str, ActivatedStageAuthority],
    gateway: _Gateway,
    targets: tuple[TrackerTarget, ...],
) -> None:
    graph = state.graph
    unit = next(item for item in queue.snapshot().units if item.unit_id == lease.unit_id)
    if unit.kind == WorkStage.PACKAGE_AUDIT.value:
        package = next(
            item
            for item in graph.packages
            if package_audit_unit_id(graph, item.package_ref_id) == lease.unit_id
        )
        analysis = next(item for item in queue.snapshot().units if item.unit_id == package.unit_id)
        receipt = load_package_audit_receipt(
            _signed(
                "audit",
                {
                    "accepted": True,
                    "analysis_completion_revision": analysis.completion_revision,
                    "analysis_completion_sha256": analysis.output_digest,
                    "cluster_id": graph.cluster_id,
                    "diagnostics": [],
                    "graph_sha256": graph.content_id,
                    "package_ref_id": package.package_ref_id,
                    "revision": PACKAGE_AUDIT_COMPLETION_REVISION,
                    "stage_input_sha256": lease.input_digest,
                },
                keys["audit"],
                authorities["audit"],
            ),
            authorities["audit"],
        )
        result = finish_package_audit(
            queue,
            lease,
            graph=graph,
            authority=authorities["audit"],
            receipt=receipt,
        )
        state.audit_receipts[package.package_ref_id] = result.receipt_sha256
        return
    if unit.kind == WorkStage.CLUSTER_RECONCILIATION.value:
        receipt = load_reconciliation_receipt(
            _signed(
                "reconciliation",
                {
                    "accepted": True,
                    "cluster_id": graph.cluster_id,
                    "completeness_receipt_sha256": _digest(f"complete:{graph.cluster_id}"),
                    "diagnostics": [],
                    "disposition_ledger_sha256": _digest(f"ledger:{graph.cluster_id}"),
                    "graph_sha256": graph.content_id,
                    "package_audit_receipts": [
                        list(item) for item in sorted(state.audit_receipts.items())
                    ],
                    "reconciliation_result_sha256": _digest(f"result:{graph.cluster_id}"),
                    "revision": CLUSTER_RECONCILIATION_COMPLETION_REVISION,
                    "stage_input_sha256": lease.input_digest,
                },
                keys["reconciliation"],
                authorities["reconciliation"],
            ),
            authorities["reconciliation"],
        )
        finish_cluster_reconciliation(
            queue,
            lease,
            graph=graph,
            authority=authorities["reconciliation"],
            receipt=receipt,
        )
        state.reconciliation = receipt
        return
    if unit.kind == WorkStage.CLUSTER_IMPLEMENTATION.value:
        reconciliation = state.reconciliation
        if reconciliation is None:
            raise RuntimeError("implementation was scheduled without reconciliation")
        receipt = load_implementation_receipt(
            _signed(
                "implementation",
                {
                    "accepted": True,
                    "cluster_id": graph.cluster_id,
                    "diagnostics": [],
                    "disposition_ledger_sha256": reconciliation.disposition_ledger_sha256,
                    "graph_sha256": graph.content_id,
                    "implementation_output_sha256": _digest(f"implementation:{graph.cluster_id}"),
                    "reconciliation_receipt_sha256": reconciliation.receipt_sha256,
                    "revision": CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
                    "stage_input_sha256": lease.input_digest,
                },
                keys["implementation"],
                authorities["implementation"],
            ),
            authorities["implementation"],
        )
        finish_cluster_implementation(
            queue,
            lease,
            graph=graph,
            reconciliation_authority=authorities["reconciliation"],
            reconciliation_receipt=reconciliation,
            authority=authorities["implementation"],
            receipt=receipt,
        )
        state.implementation = receipt
        return
    if unit.kind != WorkStage.TRACKER_PUBLICATION.value:
        raise RuntimeError("unexpected synthetic stage")
    reconciliation = state.reconciliation
    implementation = state.implementation
    if reconciliation is None or implementation is None:
        raise RuntimeError("publication was scheduled without implementation")
    fanout = publish_tracker_fanout(queue, lease, gateway, targets)
    receipt = load_publication_receipt(
        _signed(
            "publication",
            {
                "accepted": True,
                "after_revision": fanout.after_revision,
                "before_revision": fanout.before_revision,
                "changed": fanout.changed,
                "cluster_id": graph.cluster_id,
                "diagnostics": [],
                "document_set_sha256": fanout.document_set_sha256,
                "graph_sha256": graph.content_id,
                "implementation_receipt_sha256": implementation.receipt_sha256,
                "paths": list(fanout.paths),
                "publication_config_sha256": fanout.publication_config_sha256,
                "queue_generation_sha256": fanout.queue_generation,
                "revision": TRACKER_PUBLICATION_COMPLETION_REVISION,
                "stage_input_sha256": lease.input_digest,
            },
            keys["publication"],
            authorities["publication"],
        ),
        authorities["publication"],
    )
    finish_tracker_publication(
        queue,
        lease,
        graph=graph,
        reconciliation_authority=authorities["reconciliation"],
        reconciliation_receipt=reconciliation,
        implementation_authority=authorities["implementation"],
        implementation_receipt=implementation,
        authority=authorities["publication"],
        fanout_receipt=fanout,
        receipt=receipt,
    )


def _build_graphs(
    queue: Queue,
    config: SyntheticAcceptanceConfig,
    authorities: dict[str, ActivatedStageAuthority],
) -> dict[str, _ClusterState]:
    result: dict[str, _ClusterState] = {}
    for cluster_index in range(config.clusters):
        cluster = f"synthetic-cluster:{cluster_index:04d}"
        plans = tuple(
            _frozen_plan(cluster, package_index)
            for package_index in range(config.units_per_cluster)
        )
        stage_pins = tuple(stage_authority_capability(authorities[stage]) for stage in _STAGE_NAMES)
        package_pins = tuple(
            CapabilityPin(pin.name, pin.revision, pin.digest)
            for plan in plans
            for pin in plan.required_capabilities
        )
        for pin in (*package_pins, *stage_pins):
            queue.register_capability(pin.capability, pin.revision, pin.digest)
            queue.activate_capability_from_absent(pin.capability, pin.revision, pin.digest)
        _complete_preparation_inputs(queue, plans)
        graph = build_cluster_graph(
            queue,
            plans,
            audit_authority=authorities["audit"],
            reconciliation_authority=authorities["reconciliation"],
            implementation_authority=authorities["implementation"],
            publication_authority=authorities["publication"],
        )
        result[cluster] = _ClusterState(graph, {})
    return result


def _complete_preparation_inputs(
    queue: Queue, plans: tuple[FrozenPackageExecutionPlan, ...]
) -> None:
    original = queue_core._requires_trusted_completion_adapter
    for plan in plans:
        completion = plan.preparation.completion
        queue.materialize_work_unit(
            completion.parent_unit_id,
            kind=PREPARATION_QUEUE_UNIT_KIND,
            capability_pins=tuple(
                CapabilityPin(item.name, item.revision, item.digest)
                for item in plan.preparation.capabilities
            ),
            input_digest=_digest(f"prep-input:{plan.target_package_ref_id}"),
        )
        lease = queue.claim("synthetic-preparation", allowed_kinds=(PREPARATION_QUEUE_UNIT_KIND,))
        if lease is None:
            raise RuntimeError("synthetic preparation did not become ready")
        with patch.object(
            queue_core,
            "_requires_trusted_completion_adapter",
            side_effect=lambda unit_id, kind, lease_id=lease.unit_id: (
                False if unit_id == lease_id else original(unit_id, kind)
            ),
        ):
            queue.finish(
                lease,
                TerminalOutcome.ACCEPTED,
                output_digest=completion.digest,
                completion_revision=completion.revision,
            )


def _complete_analysis_inputs(queue: Queue) -> None:
    original = queue_core._requires_trusted_completion_adapter
    while lease := queue.claim(
        "synthetic-package-validator", allowed_kinds=(WorkStage.PACKAGE_ANALYSIS.value,)
    ):
        lease_id = lease.unit_id
        with patch.object(
            queue_core,
            "_requires_trusted_completion_adapter",
            side_effect=lambda unit_id, kind, active_id=lease_id: (
                False if unit_id == active_id else original(unit_id, kind)
            ),
        ):
            queue.finish(
                lease,
                TerminalOutcome.ACCEPTED,
                expected_input_digest=lease.input_digest,
                output_digest=_digest(f"validated:{lease.unit_id}"),
                completion_revision=VALIDATED_PACKAGE_OUTPUT_REVISION,
            )


def _cluster_for(queue: Queue, unit_id: str) -> str:
    unit = next(item for item in queue.snapshot().units if item.unit_id == unit_id)
    if unit.cluster_id is None:
        raise RuntimeError("stage unit has no cluster")
    return unit.cluster_id


def _authorities() -> tuple[dict[str, Ed25519PrivateKey], dict[str, ActivatedStageAuthority]]:
    keys: dict[str, Ed25519PrivateKey] = {}
    authorities: dict[str, ActivatedStageAuthority] = {}
    documents: dict[str, bytes] = {}
    config: dict[str, tuple[str, int]] = {}
    for stage in _STAGE_NAMES:
        key = Ed25519PrivateKey.from_private_bytes(
            hashlib.sha256(f"synthetic-stage-key:{stage}".encode()).digest()
        )
        public = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        canonical = _canonical(
            {
                "authority_id": f"synthetic-{stage}",
                "generation": 1,
                "public_key": public.hex(),
                "revision": STAGE_AUTHORITY_REVISION,
                "stage": stage,
            }
        )
        digest = hashlib.sha256(b"phase4-v2:stage-authority\0" + canonical).hexdigest()
        keys[stage] = key
        documents[stage] = canonical
        config[stage] = (digest, 1)
    for stage in _STAGE_NAMES:
        authorities[stage] = _load_stage_authority_with_config(documents[stage], config)
    return keys, authorities


def _signed(
    stage: str,
    payload: dict[str, object],
    key: Ed25519PrivateKey,
    authority: ActivatedStageAuthority,
) -> bytes:
    payload = {**payload, "authority_sha256": authority.authority_sha256, "stage": stage}
    signature = key.sign(
        f"phase4-v2:signed-stage-receipt:{stage}".encode() + b"\0" + _canonical(payload)
    ).hex()
    return _canonical({"payload": payload, "signature": signature})


def _frozen_plan(cluster: str, index: int) -> FrozenPackageExecutionPlan:
    package = f"p{index:04d}"
    package_ref = _digest(f"package:{cluster}:{package}")
    capability = FrozenCapabilityPin(
        f"analysis:{cluster}:{package}",
        "synthetic-analysis-v1",
        _digest(f"cap:{cluster}:{package}"),
    )
    preparation_capabilities = tuple(
        FrozenCapabilityPin(
            f"preparation-{kind}:{cluster}:{package}",
            f"preparation-{kind}-v1",
            _digest(f"preparation-{kind}:{cluster}:{package}"),
        )
        for kind in ("authority", "candidate", "execution", "registry")
    )
    preparation_completion = FrozenCompletionPin(
        f"package-preparation:{package_ref}",
        PREPARATION_RECEIPT_REVISION,
        _digest(f"receipt:{cluster}:{package}"),
    )
    preparation = FrozenPreparationPlanBinding(
        package_ref,
        f"org.example.{package}",
        "1",
        "1.0",
        _digest(f"artifact:{cluster}:{package}"),
        _digest(f"preflight:{cluster}:{package}"),
        preparation_completion.digest,
        preparation_completion,
        preparation_capabilities,
    )
    required_capabilities = tuple(
        sorted((*preparation_capabilities, capability), key=lambda item: item.name)
    )
    data = {
        "authoritative_root_count": 1,
        "cluster_id": cluster,
        "package_local": {
            "package_name": f"org.example.{package}",
            "requirements_sha256": _digest(f"preflight:{cluster}:{package}"),
            "target_artifact_digest": _digest(f"artifact:{cluster}:{package}"),
            "version_code": "1",
            "version_name": "1.0",
        },
        "preparation": preparation.to_data(),
        "required_capabilities": [
            {"digest": item.digest, "name": item.name, "revision": item.revision}
            for item in required_capabilities
        ],
        "required_completions": [
            {
                "digest": preparation_completion.digest,
                "parent_unit_id": preparation_completion.parent_unit_id,
                "revision": preparation_completion.revision,
            }
        ],
        "revision": PACKAGE_EXECUTION_PLAN_REVISION,
        "status": PackagePlanStatus.EXECUTABLE.value,
        "target_package_ref_id": package_ref,
    }
    canonical = _canonical(data)
    result = object.__new__(FrozenPackageExecutionPlan)
    values = {
        "target_package_ref_id": package_ref,
        "cluster_id": cluster,
        "canonical_bytes": canonical,
        "digest": hashlib.sha256(b"phase4-v2:package-execution-plan\0" + canonical).hexdigest(),
        "status": PackagePlanStatus.EXECUTABLE,
        "root_count": 1,
        "package_name": f"org.example.{package}",
        "version_code": "1",
        "version_name": "1.0",
        "target_artifact_digest": _digest(f"artifact:{cluster}:{package}"),
        "preflight_sha256": _digest(f"preflight:{cluster}:{package}"),
        "preparation": preparation,
        "inherited_semantic_roots": (),
        "semantic_audit_completion_digests": (),
        "required_capabilities": required_capabilities,
        "required_completions": (preparation_completion,),
    }
    for field, value in values.items():
        object.__setattr__(result, field, value)
    return result


def _pin(name: str) -> CapabilityPin:
    return CapabilityPin(name, f"{name}-v1", _digest(name))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


_STAGE_NAMES = ("audit", "reconciliation", "implementation", "publication")
