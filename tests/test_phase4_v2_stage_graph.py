"""Synthetic proofs for the content-bound cluster stage graph."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from unittest.mock import patch

import pytest

import tools.phase4_v2.queue.core as queue_core
from tools.phase4_v2.equivalence.plan import (
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    package_queue_unit_id,
)
from tools.phase4_v2.orchestration import (
    CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
    CLUSTER_RECONCILIATION_COMPLETION_REVISION,
    PACKAGE_AUDIT_COMPLETION_REVISION,
    TRACKER_PUBLICATION_COMPLETION_REVISION,
    ClusterGraphPlan,
    PackageAnalysisUnit,
    WorkStage,
    cluster_implementation_unit_id,
    cluster_reconciliation_unit_id,
    finish_cluster_implementation,
    finish_cluster_reconciliation,
    finish_package_audit,
    finish_tracker_publication,
    materialize_cluster_graph,
    package_audit_unit_id,
    tracker_publication_unit_id,
)
from tools.phase4_v2.queue import (
    ORCHESTRATION_PACKAGE_ANALYSIS_KIND,
    CapabilityPin,
    Lease,
    Queue,
    QueueConflictError,
    TerminalOutcome,
    WorkUnitSnapshot,
    WorkUnitStatus,
)
from tools.phase4_v2.queue.cli import main as queue_main


@dataclass(frozen=True, slots=True)
class _AuditReceipt:
    revision: str
    graph_sha256: str
    cluster_id: str
    package_ref_id: str
    stage_input_sha256: str
    analysis_completion_revision: str
    analysis_completion_sha256: str
    accepted: bool = True
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ReconciliationReceipt:
    revision: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    package_audit_receipts: tuple[tuple[str, str], ...]
    reconciliation_result_sha256: str
    completeness_receipt_sha256: str
    disposition_ledger_sha256: str
    accepted: bool = True
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ImplementationReceipt:
    revision: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    reconciliation_receipt_sha256: str
    disposition_ledger_sha256: str
    implementation_output_sha256: str
    accepted: bool = True
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PublicationReceipt:
    revision: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    implementation_receipt_sha256: str
    queue_generation_sha256: str
    document_set_sha256: str
    publication_config_sha256: str
    accepted: bool = True
    diagnostics: tuple[str, ...] = ()


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    result = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    result.initialize()
    return result


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pin(name: str) -> CapabilityPin:
    return CapabilityPin(name, f"{name}-v1", _digest(name))


def _graph(cluster: str, package_names: tuple[str, ...]) -> ClusterGraphPlan:
    packages = tuple(
        sorted(
            (
                PackageAnalysisUnit(
                    package_ref_id=_digest(f"package:{name}"),
                    unit_id=package_queue_unit_id(_digest(f"package:{name}")),
                    input_sha256=_digest(f"input:{name}"),
                    capability_pins=(_pin(f"analysis-{cluster}-{name}"),),
                    dependency_pins=(),
                )
                for name in package_names
            ),
            key=lambda item: item.package_ref_id,
        )
    )
    return ClusterGraphPlan(
        cluster_id=cluster,
        packages=packages,
        audit_capability_pins=(_pin(f"audit-{cluster}"),),
        reconciliation_capability_pins=(_pin(f"reconciliation-{cluster}"),),
        implementation_capability_pins=(_pin(f"implementation-{cluster}"),),
        publication_capability_pins=(_pin(f"publication-{cluster}"),),
    )


def _activate_graph(queue: Queue, graph: ClusterGraphPlan) -> None:
    pins = {pin.capability: pin for package in graph.packages for pin in package.capability_pins}
    pins.update(
        {
            pin.capability: pin
            for pin in (
                *graph.audit_capability_pins,
                *graph.reconciliation_capability_pins,
                *graph.implementation_capability_pins,
                *graph.publication_capability_pins,
            )
        }
    )
    for pin in pins.values():
        queue.register_capability(pin.capability, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.capability, pin.revision, pin.digest)


def _claim(queue: Queue, stage: WorkStage, owner: str) -> Lease:
    lease = queue.claim(owner, allowed_kinds=(stage.value,))
    assert lease is not None
    return lease


def _unit(queue: Queue, unit_id: str) -> WorkUnitSnapshot:
    return next(item for item in queue.snapshot().units if item.unit_id == unit_id)


def _complete_analysis_fixture(queue: Queue, lease: Lease) -> None:
    """Stand in only for the separately tested validated-package-output adapter."""
    original = queue_core._requires_trusted_completion_adapter
    with patch.object(
        queue_core,
        "_requires_trusted_completion_adapter",
        side_effect=lambda unit_id, kind: (
            False if unit_id == lease.unit_id else original(unit_id, kind)
        ),
    ):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            expected_input_digest=lease.input_digest,
            output_digest=_digest(f"analysis-output:{lease.unit_id}"),
            completion_revision=VALIDATED_PACKAGE_OUTPUT_REVISION,
        )


def _audit_receipt(queue: Queue, graph: ClusterGraphPlan, lease: Lease) -> _AuditReceipt:
    package = next(
        item
        for item in graph.packages
        if package_audit_unit_id(graph, item.package_ref_id) == lease.unit_id
    )
    analysis = _unit(queue, package.unit_id)
    assert analysis.completion_revision is not None
    assert analysis.output_digest is not None
    return _AuditReceipt(
        revision=PACKAGE_AUDIT_COMPLETION_REVISION,
        graph_sha256=graph.content_id,
        cluster_id=graph.cluster_id,
        package_ref_id=package.package_ref_id,
        stage_input_sha256=lease.input_digest,
        analysis_completion_revision=analysis.completion_revision,
        analysis_completion_sha256=analysis.output_digest,
    )


def test_progressive_graph_and_typed_receipts_bind_every_parent(queue: Queue) -> None:
    graph = _graph("cluster-011", ("alpha", "beta"))
    _activate_graph(queue, graph)

    first = materialize_cluster_graph(queue, graph)
    assert first.materialized_units == first.analysis_units
    assert first.reconciliation_unit not in first.materialized_units
    assert first.implementation_unit not in first.materialized_units

    _complete_analysis_fixture(queue, _claim(queue, WorkStage.PACKAGE_ANALYSIS, "analysis-1"))
    partial = materialize_cluster_graph(queue, graph)
    assert len(partial.audit_units) == 2
    assert len(set(partial.materialized_units) & set(partial.audit_units)) == 1
    assert partial.reconciliation_unit not in partial.materialized_units

    _complete_analysis_fixture(queue, _claim(queue, WorkStage.PACKAGE_ANALYSIS, "analysis-2"))
    audits_ready = materialize_cluster_graph(queue, graph)
    assert set(audits_ready.audit_units) <= set(audits_ready.materialized_units)

    audit_completions: dict[str, str] = {}
    first_audit = _claim(queue, WorkStage.PACKAGE_AUDIT, "audit-1")
    with pytest.raises(QueueConflictError, match="trusted publication adapter"):
        queue.finish_accepted_if_input_matches(
            first_audit,
            expected_input_digest=first_audit.input_digest,
            output_digest=_digest("generic-bypass"),
            completion_revision=PACKAGE_AUDIT_COMPLETION_REVISION,
        )
    first_receipt = _audit_receipt(queue, graph, first_audit)
    first_result = finish_package_audit(queue, first_audit, graph=graph, receipt=first_receipt)
    audit_completions[first_receipt.package_ref_id] = first_result.receipt_sha256
    assert (
        materialize_cluster_graph(queue, graph).reconciliation_unit
        not in materialize_cluster_graph(queue, graph).materialized_units
    )

    second_audit = _claim(queue, WorkStage.PACKAGE_AUDIT, "audit-2")
    second_receipt = _audit_receipt(queue, graph, second_audit)
    second_result = finish_package_audit(queue, second_audit, graph=graph, receipt=second_receipt)
    audit_completions[second_receipt.package_ref_id] = second_result.receipt_sha256

    reconciled_graph = materialize_cluster_graph(queue, graph)
    assert reconciled_graph.reconciliation_unit in reconciled_graph.materialized_units
    assert reconciled_graph.implementation_unit not in reconciled_graph.materialized_units
    reconciliation_lease = _claim(queue, WorkStage.CLUSTER_RECONCILIATION, "reconciliation")
    reconciliation_receipt = _ReconciliationReceipt(
        revision=CLUSTER_RECONCILIATION_COMPLETION_REVISION,
        graph_sha256=graph.content_id,
        cluster_id=graph.cluster_id,
        stage_input_sha256=reconciliation_lease.input_digest,
        package_audit_receipts=tuple(sorted(audit_completions.items())),
        reconciliation_result_sha256=_digest("reconciliation-result"),
        completeness_receipt_sha256=_digest("all-members-complete"),
        disposition_ledger_sha256=_digest("disposition-ledger"),
    )
    with pytest.raises(QueueConflictError, match="all package audits"):
        finish_cluster_reconciliation(
            queue,
            reconciliation_lease,
            graph=graph,
            receipt=replace(reconciliation_receipt, package_audit_receipts=()),
        )
    reconciliation_result = finish_cluster_reconciliation(
        queue, reconciliation_lease, graph=graph, receipt=reconciliation_receipt
    )

    implemented_graph = materialize_cluster_graph(queue, graph)
    assert implemented_graph.implementation_unit in implemented_graph.materialized_units
    assert implemented_graph.publication_unit not in implemented_graph.materialized_units
    implementation_lease = _claim(queue, WorkStage.CLUSTER_IMPLEMENTATION, "implementation")
    implementation_receipt = _ImplementationReceipt(
        revision=CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
        graph_sha256=graph.content_id,
        cluster_id=graph.cluster_id,
        stage_input_sha256=implementation_lease.input_digest,
        reconciliation_receipt_sha256=reconciliation_result.receipt_sha256,
        disposition_ledger_sha256=reconciliation_receipt.disposition_ledger_sha256,
        implementation_output_sha256=_digest("implementation-output"),
    )
    with pytest.raises(QueueConflictError, match="accepted ledger"):
        finish_cluster_implementation(
            queue,
            implementation_lease,
            graph=graph,
            reconciliation_receipt=reconciliation_receipt,
            receipt=replace(
                implementation_receipt,
                disposition_ledger_sha256=_digest("different-ledger"),
            ),
        )
    implementation_result = finish_cluster_implementation(
        queue,
        implementation_lease,
        graph=graph,
        reconciliation_receipt=reconciliation_receipt,
        receipt=implementation_receipt,
    )

    publication_graph = materialize_cluster_graph(queue, graph)
    assert publication_graph.publication_unit in publication_graph.materialized_units
    publication_lease = _claim(queue, WorkStage.TRACKER_PUBLICATION, "publication")
    publication_receipt = _PublicationReceipt(
        revision=TRACKER_PUBLICATION_COMPLETION_REVISION,
        graph_sha256=graph.content_id,
        cluster_id=graph.cluster_id,
        stage_input_sha256=publication_lease.input_digest,
        implementation_receipt_sha256=implementation_result.receipt_sha256,
        queue_generation_sha256=queue.snapshot().generation_id,
        document_set_sha256=_digest("document-set"),
        publication_config_sha256=_digest("publication-config"),
    )
    finish_tracker_publication(
        queue,
        publication_lease,
        graph=graph,
        implementation_receipt=implementation_receipt,
        reconciliation_receipt=reconciliation_receipt,
        receipt=publication_receipt,
    )
    assert all(unit.status is WorkUnitStatus.COMPLETED for unit in queue.snapshot().units)


def test_graph_drift_conflicts_with_stable_semantic_unit_ids(queue: Queue) -> None:
    graph = _graph("cluster-drift", ("alpha",))
    _activate_graph(queue, graph)
    materialize_cluster_graph(queue, graph)
    _complete_analysis_fixture(queue, _claim(queue, WorkStage.PACKAGE_ANALYSIS, "analysis"))
    materialize_cluster_graph(queue, graph)

    drifted = replace(graph, audit_capability_pins=(_pin("drifted-audit"),))
    assert cluster_reconciliation_unit_id(drifted) == cluster_reconciliation_unit_id(graph)
    assert cluster_implementation_unit_id(drifted) == cluster_implementation_unit_id(graph)
    assert tracker_publication_unit_id(drifted) == tracker_publication_unit_id(graph)
    with pytest.raises(QueueConflictError, match="materialized work unit changed"):
        materialize_cluster_graph(queue, drifted)


def test_graph_rejects_unsupported_audit_completion_revision(queue: Queue) -> None:
    graph = _graph("cluster-corrupt-audit", ("alpha",))
    _activate_graph(queue, graph)
    materialize_cluster_graph(queue, graph)
    _complete_analysis_fixture(queue, _claim(queue, WorkStage.PACKAGE_ANALYSIS, "analysis"))
    materialize_cluster_graph(queue, graph)
    lease = _claim(queue, WorkStage.PACKAGE_AUDIT, "audit")
    queue._finish_trusted_orchestration_stage(
        lease,
        kind=WorkStage.PACKAGE_AUDIT.value,
        cluster_id=graph.cluster_id,
        expected_input_digest=lease.input_digest,
        output_digest=_digest("invalid-audit-receipt"),
        completion_revision="unsupported-audit-revision",
    )

    with pytest.raises(QueueConflictError, match="audit completion revision"):
        materialize_cluster_graph(queue, graph)


def test_receipt_transplant_and_replay_are_rejected(queue: Queue) -> None:
    first_graph = _graph("cluster-first", ("alpha",))
    second_graph = _graph("cluster-second", ("beta",))
    for graph in (first_graph, second_graph):
        _activate_graph(queue, graph)
        materialize_cluster_graph(queue, graph)
    for owner in ("analysis-1", "analysis-2"):
        _complete_analysis_fixture(queue, _claim(queue, WorkStage.PACKAGE_ANALYSIS, owner))
    for graph in (first_graph, second_graph):
        materialize_cluster_graph(queue, graph)

    first_lease = _claim(queue, WorkStage.PACKAGE_AUDIT, "audit-first")
    second_lease = _claim(queue, WorkStage.PACKAGE_AUDIT, "audit-second")
    leases = {lease.unit_id: lease for lease in (first_lease, second_lease)}
    first_lease = leases[package_audit_unit_id(first_graph, first_graph.packages[0].package_ref_id)]
    second_lease = leases[
        package_audit_unit_id(second_graph, second_graph.packages[0].package_ref_id)
    ]
    first_receipt = _audit_receipt(queue, first_graph, first_lease)
    with pytest.raises(QueueConflictError, match="another cluster"):
        finish_package_audit(queue, second_lease, graph=second_graph, receipt=first_receipt)
    finish_package_audit(queue, first_lease, graph=first_graph, receipt=first_receipt)
    with pytest.raises(QueueConflictError, match="stage input"):
        finish_package_audit(queue, second_lease, graph=first_graph, receipt=first_receipt)
    second_receipt = _audit_receipt(queue, second_graph, second_lease)
    with pytest.raises(QueueConflictError, match="stage input"):
        finish_package_audit(
            queue,
            second_lease,
            graph=second_graph,
            receipt=replace(second_receipt, stage_input_sha256=_digest("drift")),
        )


def test_generic_cli_cannot_accept_reserved_semantic_stage(
    queue: Queue, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue.enqueue(
        "audit-cli",
        kind=WorkStage.PACKAGE_AUDIT.value,
        cluster_id="cluster-cli",
        input_digest=_digest("cli-input"),
    )
    lease = _claim(queue, WorkStage.PACKAGE_AUDIT, "cli-worker")
    lease_file = tmp_path / "lease.json"
    payload = asdict(lease)
    payload["workspace"] = str(lease.workspace)
    lease_file.write_text(json.dumps(payload), encoding="utf-8")
    result = queue_main(
        [
            "--database",
            str(queue.database),
            "--attempts-root",
            str(queue.attempts_root),
            "finish",
            "--lease-file",
            str(lease_file),
            "--outcome",
            "ACCEPTED",
            "--expected-input-digest",
            lease.input_digest,
            "--output-digest",
            _digest("generic-output"),
            "--completion-revision",
            "generic-v1",
        ]
    )
    assert result == 2
    assert "typed completion adapter" in capsys.readouterr().err
    assert queue.status(lease.unit_id) is WorkUnitStatus.LEASED


def test_package_analysis_kind_remains_reserved() -> None:
    assert WorkStage.PACKAGE_ANALYSIS.value == ORCHESTRATION_PACKAGE_ANALYSIS_KIND
