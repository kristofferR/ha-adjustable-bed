"""Deterministic typed comparison engine for Phase 4 v2 package reports."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from tools.phase4_v2.equivalence import Route

from .model import (
    AreaSurface,
    CanonicalValue,
    ClosureStatus,
    ComparisonArea,
    DispositionStatus,
    PackageSurface,
    ReconciliationError,
    ReconciliationInput,
    RootProvenance,
    canonical_content_id,
    dumps_input,
    loads_input,
)

RESULT_REVISION = "phase4-v2-reconciliation-result-v2"
_MAX_RESULT_ATOM_REFERENCES = 1_000_000
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")


class ComparisonDecision(StrEnum):
    """Exact decision for one package pair and comparison area."""

    DIFFERENT = "DIFFERENT"
    INCOMPLETE = "INCOMPLETE"
    SAME = "SAME"


@dataclass(frozen=True, slots=True, order=True)
class AtomSource:
    """Package and root provenance contributing one normalized atom."""

    package_ref_id: str
    root_ref_id: str

    def to_data(self) -> dict[str, str]:
        return {"package_ref_id": self.package_ref_id, "root_ref_id": self.root_ref_id}


@dataclass(frozen=True, slots=True)
class SemanticAtom:
    """One content-addressed normalized claim or exact-set disposition."""

    area: ComparisonArea
    kind: str
    identity: str
    payload: CanonicalValue
    sources: tuple[AtomSource, ...]

    @property
    def payload_sha256(self) -> str:
        return self.payload.sha256

    @property
    def content_id(self) -> str:
        return canonical_content_id(
            "reconciliation-atom",
            {
                "area": self.area.value,
                "identity": self.identity,
                "kind": self.kind,
                "payload_sha256": self.payload_sha256,
            },
        )

    def to_data(self) -> dict[str, object]:
        return {
            "area": self.area.value,
            "atom_id": self.content_id,
            "identity": self.identity,
            "kind": self.kind,
            "payload": self.payload.to_data(),
            "payload_sha256": self.payload_sha256,
            "sources": [item.to_data() for item in self.sources],
        }


@dataclass(frozen=True, slots=True)
class Contradiction:
    """An exact duplicate or conflict inside one package-local area."""

    package_ref_id: str
    area: ComparisonArea
    code: str
    identity: str
    atom_ids: tuple[str, ...]
    root_ref_ids: tuple[str, ...]

    @property
    def content_id(self) -> str:
        return canonical_content_id("reconciliation-contradiction", self.payload_data())

    def payload_data(self) -> dict[str, object]:
        return {
            "area": self.area.value,
            "atom_ids": list(self.atom_ids),
            "code": self.code,
            "identity": self.identity,
            "package_ref_id": self.package_ref_id,
            "root_ref_ids": list(self.root_ref_ids),
        }

    def to_data(self) -> dict[str, object]:
        return {"contradiction_id": self.content_id, **self.payload_data()}


@dataclass(frozen=True, slots=True)
class PairDecision:
    """The complete comparison result for one package-area pair."""

    left_package_ref_id: str
    right_package_ref_id: str
    area: ComparisonArea
    decision: ComparisonDecision
    shared_atom_ids: tuple[str, ...]
    left_only_atom_ids: tuple[str, ...]
    right_only_atom_ids: tuple[str, ...]
    contradiction_ids: tuple[str, ...]
    incomplete_reasons: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "area": self.area.value,
            "contradiction_ids": list(self.contradiction_ids),
            "decision": self.decision.value,
            "incomplete_reasons": list(self.incomplete_reasons),
            "left_only_atom_ids": list(self.left_only_atom_ids),
            "left_package_ref_id": self.left_package_ref_id,
            "right_only_atom_ids": list(self.right_only_atom_ids),
            "right_package_ref_id": self.right_package_ref_id,
            "shared_atom_ids": list(self.shared_atom_ids),
        }


@dataclass(frozen=True, slots=True)
class AreaAggregate:
    """Deterministic union and intersection across all cluster members."""

    area: ComparisonArea
    union_atom_ids: tuple[str, ...]
    intersection_atom_ids: tuple[str, ...]
    complete_package_ref_ids: tuple[str, ...]
    incomplete_package_ref_ids: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "area": self.area.value,
            "complete_package_ref_ids": list(self.complete_package_ref_ids),
            "incomplete_package_ref_ids": list(self.incomplete_package_ref_ids),
            "intersection_atom_ids": list(self.intersection_atom_ids),
            "union_atom_ids": list(self.union_atom_ids),
        }


@dataclass(frozen=True, slots=True, order=True)
class FullPromotion:
    """One exact-reuse root that must be promoted before acceptance."""

    package_ref_id: str
    root_ref_id: str
    area: ComparisonArea
    reason_code: str

    def to_data(self) -> dict[str, str]:
        return {
            "area": self.area.value,
            "package_ref_id": self.package_ref_id,
            "reason_code": self.reason_code,
            "root_ref_id": self.root_ref_id,
        }


@dataclass(frozen=True, slots=True, order=True)
class RepairRequirement:
    """One already-full or blocked package area that remains incomplete."""

    package_ref_id: str
    area: ComparisonArea
    reason_code: str

    def to_data(self) -> dict[str, str]:
        return {
            "area": self.area.value,
            "package_ref_id": self.package_ref_id,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class RootResultReference:
    """Minimal immutable root identity carried into the result."""

    package_ref_id: str
    root_ref_id: str
    target_root_id: str
    occurrence_identity_sha256: str
    route: Route
    semantic_root_sha256: str | None
    source_root_id: str | None

    def to_data(self) -> dict[str, object]:
        return {
            "occurrence_identity_sha256": self.occurrence_identity_sha256,
            "package_ref_id": self.package_ref_id,
            "root_ref_id": self.root_ref_id,
            "route": self.route.value,
            "semantic_root_sha256": self.semantic_root_sha256,
            "source_root_id": self.source_root_id,
            "target_root_id": self.target_root_id,
        }


@dataclass(frozen=True, slots=True)
class PackageResultReference:
    """Frozen package/report identity consumed by the result."""

    package_ref_id: str
    package_surface_id: str
    report_sha256: str
    package_local_ref_id: str
    roots: tuple[RootResultReference, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "package_ref_id": self.package_ref_id,
            "package_local_ref_id": self.package_local_ref_id,
            "package_surface_id": self.package_surface_id,
            "report_sha256": self.report_sha256,
            "roots": [item.to_data() for item in self.roots],
        }


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Content-addressed complete output of the deterministic engine."""

    cluster_id: str
    input_id: str
    status: ClosureStatus
    packages: tuple[PackageResultReference, ...]
    atoms: tuple[SemanticAtom, ...]
    area_aggregates: tuple[AreaAggregate, ...]
    pair_decisions: tuple[PairDecision, ...]
    contradictions: tuple[Contradiction, ...]
    required_full_promotions: tuple[FullPromotion, ...]
    repairs_required: tuple[RepairRequirement, ...]
    revision: str = RESULT_REVISION

    def __post_init__(self) -> None:
        if self.revision != RESULT_REVISION or _TOKEN.fullmatch(self.cluster_id) is None:
            raise ReconciliationError("result revision or cluster ID is invalid")
        _require_digest(self.input_id, "result.input_id")
        if type(self.status) is not ClosureStatus:
            raise ReconciliationError("result status must use ClosureStatus")
        if type(self.packages) is not tuple or not 1 <= len(self.packages) <= 32:
            raise ReconciliationError("result packages are invalid")
        if any(type(item) is not PackageResultReference for item in self.packages):
            raise ReconciliationError("result packages must use PackageResultReference")
        package_ids = tuple(item.package_ref_id for item in self.packages)
        if package_ids != tuple(sorted(set(package_ids))):
            raise ReconciliationError("result packages must be sorted and unique")
        roots: dict[tuple[str, str], Route] = {}
        package_local_sources: set[tuple[str, str]] = set()
        for package in self.packages:
            _require_digest(package.package_ref_id, "result package reference")
            _require_digest(package.package_surface_id, "result package surface")
            _require_digest(package.report_sha256, "result report")
            _require_digest(package.package_local_ref_id, "result package-local provenance")
            package_local_sources.add(
                (package.package_ref_id, package.package_local_ref_id)
            )
            if (
                type(package.roots) is not tuple
                or any(type(item) is not RootResultReference for item in package.roots)
                or not package.roots
            ):
                raise ReconciliationError("result roots must use RootResultReference")
            if package.roots != tuple(sorted(package.roots, key=lambda item: item.root_ref_id)):
                raise ReconciliationError("result roots must be sorted")
            for root in package.roots:
                if root.package_ref_id != package.package_ref_id:
                    raise ReconciliationError("result root belongs to a different package")
                for value in (
                    root.root_ref_id,
                    root.target_root_id,
                    root.occurrence_identity_sha256,
                ):
                    _require_digest(value, "result root digest")
                if type(root.route) is not Route:
                    raise ReconciliationError("result root route is invalid")
                if root.semantic_root_sha256 is not None:
                    _require_digest(root.semantic_root_sha256, "result semantic root")
                if root.source_root_id is not None:
                    _require_digest(root.source_root_id, "result source root")
                if root.route is Route.FULL_ANALYSIS and (
                    root.semantic_root_sha256 is None or root.source_root_id is not None
                ):
                    raise ReconciliationError("result FULL root provenance is inconsistent")
                if root.route is Route.EXACT_REUSE and (
                    root.semantic_root_sha256 is None or root.source_root_id is None
                ):
                    raise ReconciliationError("result reuse root provenance is inconsistent")
                if root.route is Route.BLOCKED and (
                    root.semantic_root_sha256 is not None or root.source_root_id is not None
                ):
                    raise ReconciliationError("result blocked root provenance is inconsistent")
                key = (root.package_ref_id, root.root_ref_id)
                if key in roots:
                    raise ReconciliationError("result contains a duplicate root")
                roots[key] = root.route

        if type(self.atoms) is not tuple or any(
            type(item) is not SemanticAtom for item in self.atoms
        ):
            raise ReconciliationError("result atoms must use SemanticAtom")
        atom_ids = tuple(item.content_id for item in self.atoms)
        if atom_ids != tuple(sorted(atom_ids)):
            raise ReconciliationError("result atoms must be sorted")
        if len(set(atom_ids)) != len(atom_ids):
            raise ReconciliationError("result contains duplicate atoms")
        for atom in self.atoms:
            if type(atom.area) is not ComparisonArea or atom.kind not in {
                "ACTION",
                "CANDIDATE",
                "CLAIM",
                "VARIANT",
            }:
                raise ReconciliationError("result atom kind or area is invalid")
            if not atom.identity or len(atom.identity) > 8192:
                raise ReconciliationError("result atom identity is invalid")
            if type(atom.payload) is not CanonicalValue:
                raise ReconciliationError("result atom payload must use CanonicalValue")
            atom.payload.__post_init__()
            if (
                type(atom.sources) is not tuple
                or not atom.sources
                or any(type(item) is not AtomSource for item in atom.sources)
            ):
                raise ReconciliationError("result atom sources must use AtomSource")
            for source in atom.sources:
                _require_digest(source.package_ref_id, "atom source package")
                _require_digest(source.root_ref_id, "atom source root")
            if atom.sources != tuple(sorted(set(atom.sources))):
                raise ReconciliationError("result atom sources must be sorted and unique")
            if any(
                (item.package_ref_id, item.root_ref_id) not in roots
                and (item.package_ref_id, item.root_ref_id) not in package_local_sources
                for item in atom.sources
            ):
                raise ReconciliationError("result atom references an unknown root")
        atom_packages = {
            atom_id: {source.package_ref_id for source in atom.sources}
            for atom_id, atom in zip(atom_ids, self.atoms, strict=True)
        }
        atoms_by_id = dict(zip(atom_ids, self.atoms, strict=True))
        atoms_by_area = {
            area: {atom_id for atom_id, atom in atoms_by_id.items() if atom.area is area}
            for area in ComparisonArea
        }

        if type(self.contradictions) is not tuple or any(
            type(item) is not Contradiction for item in self.contradictions
        ):
            raise ReconciliationError("result contradictions must use Contradiction")
        if self.contradictions != tuple(
            sorted(self.contradictions, key=lambda item: item.content_id)
        ):
            raise ReconciliationError("result contradictions must be sorted")
        contradiction_ids = tuple(item.content_id for item in self.contradictions)
        if len(set(contradiction_ids)) != len(contradiction_ids):
            raise ReconciliationError("result contains duplicate contradictions")
        for item in self.contradictions:
            if item.package_ref_id not in package_ids or type(item.area) is not ComparisonArea:
                raise ReconciliationError("result contradiction package or area is invalid")
            if item.code not in {
                "CONFLICTING_SEMANTIC_IDENTITY",
                "DUPLICATE_SEMANTIC_IDENTITY",
            }:
                raise ReconciliationError("result contradiction code is invalid")
            if not item.identity or len(item.identity) > 8192:
                raise ReconciliationError("result contradiction identity is invalid")
            _require_sorted_digests(item.atom_ids, "contradiction atom IDs", set(atom_ids))
            _require_sorted_digests(item.root_ref_ids, "contradiction root IDs")
            if any(
                (item.package_ref_id, root_id) not in roots
                and (item.package_ref_id, root_id) not in package_local_sources
                for root_id in item.root_ref_ids
            ):
                raise ReconciliationError("result contradiction references an unknown root")

        if type(self.area_aggregates) is not tuple or any(
            type(item) is not AreaAggregate for item in self.area_aggregates
        ):
            raise ReconciliationError("result aggregates must use AreaAggregate")
        if tuple(item.area for item in self.area_aggregates) != tuple(ComparisonArea):
            raise ReconciliationError("result must contain all area aggregates in order")
        for aggregate in self.area_aggregates:
            _require_sorted_digests(aggregate.union_atom_ids, "area union", set(atom_ids))
            _require_sorted_digests(
                aggregate.intersection_atom_ids,
                "area intersection",
                set(aggregate.union_atom_ids),
            )
            complete = aggregate.complete_package_ref_ids
            incomplete = aggregate.incomplete_package_ref_ids
            _require_sorted_digests(complete, "complete package IDs", set(package_ids))
            _require_sorted_digests(incomplete, "incomplete package IDs", set(package_ids))
            if not set(complete).isdisjoint(incomplete) or {
                *complete,
                *incomplete,
            } != set(package_ids):
                raise ReconciliationError("aggregate package sets must form an exact partition")
            if set(aggregate.union_atom_ids) != atoms_by_area[aggregate.area]:
                raise ReconciliationError("aggregate union is not the exact area atom set")
            expected_intersection = {
                atom_id
                for atom_id in atoms_by_area[aggregate.area]
                if atom_packages[atom_id] == set(package_ids)
            }
            if set(aggregate.intersection_atom_ids) != expected_intersection:
                raise ReconciliationError("aggregate intersection is not exact")

        expected_pairs = tuple(
            (left, right, area)
            for left, right in combinations(package_ids, 2)
            for area in ComparisonArea
        )
        if type(self.pair_decisions) is not tuple or any(
            type(item) is not PairDecision for item in self.pair_decisions
        ):
            raise ReconciliationError("result decisions must use PairDecision")
        actual_pairs = tuple(
            (item.left_package_ref_id, item.right_package_ref_id, item.area)
            for item in self.pair_decisions
        )
        if actual_pairs != expected_pairs:
            raise ReconciliationError("result pair decisions are not the exact ordered universe")
        incomplete_packages: dict[ComparisonArea, set[str]] = {
            area: set() for area in ComparisonArea
        }
        incomplete_codes: defaultdict[tuple[str, ComparisonArea], set[str]] = defaultdict(set)
        expected_promotions: set[FullPromotion] = set()
        expected_repairs: set[RepairRequirement] = set()
        for item in self.pair_decisions:
            if type(item.decision) is not ComparisonDecision:
                raise ReconciliationError("pair decision enum is invalid")
            _require_sorted_digests(item.shared_atom_ids, "shared atoms", set(atom_ids))
            _require_sorted_digests(item.left_only_atom_ids, "left-only atoms", set(atom_ids))
            _require_sorted_digests(item.right_only_atom_ids, "right-only atoms", set(atom_ids))
            _require_sorted_digests(
                item.contradiction_ids,
                "pair contradiction IDs",
                set(contradiction_ids),
            )
            if not (
                set(item.shared_atom_ids).isdisjoint(item.left_only_atom_ids)
                and set(item.shared_atom_ids).isdisjoint(item.right_only_atom_ids)
                and set(item.left_only_atom_ids).isdisjoint(item.right_only_atom_ids)
            ):
                raise ReconciliationError("pair atom partitions overlap")
            left_atoms = {
                atom_id
                for atom_id in atoms_by_area[item.area]
                if item.left_package_ref_id in atom_packages[atom_id]
            }
            right_atoms = {
                atom_id
                for atom_id in atoms_by_area[item.area]
                if item.right_package_ref_id in atom_packages[atom_id]
            }
            if (
                set(item.shared_atom_ids) != left_atoms & right_atoms
                or set(item.left_only_atom_ids) != left_atoms - right_atoms
                or set(item.right_only_atom_ids) != right_atoms - left_atoms
            ):
                raise ReconciliationError("pair atoms do not match package provenance")
            expected_contradictions = {
                contradiction.content_id
                for contradiction in self.contradictions
                if contradiction.area is item.area
                and contradiction.package_ref_id
                in {item.left_package_ref_id, item.right_package_ref_id}
            }
            if set(item.contradiction_ids) != expected_contradictions:
                raise ReconciliationError("pair contradiction set is not exact")
            if type(item.incomplete_reasons) is not tuple or any(
                type(reason) is not str for reason in item.incomplete_reasons
            ):
                raise ReconciliationError("pair incomplete reasons must be strings")
            if item.incomplete_reasons != tuple(sorted(set(item.incomplete_reasons))):
                raise ReconciliationError("pair incomplete reasons must be sorted and unique")
            for reason in item.incomplete_reasons:
                side, separator, code = reason.partition(":")
                if (
                    separator != ":"
                    or side not in {"LEFT", "RIGHT"}
                    or code
                    not in {
                        "AREA_DECLARED_INCOMPLETE",
                        "AREA_MISSING",
                        "INCOMPLETE_DISPOSITION",
                        "ROOT_BLOCKED",
                        "UNRESOLVED_GAPS",
                    }
                ):
                    raise ReconciliationError("pair incomplete reason is invalid")
                package_id = (
                    item.left_package_ref_id if side == "LEFT" else item.right_package_ref_id
                )
                incomplete_packages[item.area].add(package_id)
                incomplete_codes[(package_id, item.area)].add(code)
            for contradiction in self.contradictions:
                if contradiction.content_id in item.contradiction_ids:
                    incomplete_packages[item.area].add(contradiction.package_ref_id)
                    incomplete_codes[(contradiction.package_ref_id, item.area)].add(
                        "CONTRADICTORY_AREA"
                    )
            incomplete = bool(item.incomplete_reasons or item.contradiction_ids)
            different = bool(item.left_only_atom_ids or item.right_only_atom_ids)
            expected = (
                ComparisonDecision.INCOMPLETE
                if incomplete
                else ComparisonDecision.DIFFERENT
                if different
                else ComparisonDecision.SAME
            )
            if item.decision is not expected:
                raise ReconciliationError("pair decision disagrees with its exact partitions")
            if item.decision is ComparisonDecision.DIFFERENT:
                _expected_difference_promotions(
                    item.left_package_ref_id,
                    item.area,
                    item.left_only_atom_ids,
                    atoms_by_id,
                    roots,
                    expected_promotions,
                )
                _expected_difference_promotions(
                    item.right_package_ref_id,
                    item.area,
                    item.right_only_atom_ids,
                    atoms_by_id,
                    roots,
                    expected_promotions,
                )

        aggregates = {item.area: item for item in self.area_aggregates}
        if len(package_ids) == 1:
            # A standalone package has no peer pairs. Its area closure still
            # requires repair or promotion before the work unit can complete.
            package_id = package_ids[0]
            for area, aggregate in aggregates.items():
                if aggregate.incomplete_package_ref_ids:
                    incomplete_packages[area].add(package_id)
                    incomplete_codes[(package_id, area)].add("AREA_DECLARED_INCOMPLETE")
            for contradiction in self.contradictions:
                incomplete_packages[contradiction.area].add(package_id)
                incomplete_codes[(package_id, contradiction.area)].add("CONTRADICTORY_AREA")
        for area, package_set in incomplete_packages.items():
            aggregate = aggregates[area]
            if set(aggregate.incomplete_package_ref_ids) != package_set:
                raise ReconciliationError("aggregate incomplete package set is not exact")
        for (package_id, area), reason_codes in incomplete_codes.items():
            package_roots = {
                root_id: route
                for (root_package_id, root_id), route in roots.items()
                if root_package_id == package_id
            }
            exact_roots = {
                root_id for root_id, route in package_roots.items() if route is Route.EXACT_REUSE
            }
            for reason_code in reason_codes:
                expected_promotions.update(
                    FullPromotion(package_id, root_id, area, reason_code) for root_id in exact_roots
                )
                if not exact_roots or any(
                    route is not Route.EXACT_REUSE for route in package_roots.values()
                ):
                    expected_repairs.add(RepairRequirement(package_id, area, reason_code))

        if type(self.required_full_promotions) is not tuple or any(
            type(item) is not FullPromotion for item in self.required_full_promotions
        ):
            raise ReconciliationError("result promotions must use FullPromotion")
        if self.required_full_promotions != tuple(sorted(set(self.required_full_promotions))):
            raise ReconciliationError("FULL promotions must be sorted and unique")
        for item in self.required_full_promotions:
            if roots.get((item.package_ref_id, item.root_ref_id)) is not Route.EXACT_REUSE:
                raise ReconciliationError("FULL promotion must identify an exact-reuse root")
            if type(item.area) is not ComparisonArea or _TOKEN.fullmatch(item.reason_code) is None:
                raise ReconciliationError("FULL promotion area or reason is invalid")
        if set(self.required_full_promotions) != expected_promotions:
            raise ReconciliationError("FULL promotion set is not exact")
        if type(self.repairs_required) is not tuple or any(
            type(item) is not RepairRequirement for item in self.repairs_required
        ):
            raise ReconciliationError("result repairs must use RepairRequirement")
        if self.repairs_required != tuple(sorted(set(self.repairs_required))):
            raise ReconciliationError("repair requirements must be sorted and unique")
        for item in self.repairs_required:
            if item.package_ref_id not in package_ids or type(item.area) is not ComparisonArea:
                raise ReconciliationError("repair package or area is invalid")
            if _TOKEN.fullmatch(item.reason_code) is None:
                raise ReconciliationError("repair reason is invalid")
        if set(self.repairs_required) != expected_repairs:
            raise ReconciliationError("repair requirement set is not exact")
        expected_status = (
            ClosureStatus.INCOMPLETE
            if self.required_full_promotions
            or self.repairs_required
            or any(item.decision is ComparisonDecision.INCOMPLETE for item in self.pair_decisions)
            else ClosureStatus.COMPLETE
        )
        if self.status is not expected_status:
            raise ReconciliationError("result status disagrees with follow-up requirements")

    def payload_data(self) -> dict[str, object]:
        return {
            "area_aggregates": [item.to_data() for item in self.area_aggregates],
            "atoms": [item.to_data() for item in self.atoms],
            "cluster_id": self.cluster_id,
            "contradictions": [item.to_data() for item in self.contradictions],
            "input_id": self.input_id,
            "packages": [item.to_data() for item in self.packages],
            "pair_decisions": [item.to_data() for item in self.pair_decisions],
            "repairs_required": [item.to_data() for item in self.repairs_required],
            "required_full_promotions": [item.to_data() for item in self.required_full_promotions],
            "revision": self.revision,
            "status": self.status.value,
        }

    @property
    def content_id(self) -> str:
        return canonical_content_id("reconciliation-result", self.payload_data())

    def to_data(self) -> dict[str, object]:
        return {"content_id": self.content_id, **self.payload_data()}


@dataclass(frozen=True, slots=True)
class _AreaView:
    atoms: tuple[SemanticAtom, ...]
    contradictions: tuple[Contradiction, ...]
    incomplete_reasons: tuple[str, ...]

    @property
    def atom_ids(self) -> frozenset[str]:
        return frozenset(item.content_id for item in self.atoms)


def reconcile(value: ReconciliationInput) -> ReconciliationResult:
    """Compare every package-area pair and derive all required follow-up work."""
    if type(value) is not ReconciliationInput:
        raise ReconciliationError("reconcile requires ReconciliationInput")
    # The strict round trip both snapshots caller-owned values and catches hostile
    # mutation of otherwise frozen records before any decision is made.
    frozen = loads_input(
        dumps_input(value),
        trusted_input=value,
    )
    packages = {item.package_ref.content_id: item for item in frozen.packages}
    roots = {
        (package_id, root.content_id): root
        for package_id, package in packages.items()
        for root in package.roots
    }
    views: dict[tuple[str, ComparisonArea], _AreaView] = {}
    all_atoms: dict[str, SemanticAtom] = {}
    all_contradictions: dict[str, Contradiction] = {}
    for package_id, package in packages.items():
        surfaces = {item.area: item for item in package.areas}
        for area in ComparisonArea:
            view = _build_area_view(package, area, surfaces.get(area))
            views[(package_id, area)] = view
            for atom in view.atoms:
                existing = all_atoms.get(atom.content_id)
                if existing is None:
                    all_atoms[atom.content_id] = atom
                else:
                    all_atoms[atom.content_id] = SemanticAtom(
                        area=atom.area,
                        kind=atom.kind,
                        identity=atom.identity,
                        payload=atom.payload,
                        sources=tuple(sorted({*existing.sources, *atom.sources})),
                    )
            for contradiction in view.contradictions:
                all_contradictions[contradiction.content_id] = contradiction

    pair_decisions: list[PairDecision] = []
    promotions: set[FullPromotion] = set()
    repairs: set[RepairRequirement] = set()
    atom_references = 0
    if len(packages) == 1:
        package_id, package = next(iter(packages.items()))
        for area in ComparisonArea:
            view = views[(package_id, area)]
            if view.incomplete_reasons or view.contradictions:
                _route_incomplete_package(
                    package,
                    area,
                    ("AREA_DECLARED_INCOMPLETE",),
                    bool(view.contradictions),
                    promotions,
                    repairs,
                )
    for left_id, right_id in combinations(packages, 2):
        for area in ComparisonArea:
            left = views[(left_id, area)]
            right = views[(right_id, area)]
            left_ids = left.atom_ids
            right_ids = right.atom_ids
            shared = tuple(sorted(left_ids & right_ids))
            left_only = tuple(sorted(left_ids - right_ids))
            right_only = tuple(sorted(right_ids - left_ids))
            contradiction_ids = tuple(
                sorted(item.content_id for item in (*left.contradictions, *right.contradictions))
            )
            reasons = tuple(
                sorted(f"LEFT:{item}" for item in left.incomplete_reasons)
                + sorted(f"RIGHT:{item}" for item in right.incomplete_reasons)
            )
            if reasons or contradiction_ids:
                decision = ComparisonDecision.INCOMPLETE
            elif left_ids == right_ids:
                decision = ComparisonDecision.SAME
            else:
                decision = ComparisonDecision.DIFFERENT
            atom_references += len(shared) + len(left_only) + len(right_only)
            if atom_references > _MAX_RESULT_ATOM_REFERENCES:
                raise ReconciliationError(
                    f"result exceeds {_MAX_RESULT_ATOM_REFERENCES} pair atom references"
                )
            pair_decisions.append(
                PairDecision(
                    left_package_ref_id=left_id,
                    right_package_ref_id=right_id,
                    area=area,
                    decision=decision,
                    shared_atom_ids=shared,
                    left_only_atom_ids=left_only,
                    right_only_atom_ids=right_only,
                    contradiction_ids=contradiction_ids,
                    incomplete_reasons=reasons,
                )
            )
            if decision is ComparisonDecision.DIFFERENT:
                _promote_atom_sources(
                    left_id,
                    area,
                    left_only,
                    all_atoms,
                    roots,
                    promotions,
                )
                _promote_atom_sources(
                    right_id,
                    area,
                    right_only,
                    all_atoms,
                    roots,
                    promotions,
                )
            elif decision is ComparisonDecision.INCOMPLETE:
                if left.incomplete_reasons or left.contradictions:
                    _route_incomplete_package(
                        packages[left_id],
                        area,
                        left.incomplete_reasons,
                        bool(left.contradictions),
                        promotions,
                        repairs,
                    )
                if right.incomplete_reasons or right.contradictions:
                    _route_incomplete_package(
                        packages[right_id],
                        area,
                        right.incomplete_reasons,
                        bool(right.contradictions),
                        promotions,
                        repairs,
                    )

    area_aggregates = tuple(
        _aggregate_area(area, tuple(packages), views) for area in ComparisonArea
    )
    package_references = tuple(_package_reference(item) for item in frozen.packages)
    status = (
        ClosureStatus.COMPLETE
        if all(item.decision is not ComparisonDecision.INCOMPLETE for item in pair_decisions)
        and not promotions
        and not repairs
        else ClosureStatus.INCOMPLETE
    )
    return ReconciliationResult(
        cluster_id=frozen.cluster_id,
        input_id=frozen.content_id,
        status=status,
        packages=package_references,
        atoms=tuple(sorted(all_atoms.values(), key=lambda item: item.content_id)),
        area_aggregates=area_aggregates,
        pair_decisions=tuple(pair_decisions),
        contradictions=tuple(sorted(all_contradictions.values(), key=lambda item: item.content_id)),
        required_full_promotions=tuple(sorted(promotions)),
        repairs_required=tuple(sorted(repairs)),
    )


def _require_digest(value: object, field: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ReconciliationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _require_sorted_digests(
    values: tuple[str, ...], field: str, allowed: set[str] | None = None
) -> None:
    if type(values) is not tuple:
        raise ReconciliationError(f"{field} must be a sorted unique tuple")
    for value in values:
        _require_digest(value, field)
    if values != tuple(sorted(set(values))):
        raise ReconciliationError(f"{field} must be a sorted unique tuple")
    if allowed is not None and not set(values) <= allowed:
        raise ReconciliationError(f"{field} contains an unknown digest")


def _expected_difference_promotions(
    package_ref_id: str,
    area: ComparisonArea,
    atom_ids: tuple[str, ...],
    atoms_by_id: dict[str, SemanticAtom],
    roots: dict[tuple[str, str], Route],
    promotions: set[FullPromotion],
) -> None:
    for atom_id in atom_ids:
        for source in atoms_by_id[atom_id].sources:
            if (
                source.package_ref_id == package_ref_id
                and roots.get((package_ref_id, source.root_ref_id)) is Route.EXACT_REUSE
            ):
                promotions.add(
                    FullPromotion(
                        package_ref_id,
                        source.root_ref_id,
                        area,
                        "DIFFERENT_SEMANTICS",
                    )
                )


def _build_area_view(
    package: PackageSurface,
    area: ComparisonArea,
    surface: AreaSurface | None,
) -> _AreaView:
    package_id = package.package_ref.content_id
    reasons: set[str] = set()
    if surface is None:
        reasons.add("AREA_MISSING")
        atoms: tuple[SemanticAtom, ...] = ()
        contradictions: tuple[Contradiction, ...] = ()
    else:
        atoms, contradictions = _surface_atoms(package_id, area, surface)
        if surface.closure is ClosureStatus.INCOMPLETE:
            reasons.add("AREA_DECLARED_INCOMPLETE")
        if surface.gaps:
            reasons.add("UNRESOLVED_GAPS")
        if any(item.status is DispositionStatus.INCOMPLETE for item in surface.dispositions):
            reasons.add("INCOMPLETE_DISPOSITION")
    if any(root.route is Route.BLOCKED for root in package.roots):
        reasons.add("ROOT_BLOCKED")
    return _AreaView(atoms, contradictions, tuple(sorted(reasons)))


def _surface_atoms(
    package_ref_id: str,
    area: ComparisonArea,
    surface: AreaSurface,
) -> tuple[tuple[SemanticAtom, ...], tuple[Contradiction, ...]]:
    grouped: defaultdict[str, list[SemanticAtom]] = defaultdict(list)
    for claim in surface.claims:
        payload = {
            "polarity": claim.polarity.value,
            "value": claim.value.to_data(),
        }
        atom = SemanticAtom(
            area=area,
            kind="CLAIM",
            identity=claim.key,
            payload=CanonicalValue.from_data(payload),
            sources=tuple(
                sorted({AtomSource(package_ref_id, item.root_ref_id) for item in claim.provenance})
            ),
        )
        grouped[f"CLAIM:{claim.key}"].append(atom)
    for disposition in surface.dispositions:
        payload = {
            "claim_keys": list(disposition.claim_keys),
            "reason_code": disposition.reason_code,
            "status": disposition.status.value,
        }
        atom = SemanticAtom(
            area=area,
            kind=disposition.kind.value,
            identity=disposition.item_id,
            payload=CanonicalValue.from_data(payload),
            sources=tuple(
                sorted(
                    {
                        AtomSource(package_ref_id, item.root_ref_id)
                        for item in disposition.provenance
                    }
                )
            ),
        )
        grouped[f"{disposition.kind.value}:{disposition.item_id}"].append(atom)

    atoms: dict[str, SemanticAtom] = {}
    contradictions: list[Contradiction] = []
    for identity, entries in sorted(grouped.items()):
        entry_ids = tuple(sorted(item.content_id for item in entries))
        roots = tuple(sorted({source.root_ref_id for entry in entries for source in entry.sources}))
        if len(entries) > 1:
            contradictions.append(
                Contradiction(
                    package_ref_id=package_ref_id,
                    area=area,
                    code=(
                        "DUPLICATE_SEMANTIC_IDENTITY"
                        if len(set(entry_ids)) == 1
                        else "CONFLICTING_SEMANTIC_IDENTITY"
                    ),
                    identity=identity,
                    atom_ids=tuple(sorted(set(entry_ids))),
                    root_ref_ids=roots,
                )
            )
        for entry in entries:
            existing = atoms.get(entry.content_id)
            if existing is None:
                atoms[entry.content_id] = entry
            else:
                atoms[entry.content_id] = SemanticAtom(
                    area=entry.area,
                    kind=entry.kind,
                    identity=entry.identity,
                    payload=entry.payload,
                    sources=tuple(sorted({*existing.sources, *entry.sources})),
                )
    return (
        tuple(sorted(atoms.values(), key=lambda item: item.content_id)),
        tuple(sorted(contradictions, key=lambda item: item.content_id)),
    )


def _promote_atom_sources(
    package_ref_id: str,
    area: ComparisonArea,
    atom_ids: tuple[str, ...],
    atoms: dict[str, SemanticAtom],
    roots: dict[tuple[str, str], RootProvenance],
    promotions: set[FullPromotion],
) -> None:
    for atom_id in atom_ids:
        for source in atoms[atom_id].sources:
            if source.package_ref_id != package_ref_id:
                continue
            root = roots.get((package_ref_id, source.root_ref_id))
            if root is not None and root.route is Route.EXACT_REUSE:
                promotions.add(
                    FullPromotion(
                        package_ref_id,
                        source.root_ref_id,
                        area,
                        "DIFFERENT_SEMANTICS",
                    )
                )


def _route_incomplete_package(
    package: PackageSurface,
    area: ComparisonArea,
    reasons: tuple[str, ...],
    contradicted: bool,
    promotions: set[FullPromotion],
    repairs: set[RepairRequirement],
) -> None:
    package_id = package.package_ref.content_id
    exact_roots = tuple(root for root in package.roots if root.route is Route.EXACT_REUSE)
    contradiction = ("CONTRADICTORY_AREA",) if contradicted else ()
    reason_codes = tuple(sorted({*reasons, *contradiction}))
    for reason in reason_codes:
        for root in exact_roots:
            promotions.add(FullPromotion(package_id, root.content_id, area, reason))
        if not exact_roots or any(root.route is not Route.EXACT_REUSE for root in package.roots):
            repairs.add(RepairRequirement(package_id, area, reason))


def _aggregate_area(
    area: ComparisonArea,
    package_ids: tuple[str, ...],
    views: dict[tuple[str, ComparisonArea], _AreaView],
) -> AreaAggregate:
    sets = [views[(package_id, area)].atom_ids for package_id in package_ids]
    union = frozenset().union(*sets)
    intersection = sets[0].intersection(*sets[1:])
    complete = tuple(
        package_id
        for package_id in package_ids
        if not views[(package_id, area)].incomplete_reasons
        and not views[(package_id, area)].contradictions
    )
    incomplete = tuple(package_id for package_id in package_ids if package_id not in complete)
    return AreaAggregate(
        area=area,
        union_atom_ids=tuple(sorted(union)),
        intersection_atom_ids=tuple(sorted(intersection)),
        complete_package_ref_ids=complete,
        incomplete_package_ref_ids=incomplete,
    )


def _package_reference(package: PackageSurface) -> PackageResultReference:
    roots = tuple(
        RootResultReference(
            package_ref_id=package.package_ref.content_id,
            root_ref_id=root.content_id,
            target_root_id=root.target_root_id,
            occurrence_identity_sha256=root.occurrence_identity_sha256,
            route=root.route,
            semantic_root_sha256=root.semantic_root_sha256,
            source_root_id=root.source_root_id,
        )
        for root in package.roots
    )
    return PackageResultReference(
        package_ref_id=package.package_ref.content_id,
        package_surface_id=package.content_id,
        report_sha256=package.report_sha256,
        package_local_ref_id=package.package_local.content_id,
        roots=roots,
    )
