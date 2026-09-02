"""Purely synthetic hostile tests for Phase 4 v2 completion gates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest

from tools.phase4_v2.equivalence import (
    PACKAGE_REPORT_REVISION,
    PACKAGE_REPORT_SCHEMA_REVISION,
    PACKAGE_REPORT_SCHEMA_SHA256,
    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    FrozenPackageExecutionPlan,
    FrozenPackageRef,
    PackagePlanStatus,
    Route,
    ValidatedPackageOutput,
)
from tools.phase4_v2.equivalence.plan import FrozenCapabilityPin, FrozenCompletionPin
from tools.phase4_v2.preflight import (
    CandidateRecord,
    InvocationRecord,
    PreparationResult,
    StreamDigest,
    ToolRecord,
    WarningRecord,
)
from tools.phase4_v2.reconciliation import (
    AreaSurface,
    CanonicalValue,
    ClaimPolarity,
    ClosureStatus,
    ComparisonArea,
    DispositionKind,
    DispositionStatus,
    LeafProvenance,
    LedgerDisposition,
    NormalizedClaim,
    PackageSurface,
    ReconciliationInput,
    RootProvenance,
    reconcile,
    render_json,
    render_markdown,
)
from tools.phase4_v2.validation import (
    CandidateLink,
    CompletionAdapter,
    ValidationPins,
    WarningDisposition,
    WarningStatus,
    candidate_occurrence_id,
    validate_completion,
    warning_occurrence_id,
)


def sha(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def candidate_index_sha(artifact: str, candidates: tuple[CandidateRecord, ...]) -> str:
    payload = (
        json.dumps(
            {
                "artifact_digest": artifact,
                "candidates": [item.to_data() for item in candidates],
                "schema": "phase4-v2-ble-candidate-index-v1",
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        + b"\n"
    )
    return sha(payload)


def preparation() -> PreparationResult:
    artifact = sha("artifact")
    warning = WarningRecord("stderr", 7, "warning: synthetic", sha("warning raw"))
    empty = StreamDigest(0, sha(b""))
    tool = ToolRecord("synthetic", 1, sha("tool"), ("--version",), "1", empty, empty, None)
    invocation = InvocationRecord(
        member="base.apk",
        input_sha256=sha("member"),
        route="jadx",
        cache_key=sha("cache"),
        tool=tool,
        arguments=("base.apk", "output"),
        flags=(),
        status="COMPLETE",
        exit_code=0,
        stdout=empty,
        stderr=empty,
        warnings=(warning,),
        failures=(),
        outputs=(),
    )
    candidates = (
        CandidateRecord(
            invocation_cache_key=cast(str, invocation.cache_key),
            member="base.apk",
            route="jadx",
            output_path="sources/A.java",
            output_sha256=sha("source"),
            start_byte=10,
            end_byte=23,
            signal="bluetooth.gatt",
        ),
    )
    return PreparationResult(
        output_directory=Path("/synthetic/not-read"),
        artifact_digest=artifact,
        pipeline_revision="synthetic-v1",
        status="COMPLETE",
        invocations=(invocation,),
        candidates=candidates,
        failures=(),
        manifest_sha256=sha("manifest"),
        candidate_index_sha256=candidate_index_sha(artifact, candidates),
    )


def package_ref(name: str, artifact: str) -> FrozenPackageRef:
    return FrozenPackageRef(name, "17", artifact, sha(name + ":preflight"), sha(name + ":receipt"))


def package_surface(
    package: FrozenPackageRef,
    report_sha: str,
    item_ids: tuple[str, str, str],
    *,
    route: Route = Route.FULL_ANALYSIS,
    claim_value: object = True,
    duplicate_action: bool = False,
) -> PackageSurface:
    root = RootProvenance(
        package_ref_id=package.content_id,
        target_root_id=sha(package.package_name + ":root"),
        occurrence_identity_sha256=sha(package.package_name + ":occurrence"),
        route=route,
        semantic_root_sha256=sha("semantic"),
        source_root_id=sha("source-root") if route is Route.EXACT_REUSE else None,
        report_pointer="/roots/0",
        evidence_anchor_ids=("anchor",),
    )
    provenance = LeafProvenance(root.content_id, "/surface", ("anchor",))
    candidate_id, action_id, variant_id = item_ids
    areas: list[AreaSurface] = []
    for area in ComparisonArea:
        claim = NormalizedClaim(
            f"/{area.value}/present",
            ClaimPolarity.AFFIRMED,
            CanonicalValue.from_data(claim_value),
            (provenance,),
        )
        dispositions: tuple[LedgerDisposition, ...] = ()
        if area is ComparisonArea.ACTIONS:
            dispositions = tuple(
                sorted(
                    (
                        LedgerDisposition(
                            DispositionKind.CANDIDATE,
                            candidate_id,
                            DispositionStatus.COVERED,
                            "covered",
                            (claim.key,),
                            (provenance,),
                        ),
                        LedgerDisposition(
                            DispositionKind.ACTION,
                            action_id,
                            DispositionStatus.COVERED,
                            "covered",
                            (claim.key,),
                            (provenance,),
                        ),
                        LedgerDisposition(
                            DispositionKind.VARIANT,
                            variant_id,
                            DispositionStatus.EXCLUDED,
                            "not-applicable",
                            (),
                            (provenance,),
                        ),
                        *(
                            (
                                LedgerDisposition(
                                    DispositionKind.ACTION,
                                    action_id,
                                    DispositionStatus.COVERED,
                                    "covered",
                                    (claim.key,),
                                    (provenance,),
                                ),
                            )
                            if duplicate_action
                            else ()
                        ),
                    ),
                    key=lambda item: item.sort_key,
                )
            )
        areas.append(AreaSurface(area, ClosureStatus.COMPLETE, (claim,), dispositions))
    return PackageSurface(package, report_sha, "synthetic-report-v1", (root,), tuple(areas))


def frozen_plan(target: FrozenPackageRef) -> FrozenPackageExecutionPlan:
    receipt_digest = sha("receipt")
    receipt_unit = f"package-validation-receipt:{target.content_id}"
    canonical = json.dumps(
        {
            "authoritative_root_count": 1,
            "package_local": {
                "package_name": target.package_name,
                "target_artifact_digest": target.artifact_digest,
                "version_code": target.version_code,
                "version_name": "1.7",
            },
            "required_capabilities": [
                {"digest": sha("capability"), "name": "pipeline", "revision": "v1"}
            ],
            "required_completions": [
                {
                    "digest": receipt_digest,
                    "parent_unit_id": receipt_unit,
                    "revision": PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
                }
            ],
            "status": "EXECUTABLE",
            "target_package_ref_id": target.content_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    result = object.__new__(FrozenPackageExecutionPlan)
    values: dict[str, object] = {
        "target_package_ref_id": target.content_id,
        "canonical_bytes": canonical,
        "digest": sha(b"phase4-v2:package-execution-plan\0" + canonical),
        "status": PackagePlanStatus.EXECUTABLE,
        "root_count": 1,
        "package_name": target.package_name,
        "version_code": target.version_code,
        "version_name": "1.7",
        "target_artifact_digest": target.artifact_digest,
        "inherited_semantic_roots": (),
        "semantic_audit_completion_digests": (),
        "required_capabilities": (FrozenCapabilityPin("pipeline", "v1", sha("capability")),),
        "required_completions": (
            FrozenCompletionPin(
                receipt_unit,
                PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
                receipt_digest,
            ),
        ),
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def validated_output(plan: FrozenPackageExecutionPlan, report_sha: str) -> ValidatedPackageOutput:
    result = object.__new__(ValidatedPackageOutput)
    values = {
        "target_package_ref_id": plan.target_package_ref_id,
        "execution_plan_id": plan.digest,
        "validation_receipt_sha256": sha("receipt"),
        "target_report_revision": PACKAGE_REPORT_REVISION,
        "target_report_schema_revision": PACKAGE_REPORT_SCHEMA_REVISION,
        "target_report_schema_sha256": PACKAGE_REPORT_SCHEMA_SHA256,
        "target_report_sha256": report_sha,
        "revision": VALIDATED_PACKAGE_OUTPUT_REVISION,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


@dataclass(frozen=True)
class Case:
    preparation: PreparationResult
    execution_plan: FrozenPackageExecutionPlan
    validated_output: ValidatedPackageOutput
    reconciliation: object
    reconciliation_json: bytes
    reconciliation_markdown: str
    adapter: CompletionAdapter
    pins: ValidationPins

    def arguments(self) -> dict[str, object]:
        return self.__dict__


def valid_case(
    *,
    target_route: Route = Route.FULL_ANALYSIS,
    target_claim: object = True,
    peer_claim: object = True,
    duplicate_action: bool = False,
    omit_target_area: ComparisonArea | None = None,
) -> Case:
    prepared = preparation()
    target = package_ref("org.example.target", prepared.artifact_digest)
    peer = package_ref("org.example.peer", sha("peer-artifact"))
    report_sha = sha("target-report")
    items = ("candidate-1", "raise-head", "model-x")
    target_surface = package_surface(
        target,
        report_sha,
        items,
        route=target_route,
        claim_value=target_claim,
        duplicate_action=duplicate_action,
    )
    if omit_target_area is not None:
        target_surface = replace(
            target_surface,
            areas=tuple(item for item in target_surface.areas if item.area is not omit_target_area),
        )
    surfaces = tuple(
        sorted(
            (
                target_surface,
                package_surface(peer, sha("peer-report"), items, claim_value=peer_claim),
            ),
            key=lambda item: item.package_ref.content_id,
        )
    )
    result = reconcile(ReconciliationInput("cluster-synthetic", surfaces))
    json_payload = render_json(result)
    markdown = render_markdown(result)
    plan = frozen_plan(target)
    output = validated_output(plan, report_sha)
    warning_id = warning_occurrence_id(prepared.invocations[0], prepared.invocations[0].warnings[0])
    adapter = CompletionAdapter(
        target.content_id,
        (CandidateLink(candidate_occurrence_id(prepared.candidates[0]), items[0]),),
        (
            WarningDisposition(
                warning_id, WarningStatus.ACCEPTED, "known-tool-warning", sha("review")
            ),
        ),
    )
    pins = ValidationPins(
        preparation_manifest_sha256=prepared.manifest_sha256,
        candidate_index_sha256=prepared.candidate_index_sha256,
        execution_plan_sha256=plan.digest,
        validated_package_output_sha256=output.content_id,
        reconciliation_input_sha256=result.input_id,
        reconciliation_result_sha256=result.content_id,
        reconciliation_json_sha256=sha(json_payload),
        reconciliation_markdown_sha256=sha(markdown),
        completion_adapter_sha256=adapter.content_id,
    )
    return Case(prepared, plan, output, result, json_payload, markdown, adapter, pins)


def codes(case: Case) -> set[str]:
    return {item.code for item in validate_completion(**case.arguments()).diagnostics}


def test_complete_chain_is_accepted_and_content_addressed() -> None:
    case = valid_case()
    first = validate_completion(**case.arguments())
    second = validate_completion(**case.arguments())

    assert first.accepted
    assert first.content_id == second.content_id
    assert (
        first.candidate_count,
        first.action_count,
        first.variant_count,
        first.warning_count,
    ) == (
        1,
        1,
        1,
        1,
    )


def test_valid_incomplete_results_expose_each_terminal_reconciliation_gate() -> None:
    incomplete = valid_case(omit_target_area=ComparisonArea.TRANSPORT)
    assert {
        "PAIR_DECISIONS_INCOMPLETE",
        "RECONCILIATION_INCOMPLETE",
        "REPAIRS_REMAIN",
    } <= codes(incomplete)

    promotion = valid_case(
        target_route=Route.EXACT_REUSE,
        target_claim="target",
        peer_claim="peer",
    )
    assert {"FULL_PROMOTIONS_REMAIN", "RECONCILIATION_INCOMPLETE"} <= codes(promotion)

    contradiction = valid_case(duplicate_action=True)
    assert {"CONTRADICTIONS_REMAIN", "RECONCILIATION_INCOMPLETE"} <= codes(contradiction)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("preparation_blocked", "PREPARATION_INCOMPLETE"),
        ("invocation_blocked", "INVOCATION_INCOMPLETE"),
        ("candidate_removed", "CANDIDATE_SOURCE_SET_MISMATCH"),
        ("candidate_unknown", "CANDIDATE_SOURCE_SET_MISMATCH"),
        ("candidate_report_unknown", "CANDIDATE_REPORT_SET_MISMATCH"),
        ("warning_removed", "WARNING_SET_MISMATCH"),
        ("warning_unknown", "WARNING_SET_MISMATCH"),
        ("warning_blocking", "WARNING_BLOCKING"),
        ("plan_blocked", "PLAN_BLOCKED"),
        ("plan_preimage", "PLAN_DIGEST_MISMATCH"),
        ("artifact_changed", "ARTIFACT_DIGEST_MISMATCH"),
        ("output_plan", "OUTPUT_PLAN_MISMATCH"),
        ("output_receipt", "OUTPUT_RECEIPT_MISMATCH"),
        ("output_report", "OUTPUT_REPORT_MISMATCH"),
        ("adapter_target", "ADAPTER_TARGET_MISMATCH"),
        ("reconciliation_incomplete", "RECONCILIATION_STRUCTURE_INVALID"),
        ("reconciliation_wrong_type", "RECONCILIATION_TYPE_INVALID"),
        ("json_changed", "RENDER_AGREEMENT_INVALID"),
        ("markdown_changed", "RENDER_AGREEMENT_INVALID"),
        ("pin_changed", "PIN_MISMATCH"),
    ],
)
def test_hostile_mutation_matrix_fails_closed(mutation: str, expected: str) -> None:
    case = valid_case()
    if mutation == "preparation_blocked":
        case = replace(case, preparation=replace(case.preparation, status="BLOCKED"))
    elif mutation == "invocation_blocked":
        invocation = replace(case.preparation.invocations[0], status="BLOCKED")
        case = replace(case, preparation=replace(case.preparation, invocations=(invocation,)))
    elif mutation == "candidate_removed":
        case = replace(case, adapter=replace(case.adapter, candidate_links=()))
    elif mutation == "candidate_unknown":
        link = replace(case.adapter.candidate_links[0], occurrence_id=sha("unknown"))
        case = replace(case, adapter=replace(case.adapter, candidate_links=(link,)))
    elif mutation == "candidate_report_unknown":
        link = replace(case.adapter.candidate_links[0], report_item_id="unknown")
        case = replace(case, adapter=replace(case.adapter, candidate_links=(link,)))
    elif mutation == "warning_removed":
        case = replace(case, adapter=replace(case.adapter, warning_dispositions=()))
    elif mutation == "warning_unknown":
        warning = replace(case.adapter.warning_dispositions[0], occurrence_id=sha("unknown"))
        case = replace(case, adapter=replace(case.adapter, warning_dispositions=(warning,)))
    elif mutation == "warning_blocking":
        warning = replace(case.adapter.warning_dispositions[0], status=WarningStatus.BLOCKING)
        case = replace(case, adapter=replace(case.adapter, warning_dispositions=(warning,)))
    elif mutation == "plan_blocked":
        object.__setattr__(case.execution_plan, "status", PackagePlanStatus.BLOCKED)
    elif mutation == "plan_preimage":
        object.__setattr__(case.execution_plan, "digest", sha("changed"))
    elif mutation == "artifact_changed":
        object.__setattr__(case.execution_plan, "target_artifact_digest", sha("changed"))
    elif mutation == "output_plan":
        object.__setattr__(case.validated_output, "execution_plan_id", sha("changed"))
    elif mutation == "output_receipt":
        object.__setattr__(case.validated_output, "validation_receipt_sha256", sha("changed"))
    elif mutation == "output_report":
        object.__setattr__(case.validated_output, "target_report_sha256", sha("changed"))
    elif mutation == "adapter_target":
        object.__setattr__(case.adapter, "target_package_ref_id", sha("changed"))
    elif mutation == "reconciliation_incomplete":
        object.__setattr__(case.reconciliation, "status", ClosureStatus.INCOMPLETE)
    elif mutation == "reconciliation_wrong_type":
        case = replace(case, reconciliation=object())
    elif mutation == "json_changed":
        case = replace(case, reconciliation_json=case.reconciliation_json + b"\n")
    elif mutation == "markdown_changed":
        case = replace(case, reconciliation_markdown=case.reconciliation_markdown + "\n")
    elif mutation == "pin_changed":
        case = replace(
            case,
            pins=replace(case.pins, reconciliation_result_sha256=sha("changed")),
        )

    receipt = validate_completion(**case.arguments())
    assert not receipt.accepted
    assert expected in {item.code for item in receipt.diagnostics}


def test_pin_type_and_duplicate_adapter_records_are_rejected_at_construction() -> None:
    case = valid_case()
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(case.pins, execution_plan_sha256="not-a-digest")
    with pytest.raises(ValueError, match="candidate occurrences must be unique"):
        replace(
            case.adapter,
            candidate_links=(case.adapter.candidate_links[0], case.adapter.candidate_links[0]),
        )
