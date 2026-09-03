"""Purely synthetic hostile tests for Phase 4 v2 completion gates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import cast

import pytest

import tools.phase4_v2.validation.gates as validation_gates
from tests.test_phase4_v2_ir import _authorized_single_leaf_document, _trusted_receipts
from tests.test_phase4_v2_ir_v1 import _authorized_document
from tools.phase4_v2.equivalence import (
    FINAL_IR_SCHEMA_SHA256,
    PACKAGE_EXECUTION_PLAN_REVISION,
    PACKAGE_REPORT_REVISION,
    PACKAGE_REPORT_SCHEMA_REVISION,
    PACKAGE_REPORT_SCHEMA_SHA256,
    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
    PREPARATION_AUTHORITY_CAPABILITY,
    PREPARATION_CANDIDATE_CAPABILITY,
    PREPARATION_EXECUTION_CAPABILITY,
    PREPARATION_PIPELINE_CAPABILITY,
    PREPARATION_REGISTRY_CAPABILITY,
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    FrozenPackageExecutionPlan,
    FrozenPackageRef,
    FrozenPreparationPlanBinding,
    PackagePlanStatus,
    Route,
    ValidatedPackageOutput,
)
from tools.phase4_v2.equivalence.plan import FrozenCapabilityPin, FrozenCompletionPin
from tools.phase4_v2.ir import (
    FINAL_SCHEMA_REVISION,
    FinalProtocolIRDocument,
    dumps_final_ir,
    loads_final_ir,
    loads_ir,
    render_final_ir_markdown,
)
from tools.phase4_v2.preflight import (
    CANDIDATE_CONTRACT_REVISION,
    CANDIDATE_CONTRACT_SHA256,
    CANDIDATE_INDEX_SCHEMA,
    EXECUTION_PROFILE_REVISION,
    PREPARATION_AUTHORITY_SCHEMA,
    PREPARATION_RECEIPT_REVISION,
    TOOL_REGISTRY_SCHEMA,
    CandidateRecord,
    InvocationRecord,
    PreparationReceipt,
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
    ReconciliationError,
    ReconciliationInput,
    RootProvenance,
    derive_final_ir_package_surface,
    reconcile,
    render_json,
    render_markdown,
)
from tools.phase4_v2.validation import (
    CandidateLink,
    CompletionAdapter,
    ValidationError,
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
                "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
                "candidates": [item.to_data() for item in candidates],
                "schema": CANDIDATE_INDEX_SCHEMA,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        + b"\n"
    )
    return sha(payload)


def preparation() -> PreparationReceipt:
    artifact = sha("artifact")
    warning = WarningRecord("stderr", 7, "warning: synthetic", sha("warning raw"))
    empty = StreamDigest(0, sha(b""))
    tool = ToolRecord(
        "synthetic",
        1,
        sha("tool"),
        1,
        sha("runtime"),
        ("--version",),
        "1",
        empty,
        empty,
        None,
    )
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
    result = object.__new__(PreparationReceipt)
    values = {
        "artifact_digest": artifact,
        "package_name": "org.example.target",
        "version_code": "17",
        "version_name": "1.7",
        "preflight_manifest_sha256": sha("preflight"),
        "manifest_sha256": sha("manifest"),
        "candidate_index_sha256": candidate_index_sha(artifact, candidates),
        "candidate_contract_sha256": CANDIDATE_CONTRACT_SHA256,
        "authority_sha256": sha("authority"),
        "tool_registry_sha256": sha("registry"),
        "pipeline_revision": "synthetic-v1",
        "execution_profile_revision": "phase4-v2-execution-profile-v1",
        "execution_profile_sha256": sha("execution-profile"),
        "invocations": (invocation,),
        "candidates": candidates,
        "revision": PREPARATION_RECEIPT_REVISION,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def replace_preparation(value: PreparationReceipt, **changes: object) -> PreparationReceipt:
    result = object.__new__(PreparationReceipt)
    for name in value.__dataclass_fields__:
        object.__setattr__(result, name, changes.get(name, getattr(value, name)))
    return result


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


def frozen_plan(
    target: FrozenPackageRef, prepared: PreparationReceipt
) -> FrozenPackageExecutionPlan:
    receipt_digest = sha("receipt")
    receipt_unit = f"package-validation-receipt:{target.content_id}"
    preparation_capabilities = tuple(
        sorted(
            (
                FrozenCapabilityPin(
                    PREPARATION_AUTHORITY_CAPABILITY,
                    PREPARATION_AUTHORITY_SCHEMA,
                    prepared.authority_sha256,
                ),
                FrozenCapabilityPin(
                    PREPARATION_CANDIDATE_CAPABILITY,
                    CANDIDATE_CONTRACT_REVISION,
                    prepared.candidate_contract_sha256,
                ),
                FrozenCapabilityPin(
                    PREPARATION_EXECUTION_CAPABILITY,
                    EXECUTION_PROFILE_REVISION,
                    prepared.execution_profile_sha256,
                ),
                FrozenCapabilityPin(
                    PREPARATION_PIPELINE_CAPABILITY,
                    prepared.pipeline_revision,
                    prepared.tool_registry_sha256,
                ),
                FrozenCapabilityPin(
                    PREPARATION_REGISTRY_CAPABILITY,
                    TOOL_REGISTRY_SCHEMA,
                    prepared.tool_registry_sha256,
                ),
            ),
            key=lambda item: item.name,
        )
    )
    preparation_completion = FrozenCompletionPin(
        f"package-preparation:{target.content_id}",
        PREPARATION_RECEIPT_REVISION,
        prepared.content_id,
    )
    preparation_binding = FrozenPreparationPlanBinding(
        package_ref_id=target.content_id,
        package_name=target.package_name,
        version_code=target.version_code,
        version_name="1.7",
        artifact_digest=target.artifact_digest,
        preflight_sha256=prepared.preflight_manifest_sha256,
        receipt_sha256=prepared.content_id,
        completion=preparation_completion,
        capabilities=preparation_capabilities,
    )
    required_capabilities = tuple(
        sorted(
            (
                *preparation_capabilities,
                FrozenCapabilityPin("pipeline", "v1", sha("capability")),
            ),
            key=lambda item: item.name,
        )
    )
    required_completions = tuple(
        sorted(
            (
                preparation_completion,
                FrozenCompletionPin(
                    receipt_unit,
                    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
                    receipt_digest,
                ),
            ),
            key=lambda item: item.parent_unit_id,
        )
    )
    canonical = json.dumps(
        {
            "authoritative_root_count": 1,
            "cluster_id": "cluster-synthetic",
            "package_local": {
                "package_name": target.package_name,
                "requirements_sha256": sha("preflight"),
                "target_artifact_digest": target.artifact_digest,
                "version_code": target.version_code,
                "version_name": "1.7",
            },
            "preparation": preparation_binding.to_data(),
            "required_capabilities": [
                {"digest": item.digest, "name": item.name, "revision": item.revision}
                for item in required_capabilities
            ],
            "required_completions": [
                {
                    "digest": item.digest,
                    "parent_unit_id": item.parent_unit_id,
                    "revision": item.revision,
                }
                for item in required_completions
            ],
            "revision": PACKAGE_EXECUTION_PLAN_REVISION,
            "status": "EXECUTABLE",
            "target_package_ref_id": target.content_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    result = object.__new__(FrozenPackageExecutionPlan)
    values: dict[str, object] = {
        "target_package_ref_id": target.content_id,
        "cluster_id": "cluster-synthetic",
        "canonical_bytes": canonical,
        "digest": sha(b"phase4-v2:package-execution-plan\0" + canonical),
        "status": PackagePlanStatus.EXECUTABLE,
        "root_count": 1,
        "package_name": target.package_name,
        "version_code": target.version_code,
        "version_name": "1.7",
        "target_artifact_digest": target.artifact_digest,
        "preflight_sha256": sha("preflight"),
        "preparation": preparation_binding,
        "inherited_semantic_roots": (),
        "semantic_audit_completion_digests": (),
        "required_capabilities": required_capabilities,
        "required_completions": required_completions,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def validated_output(
    plan: FrozenPackageExecutionPlan, report_sha: str, final_ir_sha: str
) -> ValidatedPackageOutput:
    result = object.__new__(ValidatedPackageOutput)
    values = {
        "target_package_ref_id": plan.target_package_ref_id,
        "execution_plan_id": plan.digest,
        "validation_receipt_sha256": sha("receipt"),
        "target_report_revision": PACKAGE_REPORT_REVISION,
        "target_report_schema_revision": PACKAGE_REPORT_SCHEMA_REVISION,
        "target_report_schema_sha256": PACKAGE_REPORT_SCHEMA_SHA256,
        "target_report_sha256": report_sha,
        "target_final_ir_schema_revision": FINAL_SCHEMA_REVISION,
        "target_final_ir_schema_sha256": FINAL_IR_SCHEMA_SHA256,
        "target_final_ir_json_sha256": final_ir_sha,
        "revision": VALIDATED_PACKAGE_OUTPUT_REVISION,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


@dataclass(frozen=True)
class Case:
    preparation: PreparationReceipt
    execution_plan: FrozenPackageExecutionPlan
    validated_output: ValidatedPackageOutput
    reconciliation_input: ReconciliationInput
    reconciliation: object
    reconciliation_json: bytes
    reconciliation_markdown: str
    final_ir: FinalProtocolIRDocument
    final_ir_json: bytes
    final_ir_markdown: str
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
    final_data, trusted_receipts = _authorized_document()
    final_document = loads_final_ir(
        json.dumps(final_data, sort_keys=True, separators=(",", ":")),
        trusted_receipts=trusted_receipts,
    )
    final_json = dumps_final_ir(final_document)
    final_markdown = render_final_ir_markdown(final_document)
    anchor_ids = tuple(sorted(dict(final_document.evidence_anchors)))

    def final_root(package: FrozenPackageRef, route: Route) -> RootProvenance:
        return RootProvenance(
            package_ref_id=package.content_id,
            target_root_id=sha(package.package_name + ":root"),
            occurrence_identity_sha256=sha(package.package_name + ":occurrence"),
            route=route,
            semantic_root_sha256=sha("semantic"),
            source_root_id=sha("source-root") if route is Route.EXACT_REUSE else None,
            report_pointer="/final_ir",
            evidence_anchor_ids=anchor_ids,
        )

    target_derivation = derive_final_ir_package_surface(
        package_ref=target,
        report_sha256=report_sha,
        report_revision=PACKAGE_REPORT_REVISION,
        roots=(final_root(target, target_route),),
        document=final_document,
        canonical_json=final_json,
        markdown=final_markdown,
    )
    target_surface = target_derivation.package_surface
    peer_surface = derive_final_ir_package_surface(
        package_ref=peer,
        report_sha256=sha("peer-report"),
        report_revision=PACKAGE_REPORT_REVISION,
        roots=(final_root(peer, Route.FULL_ANALYSIS),),
        document=final_document,
        canonical_json=final_json,
        markdown=final_markdown,
    ).package_surface
    if target_claim is not True:
        target_surface = _replace_first_claim(target_surface, target_claim)
    if peer_claim is not True:
        peer_surface = _replace_first_claim(peer_surface, peer_claim)
    if duplicate_action:
        target_surface = _duplicate_first_action(target_surface)
    if omit_target_area is not None:
        target_surface = replace(
            target_surface,
            areas=tuple(item for item in target_surface.areas if item.area is not omit_target_area),
        )
    surfaces = tuple(
        sorted(
            (
                target_surface,
                peer_surface,
            ),
            key=lambda item: item.package_ref.content_id,
        )
    )
    reconciliation_input = ReconciliationInput("cluster-synthetic", surfaces)
    result = reconcile(reconciliation_input)
    json_payload = render_json(result)
    markdown = render_markdown(result)
    plan = frozen_plan(target, prepared)
    output = validated_output(plan, report_sha, sha(final_json))
    warning_id = warning_occurrence_id(prepared.invocations[0], prepared.invocations[0].warnings[0])
    adapter = CompletionAdapter(
        target.content_id,
        (
            CandidateLink(
                candidate_occurrence_id(prepared.candidates[0]),
                target_derivation.candidate_ids[0],
            ),
        ),
        (
            WarningDisposition(
                warning_id, WarningStatus.ACCEPTED, "known-tool-warning", sha("review")
            ),
        ),
    )
    pins = ValidationPins(
        preparation_receipt_sha256=prepared.content_id,
        preflight_manifest_sha256=prepared.preflight_manifest_sha256,
        preparation_manifest_sha256=prepared.manifest_sha256,
        candidate_index_sha256=prepared.candidate_index_sha256,
        candidate_contract_sha256=prepared.candidate_contract_sha256,
        preparation_authority_sha256=prepared.authority_sha256,
        tool_registry_sha256=prepared.tool_registry_sha256,
        execution_profile_sha256=prepared.execution_profile_sha256,
        execution_plan_sha256=plan.digest,
        validated_package_output_sha256=output.content_id,
        reconciliation_input_sha256=result.input_id,
        reconciliation_result_sha256=result.content_id,
        reconciliation_json_sha256=sha(json_payload),
        reconciliation_markdown_sha256=sha(markdown),
        completion_adapter_sha256=adapter.content_id,
        final_ir_schema_sha256=FINAL_IR_SCHEMA_SHA256,
        final_ir_json_sha256=sha(final_json),
        final_ir_markdown_sha256=sha(final_markdown),
        final_package_surface_sha256=target_derivation.package_surface.content_id,
    )
    return Case(
        prepared,
        plan,
        output,
        reconciliation_input,
        result,
        json_payload,
        markdown,
        final_document,
        final_json,
        final_markdown,
        adapter,
        pins,
    )


def _replace_first_claim(surface: PackageSurface, value: object) -> PackageSurface:
    area = surface.areas[0]
    claim = replace(area.claims[0], value=CanonicalValue.from_data(value))
    changed_area = replace(
        area,
        claims=tuple(sorted((claim, *area.claims[1:]), key=lambda item: item.sort_key)),
    )
    return replace(surface, areas=(changed_area, *surface.areas[1:]))


def _duplicate_first_action(surface: PackageSurface) -> PackageSurface:
    index = next(
        index for index, area in enumerate(surface.areas) if area.area is ComparisonArea.ACTIONS
    )
    area = surface.areas[index]
    action = next(item for item in area.dispositions if item.kind is DispositionKind.ACTION)
    changed_area = replace(
        area,
        dispositions=tuple(sorted((*area.dispositions, action), key=lambda item: item.sort_key)),
    )
    return replace(
        surface, areas=surface.areas[:index] + (changed_area,) + surface.areas[index + 1 :]
    )


def _drop_disposition(case: Case, kind: DispositionKind) -> Case:
    target_id = case.execution_plan.target_package_ref_id
    packages: list[PackageSurface] = []
    for surface in case.reconciliation_input.packages:
        if surface.package_ref.content_id != target_id:
            packages.append(surface)
            continue
        changed = False
        areas: list[AreaSurface] = []
        for area in surface.areas:
            dispositions = list(area.dispositions)
            index = next(
                (index for index, item in enumerate(dispositions) if item.kind is kind),
                None,
            )
            if index is not None and not changed:
                del dispositions[index]
                changed = True
            areas.append(replace(area, dispositions=tuple(dispositions)))
        assert changed
        packages.append(replace(surface, areas=tuple(areas)))
    reconciliation_input = ReconciliationInput(
        case.reconciliation_input.cluster_id,
        tuple(sorted(packages, key=lambda item: item.package_ref.content_id)),
    )
    result = reconcile(reconciliation_input)
    json_payload = render_json(result)
    markdown = render_markdown(result)
    pins = replace(
        case.pins,
        reconciliation_input_sha256=reconciliation_input.content_id,
        reconciliation_result_sha256=result.content_id,
        reconciliation_json_sha256=sha(json_payload),
        reconciliation_markdown_sha256=sha(markdown),
    )
    return replace(
        case,
        reconciliation_input=reconciliation_input,
        reconciliation=result,
        reconciliation_json=json_payload,
        reconciliation_markdown=markdown,
        pins=pins,
    )


def codes(case: Case) -> set[str]:
    return {item.code for item in validate_completion(**case.arguments()).diagnostics}


def test_complete_chain_is_accepted_and_content_addressed() -> None:
    case = valid_case()
    first = validate_completion(**case.arguments())
    second = validate_completion(**case.arguments())

    assert first.accepted
    assert first.content_id == second.content_id
    assert first.candidate_count > 1
    assert first.action_count == 4
    assert first.variant_count == 2
    assert first.warning_count == 1


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
        ("preparation_invalid", "PREPARATION_FIELDS_INVALID"),
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
        ("cluster_mismatch", "RECONCILIATION_CLUSTER_MISMATCH"),
        ("reconciliation_incomplete", "RECONCILIATION_STRUCTURE_INVALID"),
        ("reconciliation_wrong_type", "RECONCILIATION_TYPE_INVALID"),
        ("json_changed", "RENDER_AGREEMENT_INVALID"),
        ("markdown_changed", "RENDER_AGREEMENT_INVALID"),
        ("final_json_changed", "FINAL_IR_DERIVATION_INVALID"),
        ("final_markdown_changed", "FINAL_IR_DERIVATION_INVALID"),
        ("final_wrong_type", "FINAL_IR_TYPE_INVALID"),
        ("reconciliation_input_changed", "RECONCILIATION_INPUT_MISMATCH"),
        ("pin_changed", "PIN_MISMATCH"),
    ],
)
def test_hostile_mutation_matrix_fails_closed(mutation: str, expected: str) -> None:
    case = valid_case()
    if mutation == "preparation_invalid":
        case = replace(
            case,
            preparation=replace_preparation(case.preparation, revision="unsupported"),
        )
    elif mutation == "invocation_blocked":
        invocation = replace(case.preparation.invocations[0], status="BLOCKED")
        case = replace(
            case,
            preparation=replace_preparation(case.preparation, invocations=(invocation,)),
        )
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
    elif mutation == "cluster_mismatch":
        object.__setattr__(case.reconciliation, "cluster_id", "cluster-transplanted")
    elif mutation == "reconciliation_incomplete":
        object.__setattr__(case.reconciliation, "status", ClosureStatus.INCOMPLETE)
    elif mutation == "reconciliation_wrong_type":
        case = replace(case, reconciliation=object())
    elif mutation == "json_changed":
        case = replace(case, reconciliation_json=case.reconciliation_json + b"\n")
    elif mutation == "markdown_changed":
        case = replace(case, reconciliation_markdown=case.reconciliation_markdown + "\n")
    elif mutation == "final_json_changed":
        case = replace(case, final_ir_json=case.final_ir_json + b" ")
    elif mutation == "final_markdown_changed":
        case = replace(case, final_ir_markdown=case.final_ir_markdown + "\n")
    elif mutation == "final_wrong_type":
        case = replace(case, final_ir=cast(FinalProtocolIRDocument, object()))
    elif mutation == "reconciliation_input_changed":
        case = replace(
            case,
            reconciliation_input=replace(
                case.reconciliation_input,
                cluster_id="cluster-transplanted",
            ),
        )
    elif mutation == "pin_changed":
        case = replace(
            case,
            pins=replace(case.pins, reconciliation_result_sha256=sha("changed")),
        )

    receipt = validate_completion(**case.arguments())
    assert not receipt.accepted
    assert expected in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (DispositionKind.CANDIDATE, "CANDIDATE_FINAL_IR_SET_MISMATCH"),
        (DispositionKind.ACTION, "ACTION_FINAL_IR_SET_MISMATCH"),
        (DispositionKind.VARIANT, "VARIANT_FINAL_IR_SET_MISMATCH"),
    ],
)
def test_caller_consistent_ledger_omission_cannot_shrink_final_ir_sets(
    kind: DispositionKind, expected: str
) -> None:
    case = _drop_disposition(valid_case(), kind)

    assert expected in codes(case)
    assert "FINAL_SURFACE_MISMATCH" in codes(case)


def test_caller_claim_substitution_cannot_replace_final_ir_semantics() -> None:
    case = valid_case(target_claim="caller-substitution")

    assert "FINAL_SURFACE_MISMATCH" in codes(case)


def test_reconciliation_result_is_reproduced_from_its_exact_input() -> None:
    case = valid_case()
    object.__setattr__(case.reconciliation, "status", ClosureStatus.INCOMPLETE)

    assert "RECONCILIATION_RESULT_MISMATCH" in codes(case)


def test_legacy_v05_ir_is_never_terminally_accepted() -> None:
    case = valid_case()
    legacy_data, identifiers = _authorized_single_leaf_document()
    legacy = loads_ir(
        json.dumps(legacy_data, sort_keys=True, separators=(",", ":")),
        trusted_receipts=_trusted_receipts(legacy_data, identifiers["package"]),
    )

    case = replace(case, final_ir=cast(FinalProtocolIRDocument, legacy))

    assert "FINAL_IR_TYPE_INVALID" in codes(case)


def test_root_provenance_must_exactly_close_every_final_ir_anchor() -> None:
    case = valid_case()
    target = next(
        surface
        for surface in case.reconciliation_input.packages
        if surface.package_ref.content_id == case.execution_plan.target_package_ref_id
    )
    root = target.roots[0]
    incomplete_root = replace(root, evidence_anchor_ids=root.evidence_anchor_ids[:-1])

    with pytest.raises(ReconciliationError, match="exactly partition"):
        derive_final_ir_package_surface(
            package_ref=target.package_ref,
            report_sha256=target.report_sha256,
            report_revision=target.report_revision,
            roots=(incomplete_root,),
            document=case.final_ir,
            canonical_json=case.final_ir_json,
            markdown=case.final_ir_markdown,
        )


def test_terminal_schema_digest_is_measured_from_the_schema_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = valid_case()
    monkeypatch.setattr(
        validation_gates,
        "final_schema_document",
        lambda: {"schema_revision": "hostile-substitution"},
    )

    result = codes(case)

    assert "VALIDATED_OUTPUT_INVALID" in result
    assert "PIN_MISMATCH" in result


def test_pin_type_and_duplicate_adapter_records_are_rejected_at_construction() -> None:
    case = valid_case()
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(case.pins, execution_plan_sha256="not-a-digest")
    with pytest.raises(ValueError, match="candidate occurrences must be unique"):
        replace(
            case.adapter,
            candidate_links=(case.adapter.candidate_links[0], case.adapter.candidate_links[0]),
        )


def test_preparation_type_identity_and_preflight_transplants_are_rejected() -> None:
    case = valid_case()

    wrong_type = replace(case, preparation=cast(PreparationReceipt, object()))
    assert "PREPARATION_TYPE_INVALID" in codes(wrong_type)

    transplanted_identity = replace_preparation(
        case.preparation,
        package_name="org.example.other",
    )
    identity_pins = replace(
        case.pins,
        preparation_receipt_sha256=transplanted_identity.content_id,
    )
    assert "PREPARATION_IDENTITY_MISMATCH" in codes(
        replace(case, preparation=transplanted_identity, pins=identity_pins)
    )

    transplanted_preflight = replace_preparation(
        case.preparation,
        preflight_manifest_sha256=sha("other-preflight"),
    )
    preflight_pins = replace(
        case.pins,
        preparation_receipt_sha256=transplanted_preflight.content_id,
        preflight_manifest_sha256=transplanted_preflight.preflight_manifest_sha256,
    )
    assert "PREPARATION_PREFLIGHT_MISMATCH" in codes(
        replace(case, preparation=transplanted_preflight, pins=preflight_pins)
    )


def test_preparation_cannot_be_reissued_by_repinning_completion_inputs() -> None:
    case = valid_case()
    forged = replace_preparation(case.preparation, manifest_sha256=sha("forged-manifest"))
    forged_pins = replace(
        case.pins,
        preparation_receipt_sha256=forged.content_id,
        preparation_manifest_sha256=forged.manifest_sha256,
    )

    assert "PREPARATION_PLAN_BINDING_MISMATCH" in codes(
        replace(case, preparation=forged, pins=forged_pins)
    )


def test_preparation_capabilities_are_bound_to_the_frozen_plan() -> None:
    case = valid_case()
    forged = replace_preparation(case.preparation, authority_sha256=sha("forged-authority"))
    forged_pins = replace(
        case.pins,
        preparation_receipt_sha256=forged.content_id,
        preparation_authority_sha256=forged.authority_sha256,
    )

    result = codes(replace(case, preparation=forged, pins=forged_pins))
    assert "PREPARATION_PLAN_BINDING_MISMATCH" in result
    assert "PREPARATION_CAPABILITY_MISMATCH" in result


def test_occurrence_identities_reject_hostile_runtime_strings_deterministically() -> None:
    prepared = preparation()
    candidate = replace(prepared.candidates[0], signal="\ud800")
    warning = replace(prepared.invocations[0].warnings[0], text="\ud800")
    invalid_stream = replace(prepared.invocations[0].warnings[0])
    object.__setattr__(invalid_stream, "stream", [])

    with pytest.raises(ValidationError, match="valid Unicode"):
        candidate_occurrence_id(candidate)
    with pytest.raises(ValidationError, match="warning text is invalid"):
        warning_occurrence_id(prepared.invocations[0], warning)
    with pytest.raises(ValidationError, match="warning stream is invalid"):
        warning_occurrence_id(prepared.invocations[0], invalid_stream)
