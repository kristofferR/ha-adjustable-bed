"""Hostile contract tests for exact-byte Phase 4 v2 equivalence."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace

import pytest

from tools.phase4_v2.equivalence import (
    LOCAL_ONLY_DOMAINS,
    AppendOnlyLedger,
    ApplicationRoot,
    ByteIdentityProof,
    EquivalenceError,
    ExtractorCapability,
    FrozenPackageRef,
    LedgerDecision,
    LedgerEntry,
    Route,
    RoutingPins,
    build_byte_identity_proof,
    route_application_root,
)
from tools.phase4_v2.equivalence import core as core_module

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def package(name: str = "org.example.one", artifact: str = SHA_A) -> FrozenPackageRef:
    return FrozenPackageRef(
        package_name=name,
        version_code="17",
        artifact_digest=artifact,
        preflight_sha256=SHA_B,
        validation_receipt_sha256=SHA_C,
    )


def capability(*, implementation: str = SHA_D) -> ExtractorCapability:
    return ExtractorCapability(
        name="dex-root-inventory",
        implementation_sha256=implementation,
        configuration_sha256=SHA_E,
        capability_revision="extractor-2026.08",
    )


def root(
    package_ref: FrozenPackageRef,
    extractor: ExtractorCapability,
    *,
    content: str = SHA_F,
    inventory: str = SHA_A,
    dependency: str = SHA_E,
    occurrence: str = SHA_C,
    kind: str = "android_dex",
    complete: bool = True,
    closure: bool = True,
    warnings: tuple[str, ...] = (),
    opaque: tuple[str, ...] = (),
    dynamic: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
) -> ApplicationRoot:
    return ApplicationRoot(
        package_ref_id=package_ref.content_id,
        root_kind=kind,
        extractor_capability_id=extractor.content_id,
        occurrence_identity_sha256=occurrence,
        content_root_sha256=content,
        inventory_sha256=inventory,
        dependency_root_sha256=dependency,
        inventory_complete=complete,
        dependency_closure_complete=closure,
        warnings=warnings,
        opaque_slices=opaque,
        dynamic_slices=dynamic,
        unresolved_slices=unresolved,
        missing_tooling=missing,
    )


def exact_pair() -> tuple[
    FrozenPackageRef,
    FrozenPackageRef,
    ExtractorCapability,
    ApplicationRoot,
    ApplicationRoot,
]:
    first_package = package()
    second_package = package("org.other.two", SHA_B)
    extractor = capability()
    return (
        first_package,
        second_package,
        extractor,
        root(first_package, extractor),
        root(second_package, extractor),
    )


def route(
    target: ApplicationRoot,
    candidates: list[ApplicationRoot] | tuple[ApplicationRoot, ...],
    *,
    audits: dict[str, str] | None = None,
) -> tuple[LedgerDecision, ByteIdentityProof | None]:
    trusted = audits
    if trusted is None:
        trusted = {candidate.content_id: SHA_D for candidate in candidates}
    return route_application_root(
        target,
        candidates,
        pins=RoutingPins(),
        trusted_direct_audits=trusted,
        trusted_inventory_receipts={
            item.content_id: SHA_E for item in (target, *candidates)
        },
    )


def test_records_are_content_addressed_and_package_refs_are_audit_only() -> None:
    first, second, extractor, left, right = exact_pair()

    assert first.content_id != second.content_id
    assert left.content_id != right.content_id
    assert left.executable_identity == right.executable_identity
    assert len(extractor.content_id) == 64
    assert replace(first).content_id == first.content_id


def test_identical_occurrences_in_one_package_remain_distinct() -> None:
    package_ref = package()
    extractor = capability()
    first = root(package_ref, extractor, occurrence=SHA_A)
    second = root(package_ref, extractor, occurrence=SHA_B)

    assert first.content_id != second.content_id
    assert first.executable_identity == second.executable_identity

    decision, proof = route_application_root(
        second,
        [first],
        pins=RoutingPins(),
        trusted_direct_audits={first.content_id: SHA_D},
        trusted_inventory_receipts={first.content_id: SHA_E, second.content_id: SHA_F},
    )
    assert decision.route is Route.EXACT_REUSE
    assert proof is not None

    first_decision, _ = route_application_root(
        first,
        [second],
        pins=RoutingPins(),
        trusted_direct_audits={first.content_id: SHA_D},
        trusted_inventory_receipts={first.content_id: SHA_E, second.content_id: SHA_F},
    )
    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[first, second],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={first.content_id: SHA_D},
        trusted_inventory_receipts={first.content_id: SHA_E, second.content_id: SHA_F},
        expected_head_id=None,
    )
    first_entry = ledger.append(first_decision, expected_head_id=None)
    second_entry = ledger.append(decision, expected_head_id=ledger.head_id)
    assert first_entry.decision.target_root_id != second_entry.decision.target_root_id


def test_conflicting_records_for_one_occurrence_are_rejected() -> None:
    package_ref = package()
    extractor = capability()
    first = root(package_ref, extractor, occurrence=SHA_A, content=SHA_B)
    conflict = root(package_ref, extractor, occurrence=SHA_A, content=SHA_C)

    with pytest.raises(EquivalenceError, match="same package-local occurrence"):
        AppendOnlyLedger(
            packages=[package_ref],
            capabilities=[extractor],
            roots=[first, conflict],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={first.content_id: SHA_D, conflict.content_id: SHA_E},
            expected_head_id=None,
        )


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("root_kind", "native"),
        ("extractor_capability_id", SHA_B),
        ("content_root_sha256", SHA_B),
        ("inventory_sha256", SHA_B),
        ("dependency_root_sha256", SHA_B),
    ],
)
def test_every_executable_identity_dimension_must_match(change: str, value: str) -> None:
    _, _, _, left, right = exact_pair()
    changed = replace(right, **{change: value})

    decision, proof = route(left, [changed])

    assert decision.route is Route.FULL_ANALYSIS
    assert decision.reason == "no_exact_executable_identity"
    assert proof is None


@pytest.mark.parametrize(
    ("change", "value", "expected"),
    [
        ("inventory_complete", False, Route.BLOCKED),
        ("dependency_closure_complete", False, Route.BLOCKED),
        ("missing_tooling", ("native-disassembler",), Route.BLOCKED),
        ("warnings", ("truncated-output",), Route.FULL_ANALYSIS),
        ("opaque_slices", ("encrypted-payload",), Route.FULL_ANALYSIS),
        ("dynamic_slices", ("runtime-loader",), Route.FULL_ANALYSIS),
        ("unresolved_slices", ("native-bridge",), Route.FULL_ANALYSIS),
    ],
)
def test_tainted_target_never_reuses(
    change: str, value: object, expected: Route
) -> None:
    _, _, _, target, candidate = exact_pair()

    decision, proof = route(replace(target, **{change: value}), [candidate])

    assert decision.route is expected
    assert proof is None


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("inventory_complete", False),
        ("dependency_closure_complete", False),
        ("warnings", ("warning",)),
        ("opaque_slices", ("opaque",)),
        ("dynamic_slices", ("dynamic",)),
        ("unresolved_slices", ("unknown-target",)),
        ("missing_tooling", ("tool",)),
    ],
)
def test_tainted_candidate_never_authorizes_reuse(change: str, value: object) -> None:
    _, _, _, target, candidate = exact_pair()

    decision, proof = route(target, [replace(candidate, **{change: value})])

    assert decision.route is Route.FULL_ANALYSIS
    assert proof is None


def test_exact_reuse_binds_only_a_root_and_retains_all_local_domains() -> None:
    _, _, _, target, candidate = exact_pair()

    decision, proof = route(target, [candidate])

    assert decision.route is Route.EXACT_REUSE
    assert decision.source_root_id == candidate.content_id
    assert decision.inherited_root_id == candidate.content_id
    assert decision.local_only_domains == LOCAL_ONLY_DOMAINS
    assert proof is not None
    assert decision.byte_identity_proof_id == proof.content_id
    serialized = decision.to_data()
    assert "package" not in serialized
    assert "report" not in serialized
    assert "findings" not in serialized


def test_exact_candidate_requires_external_independent_audit_pin() -> None:
    _, _, _, target, candidate = exact_pair()

    decision, proof = route(target, [candidate], audits={})

    assert decision.route is Route.FULL_ANALYSIS
    assert proof is None


def test_inventory_acceptance_is_required_for_target_and_source() -> None:
    _, _, _, target, candidate = exact_pair()

    blocked, target_proof = route_application_root(
        target,
        [candidate],
        pins=RoutingPins(),
        trusted_direct_audits={candidate.content_id: SHA_D},
        trusted_inventory_receipts={candidate.content_id: SHA_E},
    )
    full, source_proof = route_application_root(
        target,
        [candidate],
        pins=RoutingPins(),
        trusted_direct_audits={candidate.content_id: SHA_D},
        trusted_inventory_receipts={target.content_id: SHA_E},
    )

    assert blocked.route is Route.BLOCKED
    assert blocked.reason == "root_inventory_not_trusted"
    assert target_proof is None
    assert full.route is Route.FULL_ANALYSIS
    assert source_proof is None


def test_inventory_receipt_substitution_changes_proof_identity() -> None:
    _, _, _, left, right = exact_pair()
    first = build_byte_identity_proof(
        left,
        right,
        pins=RoutingPins(),
        trusted_inventory_receipts={left.content_id: SHA_A, right.content_id: SHA_B},
    )
    second = build_byte_identity_proof(
        left,
        right,
        pins=RoutingPins(),
        trusted_inventory_receipts={left.content_id: SHA_A, right.content_id: SHA_C},
    )

    assert first.inventory_acceptance_sha256 != second.inventory_acceptance_sha256
    assert first.content_id != second.content_id


def test_every_decision_binds_target_inventory_acceptance() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor, content=SHA_B)
    first, _ = route_application_root(
        target,
        [],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_D},
    )
    substituted, _ = route_application_root(
        target,
        [],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_E},
    )

    assert first.target_inventory_receipt_sha256 == SHA_D
    assert substituted.target_inventory_receipt_sha256 == SHA_E
    assert first.content_id != substituted.content_id

    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[target],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_D},
        expected_head_id=None,
    )
    ledger.append(first, expected_head_id=None)
    with pytest.raises(EquivalenceError, match="does not reproduce"):
        AppendOnlyLedger(
            packages=[package_ref],
            capabilities=[extractor],
            roots=[target],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={target.content_id: SHA_E},
            entries=ledger.entries,
            expected_head_id=ledger.head_id,
        )


def test_missing_inventory_acceptance_is_bound_as_explicit_absence() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor)
    decision, _ = route_application_root(
        target,
        [],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={},
    )

    assert decision.route is Route.BLOCKED
    assert decision.target_inventory_receipt_sha256 is None


class _LyingReceiptMapping(Mapping[str, str]):
    def __init__(self, keys: Iterator[str]) -> None:
        self._keys = keys

    def __getitem__(self, key: str) -> str:
        return SHA_A

    def __iter__(self) -> Iterator[str]:
        return self._keys

    def __len__(self) -> int:
        return 0


def test_trusted_receipt_mapping_bounds_iteration_despite_lying_length() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor)
    hostile = _LyingReceiptMapping(iter(f"{index:064x}" for index in range(250_001)))

    with pytest.raises(EquivalenceError, match="count exceeds"):
        route_application_root(
            target,
            [],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts=hostile,
        )


def test_trusted_receipt_mapping_rejects_duplicate_yielded_keys() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor)
    hostile = _LyingReceiptMapping(iter((target.content_id, target.content_id)))

    with pytest.raises(EquivalenceError, match="duplicate root ID"):
        route_application_root(
            target,
            [],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts=hostile,
        )


def test_proof_is_symmetric_canonical_and_reproducible() -> None:
    _, _, _, left, right = exact_pair()

    receipts = {left.content_id: SHA_E, right.content_id: SHA_F}
    forward = build_byte_identity_proof(
        left, right, pins=RoutingPins(), trusted_inventory_receipts=receipts
    )
    reverse = build_byte_identity_proof(
        right, left, pins=RoutingPins(), trusted_inventory_receipts=receipts
    )

    assert forward == reverse
    assert forward.content_id == reverse.content_id
    assert forward.left_root_id < forward.right_root_id


def test_proof_rejects_self_nonidentical_and_tainted_roots() -> None:
    _, _, _, left, right = exact_pair()
    with pytest.raises(EquivalenceError, match="distinct"):
        build_byte_identity_proof(
            left,
            left,
            pins=RoutingPins(),
            trusted_inventory_receipts={left.content_id: SHA_E},
        )
    with pytest.raises(EquivalenceError, match="not exactly identical"):
        build_byte_identity_proof(
            left,
            replace(right, content_root_sha256=SHA_B),
            pins=RoutingPins(),
            trusted_inventory_receipts={},
        )
    with pytest.raises(EquivalenceError, match="warning-free"):
        build_byte_identity_proof(
            left,
            replace(right, warnings=("x",)),
            pins=RoutingPins(),
            trusted_inventory_receipts={},
        )


def test_candidate_order_duplicates_and_irrelevant_metadata_do_not_change_route() -> None:
    target_package = package()
    source_a_package = package("org.source.a", SHA_B)
    source_b_package = package("org.source.b", SHA_C)
    extractor = capability()
    target = root(target_package, extractor)
    source_a = root(source_a_package, extractor)
    source_b = root(source_b_package, extractor)

    first, proof_a = route(target, [source_b, source_a, source_b])
    second, proof_b = route(target, [source_a, source_b])

    assert first == second
    assert proof_a == proof_b
    assert first.source_root_id == min(source_a.content_id, source_b.content_id)


def test_exact_route_api_has_no_weak_candidate_inputs() -> None:
    import inspect

    parameters = inspect.signature(route_application_root).parameters
    forbidden = {
        "brand",
        "developer",
        "filename",
        "fuzzy",
        "package_name",
        "signer",
        "similarity",
        "version",
    }
    assert forbidden.isdisjoint(parameters)


def test_revision_pins_fail_closed() -> None:
    with pytest.raises(EquivalenceError, match="unsupported equivalence revision"):
        RoutingPins(equivalence="phase4-v2-exact-equivalence-v0")


def test_hostile_post_construction_revision_mutation_fails_closed() -> None:
    _, _, _, target, candidate = exact_pair()
    pins = RoutingPins()
    object.__setattr__(pins, "application_root", "old-root-revision")
    with pytest.raises(EquivalenceError, match="unsupported application_root revision"):
        route_application_root(
            target,
            [candidate],
            pins=pins,
            trusted_direct_audits={candidate.content_id: SHA_D},
            trusted_inventory_receipts={target.content_id: SHA_E, candidate.content_id: SHA_E},
        )
    pins = RoutingPins()
    object.__setattr__(candidate, "revision", "old-root-revision")
    with pytest.raises(EquivalenceError, match="revision"):
        route_application_root(
            target,
            [candidate],
            pins=pins,
            trusted_direct_audits={candidate.content_id: SHA_D},
            trusted_inventory_receipts={target.content_id: SHA_E, candidate.content_id: SHA_E},
        )


@pytest.mark.parametrize(
    ("record_name", "field", "value", "message"),
    [
        ("package", "artifact_digest", "not-a-digest", "artifact_digest"),
        ("capability", "implementation_sha256", "not-a-digest", "implementation_sha256"),
        ("root", "inventory_complete", "yes", "inventory_complete"),
        ("proof", "content_root_sha256", "not-a-digest", "content_root_sha256"),
    ],
)
def test_ledger_revalidates_mutated_external_record_state(
    record_name: str, field: str, value: object, message: str
) -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    receipts = {left.content_id: SHA_E, right.content_id: SHA_F}
    proof = build_byte_identity_proof(
        left, right, pins=RoutingPins(), trusted_inventory_receipts=receipts
    )
    records: dict[str, object] = {
        "package": left_package,
        "capability": extractor,
        "root": left,
        "proof": proof,
    }
    object.__setattr__(records[record_name], field, value)

    with pytest.raises(EquivalenceError, match=message):
        AppendOnlyLedger(
            packages=[left_package, right_package],
            capabilities=[extractor],
            roots=[left, right],
            proofs=[proof],
            pins=RoutingPins(),
            trusted_direct_audits={right.content_id: SHA_D},
            trusted_inventory_receipts=receipts,
            expected_head_id=None,
        )


def test_defensive_copy_rejects_hostile_iterable_without_consuming_it() -> None:
    class ExplodingIterable:
        def __iter__(self) -> object:
            raise AssertionError("hostile iterable was consumed")

    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor)
    object.__setattr__(target, "warnings", ExplodingIterable())

    with pytest.raises(EquivalenceError, match="immutable tuple"):
        AppendOnlyLedger(
            packages=[package_ref],
            capabilities=[extractor],
            roots=[target],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={},
            expected_head_id=None,
        )


def test_defensive_copy_rejects_hostile_tuple_subclass_without_invoking_it() -> None:
    class HostileTuple(tuple[str, ...]):
        def __len__(self) -> int:
            raise AssertionError("hostile tuple length was invoked")

        def __iter__(self) -> Iterator[str]:
            raise AssertionError("hostile tuple iterator was invoked")

    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor)
    object.__setattr__(target, "warnings", HostileTuple(("warning",)))

    with pytest.raises(EquivalenceError, match="immutable tuple"):
        AppendOnlyLedger(
            packages=[package_ref],
            capabilities=[extractor],
            roots=[target],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={},
            expected_head_id=None,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("route", "EXACT_REUSE", "must be a Route"),
        ("local_only_domains", (), "cannot be inherited"),
        ("inherited_root_id", SHA_A, "cannot inherit"),
    ],
)
def test_ledger_revalidates_mutated_decision_state(
    field: str, value: object, message: str
) -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor, content=SHA_B)
    decision, _ = route(target, [])
    object.__setattr__(decision, field, value)
    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[target],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_E},
        expected_head_id=None,
    )

    with pytest.raises(EquivalenceError, match=message):
        ledger.append(decision, expected_head_id=None)

def test_root_risk_sets_must_be_bounded_sorted_and_unique() -> None:
    _, _, _, left, _ = exact_pair()
    with pytest.raises(EquivalenceError, match="sorted and unique"):
        replace(left, warnings=("z", "a"))
    with pytest.raises(EquivalenceError, match="sorted and unique"):
        replace(left, warnings=("a", "a"))
    with pytest.raises(EquivalenceError, match="exceeds its limit"):
        replace(left, warnings=tuple(f"w{i:04d}" for i in range(4_097)))


def test_candidate_count_is_bounded() -> None:
    _, _, _, target, candidate = exact_pair()

    with pytest.raises(EquivalenceError, match="candidate count exceeds"):
        route_application_root(
            target,
            (candidate for _ in range(250_002)),
            pins=RoutingPins(),
            trusted_direct_audits={candidate.content_id: SHA_D},
            trusted_inventory_receipts={target.content_id: SHA_E, candidate.content_id: SHA_E},
        )


def test_ledger_validates_transitive_graph_and_hash_chain() -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    decision, proof = route(left, [right])
    assert proof is not None
    ledger = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, right],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={right.content_id: SHA_D},
        trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
        expected_head_id=None,
    )

    entry = ledger.append(decision, expected_head_id=None)

    assert entry.sequence == 0
    assert entry.previous_entry_id is None
    assert ledger.head_id == entry.content_id
    restored = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, right],
        proofs=[proof],
        pins=RoutingPins(),
        entries=ledger.entries,
        trusted_direct_audits={right.content_id: SHA_D},
        trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
        expected_head_id=ledger.head_id,
    )
    assert restored.head_id == ledger.head_id


def test_ledger_replay_preserves_historical_exact_reuse_source() -> None:
    package_ref = package()
    extractor = capability()
    new_source, old_source, target = sorted(
        (
            root(package_ref, extractor, occurrence=f"{index:064x}")
            for index in range(3)
        ),
        key=lambda item: item.content_id,
    )
    receipts = {
        old_source.content_id: SHA_E,
        target.content_id: SHA_E,
    }
    decision, proof = route_application_root(
        target,
        [old_source],
        pins=RoutingPins(),
        trusted_direct_audits={old_source.content_id: SHA_D},
        trusted_inventory_receipts=receipts,
    )
    assert proof is not None
    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[old_source, target],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={old_source.content_id: SHA_D},
        trusted_inventory_receipts=receipts,
        expected_head_id=None,
    )
    ledger.append(decision, expected_head_id=None)

    replayed = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[new_source, old_source, target],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={new_source.content_id: SHA_D, old_source.content_id: SHA_D},
        trusted_inventory_receipts={**receipts, new_source.content_id: SHA_E},
        entries=ledger.entries,
        expected_head_id=ledger.head_id,
    )

    assert replayed.entries[0].decision.source_root_id == old_source.content_id


def test_ledger_replay_preserves_full_analysis_before_source_discovery() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor, occurrence=SHA_A)
    discovered_source = root(package_ref, extractor, occurrence=SHA_B)
    decision, _ = route_application_root(
        target,
        [],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_E},
    )
    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[target],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_E},
        expected_head_id=None,
    )
    ledger.append(decision, expected_head_id=None)

    replayed = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[target, discovered_source],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={discovered_source.content_id: SHA_D},
        trusted_inventory_receipts={target.content_id: SHA_E, discovered_source.content_id: SHA_E},
        entries=ledger.entries,
        expected_head_id=ledger.head_id,
    )

    assert replayed.entries[0].decision.route is Route.FULL_ANALYSIS


def test_ledger_validates_trust_maps_once_not_per_proof_or_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    decision, proof = route(left, [right])
    assert proof is not None
    calls = {"audits": 0, "inventories": 0}
    original_audits = core_module._trusted_direct_audits
    original_inventories = core_module._trusted_root_receipts

    def count_audits(value: Mapping[str, str]) -> dict[str, str]:
        calls["audits"] += 1
        return original_audits(value)

    def count_inventories(
        value: Mapping[str, str], *, field: str
    ) -> dict[str, str]:
        calls["inventories"] += 1
        return original_inventories(value, field=field)

    monkeypatch.setattr(core_module, "_trusted_direct_audits", count_audits)
    monkeypatch.setattr(core_module, "_trusted_root_receipts", count_inventories)
    ledger = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, right],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={right.content_id: SHA_D},
        trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
        expected_head_id=None,
    )
    construction_calls = calls.copy()
    ledger.append(decision, expected_head_id=None)

    assert construction_calls == {"audits": 1, "inventories": 2}
    assert calls == construction_calls


def test_ledger_rejects_mutated_chain_and_duplicate_decision() -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    decision, proof = route(left, [right])
    assert proof is not None
    ledger = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, right],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={right.content_id: SHA_D},
        trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
        expected_head_id=None,
    )
    entry = ledger.append(decision, expected_head_id=None)
    with pytest.raises(EquivalenceError, match="already has"):
        ledger.append(decision, expected_head_id=ledger.head_id)
    with pytest.raises(EquivalenceError, match="hash-chain"):
        AppendOnlyLedger(
            packages=[left_package, right_package],
            capabilities=[extractor],
            roots=[left, right],
            proofs=[proof],
            pins=RoutingPins(),
            entries=[replace(entry, sequence=1)],
            trusted_direct_audits={right.content_id: SHA_D},
            trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
            expected_head_id=entry.content_id,
        )


def test_ledger_append_requires_current_caller_pinned_head() -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    decision, proof = route(left, [right])
    assert proof is not None
    ledger = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, right],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={right.content_id: SHA_D},
        trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
        expected_head_id=None,
    )
    with pytest.raises(EquivalenceError, match="expected head"):
        ledger.append(decision, expected_head_id=SHA_A)


def test_ledger_rejects_proof_substitution() -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    decision, proof = route(left, [right])
    assert proof is not None
    fake = ByteIdentityProof(
        left_root_id=proof.left_root_id,
        right_root_id=proof.right_root_id,
        root_kind=proof.root_kind,
        extractor_capability_id=proof.extractor_capability_id,
        content_root_sha256=SHA_B,
        inventory_sha256=proof.inventory_sha256,
        dependency_root_sha256=proof.dependency_root_sha256,
        inventory_acceptance_sha256=proof.inventory_acceptance_sha256,
    )
    with pytest.raises(EquivalenceError, match="does not reproduce"):
        AppendOnlyLedger(
            packages=[left_package, right_package],
            capabilities=[extractor],
            roots=[left, right],
            proofs=[fake],
            pins=RoutingPins(),
            trusted_direct_audits={right.content_id: SHA_D},
            trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
            expected_head_id=None,
        )


def test_ledger_rejects_orphaned_transitive_references() -> None:
    left_package, _, extractor, left, _ = exact_pair()
    with pytest.raises(EquivalenceError, match="unknown frozen package"):
        AppendOnlyLedger(
            packages=[],
            capabilities=[extractor],
            roots=[left],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={left.content_id: SHA_E},
            expected_head_id=None,
        )
    with pytest.raises(EquivalenceError, match="unknown extractor"):
        AppendOnlyLedger(
            packages=[left_package],
            capabilities=[],
            roots=[left],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={left.content_id: SHA_E},
            expected_head_id=None,
        )


def test_blocked_root_cannot_be_downgraded_in_ledger() -> None:
    package_ref = package()
    extractor = capability()
    blocked = root(package_ref, extractor, complete=False)
    dishonest = LedgerDecision(
        target_root_id=blocked.content_id,
        route=Route.FULL_ANALYSIS,
        reason="no_exact_executable_identity",
    )
    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[blocked],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={blocked.content_id: SHA_E},
        expected_head_id=None,
    )
    with pytest.raises(EquivalenceError, match="does not reproduce"):
        ledger.append(dishonest, expected_head_id=None)


def test_non_reuse_decision_cannot_smuggle_inheritance() -> None:
    _, _, _, left, right = exact_pair()
    with pytest.raises(EquivalenceError, match="cannot inherit"):
        LedgerDecision(
            target_root_id=left.content_id,
            route=Route.FULL_ANALYSIS,
            reason="no_exact_executable_identity",
            source_root_id=right.content_id,
        )
    with pytest.raises(EquivalenceError, match="cannot be inherited"):
        LedgerDecision(
            target_root_id=left.content_id,
            route=Route.FULL_ANALYSIS,
            reason="no_exact_executable_identity",
            local_only_domains=(),
        )


def test_manual_forged_exact_decision_fails_ledger_validation() -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    altered = replace(right, inventory_sha256=SHA_B)
    # Syntactically valid proof IDs cannot bypass the registered proof set.
    forged = LedgerDecision(
        target_root_id=left.content_id,
        route=Route.EXACT_REUSE,
        reason="exact_executable_identity",
        source_root_id=altered.content_id,
        byte_identity_proof_id=SHA_C,
        inherited_root_id=altered.content_id,
        source_audit_receipt_sha256=SHA_D,
    )
    ledger = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, altered],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={left.content_id: SHA_E, altered.content_id: SHA_E},
        expected_head_id=None,
    )
    with pytest.raises(EquivalenceError, match="does not reproduce"):
        ledger.append(forged, expected_head_id=None)


def test_ledger_entry_is_immutable_content_addressed_data() -> None:
    _, _, _, target, _ = exact_pair()
    decision = LedgerDecision(
        target_root_id=target.content_id,
        route=Route.FULL_ANALYSIS,
        reason="no_exact_executable_identity",
    )
    entry = LedgerEntry(sequence=0, previous_entry_id=None, decision=decision)

    assert len(entry.content_id) == 64
    with pytest.raises(AttributeError):
        entry.sequence = 2  # type: ignore[misc]


def test_ledger_owns_records_after_construction() -> None:
    left_package, right_package, extractor, left, right = exact_pair()
    decision, proof = route(left, [right])
    assert proof is not None
    ledger = AppendOnlyLedger(
        packages=[left_package, right_package],
        capabilities=[extractor],
        roots=[left, right],
        proofs=[proof],
        pins=RoutingPins(),
        trusted_direct_audits={right.content_id: SHA_D},
        trusted_inventory_receipts={left.content_id: SHA_E, right.content_id: SHA_E},
        expected_head_id=None,
    )
    original_target_id = decision.target_root_id

    object.__setattr__(left, "content_root_sha256", SHA_B)
    object.__setattr__(right_package, "artifact_digest", SHA_C)
    object.__setattr__(proof, "inventory_sha256", SHA_D)

    entry = ledger.append(decision, expected_head_id=None)
    assert entry.decision.target_root_id == original_target_id


def test_ledger_returns_defensive_entry_and_decision_copies() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor, content=SHA_B)
    decision, _ = route(target, [])
    ledger = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[target],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_E},
        expected_head_id=None,
    )
    returned = ledger.append(decision, expected_head_id=None)
    trusted_head = ledger.head_id

    object.__setattr__(decision, "route", "BLOCKED")
    object.__setattr__(returned, "sequence", 99)
    object.__setattr__(returned.decision, "reason", "mutated")
    snapshot = ledger.entries
    object.__setattr__(snapshot[0].decision, "reason", "also-mutated")

    assert ledger.head_id == trusted_head
    assert ledger.entries[0].sequence == 0
    assert ledger.entries[0].decision.reason == "no_exact_executable_identity"


def test_ledger_replay_uses_preindexed_exact_reuse_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_ref = package()
    extractor = capability()
    roots = [
        root(package_ref, extractor, occurrence=f"{index:064x}") for index in range(16)
    ]
    audits = {item.content_id: SHA_D for item in roots}
    receipts = {item.content_id: SHA_E for item in roots}
    entries: list[LedgerEntry] = []
    proofs: dict[str, ByteIdentityProof] = {}
    previous_entry_id: str | None = None
    for sequence, target in enumerate(roots):
        decision, proof = route_application_root(
            target,
            roots,
            pins=RoutingPins(),
            trusted_direct_audits=audits,
            trusted_inventory_receipts=receipts,
        )
        assert proof is not None
        proofs[proof.content_id] = proof
        entry = LedgerEntry(sequence, previous_entry_id, decision)
        entries.append(entry)
        previous_entry_id = entry.content_id

    candidate_counts: list[int] = []
    original_route = core_module._route_application_root_validated

    def counted_route(
        target: ApplicationRoot,
        candidates: Iterator[ApplicationRoot] | tuple[ApplicationRoot, ...],
        **kwargs: object,
    ) -> tuple[LedgerDecision, ByteIdentityProof | None]:
        materialized = tuple(candidates)
        candidate_counts.append(len(materialized))
        return original_route(target, materialized, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(core_module, "_route_application_root_validated", counted_route)
    replayed = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=roots,
        proofs=proofs.values(),
        pins=RoutingPins(),
        trusted_direct_audits=audits,
        trusted_inventory_receipts=receipts,
        entries=entries,
        expected_head_id=entries[-1].content_id,
    )

    assert len(replayed.entries) == len(roots)
    assert candidate_counts == []


def test_ledger_replay_preserves_historical_route_when_a_source_is_added() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor, occurrence=SHA_A)
    original_decision, proof = route_application_root(
        target,
        [],
        pins=RoutingPins(),
        trusted_direct_audits={},
        trusted_inventory_receipts={target.content_id: SHA_E},
    )
    assert proof is None
    entry = LedgerEntry(0, None, original_decision)
    source = root(package_ref, extractor, occurrence=SHA_B)

    replayed = AppendOnlyLedger(
        packages=[package_ref],
        capabilities=[extractor],
        roots=[target, source],
        proofs=[],
        pins=RoutingPins(),
        trusted_direct_audits={source.content_id: SHA_D},
        trusted_inventory_receipts={target.content_id: SHA_E, source.content_id: SHA_E},
        entries=[entry],
        expected_head_id=entry.content_id,
    )

    assert replayed.entries == (entry,)


def test_ledger_replay_rejects_route_ineligible_for_the_target() -> None:
    package_ref = package()
    extractor = capability()
    target = root(package_ref, extractor, complete=False)
    dishonest = LedgerDecision(
        target_root_id=target.content_id,
        route=Route.FULL_ANALYSIS,
        reason="no_exact_executable_identity",
        target_inventory_receipt_sha256=SHA_E,
    )
    entry = LedgerEntry(0, None, dishonest)

    with pytest.raises(EquivalenceError, match="pinned target routing inputs"):
        AppendOnlyLedger(
            packages=[package_ref],
            capabilities=[extractor],
            roots=[target],
            proofs=[],
            pins=RoutingPins(),
            trusted_direct_audits={},
            trusted_inventory_receipts={target.content_id: SHA_E},
            entries=[entry],
            expected_head_id=entry.content_id,
        )
