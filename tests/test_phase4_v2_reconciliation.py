"""Synthetic contract tests for Phase 4 v2 typed cluster reconciliation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from jsonschema.validators import Draft202012Validator

import tools.phase4_v2.equivalence.core as equivalence_core_module
from tests.phase4_v2_authenticated_fixtures import authenticated_package_ref
from tools.phase4_v2.equivalence import LOCAL_ONLY_DOMAINS, FrozenPackageRef, Route
from tools.phase4_v2.reconciliation import (
    COMPARISON_AREAS,
    INPUT_SCHEMA_CANONICAL_BYTES,
    INPUT_SCHEMA_REVISION,
    INPUT_SCHEMA_SHA256,
    AreaSurface,
    CanonicalValue,
    ClaimPolarity,
    ClosureStatus,
    ComparisonArea,
    ComparisonDecision,
    DispositionKind,
    DispositionStatus,
    LeafProvenance,
    LedgerDisposition,
    NormalizedClaim,
    PackageLocalProvenance,
    PackageLocalTarget,
    PackageSurface,
    ReconciliationError,
    ReconciliationInput,
    RootProvenance,
    dumps_input,
    loads_input,
    reconcile,
    render_json,
    render_markdown,
    schema_document,
    verify_render_agreement,
)
from tools.phase4_v2.reconciliation import engine as reconciliation_engine
from tools.phase4_v2.reconciliation import model as reconciliation_model


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


_VALIDATOR_ACTIVATION = ""


@pytest.fixture(autouse=True)
def _activate_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        equivalence_core_module,
        "_read_protected_validator_pin",
        lambda: _VALIDATOR_ACTIVATION,
    )


def frozen_package(name: str) -> FrozenPackageRef:
    package_ref, activation = authenticated_package_ref(
        package_name=name,
        version_code="17",
        artifact_digest=sha(name + ":artifact"),
        preflight_sha256=sha(name + ":preflight"),
    )
    global _VALIDATOR_ACTIVATION
    _VALIDATOR_ACTIVATION = activation
    return package_ref


def root_for(package: FrozenPackageRef, route: Route = Route.FULL_ANALYSIS) -> RootProvenance:
    return RootProvenance(
        package_ref_id=package.content_id,
        target_root_id=sha(package.package_name + ":root"),
        occurrence_identity_sha256=sha(package.package_name + ":occurrence"),
        route=route,
        semantic_root_sha256=(None if route is Route.BLOCKED else sha("shared-semantic")),
        source_root_id=(sha("source-root") if route is Route.EXACT_REUSE else None),
        source_package_ref_id=(None if route is Route.BLOCKED else package.content_id),
        source_occurrence_identity_sha256=(
            None if route is Route.BLOCKED else sha(package.package_name + ":source-occurrence")
        ),
        source_validation_receipt_sha256=(
            None if route is Route.BLOCKED else sha(package.package_name + ":source-receipt")
        ),
        source_raw_receipt_sha256=(
            None if route is Route.BLOCKED else sha(package.package_name + ":raw-source-receipt")
        ),
        report_pointer="/roots/0",
        evidence_anchor_ids=("conflict-anchor", "leaf-anchor", "root-anchor")
        if route is not Route.BLOCKED
        else (),
        blockers=("tool-unavailable",) if route is Route.BLOCKED else (),
    )


def surface(
    area: ComparisonArea,
    provenance: LeafProvenance,
    *,
    value: object = True,
    polarity: ClaimPolarity = ClaimPolarity.AFFIRMED,
    closure: ClosureStatus = ClosureStatus.COMPLETE,
    dispositions: tuple[LedgerDisposition, ...] = (),
    extra_claims: tuple[NormalizedClaim, ...] = (),
) -> AreaSurface:
    claim = NormalizedClaim(
        key=f"/{area.value}/surface",
        polarity=polarity,
        value=CanonicalValue.from_data(value),
        provenance=(provenance,),
    )
    claims = tuple(sorted((claim, *extra_claims), key=lambda item: item.sort_key))
    return AreaSurface(
        area=area,
        closure=closure,
        claims=claims,
        dispositions=tuple(sorted(dispositions, key=lambda item: item.sort_key)),
        gaps=("unresolved-path",) if closure is ClosureStatus.INCOMPLETE else (),
    )


def disposition(
    area: ComparisonArea,
    provenance: LeafProvenance,
    kind: DispositionKind,
    *,
    status: DispositionStatus = DispositionStatus.COVERED,
    item_id: str = "item-1",
) -> LedgerDisposition:
    return LedgerDisposition(
        kind=kind,
        item_id=item_id,
        status=status,
        reason_code="reachable" if status is DispositionStatus.COVERED else "excluded",
        claim_keys=(f"/{area.value}/surface",) if status is DispositionStatus.COVERED else (),
        provenance=(provenance,),
    )


def package_surface(
    name: str,
    *,
    route: Route = Route.FULL_ANALYSIS,
    values: dict[ComparisonArea, object] | None = None,
    missing: frozenset[ComparisonArea] = frozenset(),
    incomplete: frozenset[ComparisonArea] = frozenset(),
    dispositions: dict[ComparisonArea, tuple[LedgerDisposition, ...]] | None = None,
    extra_claims: dict[ComparisonArea, tuple[NormalizedClaim, ...]] | None = None,
) -> PackageSurface:
    package = frozen_package(name)
    root = root_for(package, route)
    root_provenance = LeafProvenance(
        root_ref_id=root.content_id,
        report_pointer="/normalized/value",
        evidence_anchor_ids=("leaf-anchor",),
    )
    local_targets = tuple(
        PackageLocalTarget(
            evidence_anchor_id=f"local-{domain}",
            terminal_ir_pointer=f"/{area.value}/surface",
            local_domain=domain,
        )
        for domain, area in zip(
            sorted(LOCAL_ONLY_DOMAINS),
            tuple(ComparisonArea)[: len(LOCAL_ONLY_DOMAINS)],
            strict=True,
        )
    )
    package_local = PackageLocalProvenance(
        package_ref_id=package.content_id,
        source_package_id=f"pkg:{sha(name + ':local-source')}",
        source_validation_receipt_sha256=sha(name + ":local-validation"),
        source_raw_receipt_sha256=sha(name + ":local-raw"),
        report_pointer="/package_local_domains",
        mandatory_domains=tuple(sorted(LOCAL_ONLY_DOMAINS)),
        evidence_anchor_ids=tuple(sorted(item.evidence_anchor_id for item in local_targets)),
        targets=tuple(sorted(local_targets, key=lambda item: item.terminal_ir_pointer)),
    )
    local_by_pointer = {item.terminal_ir_pointer: item for item in local_targets}
    areas = tuple(
        surface(
            area,
            (
                LeafProvenance(
                    root_ref_id=package_local.content_id,
                    report_pointer=f"/{area.value}/surface",
                    evidence_anchor_ids=(local_by_pointer[f"/{area.value}/surface"].evidence_anchor_id,),
                )
                if f"/{area.value}/surface" in local_by_pointer
                else root_provenance
            ),
            value=(values or {}).get(area, True),
            closure=(ClosureStatus.INCOMPLETE if area in incomplete else ClosureStatus.COMPLETE),
            dispositions=(dispositions or {}).get(area, ()),
            extra_claims=(extra_claims or {}).get(area, ()),
        )
        for area in ComparisonArea
        if area not in missing
        and (route is not Route.BLOCKED or f"/{area.value}/surface" in local_by_pointer)
    )
    return PackageSurface(
        package_ref=package,
        report_sha256=sha(name + ":report"),
        report_revision="synthetic-report-v1",
        package_local=package_local,
        roots=(root,),
        areas=areas,
    )


def cluster(*packages: PackageSurface) -> ReconciliationInput:
    return ReconciliationInput(
        cluster_id="cluster-synthetic",
        packages=tuple(sorted(packages, key=lambda item: item.package_ref.content_id)),
    )


def claim_for(package: PackageSurface, area: ComparisonArea, value: object) -> NormalizedClaim:
    return NormalizedClaim(
        key=f"/{area.value}/surface",
        polarity=ClaimPolarity.AFFIRMED,
        value=CanonicalValue.from_data(value),
        provenance=(
            LeafProvenance(
                root_ref_id=package.roots[0].content_id,
                report_pointer="/normalized/conflict",
                evidence_anchor_ids=("conflict-anchor",),
            ),
        ),
    )


def test_schema_has_closed_eleven_area_surface_and_is_defensive() -> None:
    assert tuple(item.value for item in ComparisonArea) == COMPARISON_AREAS
    assert len(COMPARISON_AREAS) == 11
    first = schema_document()
    second = schema_document()
    first["title"] = "mutated"
    assert second["title"] != "mutated"
    properties = second["properties"]
    assert isinstance(properties, dict)
    assert properties["revision"] == {"const": INPUT_SCHEMA_REVISION}
    assert hashlib.sha256(INPUT_SCHEMA_CANONICAL_BYTES).hexdigest() == INPUT_SCHEMA_SHA256
    assert json.loads(INPUT_SCHEMA_CANONICAL_BYTES) == second
    Draft202012Validator.check_schema(second)


@pytest.mark.parametrize("route", [Route.FULL_ANALYSIS, Route.EXACT_REUSE])
@pytest.mark.parametrize("incomplete", [False, True])
def test_single_package_work_unit_preserves_closure(route: Route, incomplete: bool) -> None:
    package = package_surface(
        "org.example.single",
        route=route,
        incomplete=frozenset({ComparisonArea.ACTIONS}) if incomplete else frozenset(),
    )
    result = reconcile(cluster(package))
    assert result.pair_decisions == ()
    assert result.status is (ClosureStatus.INCOMPLETE if incomplete else ClosureStatus.COMPLETE)
    assert bool(result.required_full_promotions) is (incomplete and route is Route.EXACT_REUSE)
    assert bool(result.repairs_required) is (incomplete and route is Route.FULL_ANALYSIS)
    assert verify_render_agreement(render_json(result), render_markdown(result)) == result.content_id


def test_single_package_missing_area_and_blocked_root_require_repair() -> None:
    for package in (
        package_surface("org.example.single", missing=frozenset({ComparisonArea.PARSING})),
        package_surface("org.example.single", route=Route.BLOCKED),
    ):
        result = reconcile(cluster(package))
        assert result.status is ClosureStatus.INCOMPLETE
        assert result.repairs_required


def test_identical_semantics_ignore_package_local_provenance() -> None:
    result = reconcile(
        cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    )

    assert result.status is ClosureStatus.COMPLETE
    assert len(result.pair_decisions) == 11
    assert {item.decision for item in result.pair_decisions} == {ComparisonDecision.SAME}
    assert all(len(item.union_atom_ids) == 1 for item in result.area_aggregates)
    assert all(len(item.intersection_atom_ids) == 1 for item in result.area_aggregates)
    assert all(len(item.sources) == 2 for item in result.atoms)


def test_atom_sources_are_sorted_and_deduplicated_by_root() -> None:
    packages: list[PackageSurface] = []
    for name in ("org.example.one", "org.example.two"):
        package = package_surface(name)
        area = package.areas[-1]
        claim = area.claims[0]
        second = replace(claim.provenance[0], report_pointer="/normalized/second")
        changed_claim = replace(
            claim,
            provenance=tuple(sorted((*claim.provenance, second), key=lambda item: item.sort_key)),
        )
        packages.append(
            replace(
                package,
                areas=(*package.areas[:-1], replace(area, claims=(changed_claim,))),
            )
        )

    result = reconcile(cluster(*packages))

    assert all(atom.sources == tuple(sorted(set(atom.sources))) for atom in result.atoms)
    assert all(len(atom.sources) == 2 for atom in result.atoms)


def test_structured_value_order_is_canonical_and_frame_order_is_not_hidden() -> None:
    area = ComparisonArea.PACKET_CONSTRUCTION
    left = package_surface("org.example.one", values={area: {"fields": [1, 2], "target": "write"}})
    equivalent = package_surface(
        "org.example.two", values={area: {"target": "write", "fields": [1, 2]}}
    )
    reordered = package_surface(
        "org.example.three", values={area: {"fields": [2, 1], "target": "write"}}
    )

    result = reconcile(cluster(left, equivalent, reordered))
    decisions = [item for item in result.pair_decisions if item.area is area]
    assert sum(item.decision is ComparisonDecision.SAME for item in decisions) == 1
    assert sum(item.decision is ComparisonDecision.DIFFERENT for item in decisions) == 2
    aggregate = next(item for item in result.area_aggregates if item.area is area)
    assert len(aggregate.union_atom_ids) == 2
    assert aggregate.intersection_atom_ids == ()
    assert result.status is ClosureStatus.COMPLETE


def test_semantic_reversal_is_different_even_when_value_is_equal() -> None:
    area = ComparisonArea.DISCOVERY
    left = package_surface("org.example.one")
    right = package_surface("org.example.two")
    right_area = next(item for item in right.areas if item.area is area)
    reversed_claim = replace(right_area.claims[0], polarity=ClaimPolarity.DENIED)
    replaced_area = replace(right_area, claims=(reversed_claim,))
    right = replace(
        right,
        areas=tuple(replaced_area if item.area is area else item for item in right.areas),
    )

    result = reconcile(cluster(left, right))
    decision = next(item for item in result.pair_decisions if item.area is area)
    assert decision.decision is ComparisonDecision.DIFFERENT


@pytest.mark.parametrize("area", list(ComparisonArea))
def test_each_closed_area_detects_a_leaf_mutation(area: ComparisonArea) -> None:
    left = package_surface("org.example.one", values={area: "before"})
    right = package_surface("org.example.two", values={area: "after"})

    result = reconcile(cluster(left, right))
    decisions = [
        item for item in result.pair_decisions if item.decision is not ComparisonDecision.SAME
    ]

    assert len(decisions) == 1
    assert decisions[0].area is area
    assert decisions[0].decision is ComparisonDecision.DIFFERENT


def test_difference_promotes_only_implicated_exact_reuse_root() -> None:
    area = ComparisonArea.TIMING_STOP_RELEASE
    full = package_surface("org.example.full", values={area: 100})
    reused = package_surface("org.example.reused", route=Route.EXACT_REUSE, values={area: 250})

    result = reconcile(cluster(full, reused))

    assert result.status is ClosureStatus.INCOMPLETE
    assert len(result.required_full_promotions) == 1
    promotion = result.required_full_promotions[0]
    assert promotion.package_ref_id == reused.package_ref.content_id
    assert promotion.root_ref_id == reused.roots[0].content_id
    assert promotion.area is area
    assert promotion.reason_code == "DIFFERENT_SEMANTICS"
    assert result.repairs_required == ()


def test_missing_area_is_explicitly_incomplete_and_routes_follow_up() -> None:
    area = ComparisonArea.PARSING
    complete = package_surface("org.example.complete")
    missing = package_surface(
        "org.example.missing", route=Route.EXACT_REUSE, missing=frozenset({area})
    )

    result = reconcile(cluster(complete, missing))
    decision = next(item for item in result.pair_decisions if item.area is area)

    assert decision.decision is ComparisonDecision.INCOMPLETE
    assert "AREA_MISSING" in " ".join(decision.incomplete_reasons)
    assert any(
        item.package_ref_id == missing.package_ref.content_id
        for item in result.required_full_promotions
    )
    aggregate = next(item for item in result.area_aggregates if item.area is area)
    assert aggregate.incomplete_package_ref_ids == (missing.package_ref.content_id,)


def test_incomplete_full_analysis_requires_repair_not_repromotion() -> None:
    area = ComparisonArea.LIFECYCLE
    complete = package_surface("org.example.complete")
    incomplete = package_surface("org.example.incomplete", incomplete=frozenset({area}))

    result = reconcile(cluster(complete, incomplete))

    assert result.required_full_promotions == ()
    assert any(
        item.package_ref_id == incomplete.package_ref.content_id and item.area is area
        for item in result.repairs_required
    )


@pytest.mark.parametrize(
    "kind,area",
    [
        (DispositionKind.CANDIDATE, ComparisonArea.DISCOVERY),
        (DispositionKind.ACTION, ComparisonArea.ACTIONS),
        (DispositionKind.VARIANT, ComparisonArea.MODELS_VARIANTS),
    ],
)
def test_candidate_action_and_variant_dispositions_are_exact_set_atoms(
    kind: DispositionKind, area: ComparisonArea
) -> None:
    first_base = package_surface("org.example.one")
    second_base = package_surface("org.example.two")
    first_provenance = first_base.areas[0].claims[0].provenance[0]
    second_provenance = second_base.areas[0].claims[0].provenance[0]
    first = package_surface(
        "org.example.one",
        dispositions={area: (disposition(area, first_provenance, kind),)},
    )
    second = package_surface(
        "org.example.two",
        dispositions={
            area: (
                disposition(
                    area,
                    second_provenance,
                    kind,
                    status=DispositionStatus.EXCLUDED,
                ),
            )
        },
    )

    result = reconcile(cluster(first, second))
    decision = next(item for item in result.pair_decisions if item.area is area)

    assert decision.decision is ComparisonDecision.DIFFERENT
    assert len(decision.left_only_atom_ids) == 1
    assert len(decision.right_only_atom_ids) == 1


def test_action_identity_change_is_not_normalized_into_false_equality() -> None:
    area = ComparisonArea.ACTIONS
    first_base = package_surface("org.example.one")
    second_base = package_surface("org.example.two")
    first = package_surface(
        "org.example.one",
        dispositions={
            area: (
                disposition(
                    area,
                    first_base.areas[0].claims[0].provenance[0],
                    DispositionKind.ACTION,
                    item_id="raise",
                ),
            )
        },
    )
    second = package_surface(
        "org.example.two",
        dispositions={
            area: (
                disposition(
                    area,
                    second_base.areas[0].claims[0].provenance[0],
                    DispositionKind.ACTION,
                    item_id="lower",
                ),
            )
        },
    )

    decision = next(
        item for item in reconcile(cluster(first, second)).pair_decisions if item.area is area
    )
    assert decision.decision is ComparisonDecision.DIFFERENT


def test_duplicate_claim_identity_is_rejected_before_reconciliation() -> None:
    area = ComparisonArea.GATT
    base = package_surface("org.example.conflict")
    conflict = claim_for(base, area, "different")
    with pytest.raises(ReconciliationError, match="duplicate semantic claim keys"):
        package_surface("org.example.conflict", extra_claims={area: (conflict,)})


def test_duplicate_disposition_is_a_contradiction_not_silently_deduplicated() -> None:
    area = ComparisonArea.ACTIONS
    base = package_surface("org.example.duplicate")
    provenance = base.areas[0].claims[0].provenance[0]
    item = disposition(area, provenance, DispositionKind.ACTION)
    duplicate = package_surface("org.example.duplicate", dispositions={area: (item, item)})

    result = reconcile(cluster(duplicate, package_surface("org.example.other")))

    assert any(
        item.area is area and item.code == "DUPLICATE_SEMANTIC_IDENTITY"
        for item in result.contradictions
    )


def test_contradiction_and_declared_incompleteness_preserve_every_follow_up_reason() -> None:
    area = ComparisonArea.ACTIONS
    base = package_surface("org.example.duplicate")
    provenance = base.areas[0].claims[0].provenance[0]
    item = disposition(area, provenance, DispositionKind.ACTION)
    duplicate = package_surface(
        "org.example.duplicate",
        incomplete=frozenset({area}),
        dispositions={area: (item, item)},
    )

    result = reconcile(cluster(duplicate, package_surface("org.example.other")))
    reasons = {
        item.reason_code
        for item in result.repairs_required
        if item.package_ref_id == duplicate.package_ref.content_id and item.area is area
    }

    assert reasons == {
        "AREA_DECLARED_INCOMPLETE",
        "CONTRADICTORY_AREA",
        "UNRESOLVED_GAPS",
    }
    assert any(
        item.area is area and item.code == "DUPLICATE_SEMANTIC_IDENTITY"
        for item in result.contradictions
    )


def test_blocked_root_keeps_every_pair_area_incomplete_without_false_promotion() -> None:
    blocked = package_surface("org.example.blocked", route=Route.BLOCKED)
    result = reconcile(cluster(blocked, package_surface("org.example.complete")))

    assert {item.decision for item in result.pair_decisions} == {ComparisonDecision.INCOMPLETE}
    assert result.required_full_promotions == ()
    assert len(result.repairs_required) == 16
    assert all(
        any("ROOT_BLOCKED" in reason for reason in item.incomplete_reasons)
        for item in result.pair_decisions
    )


def test_result_carries_exact_package_report_and_root_identity() -> None:
    first = package_surface("org.example.one")
    result = reconcile(cluster(first, package_surface("org.example.two")))
    reference = next(
        item for item in result.packages if item.package_ref_id == first.package_ref.content_id
    )

    assert reference.package_surface_id == first.content_id
    assert reference.report_sha256 == first.report_sha256
    assert reference.roots[0].root_ref_id == first.roots[0].content_id
    assert reference.roots[0].target_root_id == first.roots[0].target_root_id
    assert reference.roots[0].semantic_root_sha256 == first.roots[0].semantic_root_sha256


def test_input_round_trip_is_canonical_and_content_addressed() -> None:
    value = cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    encoded = dumps_input(value)
    loaded = loads_input(encoded, trusted_input=value)

    assert dumps_input(loaded) == encoded
    assert loaded.content_id == value.content_id
    assert b" " not in encoded
    assert "package_ref_id" in json.loads(encoded)["packages"][0]
    assert "package_ref" not in json.loads(encoded)["packages"][0]
    assert (
        encoded
        == json.dumps(
            json.loads(encoded), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    )


def test_loader_requires_exact_authority_derived_input() -> None:
    value = cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    encoded = dumps_input(value)
    transplanted = cluster(package_surface("org.example.one"), package_surface("org.example.other"))
    with pytest.raises(ReconciliationError, match="authority-derived"):
        loads_input(encoded, trusted_input=transplanted)


def test_loader_rejects_duplicate_keys_nonfinite_values_and_extra_fields() -> None:
    with pytest.raises(ReconciliationError, match="authority-derived"):
        loads_input(
            '{"cluster_id":"a","cluster_id":"b","packages":[],"revision":"x"}',
            trusted_input=cluster(package_surface("org.example.one"), package_surface("org.example.two")),
        )
    with pytest.raises(ReconciliationError, match="authority-derived"):
        loads_input('{"value":NaN}', trusted_input=cluster(package_surface("org.example.one"), package_surface("org.example.two")))

    value = cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    raw = json.loads(dumps_input(value))
    raw["unexpected"] = True
    with pytest.raises(ReconciliationError, match="authority-derived"):
        loads_input(json.dumps(raw), trusted_input=value)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"x":1,"x":2}', "duplicate JSON key"),
        (b'NaN', "not permitted"),
        (b'1e999', "finite"),
        (b'9' * 5000, "64-bit range"),
        (b'[' * 2000 + b'0' + b']' * 2000, "strict UTF-8 JSON|exceeds depth"),
    ],
    ids=["duplicate-key", "nonfinite", "float-overflow", "integer-limit", "depth-limit"],
)
def test_canonical_values_exercise_json_decoder_rejections(payload: bytes, message: str) -> None:
    with pytest.raises(ReconciliationError, match=message):
        CanonicalValue(payload)


def test_loader_and_values_enforce_resource_and_unicode_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reconciliation_model, "_MAX_INPUT_BYTES", 8)
    with pytest.raises(ReconciliationError, match="exceeds 8 bytes"):
        loads_input(b'{"long":true}', trusted_input=cluster(package_surface("org.example.one"), package_surface("org.example.two")))

    monkeypatch.setattr(reconciliation_model, "_MAX_JSON_DEPTH", 2)
    with pytest.raises(ReconciliationError, match="exceeds depth"):
        CanonicalValue.from_data([[[0]]])
    with pytest.raises(ReconciliationError, match="valid Unicode"):
        CanonicalValue.from_data("\ud800")


def test_model_rejects_foreign_root_provenance_and_noncanonical_order() -> None:
    package = package_surface("org.example.one")
    area = package.areas[-1]
    foreign = replace(area.claims[0].provenance[0], root_ref_id=sha("foreign"))
    claim = replace(area.claims[0], provenance=(foreign,))
    bad_area = replace(area, claims=(claim,))
    with pytest.raises(ReconciliationError, match="outside its package"):
        replace(package, areas=(*package.areas[:-1], bad_area))

    unattested = replace(area.claims[0].provenance[0], evidence_anchor_ids=("unknown",))
    unattested_claim = replace(area.claims[0], provenance=(unattested,))
    unattested_area = replace(area, claims=(unattested_claim,))
    with pytest.raises(ReconciliationError, match="not attested by its root"):
        replace(package, areas=(*package.areas[:-1], unattested_area))

    first = package_surface("org.example.one")
    second = package_surface("org.example.two")
    ordered = tuple(sorted((first, second), key=lambda item: item.package_ref.content_id))
    with pytest.raises(ReconciliationError, match="packages must be sorted"):
        ReconciliationInput("cluster-synthetic", tuple(reversed(ordered)))


def test_hostile_post_construction_mutation_fails_before_comparison() -> None:
    value = cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    object.__setattr__(value.packages[0].areas[0].claims[0], "key", "not-a-pointer")

    with pytest.raises(ReconciliationError, match="JSON pointer"):
        reconcile(value)


def test_result_amplification_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reconciliation_engine, "_MAX_RESULT_ATOM_REFERENCES", 1)
    with pytest.raises(ReconciliationError, match="pair atom references"):
        reconcile(cluster(package_surface("org.example.one"), package_surface("org.example.two")))


def test_json_and_markdown_are_deterministic_and_exactly_agree() -> None:
    result = reconcile(
        cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    )
    json_payload = render_json(result)
    markdown = render_markdown(result)

    assert render_json(result) == json_payload
    assert render_markdown(result) == markdown
    assert result.content_id in markdown
    assert verify_render_agreement(json_payload, markdown) == result.content_id


@pytest.mark.parametrize("separator", [" ", "\u2028", "\u2029", "\u0085"])
def test_render_markers_inside_payload_strings_do_not_shadow_marker_lines(separator: str) -> None:
    marker_text = f"payload{separator}<!-- phase4-v2-reconciliation-json:START -->{separator}text"
    result = reconcile(
        cluster(
            package_surface(
                "org.example.one",
                values={ComparisonArea.ACTIONS: marker_text},
            ),
            package_surface(
                "org.example.two",
                values={ComparisonArea.ACTIONS: marker_text},
            ),
        )
    )
    json_payload = render_json(result)
    markdown = render_markdown(result)

    assert marker_text in markdown
    assert verify_render_agreement(json_payload, markdown) == result.content_id


def test_renderer_revalidates_a_hostile_result_mutation() -> None:
    result = reconcile(
        cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    )
    object.__setattr__(result, "status", ClosureStatus.INCOMPLETE)

    with pytest.raises(ReconciliationError, match="status disagrees"):
        render_json(result)


def test_render_agreement_rejects_json_or_markdown_mutation() -> None:
    result = reconcile(
        cluster(package_surface("org.example.one"), package_surface("org.example.two"))
    )
    json_payload = render_json(result)
    markdown = render_markdown(result)
    raw = json.loads(json_payload)
    raw["status"] = "INCOMPLETE"
    mutated_json = json.dumps(raw, separators=(",", ":"), sort_keys=True).encode()

    with pytest.raises(ReconciliationError, match="content ID does not verify"):
        verify_render_agreement(mutated_json, markdown)
    with pytest.raises(ReconciliationError, match="payloads disagree"):
        verify_render_agreement(
            json_payload, markdown.replace('"status":"COMPLETE"', '"status":"INCOMPLETE"')
        )
    with pytest.raises(ReconciliationError, match="not the deterministic rendering"):
        verify_render_agreement(json_payload, markdown.replace("SAME: 11", "SAME: 10"))
    with pytest.raises(ReconciliationError, match="not canonical"):
        verify_render_agreement(json_payload + b" ", markdown)
