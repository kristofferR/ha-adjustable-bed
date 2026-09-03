"""Authenticated hostile tests for the Phase 4 v2 terminal gates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.validation.gates as validation_gates
from tests.phase4_v2_orchestration_acceptance import (
    AuthenticatedSyntheticPackage,
    _protected_stage_authorities,
    _signed,
    complete_authenticated_exact_reuse_synthetic_package_inputs,
    complete_authenticated_synthetic_package_inputs,
)
from tests.phase4_v2_orchestration_testing import (
    _authorized_final_ir,
    build_synthetic_package_inputs,
    protected_exact_reuse_trust,
    protected_fixture_trust,
)
from tests.test_phase4_v2_ir import _authorized_single_leaf_document, _trusted_receipts
from tools.phase4_v2.equivalence import (
    FINAL_IR_SCHEMA_SHA256,
    PackagePlanStatus,
)
from tools.phase4_v2.ir import (
    FinalProtocolIRDocument,
    dumps_final_ir,
    loads_final_ir,
    loads_ir,
    render_final_ir_markdown,
)
from tools.phase4_v2.orchestration import (
    PACKAGE_AUDIT_COMPLETION_REVISION,
    ActivatedStageAuthority,
    AuthenticatedReconciliationInput,
    ClusterGraphPlan,
    TrustedPackageAuditReceipt,
    WorkStage,
    build_authenticated_reconciliation_input,
    build_cluster_graph,
    finish_package_audit,
    load_package_audit_receipt,
    materialize_cluster_graph,
    package_audit_unit_id,
    stage_authority_capability,
)
from tools.phase4_v2.queue import Queue, QueueConflictError
from tools.phase4_v2.reconciliation import (
    CanonicalValue,
    ClosureStatus,
    ComparisonArea,
    DispositionKind,
    DispositionStatus,
    LedgerDisposition,
    PackageSurface,
    ReconciliationInput,
    ReconciliationResult,
    derive_authenticated_final_ir_package_surface,
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
)


def _sha(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class _TerminalPackage:
    authenticated: AuthenticatedSyntheticPackage
    document: FinalProtocolIRDocument
    canonical_json: bytes
    markdown: str
    surface: PackageSurface
    candidate_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    variant_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Case:
    queue: Queue
    packages: tuple[_TerminalPackage, ...]
    graph: ClusterGraphPlan
    audit_authority: ActivatedStageAuthority
    authenticated_reconciliation_input: AuthenticatedReconciliationInput
    reconciliation: ReconciliationResult
    reconciliation_json: bytes
    reconciliation_markdown: str
    adapter: CompletionAdapter
    pins: ValidationPins

    @property
    def target(self) -> _TerminalPackage:
        return self.packages[0]

    @property
    def reconciliation_input(self) -> ReconciliationInput:
        return self.authenticated_reconciliation_input.reconciliation_input

    def arguments(self) -> dict[str, object]:
        target = self.target.authenticated
        return {
            "preparation": target.preparation_receipt,
            "execution_plan": target.frozen_plan,
            "validated_output": target.output,
            "execution_envelope": target.execution_envelope,
            "queue": self.queue,
            "package_ref": target.package_ref,
            "report_bytes": target.report_bytes,
            "report_manifest_bytes": target.report_manifest_bytes,
            "source_registry": target.source_registry,
            "exact_reuse_receipts": target.exact_reuse_receipts,
            "reconciliation_input": self.reconciliation_input,
            "authenticated_reconciliation_input": self.authenticated_reconciliation_input,
            "reconciliation": self.reconciliation,
            "reconciliation_json": self.reconciliation_json,
            "reconciliation_markdown": self.reconciliation_markdown,
            "final_ir": self.target.document,
            "final_ir_json": self.target.canonical_json,
            "final_ir_markdown": self.target.markdown,
            "adapter": self.adapter,
            "pins": self.pins,
        }


def _terminal(queue: Queue, package: AuthenticatedSyntheticPackage) -> _TerminalPackage:
    data, receipts = _authorized_final_ir(package.source_registry)
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    document = loads_final_ir(encoded, trusted_receipts=receipts)
    canonical = dumps_final_ir(document)
    markdown = render_final_ir_markdown(document)
    derivation = derive_authenticated_final_ir_package_surface(
        package_ref=package.package_ref,
        execution_plan=package.frozen_plan,
        queue=queue,
        validated_output=package.output,
        execution_envelope=package.execution_envelope,
        report_bytes=package.report_bytes,
        report_manifest_bytes=package.report_manifest_bytes,
        document=document,
        canonical_json=canonical,
        markdown=markdown,
        source_registry=package.source_registry,
        exact_reuse_receipts=package.exact_reuse_receipts,
    )
    return _TerminalPackage(
        package,
        document,
        canonical,
        markdown,
        derivation.package_surface,
        derivation.candidate_ids,
        derivation.action_ids,
        derivation.variant_ids,
    )


def _adapter(target: _TerminalPackage) -> CompletionAdapter:
    candidates = target.authenticated.preparation_receipt.candidates
    if len(candidates) > len(target.candidate_ids):
        raise RuntimeError("terminal fixture has fewer candidates than preparation")
    return CompletionAdapter(
        target.authenticated.package_ref.content_id,
        tuple(
            sorted(
                CandidateLink(candidate_occurrence_id(candidate), report_id)
                for candidate, report_id in zip(
                    candidates,
                    target.candidate_ids[: len(candidates)],
                    strict=True,
                )
            )
        ),
        (),
    )


def _pins(
    target: _TerminalPackage,
    reconciliation_input: ReconciliationInput,
    result: ReconciliationResult,
    rendered_json: bytes,
    rendered_markdown: str,
    adapter: CompletionAdapter,
) -> ValidationPins:
    preparation = target.authenticated.preparation_receipt
    return ValidationPins(
        preparation_receipt_sha256=preparation.content_id,
        preflight_manifest_sha256=preparation.preflight_manifest_sha256,
        preparation_manifest_sha256=preparation.manifest_sha256,
        candidate_index_sha256=preparation.candidate_index_sha256,
        candidate_contract_sha256=preparation.candidate_contract_sha256,
        preparation_authority_sha256=preparation.authority_sha256,
        tool_registry_sha256=preparation.tool_registry_sha256,
        execution_profile_sha256=preparation.execution_profile_sha256,
        execution_plan_sha256=target.authenticated.frozen_plan.digest,
        validated_package_output_sha256=target.authenticated.output.content_id,
        reconciliation_input_sha256=reconciliation_input.content_id,
        reconciliation_result_sha256=result.content_id,
        reconciliation_json_sha256=_sha(rendered_json),
        reconciliation_markdown_sha256=_sha(rendered_markdown),
        completion_adapter_sha256=adapter.content_id,
        final_ir_schema_sha256=FINAL_IR_SCHEMA_SHA256,
        final_ir_json_sha256=_sha(target.canonical_json),
        final_ir_markdown_sha256=_sha(target.markdown),
        final_package_surface_sha256=target.surface.content_id,
    )


def _build_audited_input(
    queue: Queue,
    packages: tuple[_TerminalPackage, ...],
    surfaces: tuple[PackageSurface, ...],
    active_capabilities: set[tuple[str, str, str]],
    keys: dict[str, Ed25519PrivateKey],
    authorities: dict[str, ActivatedStageAuthority],
) -> tuple[ClusterGraphPlan, AuthenticatedReconciliationInput]:
    for authority in authorities.values():
        pin = stage_authority_capability(authority)
        identity = (pin.capability, pin.revision, pin.digest)
        if identity not in active_capabilities:
            queue.register_capability(*identity)
            queue.activate_capability_from_absent(*identity)
            active_capabilities.add(identity)
    graph = build_cluster_graph(
        queue,
        tuple(item.authenticated.frozen_plan for item in packages),
        audit_authority=authorities["audit"],
        reconciliation_authority=authorities["reconciliation"],
        implementation_authority=authorities["implementation"],
        publication_authority=authorities["publication"],
    )
    materialize_cluster_graph(queue, graph)
    surfaces_by_package = {item.package_ref.content_id: item for item in surfaces}
    receipts: list[TrustedPackageAuditReceipt] = []
    for index in range(len(packages)):
        lease = queue.claim(
            f"validation-gate-audit-{index}",
            allowed_kinds=(WorkStage.PACKAGE_AUDIT.value,),
        )
        if lease is None:
            raise RuntimeError("synthetic package audit did not become ready")
        package = next(
            item
            for item in graph.packages
            if package_audit_unit_id(graph, item.package_ref_id) == lease.unit_id
        )
        analysis = next(item for item in queue.snapshot().units if item.unit_id == package.unit_id)
        canonical = _signed(
            "audit",
            {
                "accepted": True,
                "analysis_completion_revision": analysis.completion_revision,
                "analysis_completion_sha256": analysis.output_digest,
                "package_surface_sha256": surfaces_by_package[package.package_ref_id].content_id,
                "cluster_id": graph.cluster_id,
                "diagnostics": [],
                "graph_sha256": graph.content_id,
                "package_ref_id": package.package_ref_id,
                "revision": PACKAGE_AUDIT_COMPLETION_REVISION,
                "stage_input_sha256": lease.input_digest,
            },
            keys["audit"],
            authorities["audit"],
        )
        receipt = load_package_audit_receipt(canonical, authorities["audit"])
        finish_package_audit(
            queue,
            lease,
            graph=graph,
            authority=authorities["audit"],
            receipt=receipt,
        )
        receipts.append(receipt)
    authenticated_input = build_authenticated_reconciliation_input(
        queue=queue,
        graph=graph,
        authority=authorities["audit"],
        package_surfaces=surfaces,
        audit_receipts=tuple(sorted(receipts, key=lambda item: item.package_ref_id)),
    )
    return graph, authenticated_input


@contextmanager
def _case_context(
    root: Path,
    surface_mutator: Callable[[tuple[PackageSurface, ...]], tuple[PackageSurface, ...]]
    | None = None,
    route_mode: str = "full",
) -> Iterator[_Case]:
    queue = Queue(root / "queue.sqlite3", root / "attempts")
    queue.initialize()
    with (
        protected_fixture_trust(root / "trust") as trust,
        protected_exact_reuse_trust() as exact_trust,
        _protected_stage_authorities() as (keys, authorities),
    ):
        active: set[tuple[str, str, str]] = set()
        if route_mode == "full":
            authenticated = tuple(
                complete_authenticated_synthetic_package_inputs(
                    queue,
                    build_synthetic_package_inputs(
                        root / "cluster-gates",
                        cluster_id="cluster-gates",
                        package_index=index,
                        trust=trust,
                    ),
                    trust,
                    active,
                )
                for index in range(2)
            )
        else:
            source = complete_authenticated_synthetic_package_inputs(
                queue,
                build_synthetic_package_inputs(
                    root / "cluster-gates",
                    cluster_id="cluster-gates",
                    package_index=1,
                    trust=trust,
                ),
                trust,
                active,
            )
            target = complete_authenticated_exact_reuse_synthetic_package_inputs(
                queue,
                build_synthetic_package_inputs(
                    root / "cluster-gates",
                    cluster_id="cluster-gates",
                    package_index=0,
                    trust=trust,
                    root_count=2 if route_mode == "mixed" else 1,
                ),
                source,
                trust,
                exact_trust,
                active,
                include_full_root=route_mode == "mixed",
            )
            authenticated = (target, source)
        packages = tuple(_terminal(queue, item) for item in authenticated)
        surfaces = tuple(item.surface for item in packages)
        if surface_mutator is not None:
            surfaces = surface_mutator(surfaces)
        graph, authenticated_input = _build_audited_input(
            queue, packages, surfaces, active, keys, authorities
        )
        reconciliation_input = authenticated_input.reconciliation_input
        result = reconcile(reconciliation_input)
        rendered_json = render_json(result)
        rendered_markdown = render_markdown(result)
        adapter = _adapter(packages[0])
        yield _Case(
            queue,
            packages,
            graph,
            authorities["audit"],
            authenticated_input,
            result,
            rendered_json,
            rendered_markdown,
            adapter,
            _pins(
                packages[0],
                reconciliation_input,
                result,
                rendered_json,
                rendered_markdown,
                adapter,
            ),
        )


@pytest.fixture
def case(tmp_path: Path) -> Iterator[_Case]:
    with _case_context(tmp_path) as value:
        yield value


def _codes(case: _Case) -> set[str]:
    return {item.code for item in validate_completion(**case.arguments()).diagnostics}


def test_genuine_authenticated_full_chain_is_accepted(case: _Case) -> None:
    first = validate_completion(**case.arguments())
    second = validate_completion(**case.arguments())

    assert first.accepted
    assert first.content_id == second.content_id
    assert first.candidate_count == 23
    assert first.action_count == 1
    assert first.variant_count == 1
    assert first.warning_count == 0
    assert all(
        root.route.value == "FULL_ANALYSIS"
        for package in case.packages
        for root in package.surface.roots
    )


def test_genuine_authenticated_mixed_route_set_is_accepted(tmp_path: Path) -> None:
    with _case_context(tmp_path, route_mode="mixed") as route_case:
        receipt = validate_completion(**route_case.arguments())

        assert receipt.accepted
        assert receipt.action_count == 1
        assert receipt.variant_count == 1
        assert {root.route.value for root in route_case.target.surface.roots} == {
            "FULL_ANALYSIS",
            "EXACT_REUSE",
        }
        assert len(route_case.target.authenticated.exact_reuse_receipts) == 1


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("execution_plan", "FINAL_IR_DERIVATION_INVALID"),
        ("validated_output", "VALIDATED_OUTPUT_AUTHENTICATION_INVALID"),
        ("execution_envelope", "VALIDATED_OUTPUT_AUTHENTICATION_INVALID"),
        ("report_bytes", "FINAL_IR_DERIVATION_INVALID"),
        ("report_manifest_bytes", "FINAL_IR_DERIVATION_INVALID"),
        ("source_registry", "FINAL_IR_DERIVATION_INVALID"),
        ("final_ir", "FINAL_IR_DERIVATION_INVALID"),
        ("final_ir_json", "FINAL_IR_DERIVATION_INVALID"),
    ],
)
def test_cross_package_transplants_fail_closed(case: _Case, field: str, expected: str) -> None:
    arguments = case.arguments()
    peer = case.packages[1]
    replacements: dict[str, object] = {
        "execution_plan": peer.authenticated.frozen_plan,
        "validated_output": peer.authenticated.output,
        "execution_envelope": peer.authenticated.execution_envelope,
        "report_bytes": peer.authenticated.report_bytes,
        "report_manifest_bytes": peer.authenticated.report_manifest_bytes,
        "source_registry": peer.authenticated.source_registry,
        "final_ir": peer.document,
        "final_ir_json": peer.canonical_json,
        "final_ir_markdown": peer.markdown,
    }
    arguments[field] = replacements[field]

    result = validate_completion(**arguments)

    assert not result.accepted
    assert expected in {item.code for item in result.diagnostics}


def test_terminal_markdown_mutation_is_rejected(case: _Case) -> None:
    arguments = case.arguments()
    arguments["final_ir_markdown"] = case.target.markdown + "\n"

    result = validate_completion(**arguments)

    assert not result.accepted
    assert "FINAL_IR_DERIVATION_INVALID" in {item.code for item in result.diagnostics}


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing", "CANDIDATE_SOURCE_SET_MISMATCH"),
        ("unknown_source", "CANDIDATE_SOURCE_SET_MISMATCH"),
        ("unknown_report", "CANDIDATE_REPORT_SET_MISMATCH"),
    ],
)
def test_candidate_links_are_exact_and_not_caller_shrinkable(
    case: _Case, mutation: str, expected: str
) -> None:
    links = case.adapter.candidate_links
    if mutation == "missing":
        changed = links[:-1]
    elif mutation == "unknown_source":
        changed = tuple(sorted((*links[:-1], replace(links[-1], occurrence_id=_sha("unknown")))))
    else:
        changed = tuple(
            sorted((*links[:-1], replace(links[-1], report_item_id=f"candidate:{_sha('unknown')}")))
        )
    adapter = CompletionAdapter(
        case.adapter.target_package_ref_id,
        changed,
        case.adapter.warning_dispositions,
    )
    changed_case = replace(
        case,
        adapter=adapter,
        pins=replace(case.pins, completion_adapter_sha256=adapter.content_id),
    )

    assert expected in _codes(changed_case)


def _candidate_ledger_mutation(
    surfaces: tuple[PackageSurface, ...], *, omit: bool
) -> tuple[PackageSurface, ...]:
    target = surfaces[0]
    index = next(
        index for index, area in enumerate(target.areas) if area.area is ComparisonArea.ACTIONS
    )
    area = target.areas[index]
    candidates = tuple(item for item in area.dispositions if item.kind is DispositionKind.CANDIDATE)
    if not candidates:
        raise RuntimeError("candidate-rich fixture produced no candidate dispositions")
    if omit:
        dispositions = tuple(item for item in area.dispositions if item != candidates[-1])
    else:
        witness = candidates[0]
        dispositions = tuple(
            sorted(
                (
                    *area.dispositions,
                    LedgerDisposition(
                        DispositionKind.CANDIDATE,
                        f"candidate:{_sha('hostile extra')}",
                        DispositionStatus.EXCLUDED,
                        "hostile-extra",
                        (),
                        witness.provenance,
                    ),
                ),
                key=lambda item: item.sort_key,
            )
        )
    changed = replace(area, dispositions=dispositions)
    surface = replace(
        target,
        areas=target.areas[:index] + (changed,) + target.areas[index + 1 :],
    )
    return (surface, *surfaces[1:])


@pytest.mark.parametrize("omit", [True, False], ids=["omission", "extra"])
def test_authenticated_candidate_ledger_cannot_omit_or_add_atoms(
    tmp_path: Path, omit: bool
) -> None:
    with _case_context(
        tmp_path,
        lambda surfaces: _candidate_ledger_mutation(surfaces, omit=omit),
    ) as changed:
        result = _codes(changed)

    assert "CANDIDATE_FINAL_IR_SET_MISMATCH" in result
    assert "FINAL_SURFACE_MISMATCH" in result


@pytest.mark.parametrize("kind", [DispositionKind.ACTION, DispositionKind.VARIANT])
@pytest.mark.parametrize("omit", [True, False], ids=["omission", "extra"])
def test_authenticated_action_and_variant_ledgers_require_exact_sets(
    tmp_path: Path, kind: DispositionKind, omit: bool
) -> None:
    area_kind = (
        ComparisonArea.ACTIONS if kind is DispositionKind.ACTION else ComparisonArea.MODELS_VARIANTS
    )

    def mutate(surfaces: tuple[PackageSurface, ...]) -> tuple[PackageSurface, ...]:
        target = surfaces[0]
        index = next(index for index, area in enumerate(target.areas) if area.area is area_kind)
        area = target.areas[index]
        matching = tuple(item for item in area.dispositions if item.kind is kind)
        if not matching:
            raise RuntimeError("rich terminal fixture produced no requested dispositions")
        if omit:
            dispositions = tuple(item for item in area.dispositions if item != matching[-1])
        else:
            extra = LedgerDisposition(
                kind,
                f"{kind.value.lower()}:{_sha('hostile extra')}",
                DispositionStatus.EXCLUDED,
                "hostile-extra",
                (),
                matching[0].provenance,
            )
            dispositions = tuple(
                sorted((*area.dispositions, extra), key=lambda item: item.sort_key)
            )
        changed = replace(
            area,
            dispositions=dispositions,
        )
        surface = replace(
            target,
            areas=target.areas[:index] + (changed,) + target.areas[index + 1 :],
        )
        return (surface, *surfaces[1:])

    with _case_context(tmp_path, mutate) as changed_case:
        result = _codes(changed_case)

    assert f"{kind.value}_FINAL_IR_SET_MISMATCH" in result
    assert "FINAL_SURFACE_MISMATCH" in result


def test_warning_disposition_set_and_blocking_status_fail_closed(case: _Case) -> None:
    extra = WarningDisposition(
        _sha("unknown warning"),
        WarningStatus.BLOCKING,
        "hostile-extra",
        _sha("unsupported warning disposition"),
    )
    adapter = CompletionAdapter(
        case.adapter.target_package_ref_id,
        case.adapter.candidate_links,
        (extra,),
    )
    changed = replace(
        case,
        adapter=adapter,
        pins=replace(case.pins, completion_adapter_sha256=adapter.content_id),
    )

    assert {"WARNING_SET_MISMATCH", "WARNING_BLOCKING"} <= _codes(changed)


@pytest.mark.parametrize(
    "mutation",
    ["missing_surface", "extra_surface", "wrong_surface_type", "substituted_surface"],
)
def test_authenticated_peer_input_rejects_surface_set_mutations(case: _Case, mutation: str) -> None:
    surfaces: object = tuple(item.surface for item in case.packages)
    if mutation == "missing_surface":
        surfaces = cast(tuple[PackageSurface, ...], surfaces)[:-1]
    elif mutation == "extra_surface":
        surfaces = (*cast(tuple[PackageSurface, ...], surfaces), case.target.surface)
    elif mutation == "wrong_surface_type":
        surfaces = [*cast(tuple[PackageSurface, ...], surfaces)]
    else:
        surfaces = (case.target.surface, case.target.surface)

    with pytest.raises(QueueConflictError):
        build_authenticated_reconciliation_input(
            queue=case.queue,
            graph=case.graph,
            authority=case.audit_authority,
            package_surfaces=cast(tuple[PackageSurface, ...], surfaces),
            audit_receipts=case.authenticated_reconciliation_input.audit_receipts,
        )


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_type", "transplanted"])
def test_authenticated_peer_input_rejects_audit_set_mutations(case: _Case, mutation: str) -> None:
    original = case.authenticated_reconciliation_input.audit_receipts
    receipts: object = original
    if mutation == "missing":
        receipts = original[:-1]
    elif mutation == "extra":
        receipts = (*original, original[0])
    elif mutation == "wrong_type":
        receipts = [*original]
    else:
        object.__setattr__(original[0], "package_ref_id", _sha("transplanted"))

    with pytest.raises(QueueConflictError):
        build_authenticated_reconciliation_input(
            queue=case.queue,
            graph=case.graph,
            authority=case.audit_authority,
            package_surfaces=tuple(item.surface for item in case.packages),
            audit_receipts=cast(tuple[TrustedPackageAuditReceipt, ...], receipts),
        )


def test_raw_or_forged_peer_input_cannot_bypass_authentication(case: _Case) -> None:
    for forged in (case.reconciliation_input, object()):
        arguments = case.arguments()
        arguments["authenticated_reconciliation_input"] = cast(
            AuthenticatedReconciliationInput, forged
        )
        result = validate_completion(**arguments)
        assert not result.accepted
        assert "RECONCILIATION_INPUT_AUTHENTICATION_INVALID" in {
            item.code for item in result.diagnostics
        }


def test_authenticated_peer_surface_receipt_cannot_cover_changed_bytes(case: _Case) -> None:
    peer = case.packages[1].surface
    area = peer.areas[0]
    changed = replace(
        peer,
        areas=(
            replace(area, closure=ClosureStatus.INCOMPLETE, gaps=("hostile gap",)),
            *peer.areas[1:],
        ),
    )
    surfaces = tuple(
        changed if item.package_ref == peer.package_ref else item
        for item in (package.surface for package in case.packages)
    )

    with pytest.raises(QueueConflictError, match="exact completed authenticated audit"):
        build_authenticated_reconciliation_input(
            queue=case.queue,
            graph=case.graph,
            authority=case.audit_authority,
            package_surfaces=surfaces,
            audit_receipts=case.authenticated_reconciliation_input.audit_receipts,
        )


def test_terminal_incomplete_gates_are_preserved_on_authenticated_input(
    tmp_path: Path,
) -> None:
    def omit_area(surfaces: tuple[PackageSurface, ...]) -> tuple[PackageSurface, ...]:
        target = surfaces[0]
        changed = replace(
            target,
            areas=tuple(area for area in target.areas if area.area is not ComparisonArea.TRANSPORT),
        )
        return (changed, *surfaces[1:])

    with _case_context(tmp_path, omit_area) as changed_case:
        result = _codes(changed_case)

    assert {
        "PAIR_DECISIONS_INCOMPLETE",
        "RECONCILIATION_INCOMPLETE",
        "REPAIRS_REMAIN",
        "FINAL_SURFACE_MISMATCH",
    } <= result


def test_authenticated_claim_substitution_cannot_replace_final_ir_semantics(
    tmp_path: Path,
) -> None:
    def substitute(surfaces: tuple[PackageSurface, ...]) -> tuple[PackageSurface, ...]:
        target = surfaces[0]
        index = next(index for index, area in enumerate(target.areas) if area.claims)
        area = target.areas[index]
        claim = replace(area.claims[0], value=CanonicalValue.from_data("caller substitution"))
        changed_area = replace(area, claims=(claim, *area.claims[1:]))
        changed = replace(
            target,
            areas=target.areas[:index] + (changed_area,) + target.areas[index + 1 :],
        )
        return (changed, *surfaces[1:])

    with _case_context(tmp_path, substitute) as changed_case:
        result = _codes(changed_case)

    assert "FINAL_SURFACE_MISMATCH" in result


def test_reconciliation_result_is_reproduced_from_exact_input(case: _Case) -> None:
    object.__setattr__(case.reconciliation, "status", ClosureStatus.INCOMPLETE)

    assert "RECONCILIATION_RESULT_MISMATCH" in _codes(case)


def test_legacy_ir_is_never_terminally_accepted(case: _Case) -> None:
    legacy_data, identifiers = _authorized_single_leaf_document()
    legacy = loads_ir(
        json.dumps(legacy_data, sort_keys=True, separators=(",", ":")),
        trusted_receipts=_trusted_receipts(legacy_data, identifiers["package"]),
    )
    arguments = case.arguments()
    arguments["final_ir"] = cast(FinalProtocolIRDocument, legacy)

    result = validate_completion(**arguments)

    assert not result.accepted
    assert "FINAL_IR_TYPE_INVALID" in {item.code for item in result.diagnostics}


def test_root_anchor_closure_is_rechecked_against_canonical_ir(case: _Case) -> None:
    object.__setattr__(case.target.document, "evidence_anchors", ())

    assert "FINAL_IR_DERIVATION_INVALID" in _codes(case)


def test_terminal_schema_digest_is_measured_from_schema_document(
    case: _Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        validation_gates,
        "final_schema_document",
        lambda: {"schema_revision": "hostile-substitution"},
    )

    result = _codes(case)

    assert "VALIDATED_OUTPUT_INVALID" in result
    assert "PIN_MISMATCH" in result


def test_pin_and_adapter_exact_types_are_enforced(case: _Case) -> None:
    with pytest.raises(ValidationError, match="pins must use the exact ValidationPins type"):
        validate_completion(**{**case.arguments(), "pins": cast(ValidationPins, object())})
    link = case.adapter.candidate_links[0]
    with pytest.raises(ValidationError, match="candidate occurrences must be unique"):
        CompletionAdapter(
            case.adapter.target_package_ref_id,
            (link, link),
            (),
        )


def test_preparation_identity_and_preflight_transplants_are_rejected(case: _Case) -> None:
    preparation = case.target.authenticated.preparation_receipt
    object.__setattr__(preparation, "package_name", "org.example.transplanted")
    object.__setattr__(preparation, "preflight_manifest_sha256", _sha("other preflight"))

    result = _codes(case)

    assert "PREPARATION_IDENTITY_MISMATCH" in result
    assert "PREPARATION_PREFLIGHT_MISMATCH" in result


def test_repinning_does_not_make_mutated_preparation_authoritative(case: _Case) -> None:
    preparation = case.target.authenticated.preparation_receipt
    object.__setattr__(preparation, "manifest_sha256", _sha("forged manifest"))
    repinned = replace(
        case,
        pins=replace(
            case.pins,
            preparation_receipt_sha256=preparation.content_id,
            preparation_manifest_sha256=preparation.manifest_sha256,
        ),
    )

    result = _codes(repinned)

    assert "PREPARATION_PLAN_BINDING_MISMATCH" in result


def test_preparation_capability_binding_is_exact(case: _Case) -> None:
    binding = case.target.authenticated.frozen_plan.preparation
    object.__setattr__(
        case.target.authenticated.frozen_plan,
        "preparation",
        binding._replace(capabilities=binding.capabilities[:-1]),
    )

    result = _codes(case)

    assert "PREPARATION_CAPABILITY_MISMATCH" in result
    assert "PLAN_STRUCTURE_INVALID" in result


@pytest.mark.parametrize("field", ["name", "revision", "digest"])
def test_frozen_capability_identity_mutations_are_rejected(case: _Case, field: str) -> None:
    binding = case.target.authenticated.frozen_plan.preparation
    capability = case.target.authenticated.frozen_plan.preparation.capabilities[0]
    changed = capability._replace(
        **{field: _sha(f"hostile {field}") if field == "digest" else f"hostile-{field}"}
    )
    object.__setattr__(
        case.target.authenticated.frozen_plan,
        "preparation",
        binding._replace(capabilities=(changed, *binding.capabilities[1:])),
    )

    result = _codes(case)

    assert "PLAN_STRUCTURE_INVALID" in result
    assert "PREPARATION_CAPABILITY_MISMATCH" in result


def test_execution_envelope_requires_its_completed_queue_output(
    case: _Case, tmp_path: Path
) -> None:
    empty_queue = Queue(tmp_path / "empty.sqlite3", tmp_path / "empty-attempts")
    empty_queue.initialize()
    arguments = case.arguments()
    arguments["queue"] = empty_queue

    result = validate_completion(**arguments)
    assert not result.accepted
    assert "RECONCILIATION_INPUT_AUTHENTICATION_INVALID" in {
        item.code for item in result.diagnostics
    }


def test_hostile_candidate_occurrence_strings_are_rejected(case: _Case) -> None:
    candidate = replace(
        case.target.authenticated.preparation_receipt.candidates[0], signal="\ud800"
    )

    with pytest.raises(ValidationError, match="candidate.signal is not valid Unicode"):
        candidate_occurrence_id(candidate)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("plan_status", "PLAN_BLOCKED"),
        ("plan_digest", "PLAN_DIGEST_MISMATCH"),
        ("artifact", "ARTIFACT_DIGEST_MISMATCH"),
        ("output_plan", "VALIDATED_OUTPUT_AUTHENTICATION_INVALID"),
        ("output_receipt", "VALIDATED_OUTPUT_AUTHENTICATION_INVALID"),
        ("output_report", "VALIDATED_OUTPUT_AUTHENTICATION_INVALID"),
        ("adapter_target", "ADAPTER_TARGET_MISMATCH"),
        ("reconciliation_cluster", "RECONCILIATION_CLUSTER_MISMATCH"),
        ("reconciliation_input", "RECONCILIATION_INPUT_AUTHENTICATION_INVALID"),
        ("json", "RENDER_AGREEMENT_INVALID"),
        ("markdown", "RENDER_AGREEMENT_INVALID"),
        ("final_json", "FINAL_IR_DERIVATION_INVALID"),
        ("final_markdown", "FINAL_IR_DERIVATION_INVALID"),
        ("pin", "PIN_MISMATCH"),
    ],
)
def test_frozen_hostile_mutation_matrix_fails_closed(
    case: _Case, mutation: str, expected: str
) -> None:
    if mutation == "plan_status":
        object.__setattr__(
            case.target.authenticated.frozen_plan, "status", PackagePlanStatus.BLOCKED
        )
    elif mutation == "plan_digest":
        object.__setattr__(case.target.authenticated.frozen_plan, "digest", _sha("changed"))
    elif mutation == "artifact":
        object.__setattr__(
            case.target.authenticated.frozen_plan,
            "target_artifact_digest",
            _sha("changed"),
        )
    elif mutation == "output_plan":
        object.__setattr__(case.target.authenticated.output, "execution_plan_id", _sha("changed"))
    elif mutation == "output_receipt":
        object.__setattr__(
            case.target.authenticated.output,
            "validation_receipt_sha256",
            _sha("changed"),
        )
    elif mutation == "output_report":
        object.__setattr__(
            case.target.authenticated.output, "target_report_sha256", _sha("changed")
        )
    elif mutation == "adapter_target":
        object.__setattr__(case.adapter, "target_package_ref_id", _sha("changed"))
    elif mutation == "reconciliation_cluster":
        object.__setattr__(case.reconciliation, "cluster_id", "cluster-transplanted")
    elif mutation == "reconciliation_input":
        object.__setattr__(
            case.authenticated_reconciliation_input,
            "reconciliation_input",
            replace(case.reconciliation_input, cluster_id="cluster-transplanted"),
        )
    elif mutation == "json":
        case = replace(case, reconciliation_json=case.reconciliation_json + b"\n")
    elif mutation == "markdown":
        case = replace(case, reconciliation_markdown=case.reconciliation_markdown + "\n")
    elif mutation == "final_json":
        case = replace(
            case,
            packages=(
                replace(case.target, canonical_json=case.target.canonical_json + b" "),
                case.packages[1],
            ),
        )
    elif mutation == "final_markdown":
        case = replace(
            case,
            packages=(replace(case.target, markdown=case.target.markdown + "\n"), case.packages[1]),
        )
    else:
        case = replace(
            case,
            pins=replace(case.pins, reconciliation_result_sha256=_sha("changed")),
        )

    if mutation == "reconciliation_input":
        result = validate_completion(**case.arguments())
        assert not result.accepted
        assert "RECONCILIATION_INPUT_AUTHENTICATION_INVALID" in {
            item.code for item in result.diagnostics
        }
        return

    result = validate_completion(**case.arguments())

    assert not result.accepted
    assert expected in {item.code for item in result.diagnostics}
