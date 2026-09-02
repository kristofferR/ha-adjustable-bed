"""Hostile tests for immutable Phase 4 v2 package execution plans."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import replace
from typing import cast

import pytest

import tools.phase4_v2.equivalence.plan as plan_module
from tools.phase4_v2.equivalence import (
    EQUIVALENCE_SCHEMA_REVISION,
    EXACT_REUSE_PIPELINE_CAPABILITY,
    LOCAL_ONLY_DOMAINS,
    PACKAGE_EXECUTION_PLAN_REVISION,
    PACKAGE_PIPELINE_CAPABILITY,
    PACKAGE_REPORT_REVISION,
    PACKAGE_REPORT_SCHEMA_SHA256,
    AcceptedTargetRootInventory,
    BlockedRootPlan,
    CapabilityPin,
    CompletionPin,
    EquivalenceError,
    ExactReusePins,
    ExactReuseRootPlan,
    FrozenPackageRef,
    FullAnalysisRootPlan,
    PackageExecutionPlan,
    PackageLocalPlan,
    PackagePlanStatus,
    Route,
    SemanticRootAudit,
    TargetRootInventory,
    TargetRootOccurrence,
    ValidatedPackageOutput,
    build_exact_reuse_root_plan,
    build_package_execution_plan,
    build_semantic_root_audit,
    build_semantic_root_completion,
    build_validated_package_output,
    freeze_package_execution_plan,
)
from tools.phase4_v2.equivalence.core import (
    EXTRACTOR_CAPABILITY_REVISION,
    LEDGER_DECISION_REVISION,
    ApplicationRoot,
    ExtractorCapability,
    LedgerDecision,
    RoutingPins,
)
from tools.phase4_v2.equivalence.plan import (
    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
    SEMANTIC_ROOT_COMPLETION_REVISION,
    TARGET_ROOT_INVENTORY_REVISION,
    package_validation_receipt_completion,
)
from tools.phase4_v2.validator import (
    PACKAGE_BOUND_VALIDATION_PROFILE,
    PACKAGE_CONTRACT_REVISION,
    VALIDATOR_REVISION,
    Diagnostic,
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
SHA_2 = "2" * 64
CLUSTER_ID = "cluster-synthetic"

TARGET_PACKAGE_REF = FrozenPackageRef(
    package_name="org.example.target",
    version_code="17",
    artifact_digest=SHA_B,
    preflight_sha256=SHA_C,
    validation_receipt_sha256=SHA_D,
)
TARGET_PACKAGE_REF_ID = TARGET_PACKAGE_REF.content_id


def local_plan() -> PackageLocalPlan:
    return PackageLocalPlan(
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        package_name="org.example.target",
        version_code="17",
        version_name="1.7",
        target_artifact_digest=SHA_B,
        requirements_sha256=SHA_C,
        pipeline_capability=CapabilityPin(
            PACKAGE_PIPELINE_CAPABILITY, PACKAGE_EXECUTION_PLAN_REVISION, SHA_F
        ),
    )


def accepted_inventory(
    *pairs: tuple[str, str], unit_id: str = "inventory:target"
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
        CompletionPin(unit_id, TARGET_ROOT_INVENTORY_REVISION, inventory.content_id),
    )


def semantic_audit(
    accepted: AcceptedTargetRootInventory,
    *,
    root_id: str = SHA_C,
    semantic_root: str = SHA_0,
    unit_suffix: str | None = None,
    bind_unrelated_source: bool = False,
) -> SemanticRootAudit:
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
        target_root_id=root_id,
        route=Route.EXACT_REUSE,
        reason="exact_executable_identity",
        target_inventory_receipt_sha256=SHA_C,
        source_root_id=source.content_id,
        byte_identity_proof_id=SHA_D,
        inherited_root_id=source.content_id,
        source_audit_receipt_sha256=SHA_1,
        pins=RoutingPins(),
    )
    completion_source = (
        replace(source, occurrence_identity_sha256=SHA_D) if bind_unrelated_source else source
    )
    audit = build_semantic_root_audit(
        source_root=source,
        ledger_decision=decision,
        extractor=extractor,
        accepted_target_inventory=accepted,
        inherited_semantic_root_sha256=semantic_root,
        inherited_semantic_root_completion=build_semantic_root_completion(
            source_root=completion_source,
            inherited_semantic_root_sha256=semantic_root,
            parent_unit_id="semantic-root:source",
        ),
        target_inventory_completion=accepted.completion,
        ledger_decision_completion=CompletionPin(
            f"ledger:{unit_suffix or 'target'}", LEDGER_DECISION_REVISION, decision.content_id
        ),
        direct_semantic_audit_completion=CompletionPin(
            f"audit:{unit_suffix or 'source'}", SEMANTIC_ROOT_COMPLETION_REVISION, SHA_1
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
    return audit


def exact_root(
    accepted: AcceptedTargetRootInventory,
    *,
    root_id: str = SHA_C,
    semantic_root: str = SHA_0,
    unit_suffix: str | None = None,
) -> ExactReuseRootPlan:
    return build_exact_reuse_root_plan(
        semantic_audit(
            accepted,
            root_id=root_id,
            semantic_root=semantic_root,
            unit_suffix=unit_suffix,
        )
    )


def full_root(
    root_id: str = SHA_E,
    occurrence: str = SHA_F,
    *,
    capability_name: str = "analyzer:full",
    capability_digest: str = SHA_A,
    dependencies: tuple[CompletionPin, ...] = (),
) -> FullAnalysisRootPlan:
    return FullAnalysisRootPlan(
        root_id,
        occurrence,
        "no_exact_identity",
        (CapabilityPin(capability_name, "full-implementation-1", capability_digest),),
        dependencies,
    )


def mixed_plan() -> PackageExecutionPlan:
    accepted = accepted_inventory((SHA_C, SHA_D), (SHA_E, SHA_F))
    return build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=local_plan(),
        accepted_target_inventory=accepted,
        root_plans=(
            exact_root(accepted),
            full_root(),
        ),
    )


def receipt(*, bundle: str = SHA_D, plan: PackageExecutionPlan | None = None) -> ValidationReceipt:
    frozen_plan = freeze_package_execution_plan(plan or mixed_plan())
    initial = ValidationReceipt(
        validator_revision=VALIDATOR_REVISION,
        accepted=True,
        source_unchanged=True,
        bundle_sha256=bundle,
        report_manifest_sha256=SHA_E,
        discovered_members=4,
        declared_members=4,
        diagnostics=(),
        dependency_digests=(
            ("corpus", SHA_A),
            ("evidence_lineage", SHA_F),
            ("execution_plan", frozen_plan.digest),
            ("ir", SHA_B),
            ("preflight", SHA_C),
            ("report_schema", PACKAGE_REPORT_SCHEMA_SHA256),
            ("schema", SHA_E),
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
    return replace(initial, validation_receipt_sha256=hashlib.sha256(payload).hexdigest())


def identify_receipt(value: ValidationReceipt) -> ValidationReceipt:
    unsigned = replace(value, validation_receipt_sha256=None)
    payload = json.dumps(
        unsigned.identity_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return replace(unsigned, validation_receipt_sha256=hashlib.sha256(payload).hexdigest())


def test_queue_pins_have_exact_queue_shapes() -> None:
    capability = CapabilityPin("extractor:dex", "revision-1", SHA_A)
    completion = CompletionPin("unit:one", "revision-2", SHA_B)

    assert capability.to_data() == {
        "name": "extractor:dex",
        "revision": "revision-1",
        "digest": SHA_A,
    }
    assert completion.to_data() == {
        "parent_unit_id": "unit:one",
        "revision": "revision-2",
        "digest": SHA_B,
    }


def test_package_local_domains_are_plain_exact_tuple_and_artifact_is_bound() -> None:
    local = local_plan()
    assert type(local.mandatory_domains) is tuple
    assert local.mandatory_domains == LOCAL_ONLY_DOMAINS
    assert local.to_data()["target_artifact_digest"] == SHA_B

    with pytest.raises(EquivalenceError, match="exact mandatory tuple"):
        replace(local, mandatory_domains=cast(tuple[str, ...], list(LOCAL_ONLY_DOMAINS)))
    with pytest.raises(EquivalenceError, match="exact mandatory tuple"):
        replace(local, mandatory_domains=LOCAL_ONLY_DOMAINS[:-1])


def test_inventory_is_authoritative_content_addressed_and_queue_accepted() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D), (SHA_E, SHA_F))
    inventory = accepted.inventory
    assert inventory.root_count == 2
    assert len(inventory.occurrence_root_set_sha256) == 64
    assert accepted.completion.digest == inventory.content_id

    with pytest.raises(EquivalenceError, match="does not accept"):
        AcceptedTargetRootInventory(
            inventory,
            CompletionPin("inventory:target", TARGET_ROOT_INVENTORY_REVISION, SHA_A),
        )


def test_exact_route_binds_every_queue_dependency_unambiguously() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D))
    root = exact_root(accepted)
    data = root.reuse.to_data()

    assert root.route is Route.EXACT_REUSE
    assert data["target_inventory_completion"] == accepted.completion.to_data()
    assert data["ledger_decision_completion"] == {
        "parent_unit_id": "ledger:target",
        "revision": LEDGER_DECISION_REVISION,
        "digest": root.reuse.ledger_decision_completion.digest,
    }
    assert data["direct_semantic_audit_completion"] == {
        "parent_unit_id": "audit:source",
        "revision": SEMANTIC_ROOT_COMPLETION_REVISION,
        "digest": SHA_1,
    }
    assert data["inherited_semantic_root_completion"] == {
        "parent_unit_id": "semantic-root:source",
        "revision": SEMANTIC_ROOT_COMPLETION_REVISION,
        "digest": root.reuse.inherited_semantic_root_completion.digest,
    }
    assert data["extractor_capability"] == {
        "name": "extractor:dex",
        "revision": "dex-implementation-2026.08",
        "digest": root.reuse.extractor_capability.digest,
    }
    assert data["extractor_record_revision"] == EXTRACTOR_CAPABILITY_REVISION
    assert data["equivalence_pipeline"] == {
        "name": EXACT_REUSE_PIPELINE_CAPABILITY,
        "revision": EQUIVALENCE_SCHEMA_REVISION,
        "digest": SHA_F,
    }


def test_exact_reuse_pins_cannot_be_constructed_directly() -> None:
    with pytest.raises(EquivalenceError, match="typed SemanticRootAudit"):
        ExactReusePins()


def test_semantic_root_audit_is_factory_only_and_relations_are_rechecked() -> None:
    with pytest.raises(EquivalenceError, match="typed evidence factory"):
        SemanticRootAudit()

    accepted = accepted_inventory((SHA_C, SHA_D))
    audit = semantic_audit(accepted)
    assert len(audit.content_id) == 64
    assert build_exact_reuse_root_plan(audit).target_root_id == SHA_C

    object.__setattr__(
        audit,
        "extractor_capability",
        CapabilityPin("extractor:dex", "dex-implementation-2026.08", SHA_A),
    )
    with pytest.raises(EquivalenceError, match="extractor relation"):
        build_exact_reuse_root_plan(audit)

    audit = semantic_audit(accepted)
    object.__setattr__(audit, "target_root_id", SHA_E)
    with pytest.raises(EquivalenceError, match="binding no longer reproduces"):
        build_exact_reuse_root_plan(audit)

    audit = semantic_audit(accepted)
    object.__setattr__(audit.inherited_semantic_root_completion, "digest", SHA_A)
    with pytest.raises(EquivalenceError, match="semantic root completion relation"):
        build_exact_reuse_root_plan(audit)


def test_semantic_root_requires_its_own_typed_completion() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D))
    audit = semantic_audit(accepted)
    assert audit.inherited_semantic_root_completion.digest != audit.inherited_semantic_root_sha256
    object.__setattr__(audit, "inherited_semantic_root_sha256", SHA_B)
    with pytest.raises(EquivalenceError, match="semantic root completion relation"):
        build_exact_reuse_root_plan(audit)


def test_semantic_root_completion_binds_the_audited_source_root() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D))

    with pytest.raises(EquivalenceError, match="audited source and inherited root"):
        semantic_audit(accepted, bind_unrelated_source=True)


def test_freeze_deduplicates_shared_inherited_semantic_roots() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D), (SHA_E, SHA_F))
    plan = build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=local_plan(),
        accepted_target_inventory=accepted,
        root_plans=(
            exact_root(accepted, unit_suffix="first"),
            exact_root(accepted, root_id=SHA_E, unit_suffix="second"),
        ),
    )

    frozen = freeze_package_execution_plan(plan)

    assert frozen.inherited_semantic_roots == (SHA_0,)


def test_full_route_has_no_reuse_pins_and_mixed_plan_is_allowed() -> None:
    plan = mixed_plan()
    full = next(item for item in plan.root_plans if type(item) is FullAnalysisRootPlan)
    assert "reuse" not in full.to_data()
    assert plan.status is PackagePlanStatus.EXECUTABLE
    assert plan.executable
    assert plan.to_data()["authoritative_root_count"] == 2
    assert {item.name for item in plan.required_capabilities} == {
        PACKAGE_PIPELINE_CAPABILITY,
        EXACT_REUSE_PIPELINE_CAPABILITY,
        "extractor:dex",
        "analyzer:full",
    }
    assert {item.parent_unit_id for item in plan.required_completions} == {
        f"package-validation-receipt:{TARGET_PACKAGE_REF_ID}",
        "inventory:target",
        "ledger:target",
        "audit:source",
        "semantic-root:source",
    }


def test_aggregate_queue_requirements_reject_conflicting_pins() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D), (SHA_E, SHA_F))
    exact = exact_root(accepted)
    with pytest.raises(EquivalenceError, match="conflicting capability"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=(
                exact,
                full_root(
                    capability_name="extractor:dex",
                    capability_digest=SHA_B,
                ),
            ),
        )
    with pytest.raises(EquivalenceError, match="conflicting completion"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=(
                exact,
                full_root(
                    dependencies=(CompletionPin("ledger:target", LEDGER_DECISION_REVISION, SHA_B),)
                ),
            ),
        )


def test_omitted_extra_or_transplanted_roots_are_rejected() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D), (SHA_E, SHA_F))
    exact = exact_root(accepted)
    full = full_root()

    with pytest.raises(EquivalenceError, match="authoritative occurrence/root set"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=(exact,),
        )
    with pytest.raises(EquivalenceError, match="authoritative occurrence/root set"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=(exact, full, full_root(SHA_2, SHA_B)),
        )

    other = accepted_inventory((SHA_C, SHA_D), (SHA_E, SHA_F), unit_id="inventory:other")
    transplanted = exact_root(other)
    with pytest.raises(EquivalenceError, match="transplanted"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=(transplanted, full),
        )


def test_any_blocked_root_blocks_package_and_output() -> None:
    accepted = accepted_inventory((SHA_C, SHA_D))
    plan = build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=local_plan(),
        accepted_target_inventory=accepted,
        root_plans=(BlockedRootPlan(SHA_C, SHA_D, ("missing_tool",)),),
    )
    assert not plan.executable
    assert plan.status is PackagePlanStatus.BLOCKED
    with pytest.raises(EquivalenceError, match="blocked package"):
        build_validated_package_output(
            execution_plan=plan,
            receipt=receipt(plan=plan),
            trusted_validation_receipt_sha256=cast(
                str, receipt(plan=plan).validation_receipt_sha256
            ),
        )


def test_builder_canonicalizes_order_and_rejects_unbounded_iterable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = mixed_plan()
    reverse = build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=local_plan(),
        accepted_target_inventory=plan.accepted_target_inventory,
        root_plans=reversed(plan.root_plans),
    )
    assert reverse.content_id == plan.content_id

    monkeypatch.setattr(plan_module, "_MAX_ROOTS", 2)
    with pytest.raises(EquivalenceError, match="exceeds 2 roots"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=plan.accepted_target_inventory,
            root_plans=(item for item in (*plan.root_plans, plan.root_plans[0])),
        )


def test_frozen_snapshot_is_stable_but_fresh_snapshot_observes_mutation() -> None:
    plan = mixed_plan()
    frozen = freeze_package_execution_plan(plan)
    assert frozen.canonical_bytes
    assert frozen.digest == plan.content_id
    assert frozen.cluster_id == CLUSTER_ID
    assert json.loads(frozen.canonical_bytes)["cluster_id"] == CLUSTER_ID
    assert frozen.root_count == 2
    assert frozen.required_capabilities == tuple(
        (item.name, item.revision, item.digest) for item in plan.required_capabilities
    )
    assert frozen.required_completions == tuple(
        (item.parent_unit_id, item.revision, item.digest) for item in plan.required_completions
    )

    object.__setattr__(plan.package_local, "version_name", "1.8")
    fresh = freeze_package_execution_plan(plan)
    assert frozen.digest != fresh.digest
    assert frozen.target_artifact_digest == SHA_B

    object.__setattr__(plan, "root_plans", list(plan.root_plans))
    with pytest.raises(EquivalenceError, match="exact supported concrete|requires at least"):
        freeze_package_execution_plan(plan)


def test_package_plan_requires_the_exact_frozen_package_identity() -> None:
    accepted = accepted_inventory((SHA_E, SHA_F))
    roots = (full_root(),)

    with pytest.raises(EquivalenceError, match="reproduce the target package ID"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=SHA_A,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=roots,
        )

    other_artifact = replace(TARGET_PACKAGE_REF, artifact_digest=SHA_E)
    with pytest.raises(EquivalenceError, match="frozen package artifact identity"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=other_artifact.content_id,
            target_package_ref=other_artifact,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=roots,
        )

    with pytest.raises(EquivalenceError, match="frozen package preflight"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=replace(local_plan(), requirements_sha256=SHA_E),
            accepted_target_inventory=accepted,
            root_plans=roots,
        )


def test_frozen_snapshot_is_factory_only_and_pins_are_structurally_immutable() -> None:
    from tools.phase4_v2.equivalence import FrozenPackageExecutionPlan

    with pytest.raises(EquivalenceError, match="canonical factory"):
        FrozenPackageExecutionPlan()
    frozen = freeze_package_execution_plan(mixed_plan())
    capability = frozen.required_capabilities[0]
    completion = frozen.required_completions[0]
    with pytest.raises(AttributeError):
        capability.name = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        completion.digest = SHA_A  # type: ignore[misc]

    object.__setattr__(frozen, "digest", SHA_A)
    with pytest.raises(EquivalenceError, match="digest does not bind"):
        plan_module._validate_frozen_package_execution_plan(frozen)

    clean = freeze_package_execution_plan(mixed_plan())
    object.__setattr__(clean, "cluster_id", "cluster-transplanted")
    with pytest.raises(EquivalenceError, match="cluster does not match"):
        plan_module._validate_frozen_package_execution_plan(clean)


def test_queue_identifier_and_global_requirement_boundaries_are_exact() -> None:
    CapabilityPin("x" * 200, "v1", SHA_A)
    with pytest.raises(EquivalenceError, match="queue identifier"):
        CapabilityPin("x" * 201, "v1", SHA_A)

    def large_plan(dependency_count: int) -> PackageExecutionPlan:
        roots: list[FullAnalysisRootPlan] = []
        inventory_pairs: list[tuple[str, str]] = []
        remaining = dependency_count
        root_index = 0
        while remaining:
            root_id = hashlib.sha256(f"root:{root_index}".encode()).hexdigest()
            occurrence = hashlib.sha256(f"occurrence:{root_index}".encode()).hexdigest()
            count = min(64, remaining)
            dependencies = tuple(
                sorted(
                    (
                        CompletionPin(
                            f"dependency:{root_index}:{index}",
                            "report-v1",
                            hashlib.sha256(f"dependency:{root_index}:{index}".encode()).hexdigest(),
                        )
                        for index in range(count)
                    ),
                    key=lambda item: item.parent_unit_id,
                )
            )
            roots.append(full_root(root_id, occurrence, dependencies=dependencies))
            inventory_pairs.append((root_id, occurrence))
            remaining -= count
            root_index += 1
        accepted = accepted_inventory(*inventory_pairs)
        return build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=roots,
        )

    at_limit = large_plan(254)
    assert len(freeze_package_execution_plan(at_limit).required_completions) == 256
    with pytest.raises(EquivalenceError, match="global completion requirement count"):
        freeze_package_execution_plan(large_plan(255))


def test_package_validation_receipt_is_an_external_queue_dependency() -> None:
    completion = package_validation_receipt_completion(TARGET_PACKAGE_REF)

    assert completion == CompletionPin(
        f"package-validation-receipt:{TARGET_PACKAGE_REF_ID}",
        PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
        TARGET_PACKAGE_REF.validation_receipt_sha256,
    )


def test_per_root_duplicates_and_global_requirement_limit_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate_capability = CapabilityPin("analyzer:full", "impl-1", SHA_A)
    with pytest.raises(EquivalenceError, match="duplicate capability"):
        FullAnalysisRootPlan(
            SHA_A,
            SHA_B,
            "full",
            (duplicate_capability, duplicate_capability),
        )
    duplicate_completion = CompletionPin("parent:one", "revision-1", SHA_A)
    with pytest.raises(EquivalenceError, match="duplicate dependency"):
        FullAnalysisRootPlan(
            SHA_A,
            SHA_B,
            "full",
            (duplicate_capability,),
            (duplicate_completion, duplicate_completion),
        )

    plan = mixed_plan()
    monkeypatch.setattr(plan_module, "_MAX_GLOBAL_REQUIREMENTS", 2)
    with pytest.raises(EquivalenceError, match="global capability requirement count"):
        freeze_package_execution_plan(plan)


def test_global_requirement_limit_stops_consuming_new_pins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_module, "_MAX_GLOBAL_REQUIREMENTS", 2)

    def capabilities() -> Iterable[CapabilityPin]:
        yield CapabilityPin("one", "v1", SHA_A)
        yield CapabilityPin("two", "v1", SHA_B)
        yield CapabilityPin("three", "v1", SHA_C)
        pytest.fail("capability aggregation consumed past the rejecting pin")

    with pytest.raises(EquivalenceError, match="global capability requirement count"):
        plan_module._merge_capabilities(capabilities())

    def completions() -> Iterable[CompletionPin]:
        yield CompletionPin("one", "v1", SHA_A)
        yield CompletionPin("two", "v1", SHA_B)
        yield CompletionPin("three", "v1", SHA_C)
        pytest.fail("completion aggregation consumed past the rejecting pin")

    with pytest.raises(EquivalenceError, match="global completion requirement count"):
        plan_module._merge_completions(completions())


def test_nested_inputs_are_copied_and_content_id_survives_caller_mutation() -> None:
    local = local_plan()
    accepted = accepted_inventory((SHA_C, SHA_D))
    root = exact_root(accepted)
    extractor_digest = root.reuse.extractor_capability.digest
    plan = build_package_execution_plan(
        cluster_id=CLUSTER_ID,
        target_package_ref_id=TARGET_PACKAGE_REF_ID,
        target_package_ref=TARGET_PACKAGE_REF,
        package_local=local,
        accepted_target_inventory=accepted,
        root_plans=(root,),
    )
    before = plan.content_id

    object.__setattr__(local, "target_artifact_digest", SHA_F)
    object.__setattr__(accepted.completion, "digest", SHA_F)
    object.__setattr__(root.reuse.extractor_capability, "digest", SHA_F)

    assert plan.content_id == before
    assert plan.package_local.target_artifact_digest == SHA_B
    assert plan.accepted_target_inventory.completion.digest != SHA_F
    planned_root = cast(ExactReuseRootPlan, plan.root_plans[0])
    assert planned_root.reuse.extractor_capability.digest == extractor_digest


def test_hostile_lists_are_not_normalized_into_trusted_tuples() -> None:
    local = local_plan()
    object.__setattr__(local, "mandatory_domains", list(LOCAL_ONLY_DOMAINS))
    accepted = accepted_inventory((SHA_C, SHA_D))
    with pytest.raises(EquivalenceError, match="exact mandatory tuple"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local,
            accepted_target_inventory=accepted,
            root_plans=(exact_root(accepted),),
        )

    inventory = accepted.inventory
    object.__setattr__(inventory, "occurrences", list(inventory.occurrences))
    with pytest.raises(EquivalenceError, match="must contain"):
        AcceptedTargetRootInventory(inventory, accepted.completion)

    blocked = BlockedRootPlan(SHA_C, SHA_D, ("blocked",))
    object.__setattr__(blocked, "blockers", ["blocked"])
    with pytest.raises(EquivalenceError, match="at least one blocker"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted_inventory((SHA_C, SHA_D)),
            root_plans=(blocked,),
        )


def test_subclasses_are_rejected_at_every_trust_boundary() -> None:
    class CapabilitySubclass(CapabilityPin):
        pass

    with pytest.raises(EquivalenceError, match="exact CapabilityPin"):
        replace(
            local_plan(),
            pipeline_capability=CapabilitySubclass(
                PACKAGE_PIPELINE_CAPABILITY, PACKAGE_EXECUTION_PLAN_REVISION, SHA_F
            ),
        )

    accepted = accepted_inventory((SHA_C, SHA_D))

    class RootSubclass(FullAnalysisRootPlan):
        pass

    with pytest.raises(EquivalenceError, match="exact supported concrete type"):
        build_package_execution_plan(
            cluster_id=CLUSTER_ID,
            target_package_ref_id=TARGET_PACKAGE_REF_ID,
            target_package_ref=TARGET_PACKAGE_REF,
            package_local=local_plan(),
            accepted_target_inventory=accepted,
            root_plans=(
                RootSubclass(
                    SHA_C,
                    SHA_D,
                    "full",
                    (CapabilityPin("analyzer:full", "impl-1", SHA_A),),
                ),
            ),
        )


def test_validated_output_can_only_come_from_current_clean_bound_receipt() -> None:
    plan = mixed_plan()
    output = build_validated_package_output(
        execution_plan=plan,
        receipt=receipt(plan=plan),
        trusted_validation_receipt_sha256=cast(str, receipt(plan=plan).validation_receipt_sha256),
    )

    assert output.execution_plan_id == freeze_package_execution_plan(plan).digest
    assert output.target_report_sha256 == SHA_D
    assert output.target_report_revision == PACKAGE_REPORT_REVISION
    assert output.target_report_schema_sha256 == PACKAGE_REPORT_SCHEMA_SHA256
    assert output.validation_receipt_sha256 == receipt(plan=plan).validation_receipt_sha256
    with pytest.raises(EquivalenceError, match="trusted receipt factory"):
        ValidatedPackageOutput()

    assert not hasattr(output, "completion_pin")


@pytest.mark.parametrize(
    ("change", "value", "message"),
    [
        ("accepted", False, "accepted unchanged"),
        ("accepted", 1, "exact booleans"),
        ("source_unchanged", False, "accepted unchanged"),
        ("diagnostics", [], "exact tuple"),
        ("validation_profile", "FILESYSTEM_ONLY", "not package-bound"),
        ("validator_revision", "old-validator", "unsupported validator"),
        ("contract_revision", "old-contract", "unsupported contract"),
        ("bundle_sha256", None, "no target bundle"),
        ("validated_artifact_identity", None, "no exact validated artifact"),
    ],
)
def test_validator_factory_fails_closed(change: str, value: object, message: str) -> None:
    changed = replace(receipt(), **{change: value, "validation_receipt_sha256": None})
    payload = json.dumps(
        changed.identity_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    changed = replace(changed, validation_receipt_sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(EquivalenceError, match=message):
        build_validated_package_output(
            execution_plan=mixed_plan(),
            receipt=changed,
            trusted_validation_receipt_sha256=cast(str, changed.validation_receipt_sha256),
        )


def test_validator_receipt_deep_snapshot_rejects_scalar_subclasses() -> None:
    class StringSubclass(str):
        pass

    original = receipt()
    identity = cast(ArtifactIdentityAttestation, original.validated_artifact_identity)
    hostile_receipts = (
        replace(original, validator_revision=StringSubclass(VALIDATOR_REVISION)),
        replace(
            original,
            diagnostics=(Diagnostic(StringSubclass("HOSTILE"), "validation-input.json"),),
        ),
        replace(
            original,
            validated_artifact_identity=replace(
                identity, package_name=StringSubclass(identity.package_name)
            ),
        ),
        replace(
            original,
            validated_evidence_members=(
                EvidenceMemberAttestation(StringSubclass("evidence/member"), SHA_A, SHA_B),
            ),
        ),
        replace(
            original,
            validated_evidence_anchors=(
                EvidenceAnchorAttestation(
                    StringSubclass("anchor"),
                    SHA_A,
                    "evidence/member",
                    SHA_B,
                    0,
                    1,
                    "/schema_revision",
                    "utf8",
                    SHA_C,
                ),
            ),
            evidence_anchors_checked=1,
        ),
        replace(original, discovered_members=True),
    )
    for hostile in hostile_receipts:
        signed = identify_receipt(hostile)
        with pytest.raises(EquivalenceError, match="exact bounded|string|integer"):
            build_validated_package_output(
                execution_plan=mixed_plan(),
                receipt=signed,
                trusted_validation_receipt_sha256=cast(str, signed.validation_receipt_sha256),
            )


def test_validator_receipt_identity_and_artifact_substitution_are_rejected() -> None:
    with pytest.raises(EquivalenceError, match="external trust pin"):
        build_validated_package_output(
            execution_plan=mixed_plan(),
            receipt=replace(receipt(), validation_receipt_sha256=SHA_A),
            trusted_validation_receipt_sha256=SHA_A,
        )


@pytest.mark.parametrize("dependency", ["execution_plan", "report_schema"])
def test_validator_receipt_must_bind_plan_and_current_report_schema(dependency: str) -> None:
    plan = mixed_plan()
    original = receipt(plan=plan)
    changed_dependencies = tuple(
        (name, SHA_A if name == dependency else digest)
        for name, digest in original.dependency_digests
    )
    changed = identify_receipt(replace(original, dependency_digests=changed_dependencies))
    with pytest.raises(EquivalenceError, match="execution plan|package-report schema"):
        build_validated_package_output(
            execution_plan=plan,
            receipt=changed,
            trusted_validation_receipt_sha256=cast(str, changed.validation_receipt_sha256),
        )


def test_external_receipt_pin_and_artifact_substitution_are_rejected() -> None:
    with pytest.raises(EquivalenceError, match="external trust pin"):
        build_validated_package_output(
            execution_plan=mixed_plan(),
            receipt=receipt(),
            trusted_validation_receipt_sha256=SHA_A,
        )

    wrong = replace(
        receipt(),
        validated_artifact_identity=ArtifactIdentityAttestation(
            "org.example.other", "17", "1.7", SHA_B
        ),
        validation_receipt_sha256=None,
    )
    payload = json.dumps(
        wrong.identity_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    wrong = replace(wrong, validation_receipt_sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(EquivalenceError, match="different artifact identity"):
        build_validated_package_output(
            execution_plan=mixed_plan(),
            receipt=wrong,
            trusted_validation_receipt_sha256=cast(str, wrong.validation_receipt_sha256),
        )


@pytest.mark.parametrize("bundle", [SHA_0, SHA_1])
def test_semantic_root_or_audit_completion_cannot_be_target_report(bundle: str) -> None:
    with pytest.raises(EquivalenceError, match="cannot serve"):
        build_validated_package_output(
            execution_plan=mixed_plan(),
            receipt=receipt(bundle=bundle),
            trusted_validation_receipt_sha256=cast(
                str, receipt(bundle=bundle).validation_receipt_sha256
            ),
        )
