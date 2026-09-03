"""Adversarial tests for package-plan queue publication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import tools.phase4_v2.equivalence.plan as plan_module
import tools.phase4_v2.validator as validator_module
from tools.phase4_v2.equivalence.core import (
    EQUIVALENCE_SCHEMA_REVISION,
    LEDGER_DECISION_REVISION,
    ApplicationRoot,
    EquivalenceError,
    ExtractorCapability,
    LedgerDecision,
    Route,
    RoutingPins,
)
from tools.phase4_v2.equivalence.plan import (
    EXACT_REUSE_PIPELINE_CAPABILITY,
    FINAL_IR_SCHEMA_SHA256,
    PACKAGE_EXECUTION_PLAN_REVISION,
    PACKAGE_PIPELINE_CAPABILITY,
    PACKAGE_REPORT_SCHEMA_SHA256,
    SEMANTIC_ROOT_COMPLETION_REVISION,
    TARGET_ROOT_INVENTORY_REVISION,
    AcceptedTargetRootInventory,
    BlockedRootPlan,
    CapabilityPin,
    CompletionPin,
    FrozenPackageRef,
    FullAnalysisRootPlan,
    PackageExecutionPlan,
    PackageLocalPlan,
    PreparationPlanBinding,
    SemanticRootAudit,
    TargetRootInventory,
    TargetRootOccurrence,
    ValidatedPackageOutput,
    build_exact_reuse_root_plan,
    build_package_execution_plan,
    build_semantic_root_audit,
    build_semantic_root_completion,
    freeze_package_execution_plan,
    package_validation_receipt_completion,
    validate_preparation_receipt_for_plan,
)
from tools.phase4_v2.equivalence.queue import (
    PACKAGE_QUEUE_UNIT_KIND,
    PackagePlanInputMismatchError,
    finish_package_execution_plan,
    finish_package_preparation,
    finish_package_validation_receipt,
    materialize_package_execution_plan,
    materialize_package_preparation,
    materialize_package_validation_receipt,
    package_queue_unit_id,
)
from tools.phase4_v2.preflight.execution import (
    CANDIDATE_CONTRACT_SHA256,
    EXECUTION_PROFILE_REVISION,
)
from tools.phase4_v2.preflight.registry import (
    PREPARATION_AUTHORITY_SCHEMA,
    PREPARATION_RECEIPT_REVISION,
    PreparationReceipt,
    load_activated_preparation_authority,
)
from tools.phase4_v2.queue import (
    DependencyNotSatisfiedError,
    FinishDisposition,
    InputCheckedFinishDisposition,
    InputDigestMismatchError,
    Lease,
    Queue,
    QueueConflictError,
    TerminalOutcome,
    WorkUnitStatus,
)
from tools.phase4_v2.validator import (
    BOUND_VALIDATION_PROFILE,
    CONTRACT_REVISION,
    PACKAGE_BOUND_VALIDATION_PROFILE,
    PACKAGE_CONTRACT_REVISION,
    VALIDATOR_REVISION,
    DependencyPins,
    EvidenceLineageTrust,
    PackageDependencyPins,
    ValidationReceipt,
)
from tools.phase4_v2.validator.binding import (
    ArtifactIdentityAttestation,
    EvidenceAnchorAttestation,
    EvidenceMemberAttestation,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
SHA_0 = "0" * 64
SHA_1 = "1" * 64
CLUSTER_ID = "cluster-synthetic"

SOURCE_RECEIPT_DEPENDENCIES = {
    "corpus": SHA_A,
    "evidence_lineage": SHA_0,
    "ir": SHA_B,
    "preflight": SHA_C,
    "schema": FINAL_IR_SCHEMA_SHA256,
}
_SOURCE_RECEIPT_WITHOUT_IDENTITY = ValidationReceipt(
    validator_revision=VALIDATOR_REVISION,
    accepted=True,
    source_unchanged=True,
    bundle_sha256=SHA_F,
    report_manifest_sha256=SHA_E,
    discovered_members=4,
    declared_members=4,
    diagnostics=(),
    dependency_digests=tuple(sorted(SOURCE_RECEIPT_DEPENDENCIES.items())),
    validation_profile=BOUND_VALIDATION_PROFILE,
    contract_revision=CONTRACT_REVISION,
    validated_artifact_identity=ArtifactIdentityAttestation(
        package_name="org.example.target",
        version_code="17",
        version_name="1.7",
        artifact_digest=SHA_B,
    ),
    evidence_anchors_checked=1,
    validated_evidence_members=(EvidenceMemberAttestation("evidence/source.txt", SHA_B, SHA_F),),
    validated_evidence_anchors=(
        EvidenceAnchorAttestation(
            "source",
            SHA_B,
            "evidence/source.txt",
            SHA_F,
            0,
            1,
            "/schema_revision",
            "utf8",
            SHA_A,
        ),
    ),
)
SOURCE_RECEIPT = replace(
    _SOURCE_RECEIPT_WITHOUT_IDENTITY,
    validation_receipt_sha256=hashlib.sha256(
        json.dumps(
            _SOURCE_RECEIPT_WITHOUT_IDENTITY.identity_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest(),
)
assert SOURCE_RECEIPT.validation_receipt_sha256 is not None

TARGET_PACKAGE_REF = FrozenPackageRef(
    package_name="org.example.target",
    version_code="17",
    artifact_digest=SHA_B,
    preflight_sha256=SHA_C,
    validation_receipt_sha256=SOURCE_RECEIPT.validation_receipt_sha256,
)
TARGET_PACKAGE_REF_ID = TARGET_PACKAGE_REF.content_id

_AUTHORITY_DATA = {
    "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
    "execution_profile_revision": EXECUTION_PROFILE_REVISION,
    "execution_profile_sha256": SHA_E,
    "pipeline_revision": "phase4-v2-preparation-pipeline-v1",
    "registry_revision": "phase4-v2-approved-tool-registry-v1",
    "registry_sha256": SHA_D,
    "schema": PREPARATION_AUTHORITY_SCHEMA,
}
_AUTHORITY_PAYLOAD = (
    json.dumps(_AUTHORITY_DATA, sort_keys=True, separators=(",", ":")).encode() + b"\n"
)
PREPARATION_AUTHORITY = load_activated_preparation_authority(
    _AUTHORITY_PAYLOAD,
    expected_activation_sha256=hashlib.sha256(_AUTHORITY_PAYLOAD).hexdigest(),
)
PREPARATION_RECEIPT = object.__new__(PreparationReceipt)
for _name, _value in {
    "artifact_digest": SHA_B,
    "package_name": "org.example.target",
    "version_code": "17",
    "version_name": "1.7",
    "preflight_manifest_sha256": SHA_C,
    "manifest_sha256": SHA_A,
    "candidate_index_sha256": SHA_0,
    "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
    "authority_sha256": PREPARATION_AUTHORITY.activation_sha256,
    "tool_registry_sha256": PREPARATION_AUTHORITY.registry_sha256,
    "pipeline_revision": PREPARATION_AUTHORITY.pipeline_revision,
    "execution_profile_revision": PREPARATION_AUTHORITY.execution_profile_revision,
    "execution_profile_sha256": PREPARATION_AUTHORITY.execution_profile_sha256,
    "invocations": (),
    "candidates": (),
    "revision": PREPARATION_RECEIPT_REVISION,
}.items():
    object.__setattr__(PREPARATION_RECEIPT, _name, _value)


def test_completion_limit_applies_after_exact_pin_deduplication() -> None:
    completion = CompletionPin("shared", "fixture-v1", SHA_A)

    assert plan_module._merge_completions([completion] * 300) == (completion,)


def _local_plan(*, version_name: str = "1.7") -> PackageLocalPlan:
    return PackageLocalPlan(
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        package_name="org.example.target",
        version_code="17",
        version_name=version_name,
        target_artifact_digest=SHA_B,
        requirements_sha256=SHA_C,
        pipeline_capability=CapabilityPin(
            PACKAGE_PIPELINE_CAPABILITY,
            PACKAGE_EXECUTION_PLAN_REVISION,
            SHA_F,
        ),
    )


def _preparation_binding(local: PackageLocalPlan | None = None) -> PreparationPlanBinding:
    package = local or _local_plan()
    return plan_module._new_accepted_preparation_plan_binding(
        package_ref=TARGET_PACKAGE_REF,
        package_local=package,
        receipt=PREPARATION_RECEIPT,
        authority=PREPARATION_AUTHORITY,
    )


def _accepted_inventory(
    *pairs: tuple[str, str],
) -> AcceptedTargetRootInventory:
    inventory = TargetRootInventory(
        TARGET_PACKAGE_REF_ID,
        tuple(
            sorted(
                (TargetRootOccurrence(root, occurrence) for root, occurrence in pairs),
                key=lambda item: (item.occurrence_identity_sha256, item.target_root_id),
            )
        ),
    )
    return AcceptedTargetRootInventory(
        inventory,
        CompletionPin(
            "inventory:target",
            TARGET_ROOT_INVENTORY_REVISION,
            inventory.content_id,
        ),
    )


def _full_plan(*, reason: str = "no_exact_identity") -> PackageExecutionPlan:
    accepted = _accepted_inventory((SHA_E, SHA_F))
    return build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        preparation=_preparation_binding(),
        accepted_target_inventory=accepted,
        root_plans=(
            FullAnalysisRootPlan(
                SHA_E,
                SHA_F,
                reason,
                (CapabilityPin("analyzer:full", "full-implementation-1", SHA_A),),
                (CompletionPin("analysis-input", "analysis-input-v1", SHA_D),),
            ),
        ),
    )


def _blocked_plan() -> PackageExecutionPlan:
    accepted = _accepted_inventory((SHA_E, SHA_F))
    return build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        preparation=_preparation_binding(),
        accepted_target_inventory=accepted,
        root_plans=(BlockedRootPlan(SHA_E, SHA_F, ("missing_authoritative_root",)),),
    )


def _reuse_plan() -> PackageExecutionPlan:
    accepted = _accepted_inventory((SHA_C, SHA_D))
    extractor = ExtractorCapability(
        name="dex-root-inventory",
        implementation_sha256=SHA_A,
        configuration_sha256=SHA_B,
        capability_revision="dex-implementation-2026.08",
    )
    source = ApplicationRoot(
        package_ref_id=SHA_A,
        root_kind="android_dex",
        extractor_capability_id=extractor.content_id,
        occurrence_identity_sha256=SHA_E,
        content_root_sha256=SHA_F,
        inventory_sha256=SHA_A,
        dependency_root_sha256=SHA_B,
        inventory_complete=True,
        dependency_closure_complete=True,
    )
    decision = LedgerDecision(
        target_root_id=SHA_C,
        route=Route.EXACT_REUSE,
        reason="exact_executable_identity",
        target_inventory_receipt_sha256=SHA_C,
        source_root_id=source.content_id,
        byte_identity_proof_id=SHA_D,
        inherited_root_id=source.content_id,
        source_audit_receipt_sha256=SHA_1,
        pins=RoutingPins(),
    )
    audit: SemanticRootAudit = build_semantic_root_audit(
        source_root=source,
        ledger_decision=decision,
        extractor=extractor,
        accepted_target_inventory=accepted,
        inherited_semantic_root_sha256=SHA_0,
        inherited_semantic_root_completion=build_semantic_root_completion(
            source_root=source,
            inherited_semantic_root_sha256=SHA_0,
            parent_unit_id="semantic-root:source",
        ),
        target_inventory_completion=accepted.completion,
        ledger_decision_completion=CompletionPin(
            "ledger:target", LEDGER_DECISION_REVISION, decision.content_id
        ),
        direct_semantic_audit_completion=CompletionPin(
            "audit:source", SEMANTIC_ROOT_COMPLETION_REVISION, SHA_1
        ),
        extractor_capability=CapabilityPin(
            "extractor:dex", "dex-implementation-2026.08", extractor.content_id
        ),
        equivalence_pipeline=CapabilityPin(
            EXACT_REUSE_PIPELINE_CAPABILITY,
            EQUIVALENCE_SCHEMA_REVISION,
            SHA_F,
        ),
    )
    return build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        preparation=_preparation_binding(),
        accepted_target_inventory=accepted,
        root_plans=(build_exact_reuse_root_plan(audit),),
    )


def _receipt(plan: PackageExecutionPlan, *, bundle_sha256: str = SHA_D) -> ValidationReceipt:
    initial = ValidationReceipt(
        validator_revision=VALIDATOR_REVISION,
        accepted=True,
        source_unchanged=True,
        bundle_sha256=bundle_sha256,
        report_manifest_sha256=SHA_E,
        discovered_members=4,
        declared_members=4,
        diagnostics=(),
        dependency_digests=(
            ("corpus", SHA_A),
            ("evidence_lineage", SHA_0),
            ("execution_plan", freeze_package_execution_plan(plan).digest),
            ("ir", SHA_B),
            ("preflight", SHA_C),
            ("report_schema", PACKAGE_REPORT_SCHEMA_SHA256),
            ("schema", FINAL_IR_SCHEMA_SHA256),
        ),
        validation_profile=PACKAGE_BOUND_VALIDATION_PROFILE,
        contract_revision=PACKAGE_CONTRACT_REVISION,
        validated_artifact_identity=ArtifactIdentityAttestation(
            package_name="org.example.target",
            version_code="17",
            version_name="1.7",
            artifact_digest=SHA_B,
        ),
    )
    payload = json.dumps(
        initial.identity_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return replace(
        initial,
        validation_receipt_sha256=hashlib.sha256(payload).hexdigest(),
    )


TRUSTED_DEPENDENCIES = DependencyPins(
    preflight_sha256=SHA_C,
    ir_sha256=SHA_B,
    schema_sha256=FINAL_IR_SCHEMA_SHA256,
    corpus_sha256=SHA_A,
)
TRUSTED_EVIDENCE_LINEAGE = EvidenceLineageTrust(
    payload=b"{}",
    expected_manifest_sha256=SHA_0,
    trusted_producers=(),
)


def _stub_valid_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    plan: PackageExecutionPlan,
) -> tuple[Path, ValidationReceipt]:
    report_root = tmp_path / "report"
    report_root.mkdir(exist_ok=True)
    receipt = _receipt(plan)

    def validate(
        received_root: Path,
        *,
        expected_dependencies: DependencyPins | PackageDependencyPins | None = None,
        expected_evidence_lineage: EvidenceLineageTrust | None = None,
        allow_unbound: bool = False,
    ) -> ValidationReceipt:
        assert received_root == report_root
        assert expected_dependencies == PackageDependencyPins(
            preflight_sha256=SHA_C,
            ir_sha256=SHA_B,
            schema_sha256=FINAL_IR_SCHEMA_SHA256,
            corpus_sha256=SHA_A,
            execution_plan_sha256=freeze_package_execution_plan(plan).digest,
            report_schema_sha256=PACKAGE_REPORT_SCHEMA_SHA256,
        )
        assert expected_evidence_lineage is not None
        assert expected_evidence_lineage.payload == TRUSTED_EVIDENCE_LINEAGE.payload
        assert expected_evidence_lineage.expected_manifest_sha256 == SHA_0
        assert expected_evidence_lineage.trusted_producers
        assert allow_unbound is False
        return receipt

    monkeypatch.setattr(validator_module, "validate_report_bundle", validate)
    return report_root, receipt


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    instance = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    instance.initialize()
    return instance


def _activate_preparation_capabilities(queue: Queue) -> None:
    for pin in plan_module.preparation_capability_pins(PREPARATION_AUTHORITY):
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)


def _copy_preparation_receipt(**changes: object) -> PreparationReceipt:
    receipt = object.__new__(PreparationReceipt)
    for name in PreparationReceipt.__dataclass_fields__:
        object.__setattr__(
            receipt,
            name,
            changes.get(name, getattr(PREPARATION_RECEIPT, name)),
        )
    return receipt


def test_preparation_requires_independently_active_capabilities(queue: Queue) -> None:
    work = materialize_package_preparation(
        queue,
        package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        authority=PREPARATION_AUTHORITY,
    )

    assert queue.claim("preparation-worker") is None
    with sqlite3.connect(queue.database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM pipeline_capability_activations"
        ).fetchone() == (0,)

    _activate_preparation_capabilities(queue)
    lease = queue.claim("preparation-worker")
    assert lease is not None and lease.unit_id == work.unit_id
    with pytest.raises(QueueConflictError, match="trusted publication adapter"):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest=PREPARATION_RECEIPT.content_id,
            completion_revision=PREPARATION_RECEIPT_REVISION,
        )

    finished = finish_package_preparation(
        queue,
        lease,
        package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        receipt=PREPARATION_RECEIPT,
        authority=PREPARATION_AUTHORITY,
    )
    assert finished.queue_result.disposition is FinishDisposition.COMPLETED
    assert finished.binding.receipt_sha256 == PREPARATION_RECEIPT.content_id
    assert finished.binding.completion.parent_unit_id == work.unit_id


def test_preparation_adapter_rejects_unpinned_and_transplanted_receipts(queue: Queue) -> None:
    unit_id = plan_module.preparation_queue_unit_id(TARGET_PACKAGE_REF_ID)
    queue.materialize_work_unit(
        unit_id,
        kind=plan_module.PREPARATION_QUEUE_UNIT_KIND,
        input_digest=SHA_A,
    )
    lease = queue.claim("untrusted-preparation-worker")
    assert lease is not None and lease.unit_id == unit_id
    with pytest.raises(QueueConflictError, match="exact activated capabilities"):
        finish_package_preparation(
            queue,
            lease,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            receipt=PREPARATION_RECEIPT,
            authority=PREPARATION_AUTHORITY,
        )

    other_queue = Queue(
        queue.database.parent / "other.sqlite3",
        queue.attempts_root.parent / "other-attempts",
    )
    other_queue.initialize()
    _activate_preparation_capabilities(other_queue)
    materialize_package_preparation(
        other_queue,
        package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        authority=PREPARATION_AUTHORITY,
    )
    other_lease = other_queue.claim("preparation-worker")
    assert other_lease is not None
    with pytest.raises(EquivalenceError, match="frozen package plan identity"):
        finish_package_preparation(
            other_queue,
            other_lease,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            receipt=_copy_preparation_receipt(version_name="9.9"),
            authority=PREPARATION_AUTHORITY,
        )


def test_self_derived_authority_and_receipt_subclasses_are_rejected(queue: Queue) -> None:
    authority = object.__new__(type(PREPARATION_AUTHORITY))
    for name in type(PREPARATION_AUTHORITY).__dataclass_fields__:
        object.__setattr__(authority, name, getattr(PREPARATION_AUTHORITY, name))
    object.__setattr__(authority, "activation_sha256", SHA_A)
    with pytest.raises(EquivalenceError, match="external activation"):
        materialize_package_preparation(
            queue,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            authority=authority,
        )

    class ReceiptSubclass(PreparationReceipt):
        pass

    forged = object.__new__(ReceiptSubclass)
    for name in PreparationReceipt.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(PREPARATION_RECEIPT, name))
    _activate_preparation_capabilities(queue)
    materialize_package_preparation(
        queue,
        package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        authority=PREPARATION_AUTHORITY,
    )
    lease = queue.claim("preparation-worker")
    assert lease is not None
    with pytest.raises(EquivalenceError, match="exact PreparationReceipt"):
        finish_package_preparation(
            queue,
            lease,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            receipt=forged,
            authority=PREPARATION_AUTHORITY,
        )


def test_plan_materialization_requires_exact_accepted_preparation(queue: Queue) -> None:
    plan = _full_plan()
    _activate_preparation_capabilities(queue)
    materialize_package_preparation(
        queue,
        package_ref=TARGET_PACKAGE_REF,
        package_local=plan.package_local,
        authority=PREPARATION_AUTHORITY,
    )
    with pytest.raises(DependencyNotSatisfiedError, match="not accepted"):
        materialize_package_execution_plan(queue, plan)

    lease = queue.claim("preparation-worker")
    assert lease is not None
    accepted = finish_package_preparation(
        queue,
        lease,
        package_ref=TARGET_PACKAGE_REF,
        package_local=plan.package_local,
        receipt=PREPARATION_RECEIPT,
        authority=PREPARATION_AUTHORITY,
    )
    forged_binding = object.__new__(PreparationPlanBinding)
    for name in PreparationPlanBinding.__dataclass_fields__:
        object.__setattr__(forged_binding, name, getattr(accepted.binding, name))
    forged_capabilities = list(accepted.binding.capabilities)
    forged_capabilities[0] = replace(forged_capabilities[0], digest=SHA_F)
    object.__setattr__(forged_binding, "capabilities", tuple(forged_capabilities))
    forged_plan = build_package_execution_plan(
        cluster_id=plan.cluster_id,
        target_package_ref_id=plan.target_package_ref_id,
        target_package_ref=plan.target_package_ref,
        package_local=plan.package_local,
        preparation=forged_binding,
        accepted_target_inventory=plan.accepted_target_inventory,
        root_plans=plan.root_plans,
    )
    with pytest.raises(DependencyNotSatisfiedError, match="not accepted"):
        materialize_package_execution_plan(queue, forged_plan)

    rebuilt = build_package_execution_plan(
        cluster_id=plan.cluster_id,
        target_package_ref_id=plan.target_package_ref_id,
        target_package_ref=plan.target_package_ref,
        package_local=plan.package_local,
        preparation=accepted.binding,
        accepted_target_inventory=plan.accepted_target_inventory,
        root_plans=plan.root_plans,
    )
    frozen = freeze_package_execution_plan(rebuilt)
    assert (
        validate_preparation_receipt_for_plan(
            frozen,
            PREPARATION_RECEIPT,
            PREPARATION_AUTHORITY,
        )
        == frozen.preparation
    )
    with pytest.raises(EquivalenceError, match="not the completion frozen"):
        validate_preparation_receipt_for_plan(
            frozen,
            _copy_preparation_receipt(manifest_sha256=SHA_F),
            PREPARATION_AUTHORITY,
        )


def _publish_prerequisites(queue: Queue, plan: PackageExecutionPlan) -> None:
    frozen = freeze_package_execution_plan(plan)
    receipt_completion = package_validation_receipt_completion(TARGET_PACKAGE_REF)
    for pin in frozen.required_capabilities:
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)
    for pin in frozen.required_completions:
        if pin.parent_unit_id == plan_module.preparation_queue_unit_id(TARGET_PACKAGE_REF_ID):
            materialize_package_preparation(
                queue,
                package_ref=TARGET_PACKAGE_REF,
                package_local=plan.package_local,
                authority=PREPARATION_AUTHORITY,
            )
            lease = queue.claim("trusted-preparation-importer")
            assert lease is not None and lease.unit_id == pin.parent_unit_id
            finished = finish_package_preparation(
                queue,
                lease,
                package_ref=TARGET_PACKAGE_REF,
                package_local=plan.package_local,
                receipt=PREPARATION_RECEIPT,
                authority=PREPARATION_AUTHORITY,
            )
            assert finished.binding == plan.preparation
            continue
        if pin.parent_unit_id == receipt_completion.parent_unit_id:
            materialize_package_validation_receipt(queue, TARGET_PACKAGE_REF)
            lease = queue.claim("trusted-receipt-importer")
            assert lease is not None and lease.unit_id == pin.parent_unit_id
            finish_package_validation_receipt(
                queue,
                lease,
                package_ref=TARGET_PACKAGE_REF,
                receipt_payload=SOURCE_RECEIPT.to_json(),
                trusted_validator_revision=VALIDATOR_REVISION,
                trusted_contract_revision=CONTRACT_REVISION,
                trusted_dependency_digests=SOURCE_RECEIPT_DEPENDENCIES,
                trusted_receipt_sha256=SOURCE_RECEIPT.validation_receipt_sha256,
            )
            continue
        queue.enqueue(pin.parent_unit_id, kind="prerequisite", input_digest=pin.digest)
        lease = queue.claim("prerequisite-publisher")
        assert lease is not None and lease.unit_id == pin.parent_unit_id
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest=pin.digest,
            completion_revision=pin.revision,
        )


def _materialize_prerequisite(queue: Queue, pin: CompletionPin) -> None:
    if pin.parent_unit_id == plan_module.preparation_queue_unit_id(TARGET_PACKAGE_REF_ID):
        _activate_preparation_capabilities(queue)
        work = materialize_package_preparation(
            queue,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            authority=PREPARATION_AUTHORITY,
        )
        assert work.unit_id == pin.parent_unit_id
        lease = queue.claim("preparation-publisher")
        assert lease is not None and lease.unit_id == pin.parent_unit_id
        finish_package_preparation(
            queue,
            lease,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            receipt=PREPARATION_RECEIPT,
            authority=PREPARATION_AUTHORITY,
        )
        return
    if (
        pin.parent_unit_id
        == package_validation_receipt_completion(TARGET_PACKAGE_REF).parent_unit_id
    ):
        work = materialize_package_validation_receipt(queue, TARGET_PACKAGE_REF)
        assert work.unit_id == pin.parent_unit_id
        lease = queue.claim("trusted-receipt-importer")
        assert lease is not None and lease.unit_id == pin.parent_unit_id
        finish_package_validation_receipt(
            queue,
            lease,
            package_ref=TARGET_PACKAGE_REF,
            receipt_payload=SOURCE_RECEIPT.to_json(),
            trusted_validator_revision=VALIDATOR_REVISION,
            trusted_contract_revision=CONTRACT_REVISION,
            trusted_dependency_digests=SOURCE_RECEIPT_DEPENDENCIES,
            trusted_receipt_sha256=SOURCE_RECEIPT.validation_receipt_sha256,
        )
        return
    queue.enqueue(pin.parent_unit_id, kind="prerequisite", input_digest=pin.digest)
    lease = queue.claim("prerequisite-publisher")
    assert lease is not None and lease.unit_id == pin.parent_unit_id
    queue.finish(
        lease,
        TerminalOutcome.ACCEPTED,
        output_digest=pin.digest,
        completion_revision=pin.revision,
    )


def test_blocked_plan_creates_no_queue_or_workspace(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")

    assert materialize_package_execution_plan(queue, _blocked_plan()) is None
    assert not queue.database.exists()
    assert not queue.attempts_root.exists()


def test_materialization_maps_exact_frozen_plan_and_is_idempotent(queue: Queue) -> None:
    plan = _full_plan()
    frozen = freeze_package_execution_plan(plan)
    for pin in frozen.required_completions:
        _materialize_prerequisite(queue, pin)

    first = materialize_package_execution_plan(queue, plan, priority=17)
    second = materialize_package_execution_plan(queue, plan, priority=17)

    assert first == second
    assert first is not None
    assert first.unit_id == package_queue_unit_id(TARGET_PACKAGE_REF_ID)
    assert first.input_digest == frozen.digest
    with sqlite3.connect(queue.database) as connection:
        unit = connection.execute(
            "SELECT kind, cluster_id, priority, input_digest FROM work_units WHERE unit_id = ?",
            (first.unit_id,),
        ).fetchone()
        capabilities = connection.execute(
            """
            SELECT capability, required_revision, required_digest
            FROM capability_requirements WHERE unit_id = ? ORDER BY capability
            """,
            (first.unit_id,),
        ).fetchall()
        dependencies = connection.execute(
            """
            SELECT parent_unit_id, required_revision, required_digest
            FROM dependencies WHERE unit_id = ? ORDER BY parent_unit_id
            """,
            (first.unit_id,),
        ).fetchall()
    assert unit == (PACKAGE_QUEUE_UNIT_KIND, CLUSTER_ID, 17, frozen.digest)
    assert capabilities == [
        (pin.name, pin.revision, pin.digest) for pin in frozen.required_capabilities
    ]
    assert dependencies == [
        (pin.parent_unit_id, pin.revision, pin.digest) for pin in frozen.required_completions
    ]


def test_materialization_waits_for_the_frozen_package_validation_receipt(
    queue: Queue,
) -> None:
    plan = _full_plan()
    frozen = freeze_package_execution_plan(plan)
    receipt_completion = package_validation_receipt_completion(TARGET_PACKAGE_REF)
    for pin in frozen.required_capabilities:
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)
    for pin in frozen.required_completions:
        if pin.parent_unit_id != receipt_completion.parent_unit_id:
            if pin.parent_unit_id == plan_module.preparation_queue_unit_id(TARGET_PACKAGE_REF_ID):
                materialize_package_preparation(
                    queue,
                    package_ref=TARGET_PACKAGE_REF,
                    package_local=plan.package_local,
                    authority=PREPARATION_AUTHORITY,
                )
                lease = queue.claim("preparation-publisher")
                assert lease is not None and lease.unit_id == pin.parent_unit_id
                finish_package_preparation(
                    queue,
                    lease,
                    package_ref=TARGET_PACKAGE_REF,
                    package_local=plan.package_local,
                    receipt=PREPARATION_RECEIPT,
                    authority=PREPARATION_AUTHORITY,
                )
                continue
            queue.enqueue(pin.parent_unit_id, kind="prerequisite", input_digest=pin.digest)
            lease = queue.claim("prerequisite-publisher")
            assert lease is not None and lease.unit_id == pin.parent_unit_id
            queue.finish(
                lease,
                TerminalOutcome.ACCEPTED,
                output_digest=pin.digest,
                completion_revision=pin.revision,
            )
    with pytest.raises(QueueConflictError, match="could not materialize"):
        materialize_package_execution_plan(queue, plan)

    with pytest.raises(ValueError, match="reserved work unit"):
        queue.enqueue(
            receipt_completion.parent_unit_id,
            kind="prerequisite",
            input_digest=receipt_completion.digest,
        )
    with pytest.raises(ValueError, match="trusted completion kinds require"):
        queue.enqueue(
            "ordinary-unit",
            kind="trusted-package-validation-receipt",
            input_digest=receipt_completion.digest,
        )
    materialize_package_validation_receipt(queue, TARGET_PACKAGE_REF)
    materialized = materialize_package_execution_plan(queue, plan)
    assert materialized is not None
    lease = queue.claim("receipt-publisher")
    assert lease is not None and lease.unit_id == receipt_completion.parent_unit_id
    with pytest.raises(QueueConflictError, match="trusted publication adapter"):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest=receipt_completion.digest,
            completion_revision=receipt_completion.revision,
        )
    finish_package_validation_receipt(
        queue,
        lease,
        package_ref=TARGET_PACKAGE_REF,
        receipt_payload=SOURCE_RECEIPT.to_json(),
        trusted_validator_revision=VALIDATOR_REVISION,
        trusted_contract_revision=CONTRACT_REVISION,
        trusted_dependency_digests=SOURCE_RECEIPT_DEPENDENCIES,
        trusted_receipt_sha256=SOURCE_RECEIPT.validation_receipt_sha256,
    )

    lease = queue.claim("package-worker")
    assert lease is not None and lease.unit_id == materialized.unit_id


def test_same_package_reference_with_changed_plan_conflicts(queue: Queue) -> None:
    original = _full_plan()
    changed = _full_plan(reason="changed_routing_evidence")
    for pin in freeze_package_execution_plan(original).required_completions:
        _materialize_prerequisite(queue, pin)
    materialize_package_execution_plan(queue, original)

    with pytest.raises(QueueConflictError, match="materialized work unit changed"):
        materialize_package_execution_plan(queue, changed)


def test_all_reuse_still_materializes_distinct_package_unit(queue: Queue) -> None:
    plan = _reuse_plan()
    frozen = freeze_package_execution_plan(plan)
    for pin in frozen.required_completions:
        _materialize_prerequisite(queue, pin)

    materialized = materialize_package_execution_plan(queue, plan)

    assert materialized is not None
    assert materialized.unit_id not in {pin.parent_unit_id for pin in frozen.required_completions}
    assert queue.status(materialized.unit_id) is WorkUnitStatus.READY


def test_finish_builds_bound_output_and_publishes_its_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    queue: Queue,
) -> None:
    plan = _full_plan()
    report_root, receipt = _stub_valid_report(monkeypatch, tmp_path, plan)
    assert receipt.validation_receipt_sha256 is not None
    _publish_prerequisites(queue, plan)
    materialized = materialize_package_execution_plan(queue, plan)
    assert materialized is not None
    lease = queue.claim("package-worker")
    assert lease is not None and lease.unit_id == materialized.unit_id

    finished = finish_package_execution_plan(
        queue,
        lease,
        execution_plan=plan,
        report_root=report_root,
        trusted_dependencies=TRUSTED_DEPENDENCIES,
        evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
    )

    assert finished.queue_result.disposition is FinishDisposition.COMPLETED
    assert finished.queue_result.output_digest == finished.output.content_id
    assert finished.output.execution_plan_id == materialized.input_digest
    assert finished.output.validation_receipt_sha256 == receipt.validation_receipt_sha256


def test_validated_package_output_rejects_generic_completion(queue: Queue) -> None:
    plan = _full_plan()
    _publish_prerequisites(queue, plan)
    materialized = materialize_package_execution_plan(queue, plan)
    assert materialized is not None
    lease = queue.claim("package-worker")
    assert lease is not None and lease.unit_id == materialized.unit_id

    with pytest.raises(QueueConflictError, match="trusted publication adapter"):
        queue.finish_accepted_if_input_matches(
            lease,
            expected_input_digest=materialized.input_digest,
            output_digest=SHA_A,
            completion_revision="caller-selected-v1",
        )

    assert queue.status(materialized.unit_id) is WorkUnitStatus.LEASED


def test_finish_rejects_missing_report_before_publication(
    tmp_path: Path,
    queue: Queue,
) -> None:
    plan = _full_plan()
    _publish_prerequisites(queue, plan)
    materialized = materialize_package_execution_plan(queue, plan)
    assert materialized is not None
    lease = queue.claim("package-worker")
    assert lease is not None and lease.unit_id == materialized.unit_id

    with pytest.raises(EquivalenceError, match="validated artifact identity"):
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=plan,
            report_root=tmp_path / "missing-report",
            trusted_dependencies=TRUSTED_DEPENDENCIES,
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
        )

    assert queue.status(materialized.unit_id) is WorkUnitStatus.LEASED
    with sqlite3.connect(queue.database) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM formal_completions WHERE unit_id = ?",
                (lease.unit_id,),
            ).fetchone()[0]
            == 0
        )


def test_finish_rejects_plan_drift_without_an_accepted_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    queue: Queue,
) -> None:
    original = _full_plan()
    changed = _full_plan(reason="changed_routing_evidence")
    report_root, _ = _stub_valid_report(monkeypatch, tmp_path, changed)
    _publish_prerequisites(queue, original)
    materialized = materialize_package_execution_plan(queue, original)
    assert materialized is not None
    lease = queue.claim("package-worker")
    assert lease is not None and lease.unit_id == materialized.unit_id
    with pytest.raises(
        PackagePlanInputMismatchError, match="does not match the leased queue input"
    ) as raised:
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=changed,
            report_root=report_root,
            trusted_dependencies=TRUSTED_DEPENDENCIES,
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
        )

    assert raised.value.output.execution_plan_id == freeze_package_execution_plan(changed).digest
    assert raised.value.queue_result.output_digest == raised.value.output.content_id
    assert queue.status(materialized.unit_id) is WorkUnitStatus.REPAIR_REQUIRED
    assert lease.workspace.is_dir()
    with sqlite3.connect(queue.database) as connection:
        assert connection.execute(
            "SELECT outcome, output_digest FROM attempt_terminals WHERE attempt_id = ?",
            (lease.attempt_id,),
        ).fetchone() == (TerminalOutcome.INPUT_MISMATCH.value, raised.value.output.content_id)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM formal_completions WHERE unit_id = ?",
                (lease.unit_id,),
            ).fetchone()[0]
            == 0
        )


def test_finish_fences_plan_mutation_while_output_is_built(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    queue: Queue,
) -> None:
    plan = _full_plan()
    report_root, receipt = _stub_valid_report(monkeypatch, tmp_path, plan)
    assert receipt.validation_receipt_sha256 is not None
    _publish_prerequisites(queue, plan)
    materialized = materialize_package_execution_plan(queue, plan)
    assert materialized is not None
    lease = queue.claim("package-worker")
    assert lease is not None and lease.unit_id == materialized.unit_id
    original_builder = plan_module.build_validated_package_output

    def build_then_mutate(
        *,
        execution_plan: PackageExecutionPlan,
        receipt: ValidationReceipt,
        trusted_validation_receipt_sha256: str,
    ) -> ValidatedPackageOutput:
        output = original_builder(
            execution_plan=execution_plan,
            receipt=receipt,
            trusted_validation_receipt_sha256=trusted_validation_receipt_sha256,
        )
        object.__setattr__(plan, "package_local", _local_plan(version_name="1.8"))
        return output

    monkeypatch.setattr(
        plan_module,
        "build_validated_package_output",
        build_then_mutate,
    )

    with pytest.raises(
        PackagePlanInputMismatchError, match="does not match the leased queue input"
    ) as raised:
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=plan,
            report_root=report_root,
            trusted_dependencies=TRUSTED_DEPENDENCIES,
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
        )

    assert queue.status(materialized.unit_id) is WorkUnitStatus.REPAIR_REQUIRED
    assert raised.value.queue_result.output_digest == raised.value.output.content_id
    assert lease.workspace.is_dir()
    with sqlite3.connect(queue.database) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM formal_completions WHERE unit_id = ?",
                (lease.unit_id,),
            ).fetchone()[0]
            == 0
        )


def test_finish_requires_matching_attempt_and_work_unit_input_digests(queue: Queue) -> None:
    queue.enqueue("unit", kind="test", input_digest=SHA_A)
    lease = queue.claim("worker")
    assert lease is not None
    with sqlite3.connect(queue.database) as connection:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'attempts_no_update'"
        ).fetchone()[0]
        assert isinstance(trigger_sql, str)
        connection.execute("DROP TRIGGER attempts_no_update")
        connection.execute(
            "UPDATE attempts SET input_digest = ? WHERE attempt_id = ?",
            (SHA_B, lease.attempt_id),
        )
        connection.execute(trigger_sql)
        connection.commit()

    with pytest.raises(InputDigestMismatchError):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest=SHA_C,
            completion_revision="result-v1",
            expected_input_digest=SHA_A,
        )
    assert queue.status("unit") is WorkUnitStatus.LEASED


def test_atomic_input_checked_finish_has_no_recovery_window(
    monkeypatch: pytest.MonkeyPatch,
    queue: Queue,
) -> None:
    queue.enqueue("unit", kind="test", input_digest=SHA_A)
    lease = queue.claim("worker")
    assert lease is not None
    competitor = Queue(queue.database, queue.attempts_root)
    original_compare = Queue._input_digests_match
    recovery_results: list[int] = []

    def expire_after_live_check(
        connection: sqlite3.Connection,
        compared_lease: Lease,
        expected_input_digest: str,
    ) -> bool:
        assert compared_lease is lease
        connection.execute(
            "UPDATE leases SET expires_at = 1 WHERE attempt_id = ?",
            (lease.attempt_id,),
        )
        recovery_results.append(competitor.recover())
        return original_compare(connection, lease, expected_input_digest)

    monkeypatch.setattr(
        Queue,
        "_input_digests_match",
        staticmethod(expire_after_live_check),
    )

    result = queue.finish_accepted_if_input_matches(
        lease,
        expected_input_digest=SHA_B,
        output_digest=SHA_C,
        completion_revision="result-v1",
    )

    assert recovery_results == [0]
    assert result.disposition is InputCheckedFinishDisposition.INPUT_MISMATCH
    assert result.finish_result.output_digest == SHA_C
    assert queue.status("unit") is WorkUnitStatus.REPAIR_REQUIRED
    with sqlite3.connect(queue.database) as connection:
        assert connection.execute(
            "SELECT outcome, output_digest FROM attempt_terminals WHERE attempt_id = ?",
            (lease.attempt_id,),
        ).fetchone() == (TerminalOutcome.INPUT_MISMATCH.value, SHA_C)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM formal_completions WHERE unit_id = 'unit'"
            ).fetchone()[0]
            == 0
        )


def test_finish_rejects_lease_for_a_different_package_plan(queue: Queue) -> None:
    plan = _full_plan()
    queue.enqueue("unrelated", kind="test", input_digest=SHA_A)
    lease = queue.claim("worker")
    assert lease is not None

    with pytest.raises(QueueConflictError, match="lease does not belong"):
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=plan,
            report_root=Path("unused"),
            trusted_dependencies=TRUSTED_DEPENDENCIES,
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
        )


def test_wrong_lease_is_untouched_before_report_validation(
    monkeypatch: pytest.MonkeyPatch,
    queue: Queue,
) -> None:
    plan = _full_plan()
    queue.enqueue("unrelated", kind="test", input_digest=SHA_A)
    lease = queue.claim("worker")
    assert lease is not None

    def unexpected_validation(*args: object, **kwargs: object) -> ValidationReceipt:
        pytest.fail("wrong lease reached report validation")

    monkeypatch.setattr(validator_module, "validate_report_bundle", unexpected_validation)

    with pytest.raises(QueueConflictError, match="lease does not belong"):
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=plan,
            report_root=Path("unused"),
            trusted_dependencies=TRUSTED_DEPENDENCIES,
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
        )

    assert queue.status("unrelated") is WorkUnitStatus.LEASED
    with sqlite3.connect(queue.database) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM attempt_terminals WHERE attempt_id = ?",
                (lease.attempt_id,),
            ).fetchone()[0]
            == 0
        )
