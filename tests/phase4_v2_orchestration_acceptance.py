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
import tools.phase4_v2.queue.fanout as fanout_module
from tests.phase4_v2_orchestration_testing import (
    IncompleteSyntheticPackage,
    SyntheticExactReuseTrust,
    SyntheticPackageInputs,
    SyntheticTrust,
    _authorized_final_ir,
    build_raw_backed_source_registry,
    build_synthetic_package_inputs,
    finish_synthetic_package_inputs,
    merge_raw_backed_source_registries,
    protected_fixture_trust,
)
from tools.phase4_v2.equivalence import (
    EQUIVALENCE_SCHEMA_REVISION,
    EXACT_REUSE_DIRECT_AUDIT_QUEUE_KIND,
    EXACT_REUSE_LEDGER_DECISION_QUEUE_KIND,
    EXACT_REUSE_PIPELINE_CAPABILITY,
    EXACT_REUSE_SEMANTIC_ROOT_QUEUE_KIND,
    INVENTORY_QUEUE_UNIT_KIND,
    PACKAGE_QUEUE_UNIT_KIND,
    PACKAGE_VALIDATION_RECEIPT_QUEUE_UNIT_KIND,
    PREPARATION_QUEUE_UNIT_KIND,
    AcceptedTargetRootInventory,
    ApplicationRoot,
    AuthenticatedExactReuseProvenance,
    AuthenticatedPackageExecutionEnvelope,
    AuthenticatedSourceReportRegistry,
    AuthenticatedTargetInventoryEnvelope,
    CapabilityPin,
    ExtractorCapability,
    FrozenPackageExecutionPlan,
    FrozenPackageRef,
    FullAnalysisRootPlan,
    PreparationPlanBinding,
    RootExecutionPlan,
    RoutingPins,
    ValidatedPackageOutput,
    build_authenticated_source_report_registry,
    build_exact_reuse_root_plan,
    build_validated_package_output,
    exact_reuse_authority_capability,
    exact_reuse_prerequisite_envelope_payload,
    exact_reuse_prerequisite_payload,
    exact_reuse_prerequisite_signing_bytes,
    exact_reuse_provenance_payload,
    exact_reuse_provenance_signing_bytes,
    execution_authority_capability,
    execution_envelope_payload,
    execution_envelope_signing_bytes,
    finish_exact_reuse_prerequisite,
    finish_package_execution_plan,
    finish_package_preparation,
    finish_package_validation_receipt,
    finish_target_inventory,
    freeze_package_execution_plan,
    inventory_authority_capability,
    inventory_extractor_capability,
    load_authenticated_exact_reuse_prerequisite,
    load_authenticated_exact_reuse_provenance,
    load_authenticated_package_execution_envelope,
    load_authenticated_target_inventory_envelope,
    load_authenticated_validator_envelope,
    materialize_exact_reuse_prerequisites,
    materialize_package_execution_plan,
    materialize_package_preparation,
    materialize_package_validation_receipt,
    materialize_target_inventory,
    preparation_capability_pins,
    route_application_root,
    semantic_root_audit_from_authenticated_prerequisite,
    source_report_root_completion,
    target_inventory_envelope_payload,
    target_inventory_signing_bytes,
)
from tools.phase4_v2.ir import dumps_final_ir, loads_final_ir, render_final_ir_markdown
from tools.phase4_v2.orchestration.completion import (
    STAGE_AUTHORITY_REVISION,
    ActivatedStageAuthority,
    TrustedImplementationReceipt,
    TrustedPackageAuditReceipt,
    TrustedReconciliationReceipt,
    build_authenticated_reconciliation_input,
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
from tools.phase4_v2.orchestration.graph import (
    CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
    CLUSTER_RECONCILIATION_COMPLETION_REVISION,
    PACKAGE_AUDIT_COMPLETION_REVISION,
    TRACKER_PUBLICATION_COMPLETION_REVISION,
    ClusterGraphPlan,
    build_cluster_graph,
    materialize_cluster_graph,
    package_audit_unit_id,
)
from tools.phase4_v2.orchestration.model import WorkStage
from tools.phase4_v2.preflight import ActivatedPreparationAuthority, PreparationReceipt
from tools.phase4_v2.queue import (
    GitHubTreeGateway,
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
from tools.phase4_v2.reconciliation import (
    PackageSurface,
    derive_authenticated_final_ir_package_surface,
    reconcile,
)
from tools.phase4_v2.validator import validate_report_bundle


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
    packages: dict[str, AuthenticatedSyntheticPackage]
    audit_receipts: dict[str, TrustedPackageAuditReceipt]
    package_surfaces: dict[str, PackageSurface]
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
    preparation_receipt: PreparationReceipt
    preparation_authority: ActivatedPreparationAuthority
    inventory_envelope: AuthenticatedTargetInventoryEnvelope
    application_roots: tuple[ApplicationRoot, ...]
    extractor: ExtractorCapability
    source_registry: AuthenticatedSourceReportRegistry
    exact_reuse_receipts: tuple[AuthenticatedExactReuseProvenance, ...]


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
    gateway_backend = _Gateway()
    targets = (
        TrackerTarget("issues/436.md", TrackerFormat.MARKDOWN),
        TrackerTarget("public/queue.html", TrackerFormat.HTML),
    )
    publication_config = TrackerPublicationConfig(
        gateway_backend.repository, gateway_backend.branch, targets
    )
    gateway = GitHubTreeGateway(
        publication_config.repository, publication_config.branch
    )
    with (
        _protected_stage_authorities() as (keys, authorities),
        protected_fixture_trust(root / "fixture-trust") as trust,
        patch.object(
            fanout_module,
            "_load_protected_publication_config_sha256",
            return_value=publication_config.sha256,
        ),
        patch.object(
            GitHubTreeGateway,
            "read",
            lambda _self, paths: gateway_backend.read(paths),
        ),
        patch.object(
            GitHubTreeGateway,
            "compare_and_replace",
            lambda _self, **values: gateway_backend.compare_and_replace(**values),
        ),
    ):
        return _run_synthetic_acceptance(
            root,
            config,
            keys,
            authorities,
            trust,
            gateway,
            publication_config,
        )


def _run_synthetic_acceptance(
    root: Path,
    config: SyntheticAcceptanceConfig,
    keys: dict[str, Ed25519PrivateKey],
    authorities: dict[str, ActivatedStageAuthority],
    trust: SyntheticTrust,
    gateway: GitHubTreeGateway,
    publication_config: TrackerPublicationConfig,
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
    gateway: GitHubTreeGateway,
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
        authenticated_package = state.packages[package.package_ref_id]
        final_data, trusted_receipts = _authorized_final_ir(
            authenticated_package.source_registry
        )
        final_json = _canonical(final_data) + b"\n"
        final_document = loads_final_ir(final_json, trusted_receipts=trusted_receipts)
        surface = derive_authenticated_final_ir_package_surface(
            package_ref=authenticated_package.package_ref,
            execution_plan=authenticated_package.frozen_plan,
            queue=queue,
            validated_output=authenticated_package.output,
            execution_envelope=authenticated_package.execution_envelope,
            report_bytes=authenticated_package.report_bytes,
            report_manifest_bytes=authenticated_package.report_manifest_bytes,
            document=final_document,
            canonical_json=dumps_final_ir(final_document),
            markdown=render_final_ir_markdown(final_document),
            source_registry=authenticated_package.source_registry,
            exact_reuse_receipts=authenticated_package.exact_reuse_receipts,
        ).package_surface
        receipt = load_package_audit_receipt(
            _signed(
                "audit",
                {
                    "accepted": True,
                    "analysis_completion_revision": analysis.completion_revision,
                    "analysis_completion_sha256": analysis.output_digest,
                    "package_surface_sha256": surface.content_id,
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
        finish_package_audit(
            queue,
            lease,
            graph=graph,
            authority=authorities["audit"],
            receipt=receipt,
        )
        state.audit_receipts[package.package_ref_id] = receipt
        state.package_surfaces[package.package_ref_id] = surface
        return
    if unit.kind == WorkStage.CLUSTER_RECONCILIATION.value:
        authenticated_input = build_authenticated_reconciliation_input(
            queue=queue,
            graph=graph,
            authority=authorities["audit"],
            package_surfaces=tuple(state.package_surfaces.values()),
            audit_receipts=tuple(state.audit_receipts.values()),
        )
        reconciliation_result = reconcile(authenticated_input.reconciliation_input)
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
                        [package_id, item.receipt_sha256]
                        for package_id, item in sorted(state.audit_receipts.items())
                    ],
                    "reconciliation_result_sha256": reconciliation_result.content_id,
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
        completed_packages = tuple(
            complete_authenticated_synthetic_package_inputs(
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
            tuple(item.frozen_plan for item in completed_packages),
            audit_authority=authorities["audit"],
            reconciliation_authority=authorities["reconciliation"],
            implementation_authority=authorities["implementation"],
            publication_authority=authorities["publication"],
        )
        result[cluster] = _ClusterState(
            graph,
            {item.package_ref.content_id: item for item in completed_packages},
            {},
            {},
        )
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
    preparation, inventory, envelope = _authenticate_synthetic_inputs(
        queue, partial, trust, active_capabilities
    )
    source_registry = build_raw_backed_source_registry(partial, envelope, trust)

    inputs = finish_synthetic_package_inputs(
        partial,
        preparation=preparation,
        target_inventory=inventory,
        source_registry=source_registry,
    )
    return _finish_authenticated_package(
        queue,
        partial,
        inputs,
        trust,
        active_capabilities,
        inventory_envelope=envelope,
        source_registry=source_registry,
        exact_reuse_receipts=(),
    )


def complete_authenticated_exact_reuse_synthetic_package_inputs(
    queue: Queue,
    partial: IncompleteSyntheticPackage,
    source_package: AuthenticatedSyntheticPackage,
    trust: SyntheticTrust,
    exact_trust: SyntheticExactReuseTrust,
    active_capabilities: set[tuple[str, str, str]],
    *,
    include_full_root: bool,
) -> AuthenticatedSyntheticPackage:
    """Complete one genuine all-reuse or mixed FULL+EXACT_REUSE package."""

    expected_roots = 2 if include_full_root else 1
    if len(partial.application_roots) != expected_roots:
        raise ValueError("synthetic target root count does not match the requested route mix")
    preparation, inventory, inventory_envelope = _authenticate_synthetic_inputs(
        queue, partial, trust, active_capabilities
    )
    source = source_package.source_registry.entries[0]
    prerequisite_source = build_authenticated_source_report_registry(
        (
            (
                source_package.package_ref,
                load_authenticated_validator_envelope(
                    source_package.package_ref.validator_envelope_bytes,
                    authority=source_package.package_ref.validator_authority,
                ),
            ),
        )
    ).entries[0]
    source_root = source_package.application_roots[0]
    target_root = partial.application_roots[0]
    source_raw = next(
        item for item in source.raw_sources if item.target_root_id == source_root.content_id
    )
    decision, proof = route_application_root(
        target_root,
        (source_root,),
        pins=RoutingPins(),
        trusted_direct_audits={source_root.content_id: source_raw.receipt_sha256},
        trusted_inventory_receipts={
            source_root.content_id: source_package.inventory_envelope.receipt_sha256,
            target_root.content_id: inventory_envelope.receipt_sha256,
        },
    )
    if proof is None:
        raise RuntimeError("synthetic exact route did not produce an identity proof")
    pipeline = CapabilityPin(
        EXACT_REUSE_PIPELINE_CAPABILITY,
        EQUIVALENCE_SCHEMA_REVISION,
        _digest("synthetic-equivalence-pipeline"),
    )
    prerequisite_kwargs = {
        "source": prerequisite_source,
        "source_raw": source_raw,
        "source_inventory": source_package.inventory_envelope,
        "source_preparation_receipt": source_package.preparation_receipt,
        "source_preparation_authority": source_package.preparation_authority,
        "source_root": source_root,
        "target_inventory": inventory_envelope,
        "target_root": target_root,
        "extractor": partial.extractor,
        "proof": proof,
        "decision": decision,
        "equivalence_pipeline": pipeline,
        "authority": exact_trust.authority,
    }
    prerequisite_payload = exact_reuse_prerequisite_payload(**prerequisite_kwargs)
    prerequisite_bytes = exact_reuse_prerequisite_envelope_payload(
        prerequisite_payload,
        signature=exact_trust.key.sign(
            exact_reuse_prerequisite_signing_bytes(prerequisite_payload)
        ).hex(),
    )
    prerequisite = load_authenticated_exact_reuse_prerequisite(
        prerequisite_bytes, **prerequisite_kwargs
    )
    for pin in (exact_reuse_authority_capability(exact_trust.authority), pipeline):
        activate_synthetic_capability(queue, pin, active_capabilities)
    materialize_exact_reuse_prerequisites(queue, prerequisite)
    for kind in (
        EXACT_REUSE_SEMANTIC_ROOT_QUEUE_KIND,
        EXACT_REUSE_LEDGER_DECISION_QUEUE_KIND,
        EXACT_REUSE_DIRECT_AUDIT_QUEUE_KIND,
    ):
        lease = _claim_required(queue, kind)
        finish_exact_reuse_prerequisite(queue, lease, receipt=prerequisite)
    exact_root_plan = build_exact_reuse_root_plan(
        semantic_root_audit_from_authenticated_prerequisite(prerequisite)
    )

    source_registry = source_package.source_registry
    root_plans: list[RootExecutionPlan] = [exact_root_plan]
    if include_full_root:
        target_registry = build_raw_backed_source_registry(
            partial, inventory_envelope, trust, root_indexes=(1,)
        )
        source_registry = merge_raw_backed_source_registries(
            source_package.source_registry, target_registry
        )
        target_source = next(
            item
            for item in target_registry.entries
            if item.package_ref.content_id == partial.package_ref.content_id
        )
        target_attestation = target_source.report.validated_root_evidence[0]
        full_root = partial.application_roots[1]
        if target_attestation.target_root_id != full_root.content_id:
            raise RuntimeError("synthetic FULL attestation targets the wrong root")
        root_plans.append(
            FullAnalysisRootPlan(
                full_root.content_id,
                full_root.occurrence_identity_sha256,
                "synthetic mixed-route analysis",
                (CapabilityPin("apktool", "pipeline-v1", partial.tool_sha256),),
                (source_report_root_completion(target_source, target_attestation),),
            )
        )
    inputs = finish_synthetic_package_inputs(
        partial,
        preparation=preparation,
        target_inventory=inventory,
        source_registry=source_registry,
        root_plans=tuple(root_plans),
    )
    frozen = freeze_package_execution_plan(inputs.execution_plan)
    exact_root_data = next(
        item for item in json.loads(frozen.canonical_bytes)["root_plans"]
        if item["route"] == "EXACT_REUSE"
    )
    root_plan_sha256 = hashlib.sha256(
        json.dumps(exact_root_data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    source_attestation = source.report.validated_root_evidence[0]
    unsigned_provenance = exact_reuse_provenance_payload(
        authority=trust.validator_authority,
        source=source,
        source_root=source_attestation,
        target_root_id=target_root.content_id,
        target_occurrence_identity_sha256=target_root.occurrence_identity_sha256,
        byte_identity_proof_id=proof.content_id,
        byte_identity_proof=proof,
        ledger_decision=decision,
        ledger_decision_completion_sha256=decision.content_id,
        root_plan_sha256=root_plan_sha256,
        signature="0" * 128,
    )
    provenance_payload = json.loads(unsigned_provenance)["payload"]
    provenance_bytes = exact_reuse_provenance_payload(
        authority=trust.validator_authority,
        source=source,
        source_root=source_attestation,
        target_root_id=target_root.content_id,
        target_occurrence_identity_sha256=target_root.occurrence_identity_sha256,
        byte_identity_proof_id=proof.content_id,
        byte_identity_proof=proof,
        ledger_decision=decision,
        ledger_decision_completion_sha256=decision.content_id,
        root_plan_sha256=root_plan_sha256,
        signature=trust.validator_key.sign(
            exact_reuse_provenance_signing_bytes(provenance_payload)
        ).hex(),
    )
    provenance = load_authenticated_exact_reuse_provenance(
        provenance_bytes,
        authority=trust.validator_authority,
        registry=source_registry,
    )
    return _finish_authenticated_package(
        queue,
        partial,
        inputs,
        trust,
        active_capabilities,
        inventory_envelope=inventory_envelope,
        source_registry=source_registry,
        exact_reuse_receipts=(provenance,),
    )


def _authenticate_synthetic_inputs(
    queue: Queue,
    partial: IncompleteSyntheticPackage,
    trust: SyntheticTrust,
    active_capabilities: set[tuple[str, str, str]],
) -> tuple[
    PreparationPlanBinding,
    AcceptedTargetRootInventory,
    AuthenticatedTargetInventoryEnvelope,
]:
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

    extractor = partial.extractor
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
    return preparation, inventory, envelope


def _finish_authenticated_package(
    queue: Queue,
    partial: IncompleteSyntheticPackage,
    inputs: SyntheticPackageInputs,
    trust: SyntheticTrust,
    active_capabilities: set[tuple[str, str, str]],
    *,
    inventory_envelope: AuthenticatedTargetInventoryEnvelope,
    source_registry: AuthenticatedSourceReportRegistry,
    exact_reuse_receipts: tuple[AuthenticatedExactReuseProvenance, ...],
) -> AuthenticatedSyntheticPackage:
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
    if not receipt.accepted:
        raise RuntimeError(f"synthetic package report failed: {receipt.diagnostics}")
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
        inputs.preparation_receipt,
        inputs.preparation_authority,
        inventory_envelope,
        partial.application_roots,
        partial.extractor,
        source_registry,
        exact_reuse_receipts,
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
