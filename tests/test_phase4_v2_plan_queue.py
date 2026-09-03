"""Adversarial tests for package-plan queue publication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.equivalence.core as equivalence_core_module
import tools.phase4_v2.equivalence.execution as execution_module
import tools.phase4_v2.equivalence.inventory as inventory_module
import tools.phase4_v2.equivalence.plan as plan_module
import tools.phase4_v2.preflight.registry as registry_module
import tools.phase4_v2.validator as validator_module
from tools.phase4_v2.equivalence.core import (
    EQUIVALENCE_SCHEMA_REVISION,
    LEDGER_DECISION_REVISION,
    ApplicationRoot,
    AuthenticatedValidatorEnvelope,
    EquivalenceError,
    ExtractorCapability,
    LedgerDecision,
    Route,
    RoutingPins,
    authenticated_validator_envelope_payload,
    frozen_package_ref_from_validator_envelope,
    load_activated_validator_authority,
    load_authenticated_validator_envelope,
    validate_authenticated_validator_envelope,
    validator_authority_payload,
    validator_authority_pin_payload,
    validator_envelope_signing_bytes,
)
from tools.phase4_v2.equivalence.execution import (
    execution_authority_payload,
    execution_authority_pin_payload,
    execution_envelope_payload,
    execution_envelope_signing_bytes,
    load_activated_execution_authority,
    load_authenticated_package_execution_envelope,
)
from tools.phase4_v2.equivalence.inventory import (
    ActivatedInventoryAuthority,
    AuthenticatedTargetInventoryEnvelope,
    InventoryAuthenticationError,
    accept_target_inventory,
    inventory_authority_payload,
    inventory_authority_pin_payload,
    load_activated_inventory_authority,
    load_authenticated_target_inventory_envelope,
    target_inventory_envelope_payload,
    target_inventory_signing_bytes,
    validate_target_inventory_envelope,
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
    finish_target_inventory,
    materialize_package_execution_plan,
    materialize_package_preparation,
    materialize_package_validation_receipt,
    materialize_target_inventory,
    package_queue_unit_id,
)
from tools.phase4_v2.preflight.execution import (
    CANDIDATE_CONTRACT_SHA256,
    EXECUTION_PROFILE_REVISION,
    InvocationRecord,
    OutputMember,
    StreamDigest,
    ToolRecord,
)
from tools.phase4_v2.preflight.registry import (
    PREPARATION_AUTHORITY_SCHEMA,
    PREPARATION_RECEIPT_REVISION,
    TOOL_REGISTRY_SCHEMA,
    PreparationReceipt,
    load_activated_preparation_authority,
)
from tools.phase4_v2.queue import (
    CompletionDependencyPin,
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
    ValidatedRootEvidenceAttestation,
    ValidatedRootEvidenceMember,
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

_VALIDATOR_KEY = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SHA_B))
_VALIDATOR_AUTHORITY_PAYLOAD = validator_authority_payload(
    authority_id="phase4-validator",
    public_key=_VALIDATOR_KEY.public_key()
    .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    .hex(),
    validator_revision=VALIDATOR_REVISION,
    contract_revision=CONTRACT_REVISION,
)
_VALIDATOR_ACTIVATION_SHA256 = json.loads(
    validator_authority_pin_payload(_VALIDATOR_AUTHORITY_PAYLOAD)
)["activation_sha256"]
_INVENTORY_KEY = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SHA_A))
_INVENTORY_AUTHORITY_PAYLOAD = inventory_authority_payload(
    authority_id="phase4-inventory",
    public_key=_INVENTORY_KEY.public_key()
    .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    .hex(),
    generation=1,
)
_INVENTORY_ACTIVATION_SHA256 = json.loads(
    inventory_authority_pin_payload(_INVENTORY_AUTHORITY_PAYLOAD)
)["activation_sha256"]
_EXECUTION_KEY = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SHA_C))
_EXECUTION_AUTHORITY_PAYLOAD = execution_authority_payload(
    authority_id="phase4-execution",
    public_key=_EXECUTION_KEY.public_key()
    .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    .hex(),
    generation=1,
)
_EXECUTION_ACTIVATION_SHA256 = json.loads(
    execution_authority_pin_payload(_EXECUTION_AUTHORITY_PAYLOAD)
)["activation_sha256"]


def _validator_envelope() -> AuthenticatedValidatorEnvelope:
    authority = load_activated_validator_authority(_VALIDATOR_AUTHORITY_PAYLOAD)
    receipt_payload = SOURCE_RECEIPT.to_json().encode()
    signature = _VALIDATOR_KEY.sign(
        validator_envelope_signing_bytes(receipt_payload, authority)
    ).hex()
    envelope_payload = authenticated_validator_envelope_payload(
        receipt_payload,
        authority,
        signature=signature,
    )
    return load_authenticated_validator_envelope(envelope_payload, authority=authority)


with patch.object(
    equivalence_core_module,
    "_read_protected_validator_pin",
    return_value=_VALIDATOR_ACTIVATION_SHA256,
):
    TARGET_PACKAGE_REF = frozen_package_ref_from_validator_envelope(_validator_envelope())
TARGET_PACKAGE_REF_ID = TARGET_PACKAGE_REF.content_id
_INVENTORIES: dict[str, AcceptedTargetRootInventory] = {}


@pytest.fixture(autouse=True)
def _activate_test_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        equivalence_core_module,
        "_read_protected_validator_pin",
        lambda: _VALIDATOR_ACTIVATION_SHA256,
    )
    monkeypatch.setattr(
        inventory_module,
        "_read_protected_inventory_pin",
        lambda: _INVENTORY_ACTIVATION_SHA256,
    )
    monkeypatch.setattr(
        execution_module,
        "_read_protected_execution_pin",
        lambda: _EXECUTION_ACTIVATION_SHA256,
    )
    monkeypatch.setattr(
        registry_module,
        "_read_protected_activation_digest",
        lambda: hashlib.sha256(_AUTHORITY_PAYLOAD).hexdigest(),
    )
    monkeypatch.setattr(
        plan_module,
        "validate_preparation_receipt_authority",
        lambda receipt, _authority: receipt,
    )


_AUTHORITY_DATA = {
    "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
    "execution_profile_revision": EXECUTION_PROFILE_REVISION,
    "execution_profile_sha256": SHA_E,
    "executor_public_key": Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SHA_A))
    .public_key()
    .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    .hex(),
    "pipeline_revision": "phase4-v2-preparation-pipeline-v1",
    "registry_revision": TOOL_REGISTRY_SCHEMA,
    "registry_sha256": SHA_D,
    "schema": PREPARATION_AUTHORITY_SCHEMA,
}
_AUTHORITY_PAYLOAD = (
    json.dumps(_AUTHORITY_DATA, sort_keys=True, separators=(",", ":")).encode() + b"\n"
)
with patch.object(
    registry_module,
    "_read_protected_activation_digest",
    return_value=hashlib.sha256(_AUTHORITY_PAYLOAD).hexdigest(),
):
    PREPARATION_AUTHORITY = load_activated_preparation_authority(_AUTHORITY_PAYLOAD)
PREPARATION_RECEIPT = object.__new__(PreparationReceipt)
_PREPARATION_PRODUCER = CapabilityPin(
    "apktool",
    PREPARATION_AUTHORITY.pipeline_revision,
    SHA_E,
)
_PREPARATION_INVOCATION = InvocationRecord(
    member="base.apk",
    input_sha256=SHA_B,
    route=_PREPARATION_PRODUCER.name,
    cache_key=SHA_A,
    tool=ToolRecord(
        executable="apktool",
        binary_bytes=1,
        binary_sha256=_PREPARATION_PRODUCER.digest,
        runtime_files=None,
        runtime_sha256=None,
        version_arguments=(),
        version="fixture",
        version_stdout=StreamDigest(0, SHA_0),
        version_stderr=StreamDigest(0, SHA_0),
        failure=None,
    ),
    arguments=(),
    flags=(),
    status="COMPLETE",
    exit_code=0,
    stdout=StreamDigest(0, SHA_0),
    stderr=StreamDigest(0, SHA_0),
    warnings=(),
    failures=(),
    outputs=(OutputMember("decoded/AndroidManifest.xml", 1, SHA_C),),
)
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
    "executor_public_key": PREPARATION_AUTHORITY.executor_public_key,
    "execution_signature": "0" * 128,
    "invocations": (_PREPARATION_INVOCATION,),
    "candidates": (),
    "manifest_bytes": b"",
    "candidate_index_bytes": b"",
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
        evidence_producer_capabilities=(_PREPARATION_PRODUCER,),
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
    authority = load_activated_inventory_authority(_INVENTORY_AUTHORITY_PAYLOAD)
    extractor = ExtractorCapability("inventory", SHA_A, SHA_B, "inventory-v1")
    unsigned = target_inventory_envelope_payload(
        package_ref=TARGET_PACKAGE_REF,
        inventory=inventory,
        extractor=extractor,
        authority=authority,
        signature="0" * 128,
    )
    payload = json.loads(unsigned)["payload"]
    canonical = target_inventory_envelope_payload(
        package_ref=TARGET_PACKAGE_REF,
        inventory=inventory,
        extractor=extractor,
        authority=authority,
        signature=_INVENTORY_KEY.sign(target_inventory_signing_bytes(payload)).hex(),
    )
    accepted = accept_target_inventory(
        load_authenticated_target_inventory_envelope(
            canonical, authority=authority, package_ref=TARGET_PACKAGE_REF
        )
    )
    _INVENTORIES[accepted.completion.parent_unit_id] = accepted
    return accepted


def _publish_inventory(queue: Queue, accepted: AcceptedTargetRootInventory) -> None:
    envelope = load_authenticated_target_inventory_envelope(
        accepted.canonical_envelope,
        authority=accepted.authority,
        package_ref=accepted.package_ref,
    )
    for pin in (
        inventory_module.inventory_authority_capability(envelope.authority),
        inventory_module.inventory_extractor_capability(envelope.extractor),
    ):
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)
    materialize_target_inventory(queue, envelope)
    lease = queue.claim("inventory-publisher")
    assert lease is not None and lease.unit_id == accepted.completion.parent_unit_id
    published, _ = finish_target_inventory(queue, lease, envelope=envelope)
    assert published == accepted


def test_target_inventory_boundary_rejects_forgery_rotation_and_generic_finish(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(InventoryAuthenticationError):
        ActivatedInventoryAuthority()
    with pytest.raises(InventoryAuthenticationError):
        AuthenticatedTargetInventoryEnvelope()
    accepted = _accepted_inventory((SHA_C, SHA_D))
    envelope = load_authenticated_target_inventory_envelope(
        accepted.canonical_envelope,
        authority=accepted.authority,
        package_ref=accepted.package_ref,
    )
    for pin in (
        inventory_module.inventory_authority_capability(envelope.authority),
        inventory_module.inventory_extractor_capability(envelope.extractor),
    ):
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)
    work = materialize_target_inventory(queue, envelope)
    lease = queue.claim("inventory-attacker")
    assert lease is not None
    with pytest.raises(QueueConflictError, match="trusted publication adapter"):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest=accepted.inventory.content_id,
            completion_revision=TARGET_ROOT_INVENTORY_REVISION,
        )
    monkeypatch.setattr(inventory_module, "_read_protected_inventory_pin", lambda: SHA_F)
    with pytest.raises(InventoryAuthenticationError, match="protected activation"):
        validate_target_inventory_envelope(envelope)
    assert work.unit_id == accepted.completion.parent_unit_id


def test_target_inventory_envelope_rejects_transplanted_package() -> None:
    accepted = _accepted_inventory((SHA_C, SHA_D))
    transplanted = frozen_package_ref_from_validator_envelope(_validator_envelope())
    object.__setattr__(transplanted, "artifact_digest", SHA_F)
    with pytest.raises(EquivalenceError, match="authenticated provenance"):
        load_authenticated_target_inventory_envelope(
            accepted.canonical_envelope,
            authority=accepted.authority,
            package_ref=transplanted,
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
    prerequisite_receipt = hashlib.sha256(b"signed-prerequisite").hexdigest()
    prerequisite_capabilities = tuple(
        sorted(
            (
                CapabilityPin("phase4-v2-exact-reuse-authority", "authority-v1", SHA_D),
                CapabilityPin(
                    EXACT_REUSE_PIPELINE_CAPABILITY,
                    EQUIVALENCE_SCHEMA_REVISION,
                    SHA_F,
                ),
                CapabilityPin(
                    "extractor:dex", "dex-implementation-2026.08", extractor.content_id
                ),
            ),
            key=lambda item: item.name,
        )
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
            parent_unit_id=(
                f"{plan_module.EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX}:"
                f"{prerequisite_receipt}"
            ),
        ),
        target_inventory_completion=accepted.completion,
        ledger_decision_completion=CompletionPin(
            f"{plan_module.EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX}:{prerequisite_receipt}",
            LEDGER_DECISION_REVISION,
            decision.content_id,
        ),
        direct_semantic_audit_completion=CompletionPin(
            f"{plan_module.EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX}:{prerequisite_receipt}",
            SEMANTIC_ROOT_COMPLETION_REVISION,
            SHA_1,
        ),
        extractor_capability=CapabilityPin(
            "extractor:dex", "dex-implementation-2026.08", extractor.content_id
        ),
        equivalence_pipeline=CapabilityPin(
            EXACT_REUSE_PIPELINE_CAPABILITY,
            EQUIVALENCE_SCHEMA_REVISION,
            SHA_F,
        ),
        exact_reuse_prerequisite_receipt_sha256=prerequisite_receipt,
        exact_reuse_prerequisite_capabilities=prerequisite_capabilities,
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


def _receipt(
    plan: PackageExecutionPlan,
    *,
    bundle_sha256: str = SHA_D,
    corpus_sha256: str = SHA_A,
    ir_sha256: str = SHA_B,
    lineage_sha256: str = SHA_0,
) -> ValidationReceipt:
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
            ("corpus", corpus_sha256),
            ("evidence_lineage", lineage_sha256),
            ("execution_plan", freeze_package_execution_plan(plan).canonical_sha256),
            ("ir", ir_sha256),
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
        evidence_anchors_checked=1,
        validated_evidence_members=(
            EvidenceMemberAttestation("evidence/source.txt", SHA_B, SHA_D),
        ),
        validated_evidence_anchors=(
            EvidenceAnchorAttestation(
                "root-anchor",
                SHA_B,
                "evidence/source.txt",
                SHA_D,
                0,
                1,
                "/root",
                "utf8",
                SHA_A,
            ),
        ),
        validated_root_evidence=(
            ValidatedRootEvidenceAttestation(
                SHA_E,
                SHA_F,
                SHA_C,
                (ValidatedRootEvidenceMember("evidence/source.txt", SHA_D, ("root-anchor",)),),
            ),
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
    inputs = report_root / "inputs"
    inputs.mkdir(exist_ok=True)
    ir_bytes = b"canonical target IR"
    corpus_bytes = b"canonical target corpus"
    (inputs / "ir.json").write_bytes(ir_bytes)
    (inputs / "corpus.json").write_bytes(corpus_bytes)
    ir_sha256 = hashlib.sha256(ir_bytes).hexdigest()
    corpus_sha256 = hashlib.sha256(corpus_bytes).hexdigest()
    lineage_sha256 = hashlib.sha256(TRUSTED_EVIDENCE_LINEAGE.payload).hexdigest()
    receipt = _receipt(
        plan,
        ir_sha256=ir_sha256,
        corpus_sha256=corpus_sha256,
        lineage_sha256=lineage_sha256,
    )

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
            ir_sha256=ir_sha256,
            schema_sha256=FINAL_IR_SCHEMA_SHA256,
            corpus_sha256=corpus_sha256,
            execution_plan_sha256=freeze_package_execution_plan(plan).canonical_sha256,
            report_schema_sha256=PACKAGE_REPORT_SCHEMA_SHA256,
        )
        assert expected_evidence_lineage is not None
        assert expected_evidence_lineage.payload == TRUSTED_EVIDENCE_LINEAGE.payload
        assert expected_evidence_lineage.expected_manifest_sha256 == lineage_sha256
        assert expected_evidence_lineage.trusted_producers
        assert allow_unbound is False
        return receipt

    monkeypatch.setattr(validator_module, "validate_report_bundle", validate)
    return report_root, receipt


def _execution_envelope(
    plan: PackageExecutionPlan, report_root: Path, receipt: ValidationReceipt
) -> object:
    authority = load_activated_execution_authority(_EXECUTION_AUTHORITY_PAYLOAD)
    frozen = freeze_package_execution_plan(plan)
    assert receipt.validation_receipt_sha256 is not None
    assert receipt.bundle_sha256 is not None
    output = plan_module.build_validated_package_output(
        execution_plan=plan,
        receipt=receipt,
        trusted_validation_receipt_sha256=receipt.validation_receipt_sha256,
    )
    fields = {
        "authority": authority,
        "receipt_bytes": receipt.to_json().encode(),
        "package_ref_id": frozen.target_package_ref_id,
        "execution_plan_sha256": frozen.canonical_sha256,
        "execution_plan_id": frozen.digest,
        "output_content_id": output.content_id,
        "report_bundle_sha256": receipt.bundle_sha256,
        "corpus_sha256": hashlib.sha256(
            (report_root / "inputs" / "corpus.json").read_bytes()
        ).hexdigest(),
        "evidence_lineage_sha256": hashlib.sha256(TRUSTED_EVIDENCE_LINEAGE.payload).hexdigest(),
        "ir_sha256": hashlib.sha256((report_root / "inputs" / "ir.json").read_bytes()).hexdigest(),
    }
    unsigned = execution_envelope_payload(**fields, signature="0" * 128)
    payload = json.loads(unsigned)["payload"]
    signature = _EXECUTION_KEY.sign(execution_envelope_signing_bytes(payload)).hex()
    return load_authenticated_package_execution_envelope(
        execution_envelope_payload(**fields, signature=signature), authority=authority
    )


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    instance = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    instance.initialize()
    return instance


def test_validator_envelope_is_factory_locked_and_protected(queue: Queue) -> None:
    with pytest.raises(EquivalenceError, match="signature verification"):
        AuthenticatedValidatorEnvelope()

    envelope = _validator_envelope()
    assert frozen_package_ref_from_validator_envelope(envelope) == TARGET_PACKAGE_REF
    with (
        patch(
            "tools.phase4_v2.equivalence.core._read_protected_validator_pin",
            return_value=SHA_F,
        ),
        pytest.raises(EquivalenceError, match="protected activation"),
    ):
        load_activated_validator_authority(envelope.authority.canonical_bytes)


def test_validator_envelope_rejects_authority_rotation_after_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _validator_envelope()
    monkeypatch.setattr(equivalence_core_module, "_read_protected_validator_pin", lambda: SHA_F)
    with pytest.raises(EquivalenceError, match="protected activation"):
        validate_authenticated_validator_envelope(envelope)


def test_queue_rejects_validator_authority_rotation_after_claim(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope = _validator_envelope()
    materialize_package_validation_receipt(queue, envelope)
    lease = queue.claim("validator-importer")
    assert lease is not None
    monkeypatch.setattr(equivalence_core_module, "_read_protected_validator_pin", lambda: SHA_F)
    with pytest.raises(EquivalenceError, match="protected activation"):
        finish_package_validation_receipt(queue, lease, envelope=envelope)
    unit = next(item for item in queue.snapshot().units if item.unit_id == lease.unit_id)
    assert unit.status is WorkUnitStatus.LEASED


def test_validator_envelope_rejects_signed_payload_tampering(queue: Queue) -> None:
    envelope = _validator_envelope()
    tampered = json.loads(envelope.canonical_bytes)
    tampered["receipt"]["bundle_sha256"] = SHA_A
    tampered_payload = json.dumps(
        tampered,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    with pytest.raises(EquivalenceError, match="signature is invalid"):
        load_authenticated_validator_envelope(
            tampered_payload,
            authority=envelope.authority,
        )


def test_validator_envelope_cannot_complete_a_transplanted_package(queue: Queue) -> None:
    envelope = _validator_envelope()
    transplanted = frozen_package_ref_from_validator_envelope(envelope)
    object.__setattr__(transplanted, "validation_receipt_sha256", SHA_F)
    with pytest.raises(EquivalenceError, match="authenticated provenance"):
        package_validation_receipt_completion(transplanted)


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


def test_preparation_finish_rejects_protected_authority_rotation(
    monkeypatch: pytest.MonkeyPatch, queue: Queue
) -> None:
    _activate_preparation_capabilities(queue)
    work = materialize_package_preparation(
        queue,
        package_ref=TARGET_PACKAGE_REF,
        package_local=_local_plan(),
        authority=PREPARATION_AUTHORITY,
    )
    lease = queue.claim("preparation-worker")
    assert lease is not None
    monkeypatch.setattr(registry_module, "_read_protected_activation_digest", lambda: SHA_F)

    with pytest.raises(RuntimeError, match="activated"):
        finish_package_preparation(
            queue,
            lease,
            package_ref=TARGET_PACKAGE_REF,
            package_local=_local_plan(),
            receipt=PREPARATION_RECEIPT,
            authority=PREPARATION_AUTHORITY,
        )

    unit = next(item for item in queue.snapshot().units if item.unit_id == work.unit_id)
    assert unit.output_digest is None


def test_preparation_adapter_rejects_unpinned_and_transplanted_receipts(queue: Queue) -> None:
    unit_id = plan_module.preparation_queue_unit_id(TARGET_PACKAGE_REF_ID)
    with pytest.raises(QueueConflictError, match="authenticated typed materializer"):
        queue.materialize_work_unit(
            unit_id,
            kind=plan_module.PREPARATION_QUEUE_UNIT_KIND,
            input_digest=SHA_A,
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


def test_plan_receipt_validation_reauthenticates_protected_preparation_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = freeze_package_execution_plan(_full_plan())
    monkeypatch.setattr(
        plan_module,
        "validate_preparation_receipt_authority",
        registry_module.validate_preparation_receipt_authority,
    )
    monkeypatch.setattr(registry_module, "_read_protected_activation_digest", lambda: SHA_F)

    with pytest.raises(EquivalenceError, match="producer authentication failed"):
        validate_preparation_receipt_for_plan(
            frozen,
            PREPARATION_RECEIPT,
            PREPARATION_AUTHORITY,
        )


def _publish_prerequisites(queue: Queue, plan: PackageExecutionPlan) -> None:
    frozen = freeze_package_execution_plan(plan)
    receipt_completion = package_validation_receipt_completion(TARGET_PACKAGE_REF)
    for pin in frozen.required_capabilities:
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)
    for pin in frozen.required_completions:
        if pin.parent_unit_id in _INVENTORIES:
            _publish_inventory(queue, _INVENTORIES[pin.parent_unit_id])
            continue
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
            envelope = _validator_envelope()
            assert frozen_package_ref_from_validator_envelope(envelope) == TARGET_PACKAGE_REF
            materialize_package_validation_receipt(queue, envelope)
            lease = queue.claim("trusted-receipt-importer")
            assert lease is not None and lease.unit_id == pin.parent_unit_id
            finish_package_validation_receipt(
                queue,
                lease,
                envelope=envelope,
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
    if pin.parent_unit_id in _INVENTORIES:
        _publish_inventory(queue, _INVENTORIES[pin.parent_unit_id])
        return
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
        envelope = _validator_envelope()
        work = materialize_package_validation_receipt(queue, envelope)
        assert work.unit_id == pin.parent_unit_id
        lease = queue.claim("trusted-receipt-importer")
        assert lease is not None and lease.unit_id == pin.parent_unit_id
        finish_package_validation_receipt(
            queue,
            lease,
            envelope=envelope,
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
            if pin.parent_unit_id in _INVENTORIES:
                _publish_inventory(queue, _INVENTORIES[pin.parent_unit_id])
                continue
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
    envelope = _validator_envelope()
    materialize_package_validation_receipt(queue, envelope)
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
        envelope=envelope,
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


def test_all_reuse_rejects_unbacked_prerequisite_completion_rows(queue: Queue) -> None:
    plan = _reuse_plan()
    frozen = freeze_package_execution_plan(plan)
    for pin in frozen.required_completions:
        if pin.parent_unit_id.startswith("exact-reuse-"):
            continue
        _materialize_prerequisite(queue, pin)

    with pytest.raises(DependencyNotSatisfiedError, match="exact-reuse"):
        materialize_package_execution_plan(queue, plan)
    assert all(
        item.unit_id != package_queue_unit_id(TARGET_PACKAGE_REF_ID)
        for item in queue.snapshot().units
    )


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
        evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
        execution_envelope=_execution_envelope(plan, report_root, receipt),
    )

    assert finished.queue_result.disposition is FinishDisposition.COMPLETED
    assert finished.queue_result.output_digest == finished.output.content_id
    assert finished.output.execution_plan_id == materialized.input_digest
    assert finished.output.validation_receipt_sha256 == receipt.validation_receipt_sha256


def test_finish_rejects_execution_authority_rotation_after_envelope_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, queue: Queue
) -> None:
    plan = _full_plan()
    report_root, receipt = _stub_valid_report(monkeypatch, tmp_path, plan)
    envelope = _execution_envelope(plan, report_root, receipt)
    _publish_prerequisites(queue, plan)
    materialized = materialize_package_execution_plan(queue, plan)
    assert materialized is not None
    lease = queue.claim("package-worker")
    assert lease is not None
    monkeypatch.setattr(execution_module, "_read_protected_execution_pin", lambda: SHA_F)

    with pytest.raises(ValueError, match="protected activation"):
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=plan,
            report_root=report_root,
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
            execution_envelope=envelope,
        )

    unit = next(item for item in queue.snapshot().units if item.unit_id == materialized.unit_id)
    assert unit.output_digest is None


def test_finish_rejects_materialized_plan_requirement_tampering(
    queue: Queue,
) -> None:
    plan = _full_plan()
    frozen = freeze_package_execution_plan(plan)
    capabilities = tuple(
        plan_module.CapabilityPin(item.name, item.revision, item.digest)
        for item in frozen.required_capabilities
    )
    forged = (replace(capabilities[0], digest=SHA_F), *capabilities[1:])
    dependencies = tuple(
        CompletionDependencyPin(item.parent_unit_id, item.revision, item.digest)
        for item in frozen.required_completions
    )

    with pytest.raises(QueueConflictError, match="exact frozen plan"):
        queue._materialize_authenticated_row(
            package_queue_unit_id(frozen.target_package_ref_id),
            authentication=plan,
            kind=PACKAGE_QUEUE_UNIT_KIND,
            capability_pins=forged,
            dependency_pins=dependencies,
            input_digest=frozen.digest,
            cluster_id=frozen.cluster_id,
        )


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

    with pytest.raises(QueueConflictError, match="report input is unavailable"):
        finish_package_execution_plan(
            queue,
            lease,
            execution_plan=plan,
            report_root=tmp_path / "missing-report",
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
            execution_envelope=object(),
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
    report_root, receipt = _stub_valid_report(monkeypatch, tmp_path, changed)
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
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
            execution_envelope=_execution_envelope(changed, report_root, receipt),
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
    envelope = _execution_envelope(plan, report_root, receipt)

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
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
            execution_envelope=envelope,
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
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
            execution_envelope=object(),
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
            evidence_lineage_payload=TRUSTED_EVIDENCE_LINEAGE.payload,
            execution_envelope=object(),
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
