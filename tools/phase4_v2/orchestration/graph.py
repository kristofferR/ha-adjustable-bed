"""Deterministic progressive materialization of one formal cluster graph."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field

from tools.phase4_v2.equivalence.plan import (
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    FrozenPackageExecutionPlan,
    PackagePlanStatus,
    package_queue_unit_id,
    validate_frozen_package_execution_plan,
)
from tools.phase4_v2.queue import (
    ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
    ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
    ORCHESTRATION_PACKAGE_ANALYSIS_KIND,
    ORCHESTRATION_PACKAGE_AUDIT_KIND,
    ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    CapabilityPin,
    CompletionDependencyPin,
    Queue,
    QueueConflictError,
    QueueSnapshot,
    WorkUnitStatus,
)

CLUSTER_GRAPH_REVISION = "phase4-v2-cluster-stage-graph-v1"
PACKAGE_AUDIT_COMPLETION_REVISION = "phase4-v2-package-audit-receipt-v1"
CLUSTER_RECONCILIATION_COMPLETION_REVISION = "phase4-v2-cluster-reconciliation-receipt-v1"
CLUSTER_IMPLEMENTATION_COMPLETION_REVISION = "phase4-v2-cluster-implementation-receipt-v1"
TRACKER_PUBLICATION_COMPLETION_REVISION = "phase4-v2-tracker-publication-receipt-v1"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_MAX_PACKAGES = 250
_MAX_PINS = 4_096


@dataclass(frozen=True, slots=True, init=False)
class PackageAnalysisUnit:
    """One pre-existing package plan projected into the cluster graph."""

    package_ref_id: str
    unit_id: str
    input_sha256: str
    capability_pins: tuple[CapabilityPin, ...]
    dependency_pins: tuple[CompletionDependencyPin, ...]
    _source_plan: FrozenPackageExecutionPlan = field(repr=False, compare=False)
    priority: int = 0

    def __init__(self) -> None:
        raise ValueError("package analysis units must be built from frozen execution plans")

    def _validate(self) -> None:
        source = validate_frozen_package_execution_plan(self._source_plan)
        expected_capabilities = tuple(
            CapabilityPin(pin.name, pin.revision, pin.digest)
            for pin in source.required_capabilities
        )
        expected_dependencies = tuple(
            CompletionDependencyPin(pin.parent_unit_id, pin.revision, pin.digest)
            for pin in source.required_completions
        )
        if (
            self.package_ref_id != source.target_package_ref_id
            or self.unit_id != package_queue_unit_id(source.target_package_ref_id)
            or self.input_sha256 != source.digest
            or self.capability_pins != expected_capabilities
            or self.dependency_pins != expected_dependencies
        ):
            raise ValueError("analysis unit no longer matches its frozen execution plan")
        _digest(self.package_ref_id, "package_ref_id")
        if self.unit_id != package_queue_unit_id(self.package_ref_id):
            raise ValueError("analysis unit does not match its package reference")
        _digest(self.input_sha256, "analysis input")
        if type(self.priority) is not int or not -(2**31) <= self.priority < 2**31:
            raise ValueError("analysis priority must be a bounded integer")
        _capabilities(self.capability_pins, "analysis capabilities")
        _dependencies(self.dependency_pins, "analysis dependencies")

    def to_data(self) -> dict[str, object]:
        return {
            "capability_pins": [_capability_data(item) for item in self.capability_pins],
            "dependency_pins": [_dependency_data(item) for item in self.dependency_pins],
            "input_sha256": self.input_sha256,
            "package_ref_id": self.package_ref_id,
            "priority": self.priority,
            "unit_id": self.unit_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class ClusterGraphPlan:
    """The complete immutable topology and capability pins for one cluster."""

    cluster_id: str
    packages: tuple[PackageAnalysisUnit, ...]
    audit_capability_pins: tuple[CapabilityPin, ...]
    reconciliation_capability_pins: tuple[CapabilityPin, ...]
    implementation_capability_pins: tuple[CapabilityPin, ...]
    publication_capability_pins: tuple[CapabilityPin, ...]
    revision: str = CLUSTER_GRAPH_REVISION
    _content_id: str = field(init=False, repr=False, compare=False)

    def __init__(self) -> None:
        raise ValueError("cluster graphs must be built from frozen execution plans")

    def _validate(self) -> None:
        _token(self.cluster_id, "cluster_id")
        if self.revision != CLUSTER_GRAPH_REVISION:
            raise ValueError("cluster graph revision is unsupported")
        if (
            type(self.packages) is not tuple
            or not 1 <= len(self.packages) <= _MAX_PACKAGES
            or any(type(item) is not PackageAnalysisUnit for item in self.packages)
        ):
            raise ValueError("cluster packages must be a bounded exact tuple")
        for package in self.packages:
            package._validate()
        if self.packages != tuple(sorted(self.packages, key=lambda item: item.package_ref_id)):
            raise ValueError("cluster packages must be sorted by package reference")
        if len({item.package_ref_id for item in self.packages}) != len(self.packages):
            raise ValueError("cluster packages contain duplicate package references")
        for name in (
            "audit_capability_pins",
            "reconciliation_capability_pins",
            "implementation_capability_pins",
            "publication_capability_pins",
        ):
            _capabilities(getattr(self, name), name)
        content_id = _content_id("phase4-v2:cluster-stage-graph", self.to_data())
        if hasattr(self, "_content_id") and self._content_id != content_id:
            raise ValueError("cluster graph no longer matches its factory-built preimage")
        object.__setattr__(self, "_content_id", content_id)

    def to_data(self) -> dict[str, object]:
        return {
            "capabilities": {
                "audit": [_capability_data(item) for item in self.audit_capability_pins],
                "implementation": [
                    _capability_data(item) for item in self.implementation_capability_pins
                ],
                "publication": [
                    _capability_data(item) for item in self.publication_capability_pins
                ],
                "reconciliation": [
                    _capability_data(item) for item in self.reconciliation_capability_pins
                ],
            },
            "cluster_id": self.cluster_id,
            "completion_revisions": {
                "audit": PACKAGE_AUDIT_COMPLETION_REVISION,
                "implementation": CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
                "package_analysis": VALIDATED_PACKAGE_OUTPUT_REVISION,
                "publication": TRACKER_PUBLICATION_COMPLETION_REVISION,
                "reconciliation": CLUSTER_RECONCILIATION_COMPLETION_REVISION,
            },
            "packages": [item.to_data() for item in self.packages],
            "revision": self.revision,
        }

    @property
    def content_id(self) -> str:
        return self._content_id


def build_cluster_graph(
    queue: Queue,
    plans: tuple[FrozenPackageExecutionPlan, ...],
    *,
    audit_capability_pins: tuple[CapabilityPin, ...],
    reconciliation_capability_pins: tuple[CapabilityPin, ...],
    implementation_capability_pins: tuple[CapabilityPin, ...],
    publication_capability_pins: tuple[CapabilityPin, ...],
    priorities: tuple[int, ...] | None = None,
) -> ClusterGraphPlan:
    """Build one graph only from canonical plans and currently activated pins."""

    if type(queue) is not Queue:
        raise ValueError("cluster graph construction requires an exact queue")
    if (
        type(plans) is not tuple
        or not 1 <= len(plans) <= _MAX_PACKAGES
        or any(type(item) is not FrozenPackageExecutionPlan for item in plans)
    ):
        raise ValueError("cluster graph plans must be a bounded exact tuple")
    frozen = tuple(validate_frozen_package_execution_plan(item) for item in plans)
    if any(item.status is not PackagePlanStatus.EXECUTABLE for item in frozen):
        raise ValueError("cluster graph plans must all be executable")
    if len({item.target_package_ref_id for item in frozen}) != len(frozen):
        raise ValueError("cluster graph plans contain duplicate package references")
    cluster_ids = {item.cluster_id for item in frozen}
    if len(cluster_ids) != 1:
        raise ValueError("cluster graph plans must belong to one cluster")
    if priorities is None:
        priorities = (0,) * len(frozen)
    if (
        type(priorities) is not tuple
        or len(priorities) != len(frozen)
        or any(type(item) is not int or not -(2**31) <= item < 2**31 for item in priorities)
    ):
        raise ValueError("cluster graph priorities must match the frozen plans")
    stage_pins = (
        audit_capability_pins,
        reconciliation_capability_pins,
        implementation_capability_pins,
        publication_capability_pins,
    )
    for name, pins in zip(
        ("audit", "reconciliation", "implementation", "publication"),
        stage_pins,
        strict=True,
    ):
        _capabilities(pins, f"{name} capabilities")
    package_pins = tuple(
        CapabilityPin(pin.name, pin.revision, pin.digest)
        for plan in frozen
        for pin in plan.required_capabilities
    )
    _require_activated(queue, (*package_pins, *(pin for pins in stage_pins for pin in pins)))
    packages: list[PackageAnalysisUnit] = []
    for plan, priority in zip(frozen, priorities, strict=True):
        unit = object.__new__(PackageAnalysisUnit)
        object.__setattr__(unit, "package_ref_id", plan.target_package_ref_id)
        object.__setattr__(unit, "unit_id", package_queue_unit_id(plan.target_package_ref_id))
        object.__setattr__(unit, "input_sha256", plan.digest)
        object.__setattr__(
            unit,
            "capability_pins",
            tuple(
                CapabilityPin(pin.name, pin.revision, pin.digest)
                for pin in plan.required_capabilities
            ),
        )
        object.__setattr__(
            unit,
            "dependency_pins",
            tuple(
                CompletionDependencyPin(pin.parent_unit_id, pin.revision, pin.digest)
                for pin in plan.required_completions
            ),
        )
        object.__setattr__(unit, "priority", priority)
        object.__setattr__(unit, "_source_plan", plan)
        unit._validate()
        packages.append(unit)
    graph = object.__new__(ClusterGraphPlan)
    object.__setattr__(graph, "cluster_id", next(iter(cluster_ids)))
    object.__setattr__(
        graph, "packages", tuple(sorted(packages, key=lambda item: item.package_ref_id))
    )
    object.__setattr__(graph, "audit_capability_pins", audit_capability_pins)
    object.__setattr__(graph, "reconciliation_capability_pins", reconciliation_capability_pins)
    object.__setattr__(graph, "implementation_capability_pins", implementation_capability_pins)
    object.__setattr__(graph, "publication_capability_pins", publication_capability_pins)
    object.__setattr__(graph, "revision", CLUSTER_GRAPH_REVISION)
    graph._validate()
    return graph


def validate_cluster_graph(graph: ClusterGraphPlan) -> ClusterGraphPlan:
    """Reconstruct a graph so mutated factory products fail at every consumer."""

    if type(graph) is not ClusterGraphPlan:
        raise ValueError("expected an exact cluster graph")
    graph._validate()
    return graph


def _require_activated(queue: Queue, pins: tuple[CapabilityPin, ...]) -> None:
    """Read exact queue heads without exposing a forgeable activation DTO."""

    queue.verify_schema()
    expected = {(pin.capability, pin.revision, pin.digest) for pin in pins}
    connection = sqlite3.connect(f"file:{queue.database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT current.capability, current.revision, current.digest
            FROM pipeline_capability_activations AS current
            JOIN (
                SELECT capability, MAX(activation_id) AS activation_id
                FROM pipeline_capability_activations GROUP BY capability
            ) AS heads ON heads.activation_id = current.activation_id
            """
        ).fetchall()
    finally:
        connection.close()
    active = {tuple(row) for row in rows}
    missing = expected - active
    if missing:
        names = ", ".join(sorted(item[0] for item in missing))
        raise QueueConflictError(f"cluster graph capability is not the active queue head: {names}")


@dataclass(frozen=True, slots=True)
class ClusterGraphMaterialization:
    """Deterministic identifiers and the subset currently in SQLite."""

    graph_sha256: str
    analysis_units: tuple[str, ...]
    audit_units: tuple[str, ...]
    reconciliation_unit: str
    implementation_unit: str
    publication_unit: str
    materialized_units: tuple[str, ...]


def package_audit_unit_id(graph: ClusterGraphPlan, package_ref_id: str) -> str:
    return _stage_unit_id("audit", graph.cluster_id, package_ref_id)


def cluster_reconciliation_unit_id(graph: ClusterGraphPlan) -> str:
    return _stage_unit_id("reconciliation", graph.cluster_id, graph.cluster_id)


def cluster_implementation_unit_id(graph: ClusterGraphPlan) -> str:
    return _stage_unit_id("implementation", graph.cluster_id, graph.cluster_id)


def tracker_publication_unit_id(graph: ClusterGraphPlan) -> str:
    return _stage_unit_id("publication", graph.cluster_id, graph.cluster_id)


def stage_input_sha256(
    graph: ClusterGraphPlan,
    *,
    stage: str,
    subject: str,
    capability_pins: tuple[CapabilityPin, ...],
    dependency_pins: tuple[CompletionDependencyPin, ...],
) -> str:
    """Bind one downstream stage to its graph and exact accepted parents."""

    _token(stage, "stage")
    _token(subject, "stage subject")
    _capabilities(capability_pins, "stage capabilities")
    _dependencies(dependency_pins, "stage dependencies")
    return _content_id(
        "phase4-v2:cluster-stage-input",
        {
            "capability_pins": [_capability_data(item) for item in capability_pins],
            "dependency_pins": [_dependency_data(item) for item in dependency_pins],
            "graph_sha256": graph.content_id,
            "stage": stage,
            "subject": subject,
        },
    )


def materialize_cluster_graph(queue: Queue, graph: ClusterGraphPlan) -> ClusterGraphMaterialization:
    """Advance exactly as far as immutable accepted parents allow."""

    if type(queue) is not Queue or type(graph) is not ClusterGraphPlan:
        raise ValueError("cluster graph materialization requires exact queue and graph types")
    validate_cluster_graph(graph)
    _require_activated(
        queue,
        tuple(
            pin
            for pins in (
                *(item.capability_pins for item in graph.packages),
                graph.audit_capability_pins,
                graph.reconciliation_capability_pins,
                graph.implementation_capability_pins,
                graph.publication_capability_pins,
            )
            for pin in pins
        ),
    )
    analysis_ids = tuple(item.unit_id for item in graph.packages)
    audit_ids = tuple(package_audit_unit_id(graph, item.package_ref_id) for item in graph.packages)
    reconciliation_id = cluster_reconciliation_unit_id(graph)
    implementation_id = cluster_implementation_unit_id(graph)
    publication_id = tracker_publication_unit_id(graph)

    for package in graph.packages:
        queue.materialize_work_unit(
            package.unit_id,
            kind=ORCHESTRATION_PACKAGE_ANALYSIS_KIND,
            cluster_id=graph.cluster_id,
            input_digest=package.input_sha256,
            capability_pins=package.capability_pins,
            dependency_pins=package.dependency_pins,
            priority=package.priority,
        )

    snapshot = queue.snapshot()
    completions = completion_pins(snapshot)
    for package in graph.packages:
        analysis = completions.get(package.unit_id)
        if analysis is None:
            continue
        if analysis.revision != VALIDATED_PACKAGE_OUTPUT_REVISION:
            raise QueueConflictError("package analysis completion revision is unsupported")
        dependencies = (analysis,)
        queue.materialize_work_unit(
            package_audit_unit_id(graph, package.package_ref_id),
            kind=ORCHESTRATION_PACKAGE_AUDIT_KIND,
            cluster_id=graph.cluster_id,
            capability_pins=graph.audit_capability_pins,
            dependency_pins=dependencies,
            input_digest=stage_input_sha256(
                graph,
                stage="audit",
                subject=package.package_ref_id,
                capability_pins=graph.audit_capability_pins,
                dependency_pins=dependencies,
            ),
        )

    snapshot = queue.snapshot()
    completions = completion_pins(snapshot)
    audit_completions = tuple(
        sorted(
            (
                completion
                for unit_id in audit_ids
                if (completion := completions.get(unit_id)) is not None
            ),
            key=lambda item: item.parent_unit_id,
        )
    )
    if any(
        completion.revision != PACKAGE_AUDIT_COMPLETION_REVISION for completion in audit_completions
    ):
        raise QueueConflictError("package audit completion revision is unsupported")
    if len(audit_completions) == len(graph.packages):
        queue.materialize_work_unit(
            reconciliation_id,
            kind=ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
            cluster_id=graph.cluster_id,
            capability_pins=graph.reconciliation_capability_pins,
            dependency_pins=audit_completions,
            input_digest=stage_input_sha256(
                graph,
                stage="reconciliation",
                subject=graph.cluster_id,
                capability_pins=graph.reconciliation_capability_pins,
                dependency_pins=audit_completions,
            ),
        )

    snapshot = queue.snapshot()
    reconciliation = completion_pins(snapshot).get(reconciliation_id)
    if reconciliation is not None:
        dependencies = (reconciliation,)
        queue.materialize_work_unit(
            implementation_id,
            kind=ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
            cluster_id=graph.cluster_id,
            capability_pins=graph.implementation_capability_pins,
            dependency_pins=dependencies,
            input_digest=stage_input_sha256(
                graph,
                stage="implementation",
                subject=graph.cluster_id,
                capability_pins=graph.implementation_capability_pins,
                dependency_pins=dependencies,
            ),
        )

    snapshot = queue.snapshot()
    implementation = completion_pins(snapshot).get(implementation_id)
    if implementation is not None:
        dependencies = (implementation,)
        queue.materialize_work_unit(
            publication_id,
            kind=ORCHESTRATION_TRACKER_PUBLICATION_KIND,
            cluster_id=graph.cluster_id,
            capability_pins=graph.publication_capability_pins,
            dependency_pins=dependencies,
            input_digest=stage_input_sha256(
                graph,
                stage="publication",
                subject=graph.cluster_id,
                capability_pins=graph.publication_capability_pins,
                dependency_pins=dependencies,
            ),
        )

    materialized = {item.unit_id for item in queue.snapshot().units}
    all_ids = (*analysis_ids, *audit_ids, reconciliation_id, implementation_id, publication_id)
    return ClusterGraphMaterialization(
        graph.content_id,
        analysis_ids,
        audit_ids,
        reconciliation_id,
        implementation_id,
        publication_id,
        tuple(unit_id for unit_id in all_ids if unit_id in materialized),
    )


def completion_pin(snapshot: QueueSnapshot, unit_id: str) -> CompletionDependencyPin | None:
    """Return an exact accepted completion pin from one immutable snapshot."""

    return completion_pins(snapshot).get(unit_id)


def completion_pins(snapshot: QueueSnapshot) -> dict[str, CompletionDependencyPin]:
    """Index every exact accepted completion in one immutable snapshot."""

    result: dict[str, CompletionDependencyPin] = {}
    for unit in snapshot.units:
        if unit.status is not WorkUnitStatus.COMPLETED:
            continue
        if unit.completion_revision is None or unit.output_digest is None:
            raise RuntimeError("completed queue unit is missing its immutable completion")
        result[unit.unit_id] = CompletionDependencyPin(
            unit.unit_id,
            unit.completion_revision,
            unit.output_digest,
        )
    return result


def _stage_unit_id(stage: str, cluster_id: str, subject: str) -> str:
    digest = _content_id(
        "phase4-v2:cluster-stage-unit",
        {"cluster_id": cluster_id, "stage": stage, "subject": subject},
    )
    return f"phase4-v2-{stage}:{digest}"


def _capability_data(pin: CapabilityPin) -> list[str]:
    return [pin.capability, pin.revision, pin.digest]


def _dependency_data(pin: CompletionDependencyPin) -> list[str]:
    return [pin.parent_unit_id, pin.revision, pin.digest]


def _capabilities(value: object, label: str) -> tuple[CapabilityPin, ...]:
    if (
        type(value) is not tuple
        or not value
        or len(value) > _MAX_PINS
        or any(type(item) is not CapabilityPin for item in value)
    ):
        raise ValueError(f"{label} must be a non-empty exact tuple")
    pins = value
    for pin in pins:
        _token(pin.capability, f"{label} capability")
        _revision(pin.revision, f"{label} revision")
        _digest(pin.digest, f"{label} digest")
    if pins != tuple(sorted(pins, key=lambda item: item.capability)) or len(
        {item.capability for item in pins}
    ) != len(pins):
        raise ValueError(f"{label} must be sorted and unique")
    return pins


def _dependencies(value: object, label: str) -> tuple[CompletionDependencyPin, ...]:
    if (
        type(value) is not tuple
        or len(value) > _MAX_PINS
        or any(type(item) is not CompletionDependencyPin for item in value)
    ):
        raise ValueError(f"{label} must be an exact tuple")
    pins = value
    for pin in pins:
        _token(pin.parent_unit_id, f"{label} parent")
        _revision(pin.revision, f"{label} revision")
        _digest(pin.digest, f"{label} digest")
    if pins != tuple(sorted(pins, key=lambda item: item.parent_unit_id)) or len(
        {item.parent_unit_id for item in pins}
    ) != len(pins):
        raise ValueError(f"{label} must be sorted and unique")
    return pins


def _content_id(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii")
        + b"\0"
        + json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _token(value: object, label: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical token")
    return value


def _revision(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > 200 or "\0" in value:
        raise ValueError(f"{label} must be a bounded revision")
    return value
