"""Hostile proofs for factory-built graphs and authenticated stage completion."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.orchestration.completion as stage_completion
from tests.phase4_v2_orchestration_acceptance import (
    SyntheticAcceptanceConfig,
    complete_synthetic_package_inputs,
    run_synthetic_acceptance,
)
from tests.phase4_v2_orchestration_testing import (
    build_synthetic_package_inputs,
    protected_fixture_trust,
)
from tools.phase4_v2.equivalence.plan import (
    PACKAGE_EXECUTION_PLAN_REVISION,
    PREPARATION_RECEIPT_REVISION,
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    FrozenCapabilityPin,
    FrozenCompletionPin,
    FrozenPackageExecutionPlan,
    FrozenPreparationPlanBinding,
    PackagePlanStatus,
)
from tools.phase4_v2.orchestration import (
    CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
    CLUSTER_RECONCILIATION_COMPLETION_REVISION,
    PACKAGE_AUDIT_COMPLETION_REVISION,
    STAGE_AUTHORITY_REVISION,
    TRACKER_PUBLICATION_COMPLETION_REVISION,
    ActivatedStageAuthority,
    ClusterGraphPlan,
    PackageAnalysisUnit,
    WorkStage,
    build_cluster_graph,
    finish_cluster_implementation,
    finish_cluster_reconciliation,
    finish_package_audit,
    finish_tracker_publication,
    load_implementation_receipt,
    load_package_audit_receipt,
    load_publication_receipt,
    load_reconciliation_receipt,
    load_stage_authority,
    materialize_cluster_graph,
    package_audit_unit_id,
    stage_authority_capability,
)
from tools.phase4_v2.queue import (
    CapabilityPin,
    FanoutPublishReceipt,
    Lease,
    Queue,
    QueueConflictError,
    TrackerDocument,
    TrackerDocumentSet,
    TrackerFormat,
    TrackerTarget,
    WorkUnitStatus,
    document_set_sha256,
    publish_tracker_fanout,
)
from tools.phase4_v2.queue.cli import main as queue_main
from tools.phase4_v2.queue.publication_config import TrackerPublicationConfig

_TARGETS = (
    TrackerTarget("issues/436.md", TrackerFormat.MARKDOWN),
    TrackerTarget("public/queue.html", TrackerFormat.HTML),
)
_PUBLICATION_CONFIG = TrackerPublicationConfig("owner/repository", "tracker", _TARGETS)
_PROTECTED_CONFIG: dict[str, tuple[str, int]] = {}
_GRAPH_AUTHORITIES: dict[str, dict[str, tuple[Ed25519PrivateKey, ActivatedStageAuthority]]] = {}


@pytest.fixture(autouse=True)
def _protected_stage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _PROTECTED_CONFIG.clear()
    _GRAPH_AUTHORITIES.clear()

    def load_config() -> dict[str, tuple[str, int]]:
        if _PROTECTED_CONFIG:
            return dict(_PROTECTED_CONFIG)
        result: dict[str, tuple[str, int]] = {}
        for stage in ("audit", "reconciliation", "implementation", "publication"):
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
            result[stage] = (
                hashlib.sha256(b"phase4-v2:stage-authority\0" + canonical).hexdigest(),
                1,
            )
        return result

    monkeypatch.setattr(stage_completion, "_load_stage_authority_config", load_config)


class _Gateway:
    def __init__(self) -> None:
        self.repository = _PUBLICATION_CONFIG.repository
        self.branch = _PUBLICATION_CONFIG.branch
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
        self.revision = "b" * 40
        return True


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    result = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    result.initialize()
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pin(name: str) -> CapabilityPin:
    return CapabilityPin(name, f"{name}-v1", _digest(name))


def _frozen_plan(cluster: str, name: str) -> FrozenPackageExecutionPlan:
    package_ref = _digest(f"package:{cluster}:{name}")
    capability = FrozenCapabilityPin(
        f"analysis:{cluster}:{name}", "synthetic-analysis-v1", _digest(f"cap:{cluster}:{name}")
    )
    preparation_capabilities = tuple(
        FrozenCapabilityPin(
            f"preparation-{kind}:{cluster}:{name}",
            f"preparation-{kind}-v1",
            _digest(f"preparation-{kind}:{cluster}:{name}"),
        )
        for kind in ("authority", "candidate", "execution", "registry")
    )
    preparation_completion = FrozenCompletionPin(
        f"package-preparation:{package_ref}",
        PREPARATION_RECEIPT_REVISION,
        _digest(f"receipt:{cluster}:{name}"),
    )
    preparation = FrozenPreparationPlanBinding(
        package_ref,
        f"org.example.{name}",
        "1",
        "1.0",
        _digest(f"artifact:{cluster}:{name}"),
        _digest(f"preflight:{cluster}:{name}"),
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
            "package_name": f"org.example.{name}",
            "requirements_sha256": _digest(f"preflight:{cluster}:{name}"),
            "target_artifact_digest": _digest(f"artifact:{cluster}:{name}"),
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
        "root_plans": [
            {
                "analysis_capabilities": [
                    {
                        "digest": capability.digest,
                        "name": capability.name,
                        "revision": capability.revision,
                    }
                ],
                "analysis_dependencies": [],
                "reason": "synthetic",
                "revision": "phase4-v2-root-execution-plan-v2",
                "route": "FULL_ANALYSIS",
                "target_occurrence_identity_sha256": _digest(
                    f"occurrence:{cluster}:{name}"
                ),
                "target_root_id": _digest(f"root:{cluster}:{name}"),
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
        "package_name": f"org.example.{name}",
        "version_code": "1",
        "version_name": "1.0",
        "target_artifact_digest": _digest(f"artifact:{cluster}:{name}"),
        "preflight_sha256": _digest(f"preflight:{cluster}:{name}"),
        "preparation": preparation,
        "inherited_semantic_roots": (),
        "semantic_audit_completion_digests": (),
        "required_capabilities": required_capabilities,
        "required_completions": (preparation_completion,),
    }
    for field, value in values.items():
        object.__setattr__(result, field, value)
    return result


def _activate(queue: Queue, pins: tuple[CapabilityPin, ...]) -> None:
    for pin in pins:
        queue.register_capability(pin.capability, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.capability, pin.revision, pin.digest)


def _graph(queue: Queue, cluster: str, names: tuple[str, ...]) -> ClusterGraphPlan:
    fixture_root = Path(tempfile.mkdtemp(prefix="phase4-stage-graph-"))
    with protected_fixture_trust(fixture_root / "trust") as trust:
        active_capabilities: set[tuple[str, str, str]] = set()
        plans = tuple(
            complete_synthetic_package_inputs(
                queue,
                build_synthetic_package_inputs(
                    fixture_root / cluster,
                    cluster_id=cluster,
                    package_index=index,
                    trust=trust,
                ),
                trust=trust,
                active_capabilities=active_capabilities,
            )
            for index, _name in enumerate(names)
        )
    authorities = {
        stage: _authority(stage)
        for stage in ("audit", "reconciliation", "implementation", "publication")
    }
    _GRAPH_AUTHORITIES[cluster] = authorities
    stage_pins = tuple(stage_authority_capability(authorities[stage][1]) for stage in authorities)
    _activate(queue, stage_pins)
    return build_cluster_graph(
        queue,
        plans,
        audit_authority=authorities["audit"][1],
        reconciliation_authority=authorities["reconciliation"][1],
        implementation_authority=authorities["implementation"][1],
        publication_authority=authorities["publication"][1],
    )


def _authority(stage: str) -> tuple[Ed25519PrivateKey, ActivatedStageAuthority]:
    key = Ed25519PrivateKey.generate()
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
    _PROTECTED_CONFIG[stage] = (digest, 1)
    return key, load_stage_authority(canonical)


def _signed(
    stage: str,
    payload: dict[str, object],
    key: Ed25519PrivateKey,
    authority: ActivatedStageAuthority,
) -> bytes:
    document = {
        "payload": {**payload, "authority_sha256": authority.authority_sha256, "stage": stage},
        "signature": "",
    }
    signing = (
        f"phase4-v2:signed-stage-receipt:{stage}".encode() + b"\0" + _canonical(document["payload"])
    )
    document["signature"] = key.sign(signing).hex()
    return _canonical(document)


def _claim(queue: Queue, stage: WorkStage, owner: str) -> Lease:
    lease = queue.claim(owner, allowed_kinds=(stage.value,))
    assert lease is not None
    return lease


def test_graph_and_authenticated_receipts_follow_real_stage_adapters(queue: Queue) -> None:
    graph = _graph(queue, "cluster-011", ("alpha", "beta"))
    authorities = _GRAPH_AUTHORITIES[graph.cluster_id]
    first = materialize_cluster_graph(queue, graph)
    assert set(first.materialized_units) == {*first.analysis_units, *first.audit_units}

    audit_receipts = []
    for index in range(2):
        lease = _claim(queue, WorkStage.PACKAGE_AUDIT, f"audit-{index}")
        package = next(
            item
            for item in graph.packages
            if package_audit_unit_id(graph, item.package_ref_id) == lease.unit_id
        )
        analysis = next(item for item in queue.snapshot().units if item.unit_id == package.unit_id)
        payload = {
            "accepted": True,
            "analysis_completion_revision": analysis.completion_revision,
            "analysis_completion_sha256": analysis.output_digest,
            "package_surface_sha256": _digest(f"surface:{package.package_ref_id}"),
            "cluster_id": graph.cluster_id,
            "diagnostics": [],
            "graph_sha256": graph.content_id,
            "package_ref_id": package.package_ref_id,
            "revision": PACKAGE_AUDIT_COMPLETION_REVISION,
            "stage_input_sha256": lease.input_digest,
        }
        key, authority = authorities["audit"]
        signed = _signed("audit", payload, key, authority)
        receipt = load_package_audit_receipt(signed, authority)
        if index == 0:
            object.__setattr__(receipt, "cluster_id", "transplanted-cluster")
            with pytest.raises(QueueConflictError, match="signed canonical preimage"):
                finish_package_audit(
                    queue, lease, graph=graph, authority=authority, receipt=receipt
                )
            receipt = load_package_audit_receipt(signed, authority)
        audit_receipts.append(receipt)
        finish_package_audit(queue, lease, graph=graph, authority=authority, receipt=receipt)

    materialize_cluster_graph(queue, graph)
    reconciliation_lease = _claim(queue, WorkStage.CLUSTER_RECONCILIATION, "reconciliation")
    key, reconciliation_authority = authorities["reconciliation"]
    reconciliation = load_reconciliation_receipt(
        _signed(
            "reconciliation",
            {
                "accepted": True,
                "cluster_id": graph.cluster_id,
                "completeness_receipt_sha256": _digest("complete"),
                "diagnostics": [],
                "disposition_ledger_sha256": _digest("ledger"),
                "graph_sha256": graph.content_id,
                "package_audit_receipts": sorted(
                    [item.package_ref_id, item.receipt_sha256] for item in audit_receipts
                ),
                "reconciliation_result_sha256": _digest("reconciled"),
                "revision": CLUSTER_RECONCILIATION_COMPLETION_REVISION,
                "stage_input_sha256": reconciliation_lease.input_digest,
            },
            key,
            reconciliation_authority,
        ),
        reconciliation_authority,
    )
    reconciliation_result = finish_cluster_reconciliation(
        queue,
        reconciliation_lease,
        graph=graph,
        authority=reconciliation_authority,
        receipt=reconciliation,
    )
    assert reconciliation_result.receipt_sha256 == reconciliation.receipt_sha256

    materialize_cluster_graph(queue, graph)
    implementation_lease = _claim(queue, WorkStage.CLUSTER_IMPLEMENTATION, "implementation")
    key, implementation_authority = authorities["implementation"]
    implementation = load_implementation_receipt(
        _signed(
            "implementation",
            {
                "accepted": True,
                "cluster_id": graph.cluster_id,
                "diagnostics": [],
                "disposition_ledger_sha256": reconciliation.disposition_ledger_sha256,
                "graph_sha256": graph.content_id,
                "implementation_output_sha256": _digest("implementation"),
                "reconciliation_receipt_sha256": reconciliation.receipt_sha256,
                "revision": CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
                "stage_input_sha256": implementation_lease.input_digest,
            },
            key,
            implementation_authority,
        ),
        implementation_authority,
    )
    finish_cluster_implementation(
        queue,
        implementation_lease,
        graph=graph,
        reconciliation_authority=reconciliation_authority,
        reconciliation_receipt=reconciliation,
        authority=implementation_authority,
        receipt=implementation,
    )

    materialize_cluster_graph(queue, graph)
    publication_lease = _claim(queue, WorkStage.TRACKER_PUBLICATION, "publication")
    key, publication_authority = authorities["publication"]
    invented_fanout = object.__new__(FanoutPublishReceipt)
    for name, value in {
        "queue_generation": queue.snapshot().generation_id,
        "before_revision": "a" * 40,
        "after_revision": "b" * 40,
        "document_set_sha256": _digest("invented-documents"),
        "publication_config_sha256": _digest("invented-config"),
        "paths": tuple(item.path for item in _TARGETS),
        "changed": True,
    }.items():
        object.__setattr__(invented_fanout, name, value)
    invented_publication = load_publication_receipt(
        _signed(
            "publication",
            {
                "accepted": True,
                "after_revision": invented_fanout.after_revision,
                "before_revision": invented_fanout.before_revision,
                "changed": invented_fanout.changed,
                "cluster_id": graph.cluster_id,
                "diagnostics": [],
                "document_set_sha256": invented_fanout.document_set_sha256,
                "graph_sha256": graph.content_id,
                "implementation_receipt_sha256": implementation.receipt_sha256,
                "paths": list(invented_fanout.paths),
                "publication_config_sha256": invented_fanout.publication_config_sha256,
                "queue_generation_sha256": invented_fanout.queue_generation,
                "revision": TRACKER_PUBLICATION_COMPLETION_REVISION,
                "stage_input_sha256": publication_lease.input_digest,
            },
            key,
            publication_authority,
        ),
        publication_authority,
    )
    with pytest.raises(QueueConflictError, match="production fanout checkpoint"):
        finish_tracker_publication(
            queue,
            publication_lease,
            graph=graph,
            reconciliation_authority=reconciliation_authority,
            reconciliation_receipt=reconciliation,
            implementation_authority=implementation_authority,
            implementation_receipt=implementation,
            authority=publication_authority,
            fanout_receipt=invented_fanout,
            receipt=invented_publication,
        )
    fanout = publish_tracker_fanout(queue, publication_lease, _Gateway(), _PUBLICATION_CONFIG)
    publication = load_publication_receipt(
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
                "stage_input_sha256": publication_lease.input_digest,
            },
            key,
            publication_authority,
        ),
        publication_authority,
    )
    finish_tracker_publication(
        queue,
        publication_lease,
        graph=graph,
        reconciliation_authority=reconciliation_authority,
        reconciliation_receipt=reconciliation,
        implementation_authority=implementation_authority,
        implementation_receipt=implementation,
        authority=publication_authority,
        fanout_receipt=fanout,
        receipt=publication,
    )
    assert all(item.status is WorkUnitStatus.COMPLETED for item in queue.snapshot().units)


def test_graph_constructors_and_inactive_capabilities_fail_closed(queue: Queue) -> None:
    with pytest.raises(ValueError, match="frozen execution plans"):
        PackageAnalysisUnit()
    with pytest.raises(ValueError, match="frozen execution plans"):
        ClusterGraphPlan()
    plan = _frozen_plan("cluster", "alpha")
    authorities = {stage: _authority(stage)[1] for stage in _PROTECTED_CONFIG or ()}
    if not authorities:
        authorities = {
            stage: _authority(stage)[1]
            for stage in ("audit", "reconciliation", "implementation", "publication")
        }
    with pytest.raises(QueueConflictError, match="active queue head"):
        build_cluster_graph(
            queue,
            (plan,),
            audit_authority=authorities["audit"],
            reconciliation_authority=authorities["reconciliation"],
            implementation_authority=authorities["implementation"],
            publication_authority=authorities["publication"],
        )
    graph = _graph(queue, "cluster-sealed", ("alpha",))
    object.__setattr__(graph, "cluster_id", "cluster-transplanted")
    with pytest.raises(ValueError, match="factory-built preimage"):
        materialize_cluster_graph(queue, graph)


def test_authority_and_receipt_forgery_wrong_key_and_mutation_fail_closed() -> None:
    key, authority = _authority("audit")
    _PROTECTED_CONFIG["audit"] = ("0" * 64, 1)
    with pytest.raises(QueueConflictError, match="protected activation"):
        load_stage_authority(authority.canonical_bytes)
    _PROTECTED_CONFIG["audit"] = (authority.authority_sha256, authority.generation)
    payload = {
        "accepted": True,
        "analysis_completion_revision": VALIDATED_PACKAGE_OUTPUT_REVISION,
        "analysis_completion_sha256": _digest("analysis"),
        "package_surface_sha256": _digest("surface"),
        "cluster_id": "cluster",
        "diagnostics": [],
        "graph_sha256": _digest("graph"),
        "package_ref_id": _digest("package"),
        "revision": PACKAGE_AUDIT_COMPLETION_REVISION,
        "stage_input_sha256": _digest("input"),
    }
    signed = _signed("audit", payload, key, authority)
    wrong_key = Ed25519PrivateKey.generate()
    forged = _signed("audit", payload, wrong_key, authority)
    with pytest.raises(QueueConflictError, match="signature"):
        load_package_audit_receipt(forged, authority)
    decoded = json.loads(signed)
    decoded["payload"]["cluster_id"] = "transplanted"
    with pytest.raises(QueueConflictError, match="signature"):
        load_package_audit_receipt(_canonical(decoded), authority)


def test_generic_cli_cannot_accept_reserved_semantic_stage(
    queue: Queue, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = _graph(queue, "cluster-cli", ("alpha",))
    materialize_cluster_graph(queue, graph)
    lease = _claim(queue, WorkStage.PACKAGE_AUDIT, "audit")
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
            "--output-digest",
            _digest("forged"),
            "--completion-revision",
            PACKAGE_AUDIT_COMPLETION_REVISION,
        ]
    )
    assert result == 2
    assert "typed completion adapter" in capsys.readouterr().err


def test_production_path_acceptance_is_seed_deterministic(tmp_path: Path) -> None:
    config = SyntheticAcceptanceConfig(
        seed=11,
        clusters=1,
        units_per_cluster=2,
        workers=2,
        crash_probability=0.25,
        forced_initial_crashes=1,
    )
    first = run_synthetic_acceptance(tmp_path / "first", config)
    second = run_synthetic_acceptance(tmp_path / "second", config)

    assert first == second
    assert first.unit_count == 13
    assert first.published_clusters == 1
