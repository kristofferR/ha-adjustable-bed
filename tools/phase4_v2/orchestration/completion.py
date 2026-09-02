"""Trusted, content-bound completion adapters for semantic cluster stages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from tools.phase4_v2.equivalence.plan import VALIDATED_PACKAGE_OUTPUT_REVISION
from tools.phase4_v2.queue import (
    ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
    ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
    ORCHESTRATION_PACKAGE_AUDIT_KIND,
    ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    CompletionDependencyPin,
    InputCheckedFinishResult,
    Lease,
    Queue,
    QueueConflictError,
)

from .graph import (
    CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
    CLUSTER_RECONCILIATION_COMPLETION_REVISION,
    PACKAGE_AUDIT_COMPLETION_REVISION,
    TRACKER_PUBLICATION_COMPLETION_REVISION,
    ClusterGraphPlan,
    cluster_implementation_unit_id,
    cluster_reconciliation_unit_id,
    completion_pin,
    completion_pins,
    package_audit_unit_id,
    stage_input_sha256,
    tracker_publication_unit_id,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_MAX_DIAGNOSTICS = 4_096
_MAX_PACKAGES = 250


class TrustedPackageAuditReceipt(Protocol):
    """Externally validated semantic-audit decision consumed by the queue."""

    revision: str
    graph_sha256: str
    cluster_id: str
    package_ref_id: str
    stage_input_sha256: str
    analysis_completion_revision: str
    analysis_completion_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]


class TrustedReconciliationReceipt(Protocol):
    """Externally validated complete reconciliation and completeness decision."""

    revision: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    package_audit_receipts: tuple[tuple[str, str], ...]
    reconciliation_result_sha256: str
    completeness_receipt_sha256: str
    disposition_ledger_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]


class TrustedImplementationReceipt(Protocol):
    """Implementation result bound to one accepted disposition ledger."""

    revision: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    reconciliation_receipt_sha256: str
    disposition_ledger_sha256: str
    implementation_output_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]


class TrustedPublicationReceipt(Protocol):
    """Tracker publication result bound to the implemented cluster."""

    revision: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    implementation_receipt_sha256: str
    queue_generation_sha256: str
    document_set_sha256: str
    publication_config_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageCompletion:
    """Canonical receipt identity and its atomic queue result."""

    receipt_sha256: str
    queue_result: InputCheckedFinishResult


def finish_package_audit(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    receipt: TrustedPackageAuditReceipt,
) -> StageCompletion:
    """Accept one package audit only against its exact analysis completion."""

    package_ref_id = _text(receipt.package_ref_id, "package audit package", digest=True)
    packages = {item.package_ref_id: item for item in graph.packages}
    package = packages.get(package_ref_id)
    if package is None:
        raise QueueConflictError("package audit receipt belongs to another cluster")
    analysis = completion_pin(queue.snapshot(), package.unit_id)
    if analysis is None or analysis.revision != VALIDATED_PACKAGE_OUTPUT_REVISION:
        raise QueueConflictError("package audit requires accepted package analysis")
    dependencies = (analysis,)
    expected_input = stage_input_sha256(
        graph,
        stage="audit",
        subject=package_ref_id,
        capability_pins=graph.audit_capability_pins,
        dependency_pins=dependencies,
    )
    diagnostics = _diagnostics(receipt.diagnostics, "package audit diagnostics")
    payload = {
        "accepted": _accepted(receipt.accepted, diagnostics, "package audit"),
        "analysis_completion_revision": _revision(
            receipt.analysis_completion_revision, "analysis completion revision"
        ),
        "analysis_completion_sha256": _text(
            receipt.analysis_completion_sha256, "analysis completion", digest=True
        ),
        "cluster_id": _token(receipt.cluster_id, "package audit cluster"),
        "diagnostics": list(diagnostics),
        "graph_sha256": _text(receipt.graph_sha256, "package audit graph", digest=True),
        "package_ref_id": package_ref_id,
        "revision": _exact_revision(
            receipt.revision, PACKAGE_AUDIT_COMPLETION_REVISION, "package audit"
        ),
        "stage_input_sha256": _text(receipt.stage_input_sha256, "package audit input", digest=True),
    }
    if (
        payload["graph_sha256"] != graph.content_id
        or payload["cluster_id"] != graph.cluster_id
        or payload["stage_input_sha256"] != expected_input
        or payload["analysis_completion_revision"] != analysis.revision
        or payload["analysis_completion_sha256"] != analysis.digest
        or lease.unit_id != package_audit_unit_id(graph, package_ref_id)
    ):
        raise QueueConflictError("package audit receipt does not bind its stage input")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_PACKAGE_AUDIT_KIND,
        expected_input,
        PACKAGE_AUDIT_COMPLETION_REVISION,
        "phase4-v2:package-audit-receipt",
        payload,
    )


def finish_cluster_reconciliation(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    receipt: TrustedReconciliationReceipt,
) -> StageCompletion:
    """Accept reconciliation only after every exact package audit is accepted."""

    payload, expected_input = _reconciliation_payload(queue, graph, receipt)
    if lease.unit_id != cluster_reconciliation_unit_id(graph):
        raise QueueConflictError("reconciliation receipt belongs to another stage")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
        expected_input,
        CLUSTER_RECONCILIATION_COMPLETION_REVISION,
        "phase4-v2:cluster-reconciliation-receipt",
        payload,
    )


def finish_cluster_implementation(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    reconciliation_receipt: TrustedReconciliationReceipt,
    receipt: TrustedImplementationReceipt,
) -> StageCompletion:
    """Accept implementation only for the exact reconciled disposition ledger."""

    payload, expected_input = _implementation_payload(
        queue,
        graph,
        reconciliation_receipt,
        receipt,
    )
    if lease.unit_id != cluster_implementation_unit_id(graph):
        raise QueueConflictError("implementation receipt belongs to another stage")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
        expected_input,
        CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
        "phase4-v2:cluster-implementation-receipt",
        payload,
    )


def finish_tracker_publication(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    implementation_receipt: TrustedImplementationReceipt,
    reconciliation_receipt: TrustedReconciliationReceipt,
    receipt: TrustedPublicationReceipt,
) -> StageCompletion:
    """Accept publication only for the exact implemented cluster receipt."""

    completions = completion_pins(queue.snapshot())
    implementation = _required_completion(
        completions, cluster_implementation_unit_id(graph), "tracker publication"
    )
    implementation_payload, _ = _implementation_payload(
        queue,
        graph,
        reconciliation_receipt,
        implementation_receipt,
        completions=completions,
    )
    implementation_sha256 = _content_id(
        "phase4-v2:cluster-implementation-receipt", implementation_payload
    )
    if (
        implementation.revision != CLUSTER_IMPLEMENTATION_COMPLETION_REVISION
        or implementation.digest != implementation_sha256
    ):
        raise QueueConflictError("publication received a different implementation receipt")
    dependencies = (implementation,)
    expected_input = stage_input_sha256(
        graph,
        stage="publication",
        subject=graph.cluster_id,
        capability_pins=graph.publication_capability_pins,
        dependency_pins=dependencies,
    )
    diagnostics = _diagnostics(receipt.diagnostics, "publication diagnostics")
    payload = {
        "accepted": _accepted(receipt.accepted, diagnostics, "publication"),
        "cluster_id": _token(receipt.cluster_id, "publication cluster"),
        "diagnostics": list(diagnostics),
        "document_set_sha256": _text(
            receipt.document_set_sha256, "published document set", digest=True
        ),
        "graph_sha256": _text(receipt.graph_sha256, "publication graph", digest=True),
        "implementation_receipt_sha256": _text(
            receipt.implementation_receipt_sha256,
            "publication implementation receipt",
            digest=True,
        ),
        "publication_config_sha256": _text(
            receipt.publication_config_sha256, "publication config", digest=True
        ),
        "queue_generation_sha256": _text(
            receipt.queue_generation_sha256, "published queue generation", digest=True
        ),
        "revision": _exact_revision(
            receipt.revision,
            TRACKER_PUBLICATION_COMPLETION_REVISION,
            "publication",
        ),
        "stage_input_sha256": _text(receipt.stage_input_sha256, "publication input", digest=True),
    }
    if (
        payload["graph_sha256"] != graph.content_id
        or payload["cluster_id"] != graph.cluster_id
        or payload["stage_input_sha256"] != expected_input
        or payload["implementation_receipt_sha256"] != implementation_sha256
        or lease.unit_id != tracker_publication_unit_id(graph)
    ):
        raise QueueConflictError("publication receipt does not bind the implemented cluster")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_TRACKER_PUBLICATION_KIND,
        expected_input,
        TRACKER_PUBLICATION_COMPLETION_REVISION,
        "phase4-v2:tracker-publication-receipt",
        payload,
    )


def _reconciliation_payload(
    queue: Queue,
    graph: ClusterGraphPlan,
    receipt: TrustedReconciliationReceipt,
    *,
    completions: Mapping[str, CompletionDependencyPin] | None = None,
) -> tuple[dict[str, object], str]:
    if completions is None:
        completions = completion_pins(queue.snapshot())
    audits = _all_audit_completions(completions, graph)
    expected_input = stage_input_sha256(
        graph,
        stage="reconciliation",
        subject=graph.cluster_id,
        capability_pins=graph.reconciliation_capability_pins,
        dependency_pins=_sorted_dependencies(audits),
    )
    pairs = _pairs(receipt.package_audit_receipts, "reconciliation package audit receipts")
    expected_pairs = tuple(
        sorted(
            (package.package_ref_id, audits[index].digest)
            for index, package in enumerate(graph.packages)
        )
    )
    diagnostics = _diagnostics(receipt.diagnostics, "reconciliation diagnostics")
    payload = {
        "accepted": _accepted(receipt.accepted, diagnostics, "reconciliation"),
        "cluster_id": _token(receipt.cluster_id, "reconciliation cluster"),
        "completeness_receipt_sha256": _text(
            receipt.completeness_receipt_sha256, "completeness receipt", digest=True
        ),
        "diagnostics": list(diagnostics),
        "disposition_ledger_sha256": _text(
            receipt.disposition_ledger_sha256, "disposition ledger", digest=True
        ),
        "graph_sha256": _text(receipt.graph_sha256, "reconciliation graph", digest=True),
        "package_audit_receipts": [list(item) for item in pairs],
        "reconciliation_result_sha256": _text(
            receipt.reconciliation_result_sha256, "reconciliation result", digest=True
        ),
        "revision": _exact_revision(
            receipt.revision,
            CLUSTER_RECONCILIATION_COMPLETION_REVISION,
            "reconciliation",
        ),
        "stage_input_sha256": _text(
            receipt.stage_input_sha256, "reconciliation input", digest=True
        ),
    }
    if (
        payload["graph_sha256"] != graph.content_id
        or payload["cluster_id"] != graph.cluster_id
        or payload["stage_input_sha256"] != expected_input
        or pairs != expected_pairs
    ):
        raise QueueConflictError("reconciliation receipt does not bind all package audits")
    return payload, expected_input


def _implementation_payload(
    queue: Queue,
    graph: ClusterGraphPlan,
    reconciliation_receipt: TrustedReconciliationReceipt,
    receipt: TrustedImplementationReceipt,
    *,
    completions: Mapping[str, CompletionDependencyPin] | None = None,
) -> tuple[dict[str, object], str]:
    if completions is None:
        completions = completion_pins(queue.snapshot())
    reconciliation = _required_completion(
        completions, cluster_reconciliation_unit_id(graph), "implementation receipt"
    )
    reconciliation_payload, _ = _reconciliation_payload(
        queue,
        graph,
        reconciliation_receipt,
        completions=completions,
    )
    reconciliation_sha256 = _content_id(
        "phase4-v2:cluster-reconciliation-receipt", reconciliation_payload
    )
    if (
        reconciliation.revision != CLUSTER_RECONCILIATION_COMPLETION_REVISION
        or reconciliation.digest != reconciliation_sha256
    ):
        raise QueueConflictError("implementation receipt has a different reconciliation")
    dependencies = (reconciliation,)
    expected_input = stage_input_sha256(
        graph,
        stage="implementation",
        subject=graph.cluster_id,
        capability_pins=graph.implementation_capability_pins,
        dependency_pins=dependencies,
    )
    diagnostics = _diagnostics(receipt.diagnostics, "implementation diagnostics")
    payload = {
        "accepted": _accepted(receipt.accepted, diagnostics, "implementation"),
        "cluster_id": _token(receipt.cluster_id, "implementation cluster"),
        "diagnostics": list(diagnostics),
        "disposition_ledger_sha256": _text(
            receipt.disposition_ledger_sha256, "implemented disposition ledger", digest=True
        ),
        "graph_sha256": _text(receipt.graph_sha256, "implementation graph", digest=True),
        "implementation_output_sha256": _text(
            receipt.implementation_output_sha256, "implementation output", digest=True
        ),
        "reconciliation_receipt_sha256": _text(
            receipt.reconciliation_receipt_sha256,
            "implementation reconciliation receipt",
            digest=True,
        ),
        "revision": _exact_revision(
            receipt.revision,
            CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
            "implementation",
        ),
        "stage_input_sha256": _text(
            receipt.stage_input_sha256, "implementation input", digest=True
        ),
    }
    if (
        payload["graph_sha256"] != graph.content_id
        or payload["cluster_id"] != graph.cluster_id
        or payload["stage_input_sha256"] != expected_input
        or payload["reconciliation_receipt_sha256"] != reconciliation_sha256
        or payload["disposition_ledger_sha256"]
        != reconciliation_payload["disposition_ledger_sha256"]
    ):
        raise QueueConflictError("implementation receipt does not bind the accepted ledger")
    return payload, expected_input


def _all_audit_completions(
    completions_by_unit: Mapping[str, CompletionDependencyPin],
    graph: ClusterGraphPlan,
) -> tuple[CompletionDependencyPin, ...]:
    completions: list[CompletionDependencyPin] = []
    for package in graph.packages:
        completion = completions_by_unit.get(
            package_audit_unit_id(graph, package.package_ref_id)
        )
        if completion is None or completion.revision != PACKAGE_AUDIT_COMPLETION_REVISION:
            raise QueueConflictError("reconciliation requires every accepted package audit")
        completions.append(completion)
    return tuple(completions)


def _sorted_dependencies(
    completions: tuple[CompletionDependencyPin, ...],
) -> tuple[CompletionDependencyPin, ...]:
    return tuple(sorted(completions, key=lambda item: item.parent_unit_id))


def _required_completion(
    completions: Mapping[str, CompletionDependencyPin],
    unit_id: str,
    stage: str,
) -> CompletionDependencyPin:
    completion = completions.get(unit_id)
    if completion is None:
        raise QueueConflictError(f"{stage} requires its accepted parent")
    return completion


def _finish(
    queue: Queue,
    lease: Lease,
    graph: ClusterGraphPlan,
    kind: str,
    expected_input: str,
    completion_revision: str,
    domain: str,
    payload: dict[str, object],
) -> StageCompletion:
    receipt_sha256 = _content_id(domain, payload)
    result = queue._finish_trusted_orchestration_stage(
        lease,
        kind=kind,
        cluster_id=graph.cluster_id,
        expected_input_digest=expected_input,
        output_digest=receipt_sha256,
        completion_revision=completion_revision,
    )
    return StageCompletion(receipt_sha256, result)


def _accepted(value: object, diagnostics: object, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} acceptance must be a boolean")
    items = _diagnostics(diagnostics, f"{label} diagnostics")
    if value is not True or items:
        raise QueueConflictError(f"{label} receipt is not an accepted zero-diagnostic result")
    return True


def _diagnostics(value: object, label: str) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or len(value) > _MAX_DIAGNOSTICS
        or any(type(item) is not str for item in value)
    ):
        raise ValueError(f"{label} must be an exact tuple")
    items = value
    for item in items:
        _token(item, label)
    if items != tuple(sorted(set(items))):
        raise ValueError(f"{label} must be sorted and unique")
    return items


def _pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or len(value) > _MAX_PACKAGES or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        for item in value
    ):
        raise ValueError(f"{label} must be an exact pair tuple")
    pairs = value
    for package_ref_id, digest in pairs:
        _text(package_ref_id, label, digest=True)
        _text(digest, label, digest=True)
    if pairs != tuple(sorted(set(pairs))):
        raise ValueError(f"{label} must be sorted and unique")
    if len({item[0] for item in pairs}) != len(pairs):
        raise ValueError(f"{label} contain duplicate package references")
    return pairs


def _exact_revision(value: object, expected: str, label: str) -> str:
    if value != expected:
        raise QueueConflictError(f"{label} receipt revision is unsupported")
    return expected


def _revision(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > 200 or "\0" in value:
        raise ValueError(f"{label} must be a bounded revision")
    return value


def _text(value: object, label: str, *, digest: bool = False) -> str:
    if type(value) is not str or (digest and _DIGEST.fullmatch(value) is None):
        suffix = " a lowercase SHA-256 digest" if digest else " text"
        raise ValueError(f"{label} must be{suffix}")
    return value


def _token(value: object, label: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical token")
    return value


def _content_id(domain: str, payload: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii")
        + b"\0"
        + json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
