"""Seeded production-path crash acceptance for the cluster stage graph."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.orchestration.completion as completion_module
from tools.phase4_v2.equivalence import (
    INVENTORY_QUEUE_UNIT_KIND,
    PACKAGE_QUEUE_UNIT_KIND,
    PACKAGE_VALIDATION_RECEIPT_QUEUE_UNIT_KIND,
    PREPARATION_QUEUE_UNIT_KIND,
    AuthenticatedPackageExecutionEnvelope,
    CapabilityPin,
    ExtractorCapability,
    FrozenPackageExecutionPlan,
    FrozenPackageRef,
    ValidatedPackageOutput,
    build_validated_package_output,
    execution_authority_capability,
    execution_envelope_payload,
    execution_envelope_signing_bytes,
    finish_package_execution_plan,
    finish_package_preparation,
    finish_package_validation_receipt,
    finish_target_inventory,
    freeze_package_execution_plan,
    inventory_authority_capability,
    inventory_extractor_capability,
    load_authenticated_package_execution_envelope,
    load_authenticated_target_inventory_envelope,
    materialize_package_execution_plan,
    materialize_package_preparation,
    materialize_package_validation_receipt,
    materialize_target_inventory,
    preparation_capability_pins,
    target_inventory_envelope_payload,
    target_inventory_signing_bytes,
)
from tools.phase4_v2.queue import (
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
from tools.phase4_v2.queue.publication_config import TrackerPublicationConfig
from tools.phase4_v2.validator import validate_report_bundle

from .completion import (
    STAGE_AUTHORITY_REVISION,
    ActivatedStageAuthority,
    TrustedImplementationReceipt,
    TrustedReconciliationReceipt,
    finish_cluster_implementation,
    finish_cluster_reconciliation,
    finish_package_audit,
    finish_tracker_publication,
    load_implementation_receipt,
    load_package_audit_receipt,
    load_publication_receipt,
    load_reconciliation_receipt,
    load_stage_authority,
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
from .testing import (
    IncompleteSyntheticPackage,
    SyntheticTrust,
    build_synthetic_package_inputs,
    finish_synthetic_package_inputs,
    protected_fixture_trust,
)


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
        maximum = self.clusters * (self.units_per_cluster + 3)
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


class _CapabilityIdentity(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def revision(self) -> str: ...

    @property
    def digest(self) -> str: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedSyntheticPackage:
    frozen_plan: FrozenPackageExecutionPlan
    output: ValidatedPackageOutput
    execution_envelope: AuthenticatedPackageExecutionEnvelope
    package_ref: FrozenPackageRef
    report_bytes: bytes
    report_manifest_bytes: bytes


class _Gateway:
    def __init__(self) -> None:
        self.repository = "synthetic/repository"
        self.branch = "tracker"
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
    with (
        _protected_stage_authorities() as (keys, authorities),
        protected_fixture_trust(root / "fixture-trust") as trust,
    ):
        return _run_synthetic_acceptance(root, config, keys, authorities, trust)


def _run_synthetic_acceptance(
    root: Path,
    config: SyntheticAcceptanceConfig,
    keys: dict[str, Ed25519PrivateKey],
    authorities: dict[str, ActivatedStageAuthority],
    trust: SyntheticTrust,
) -> SyntheticAcceptanceReport:
    database = root / "state" / "queue.sqlite3"
    attempts_root = root / "attempts"
    queue = Queue(database, attempts_root)
    queue.initialize()
    states = _build_graphs(queue, config, authorities, trust, root / "fixtures")
    for state in states.values():
        materialize_cluster_graph(queue, state.graph)

    generator = random.Random(config.seed)
    attempts = crashes = recovered = fenced = rounds = 0
    max_debt = 0
    gateway = _Gateway()
    targets = (
        TrackerTarget("issues/436.md", TrackerFormat.MARKDOWN),
        TrackerTarget("public/queue.html", TrackerFormat.HTML),
    )
    publication_config = TrackerPublicationConfig(gateway.repository, gateway.branch, targets)
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
            _finish_stage(
                queue,
                lease,
                state,
                keys,
                authorities,
                gateway,
                publication_config,
            )
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
    expected_units = config.clusters * (5 * config.units_per_cluster + 3)
    if len(final.units) != expected_units:
        raise RuntimeError("production graph lost or added a work unit")
    workspace_count = sum(1 for unit in attempts_root.iterdir() for _child in unit.iterdir())
    setup_attempts = 4 * config.clusters * config.units_per_cluster
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
    publication_config: TrackerPublicationConfig,
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
    fanout = publish_tracker_fanout(queue, lease, gateway, publication_config)
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
    trust: SyntheticTrust,
    fixtures_root: Path,
) -> dict[str, _ClusterState]:
    result: dict[str, _ClusterState] = {}
    active_capabilities: set[tuple[str, str, str]] = set()
    for stage in _STAGE_NAMES:
        stage_pin = stage_authority_capability(authorities[stage])
        activate_synthetic_capability(
            queue,
            CapabilityPin(stage_pin.capability, stage_pin.revision, stage_pin.digest),
            active_capabilities,
        )
    for pin in preparation_capability_pins(trust.preparation_authority):
        activate_synthetic_capability(queue, pin, active_capabilities)
    for cluster_index in range(config.clusters):
        cluster = f"synthetic-cluster:{cluster_index:04d}"
        plans = tuple(
            complete_synthetic_package_inputs(
                queue,
                build_synthetic_package_inputs(
                    fixtures_root / cluster,
                    cluster_id=cluster,
                    package_index=package_index,
                    trust=trust,
                ),
                trust,
                active_capabilities,
            )
            for package_index in range(config.units_per_cluster)
        )
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


def complete_synthetic_package_inputs(
    queue: Queue,
    partial: IncompleteSyntheticPackage,
    trust: SyntheticTrust,
    active_capabilities: set[tuple[str, str, str]],
) -> FrozenPackageExecutionPlan:
    return complete_authenticated_synthetic_package_inputs(
        queue, partial, trust, active_capabilities
    ).frozen_plan


def complete_authenticated_synthetic_package_inputs(
    queue: Queue,
    partial: IncompleteSyntheticPackage,
    trust: SyntheticTrust,
    active_capabilities: set[tuple[str, str, str]],
) -> AuthenticatedSyntheticPackage:
    for pin in preparation_capability_pins(
        partial.preparation_authority,
    ):
        activate_synthetic_capability(queue, pin, active_capabilities)
    materialize_package_preparation(
        queue,
        package_ref=partial.package_ref,
        package_local=partial.package_local,
        authority=partial.preparation_authority,
    )
    preparation_lease = _claim_required(queue, PREPARATION_QUEUE_UNIT_KIND)
    preparation = finish_package_preparation(
        queue,
        preparation_lease,
        package_ref=partial.package_ref,
        package_local=partial.package_local,
        receipt=partial.preparation_receipt,
        authority=partial.preparation_authority,
    ).binding

    materialize_package_validation_receipt(queue, partial.source_envelope)
    validation_lease = _claim_required(queue, PACKAGE_VALIDATION_RECEIPT_QUEUE_UNIT_KIND)
    finish_package_validation_receipt(queue, validation_lease, envelope=partial.source_envelope)

    extractor = ExtractorCapability(
        name="phase4-v2-synthetic-inventory-extractor",
        implementation_sha256=trust.tool_sha256,
        configuration_sha256=_digest("synthetic-inventory-configuration"),
        capability_revision="synthetic-inventory-v1",
    )
    for pin in (
        inventory_authority_capability(trust.inventory_authority),
        inventory_extractor_capability(extractor),
    ):
        activate_synthetic_capability(queue, pin, active_capabilities)
    unsigned = target_inventory_envelope_payload(
        package_ref=partial.package_ref,
        inventory=partial.target_inventory,
        extractor=extractor,
        authority=trust.inventory_authority,
        signature="0" * 128,
    )
    payload = json.loads(unsigned)["payload"]
    signature = trust.inventory_key.sign(target_inventory_signing_bytes(payload)).hex()
    envelope = load_authenticated_target_inventory_envelope(
        target_inventory_envelope_payload(
            package_ref=partial.package_ref,
            inventory=partial.target_inventory,
            extractor=extractor,
            authority=trust.inventory_authority,
            signature=signature,
        ),
        authority=trust.inventory_authority,
        package_ref=partial.package_ref,
    )
    materialize_target_inventory(queue, envelope)
    inventory_lease = _claim_required(queue, INVENTORY_QUEUE_UNIT_KIND)
    inventory, _inventory_result = finish_target_inventory(
        queue, inventory_lease, envelope=envelope
    )

    inputs = finish_synthetic_package_inputs(
        partial, preparation=preparation, target_inventory=inventory
    )
    frozen = freeze_package_execution_plan(inputs.execution_plan)
    for pin in frozen.required_capabilities:
        activate_synthetic_capability(queue, pin, active_capabilities)
    execution_capability = execution_authority_capability(trust.execution_authority)
    activate_synthetic_capability(queue, CapabilityPin(*execution_capability), active_capabilities)
    receipt = validate_report_bundle(
        inputs.report_root,
        expected_dependencies=inputs.dependencies,
        expected_evidence_lineage=inputs.lineage,
    )
    assert receipt.validation_receipt_sha256 is not None
    output = build_validated_package_output(
        execution_plan=inputs.execution_plan,
        receipt=receipt,
        trusted_validation_receipt_sha256=receipt.validation_receipt_sha256,
    )
    unsigned_execution = execution_envelope_payload(
        authority=trust.execution_authority,
        receipt_bytes=receipt.to_json().encode(),
        package_ref_id=frozen.target_package_ref_id,
        execution_plan_sha256=frozen.canonical_sha256,
        execution_plan_id=frozen.digest,
        output_content_id=output.content_id,
        report_bundle_sha256=receipt.bundle_sha256 or "",
        corpus_sha256=inputs.dependencies.corpus_sha256,
        evidence_lineage_sha256=inputs.lineage.expected_manifest_sha256,
        ir_sha256=inputs.dependencies.ir_sha256,
        signature="0" * 128,
    )
    execution_payload = json.loads(unsigned_execution)["payload"]
    execution_signature = trust.execution_key.sign(
        execution_envelope_signing_bytes(execution_payload)
    ).hex()
    execution_envelope = load_authenticated_package_execution_envelope(
        execution_envelope_payload(
            authority=trust.execution_authority,
            receipt_bytes=receipt.to_json().encode(),
            package_ref_id=frozen.target_package_ref_id,
            execution_plan_sha256=frozen.canonical_sha256,
            execution_plan_id=frozen.digest,
            output_content_id=output.content_id,
            report_bundle_sha256=receipt.bundle_sha256 or "",
            corpus_sha256=inputs.dependencies.corpus_sha256,
            evidence_lineage_sha256=inputs.lineage.expected_manifest_sha256,
            ir_sha256=inputs.dependencies.ir_sha256,
            signature=execution_signature,
        ),
        authority=trust.execution_authority,
    )
    materialize_package_execution_plan(queue, inputs.execution_plan)
    analysis_lease = _claim_required(queue, PACKAGE_QUEUE_UNIT_KIND)
    finished = finish_package_execution_plan(
        queue,
        analysis_lease,
        execution_plan=inputs.execution_plan,
        report_root=inputs.report_root,
        evidence_lineage_payload=inputs.lineage.payload,
        execution_envelope=execution_envelope,
    )
    if finished.output != output:
        raise RuntimeError("queue publication changed the validated package output")
    return AuthenticatedSyntheticPackage(
        frozen,
        output,
        execution_envelope,
        inputs.package_ref,
        (inputs.report_root / "analysis.json").read_bytes(),
        (inputs.report_root / "REPORT.SHA256").read_bytes(),
    )


def activate_synthetic_capability(
    queue: Queue,
    pin: _CapabilityIdentity,
    active_capabilities: set[tuple[str, str, str]],
) -> None:
    identity = (pin.name, pin.revision, pin.digest)
    if identity in active_capabilities:
        return
    queue.register_capability(*identity)
    queue.activate_capability_from_absent(*identity)
    active_capabilities.add(identity)


def _claim_required(queue: Queue, kind: str) -> Lease:
    lease = queue.claim(f"synthetic-{kind}", allowed_kinds=(kind,))
    if lease is None:
        raise RuntimeError(f"synthetic {kind} input did not become ready")
    return lease


def _cluster_for(queue: Queue, unit_id: str) -> str:
    unit = next(item for item in queue.snapshot().units if item.unit_id == unit_id)
    if unit.cluster_id is None:
        raise RuntimeError("stage unit has no cluster")
    return unit.cluster_id


@contextmanager
def _protected_stage_authorities() -> Iterator[
    tuple[dict[str, Ed25519PrivateKey], dict[str, ActivatedStageAuthority]]
]:
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
    with patch.object(completion_module, "_load_stage_authority_config", return_value=config):
        for stage in _STAGE_NAMES:
            authorities[stage] = load_stage_authority(documents[stage])
        yield keys, authorities


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


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


_STAGE_NAMES = ("audit", "reconciliation", "implementation", "publication")
