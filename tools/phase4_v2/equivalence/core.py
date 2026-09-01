"""Fail-closed exact-byte equivalence and append-only routing ledger.

This first slice deliberately has no representation for fuzzy or audited
non-identical equivalence.  A root either has an exact clean byte witness or it
is routed to full analysis (or blocked when analysis cannot safely start).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Never

EQUIVALENCE_SCHEMA_REVISION = "phase4-v2-exact-equivalence-v1"
PACKAGE_REF_REVISION = "phase4-v2-frozen-package-ref-v1"
EXTRACTOR_CAPABILITY_REVISION = "phase4-v2-extractor-capability-v1"
APPLICATION_ROOT_REVISION = "phase4-v2-application-root-v1"
BYTE_IDENTITY_PROOF_REVISION = "phase4-v2-byte-identity-proof-v1"
LEDGER_DECISION_REVISION = "phase4-v2-equivalence-decision-v1"
LEDGER_ENTRY_REVISION = "phase4-v2-equivalence-ledger-entry-v1"

LOCAL_ONLY_DOMAINS = (
    "configuration",
    "lifecycle",
    "negative_closure",
    "reachability",
    "resources",
    "selectors",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_PACKAGE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_MAX_PACKAGE_NAME = 512
_MAX_VERSION = 256
_MAX_ROOT_KIND = 200
_MAX_CAPABILITY_NAME = 200
_MAX_REVISION = 200
_MAX_REASON = 200
_MAX_SLICE_ID = 4_096
_MAX_RISKS_PER_ROOT = 4_096
_MAX_CANDIDATES = 250_000
_MAX_LEDGER_RECORDS = 1_000_000
_MAX_TRUSTED_SOURCE_ROOTS = 250_000


class EquivalenceError(ValueError):
    """An equivalence record or transition violated the accepted contract."""


class Route(StrEnum):
    """The only routes supported by the exact-identical first slice."""

    EXACT_REUSE = "EXACT_REUSE"
    FULL_ANALYSIS = "FULL_ANALYSIS"
    BLOCKED = "BLOCKED"


def _fail(message: str) -> Never:
    raise EquivalenceError(message)


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256 digest")
    return value


def _token(value: str, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or len(value) > maximum or _TOKEN.fullmatch(value) is None:
        _fail(f"{field} is not a valid revision token")
    return value


def _text(value: str, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _fail(f"{field} must be a non-empty string of at most {maximum} characters")
    if any(ord(character) < 0x20 for character in value):
        _fail(f"{field} contains a control character")
    return value


def _ordered_unique(
    values: tuple[str, ...], field: str, *, maximum_count: int, maximum_length: int
) -> tuple[str, ...]:
    if type(values) is not tuple:
        _fail(f"{field} must be an immutable tuple")
    if len(values) > maximum_count:
        _fail(f"{field} exceeds its limit of {maximum_count}")
    for index, value in enumerate(values):
        _text(value, f"{field}[{index}]", maximum=maximum_length)
    if tuple(sorted(set(values))) != values:
        _fail(f"{field} must be sorted and unique")
    return values


def _canonical_content_id(domain: str, data: Mapping[str, object]) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("ascii") + b"\0" + encoded).hexdigest()


def _validate_pins(pins: RoutingPins) -> None:
    if not isinstance(pins, RoutingPins):
        _fail("exact externally supplied RoutingPins are required")
    # Reconstructing invokes every revision check again, including after a
    # hostile caller has bypassed frozen dataclass assignment guards.
    RoutingPins(**pins.to_data())


def _validate_root_revision(root: ApplicationRoot, pins: RoutingPins) -> None:
    if not isinstance(root, ApplicationRoot):
        _fail("application roots must use the immutable ApplicationRoot type")
    root.__post_init__()
    if root.revision != pins.application_root:
        _fail("application-root revision differs from the trusted pin")


@dataclass(frozen=True, slots=True)
class RoutingPins:
    """Orchestrator-owned revision pins for every transitive record type."""

    equivalence: str = EQUIVALENCE_SCHEMA_REVISION
    package_ref: str = PACKAGE_REF_REVISION
    extractor_capability: str = EXTRACTOR_CAPABILITY_REVISION
    application_root: str = APPLICATION_ROOT_REVISION
    byte_identity_proof: str = BYTE_IDENTITY_PROOF_REVISION
    ledger_decision: str = LEDGER_DECISION_REVISION
    ledger_entry: str = LEDGER_ENTRY_REVISION

    def __post_init__(self) -> None:
        for field, expected in (
            ("equivalence", EQUIVALENCE_SCHEMA_REVISION),
            ("package_ref", PACKAGE_REF_REVISION),
            ("extractor_capability", EXTRACTOR_CAPABILITY_REVISION),
            ("application_root", APPLICATION_ROOT_REVISION),
            ("byte_identity_proof", BYTE_IDENTITY_PROOF_REVISION),
            ("ledger_decision", LEDGER_DECISION_REVISION),
            ("ledger_entry", LEDGER_ENTRY_REVISION),
        ):
            value = getattr(self, field)
            _token(value, f"pins.{field}")
            if value != expected:
                _fail(f"unsupported {field} revision {value!r}; expected {expected!r}")

    def to_data(self) -> dict[str, str]:
        return {
            "application_root": self.application_root,
            "byte_identity_proof": self.byte_identity_proof,
            "equivalence": self.equivalence,
            "extractor_capability": self.extractor_capability,
            "ledger_decision": self.ledger_decision,
            "ledger_entry": self.ledger_entry,
            "package_ref": self.package_ref,
        }


@dataclass(frozen=True, slots=True)
class FrozenPackageRef:
    """Frozen package identity and its trusted package-local validation roots."""

    package_name: str
    version_code: str
    artifact_digest: str
    preflight_sha256: str
    validation_receipt_sha256: str
    revision: str = PACKAGE_REF_REVISION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.package_name, str)
            or len(self.package_name) > _MAX_PACKAGE_NAME
            or _PACKAGE.fullmatch(self.package_name) is None
        ):
            _fail("package_name is invalid")
        _text(self.version_code, "version_code", maximum=_MAX_VERSION)
        _sha256(self.artifact_digest, "artifact_digest")
        _sha256(self.preflight_sha256, "preflight_sha256")
        _sha256(self.validation_receipt_sha256, "validation_receipt_sha256")
        if self.revision != PACKAGE_REF_REVISION:
            _fail("unsupported frozen package reference revision")

    def to_data(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "package_name": self.package_name,
            "preflight_sha256": self.preflight_sha256,
            "revision": self.revision,
            "validation_receipt_sha256": self.validation_receipt_sha256,
            "version_code": self.version_code,
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:frozen-package-ref", self.to_data())


@dataclass(frozen=True, slots=True)
class ExtractorCapability:
    """Exact extractor implementation and configuration used for an inventory."""

    name: str
    implementation_sha256: str
    configuration_sha256: str
    capability_revision: str
    revision: str = EXTRACTOR_CAPABILITY_REVISION

    def __post_init__(self) -> None:
        _token(self.name, "extractor.name", maximum=_MAX_CAPABILITY_NAME)
        _sha256(self.implementation_sha256, "extractor.implementation_sha256")
        _sha256(self.configuration_sha256, "extractor.configuration_sha256")
        _token(
            self.capability_revision,
            "extractor.capability_revision",
            maximum=_MAX_REVISION,
        )
        if self.revision != EXTRACTOR_CAPABILITY_REVISION:
            _fail("unsupported extractor capability record revision")

    def to_data(self) -> dict[str, object]:
        return {
            "capability_revision": self.capability_revision,
            "configuration_sha256": self.configuration_sha256,
            "implementation_sha256": self.implementation_sha256,
            "name": self.name,
            "revision": self.revision,
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:extractor-capability", self.to_data())


@dataclass(frozen=True, slots=True)
class ApplicationRoot:
    """One package-local, complete application-root inventory attestation."""

    package_ref_id: str
    root_kind: str
    extractor_capability_id: str
    occurrence_identity_sha256: str
    content_root_sha256: str
    inventory_sha256: str
    dependency_root_sha256: str
    inventory_complete: bool
    dependency_closure_complete: bool
    warnings: tuple[str, ...] = ()
    opaque_slices: tuple[str, ...] = ()
    dynamic_slices: tuple[str, ...] = ()
    unresolved_slices: tuple[str, ...] = ()
    missing_tooling: tuple[str, ...] = ()
    revision: str = APPLICATION_ROOT_REVISION

    def __post_init__(self) -> None:
        _sha256(self.package_ref_id, "root.package_ref_id")
        _token(self.root_kind, "root.root_kind", maximum=_MAX_ROOT_KIND)
        _sha256(self.extractor_capability_id, "root.extractor_capability_id")
        _sha256(self.occurrence_identity_sha256, "root.occurrence_identity_sha256")
        _sha256(self.content_root_sha256, "root.content_root_sha256")
        _sha256(self.inventory_sha256, "root.inventory_sha256")
        _sha256(self.dependency_root_sha256, "root.dependency_root_sha256")
        if not isinstance(self.inventory_complete, bool):
            _fail("root.inventory_complete must be a bool")
        if not isinstance(self.dependency_closure_complete, bool):
            _fail("root.dependency_closure_complete must be a bool")
        for field in (
            "warnings",
            "opaque_slices",
            "dynamic_slices",
            "unresolved_slices",
            "missing_tooling",
        ):
            _ordered_unique(
                getattr(self, field),
                f"root.{field}",
                maximum_count=_MAX_RISKS_PER_ROOT,
                maximum_length=_MAX_SLICE_ID,
            )
        if self.revision != APPLICATION_ROOT_REVISION:
            _fail("unsupported application-root record revision")

    @property
    def automatic_reuse_eligible(self) -> bool:
        return self.inventory_complete and self.dependency_closure_complete and not any(
            (
                self.warnings,
                self.opaque_slices,
                self.dynamic_slices,
                self.unresolved_slices,
                self.missing_tooling,
            )
        )

    @property
    def executable_identity(self) -> tuple[str, str, str, str, str]:
        """The complete and exclusive candidate-selection key."""
        return (
            self.root_kind,
            self.extractor_capability_id,
            self.content_root_sha256,
            self.inventory_sha256,
            self.dependency_root_sha256,
        )

    def to_data(self) -> dict[str, object]:
        return {
            "content_root_sha256": self.content_root_sha256,
            "dependency_closure_complete": self.dependency_closure_complete,
            "dependency_root_sha256": self.dependency_root_sha256,
            "dynamic_slices": list(self.dynamic_slices),
            "extractor_capability_id": self.extractor_capability_id,
            "inventory_complete": self.inventory_complete,
            "inventory_sha256": self.inventory_sha256,
            "missing_tooling": list(self.missing_tooling),
            "occurrence_identity_sha256": self.occurrence_identity_sha256,
            "opaque_slices": list(self.opaque_slices),
            "package_ref_id": self.package_ref_id,
            "revision": self.revision,
            "root_kind": self.root_kind,
            "unresolved_slices": list(self.unresolved_slices),
            "warnings": list(self.warnings),
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:application-root", self.to_data())


@dataclass(frozen=True, slots=True)
class ByteIdentityProof:
    """Exact equality proof between two clean package-local application roots."""

    left_root_id: str
    right_root_id: str
    root_kind: str
    extractor_capability_id: str
    content_root_sha256: str
    inventory_sha256: str
    dependency_root_sha256: str
    inventory_acceptance_sha256: str
    revision: str = BYTE_IDENTITY_PROOF_REVISION

    def __post_init__(self) -> None:
        _sha256(self.left_root_id, "proof.left_root_id")
        _sha256(self.right_root_id, "proof.right_root_id")
        if self.left_root_id >= self.right_root_id:
            _fail("proof root IDs must be distinct and canonically ordered")
        _token(self.root_kind, "proof.root_kind", maximum=_MAX_ROOT_KIND)
        _sha256(self.extractor_capability_id, "proof.extractor_capability_id")
        _sha256(self.content_root_sha256, "proof.content_root_sha256")
        _sha256(self.inventory_sha256, "proof.inventory_sha256")
        _sha256(self.dependency_root_sha256, "proof.dependency_root_sha256")
        _sha256(self.inventory_acceptance_sha256, "proof.inventory_acceptance_sha256")
        if self.revision != BYTE_IDENTITY_PROOF_REVISION:
            _fail("unsupported byte-identity proof revision")

    def to_data(self) -> dict[str, object]:
        return {
            "content_root_sha256": self.content_root_sha256,
            "dependency_root_sha256": self.dependency_root_sha256,
            "extractor_capability_id": self.extractor_capability_id,
            "inventory_sha256": self.inventory_sha256,
            "inventory_acceptance_sha256": self.inventory_acceptance_sha256,
            "left_root_id": self.left_root_id,
            "revision": self.revision,
            "right_root_id": self.right_root_id,
            "root_kind": self.root_kind,
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:byte-identity-proof", self.to_data())


def build_byte_identity_proof(
    left: ApplicationRoot,
    right: ApplicationRoot,
    *,
    pins: RoutingPins,
    trusted_inventory_receipts: Mapping[str, str],
) -> ByteIdentityProof:
    """Prove exact equality without consulting package or ecosystem metadata."""
    inventory_receipts = _trusted_root_receipts(
        trusted_inventory_receipts, field="trusted_inventory_receipts"
    )
    return _build_byte_identity_proof_validated(
        left, right, pins=pins, inventory_receipts=inventory_receipts
    )


def _build_byte_identity_proof_validated(
    left: ApplicationRoot,
    right: ApplicationRoot,
    *,
    pins: RoutingPins,
    inventory_receipts: Mapping[str, str],
) -> ByteIdentityProof:
    """Build a proof from a ledger-owned, already-copied receipt map."""
    _validate_pins(pins)
    _validate_root_revision(left, pins)
    _validate_root_revision(right, pins)
    if left.content_id == right.content_id:
        _fail("a byte-identity proof requires two distinct package-local roots")
    if not left.automatic_reuse_eligible or not right.automatic_reuse_eligible:
        _fail("byte-identity proof requires complete, warning-free, resolved roots")
    if left.executable_identity != right.executable_identity:
        _fail("application roots are not exactly identical")
    if left.content_id not in inventory_receipts or right.content_id not in inventory_receipts:
        _fail("byte-identity proof requires accepted inventory receipts for both roots")
    first, second = sorted((left.content_id, right.content_id))
    inventory_acceptance = _canonical_content_id(
        "phase4-v2:inventory-acceptance",
        {
            "roots": [
                {"receipt_sha256": inventory_receipts[root_id], "root_id": root_id}
                for root_id in (first, second)
            ]
        },
    )
    return ByteIdentityProof(
        left_root_id=first,
        right_root_id=second,
        root_kind=left.root_kind,
        extractor_capability_id=left.extractor_capability_id,
        content_root_sha256=left.content_root_sha256,
        inventory_sha256=left.inventory_sha256,
        dependency_root_sha256=left.dependency_root_sha256,
        inventory_acceptance_sha256=inventory_acceptance,
    )


@dataclass(frozen=True, slots=True)
class LedgerDecision:
    """Immutable route plus explicit evidence and package-local retention scope."""

    target_root_id: str
    route: Route
    reason: str
    target_inventory_receipt_sha256: str | None = None
    source_root_id: str | None = None
    byte_identity_proof_id: str | None = None
    inherited_root_id: str | None = None
    source_audit_receipt_sha256: str | None = None
    local_only_domains: tuple[str, ...] = LOCAL_ONLY_DOMAINS
    pins: RoutingPins = RoutingPins()
    revision: str = LEDGER_DECISION_REVISION

    def __post_init__(self) -> None:
        _sha256(self.target_root_id, "decision.target_root_id")
        if not isinstance(self.route, Route):
            _fail("decision.route must be a Route")
        _token(self.reason, "decision.reason", maximum=_MAX_REASON)
        if self.local_only_domains != LOCAL_ONLY_DOMAINS:
            _fail("package-local evidence domains cannot be inherited or omitted")
        if not isinstance(self.pins, RoutingPins):
            _fail("decision pins must use RoutingPins")
        if self.revision != LEDGER_DECISION_REVISION:
            _fail("unsupported ledger decision revision")
        if self.target_inventory_receipt_sha256 is not None:
            _sha256(
                self.target_inventory_receipt_sha256,
                "decision.target_inventory_receipt_sha256",
            )
        references = (
            self.source_root_id,
            self.byte_identity_proof_id,
            self.inherited_root_id,
            self.source_audit_receipt_sha256,
        )
        for index, value in enumerate(references):
            if value is not None:
                _sha256(value, f"decision.reference[{index}]")
        if self.route is Route.EXACT_REUSE:
            if any(value is None for value in references):
                _fail("exact reuse requires source, proof, and inherited-root bindings")
            if self.inherited_root_id != self.source_root_id:
                _fail("inherited findings must bind to the proven source root")
            if self.source_root_id == self.target_root_id:
                _fail("a root cannot reuse itself")
        elif any(value is not None for value in references):
            _fail("non-reuse routes cannot inherit or cite a byte-identity proof")

    def to_data(self) -> dict[str, object]:
        return {
            "byte_identity_proof_id": self.byte_identity_proof_id,
            "inherited_root_id": self.inherited_root_id,
            "local_only_domains": list(self.local_only_domains),
            "pins": self.pins.to_data(),
            "reason": self.reason,
            "revision": self.revision,
            "route": self.route.value,
            "source_root_id": self.source_root_id,
            "source_audit_receipt_sha256": self.source_audit_receipt_sha256,
            "target_root_id": self.target_root_id,
            "target_inventory_receipt_sha256": self.target_inventory_receipt_sha256,
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:equivalence-decision", self.to_data())


def route_application_root(
    target: ApplicationRoot,
    candidates: Iterable[ApplicationRoot],
    *,
    pins: RoutingPins,
    trusted_direct_audits: Mapping[str, str],
    trusted_inventory_receipts: Mapping[str, str],
) -> tuple[LedgerDecision, ByteIdentityProof | None]:
    """Route a root using only exact executable identities.

    The API intentionally accepts no name, signer, developer, brand, filename,
    version-similarity, or fuzzy-similarity inputs.
    """
    audits = _trusted_direct_audits(trusted_direct_audits)
    inventory_receipts = _trusted_root_receipts(
        trusted_inventory_receipts, field="trusted_inventory_receipts"
    )
    return _route_application_root_validated(
        target,
        candidates,
        pins=pins,
        audits=audits,
        inventory_receipts=inventory_receipts,
    )


def _route_application_root_validated(
    target: ApplicationRoot,
    candidates: Iterable[ApplicationRoot],
    *,
    pins: RoutingPins,
    audits: Mapping[str, str],
    inventory_receipts: Mapping[str, str],
) -> tuple[LedgerDecision, ByteIdentityProof | None]:
    """Route using ledger-owned maps validated and copied at construction."""
    _validate_pins(pins)
    _validate_root_revision(target, pins)
    if target.content_id not in inventory_receipts:
        return (
            LedgerDecision(
                target_root_id=target.content_id,
                route=Route.BLOCKED,
                reason="root_inventory_not_trusted",
                target_inventory_receipt_sha256=None,
                pins=pins,
            ),
            None,
        )
    if (
        target.missing_tooling
        or not target.inventory_complete
        or not target.dependency_closure_complete
    ):
        return (
            LedgerDecision(
                target_root_id=target.content_id,
                route=Route.BLOCKED,
                reason="root_not_completely_inventoryable",
                target_inventory_receipt_sha256=inventory_receipts[target.content_id],
                pins=pins,
            ),
            None,
        )
    if not target.automatic_reuse_eligible:
        return (
            LedgerDecision(
                target_root_id=target.content_id,
                route=Route.FULL_ANALYSIS,
                reason="root_contains_non_reusable_surface",
                target_inventory_receipt_sha256=inventory_receipts[target.content_id],
                pins=pins,
            ),
            None,
        )

    exact: list[ApplicationRoot] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if index >= _MAX_CANDIDATES:
            _fail(f"candidate count exceeds {_MAX_CANDIDATES}")
        _validate_root_revision(candidate, pins)
        candidate_id = candidate.content_id
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        if candidate_id == target.content_id:
            continue
        if (
            candidate.automatic_reuse_eligible
            and candidate.executable_identity == target.executable_identity
            and candidate_id in audits
            and candidate_id in inventory_receipts
        ):
            exact.append(candidate)
    if not exact:
        return (
            LedgerDecision(
                target_root_id=target.content_id,
                route=Route.FULL_ANALYSIS,
                reason="no_exact_executable_identity",
                target_inventory_receipt_sha256=inventory_receipts[target.content_id],
                pins=pins,
            ),
            None,
        )

    # Root IDs are used only to choose deterministically among already-proven,
    # byte-identical witnesses.  They never nominate or authorize a candidate.
    source = min(exact, key=lambda item: item.content_id)
    proof = _build_byte_identity_proof_validated(
        target,
        source,
        pins=pins,
        inventory_receipts=inventory_receipts,
    )
    return (
        LedgerDecision(
            target_root_id=target.content_id,
            route=Route.EXACT_REUSE,
            reason="exact_executable_identity",
            target_inventory_receipt_sha256=inventory_receipts[target.content_id],
            source_root_id=source.content_id,
            byte_identity_proof_id=proof.content_id,
            inherited_root_id=source.content_id,
            source_audit_receipt_sha256=audits[source.content_id],
            pins=pins,
        ),
        proof,
    )


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One hash-chained append-only decision record."""

    sequence: int
    previous_entry_id: str | None
    decision: LedgerDecision
    revision: str = LEDGER_ENTRY_REVISION

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            _fail("ledger sequence must be a non-negative integer")
        if self.previous_entry_id is not None:
            _sha256(self.previous_entry_id, "entry.previous_entry_id")
        if not isinstance(self.decision, LedgerDecision):
            _fail("entry decision must be an immutable LedgerDecision")
        if self.revision != LEDGER_ENTRY_REVISION:
            _fail("unsupported ledger entry revision")

    def to_data(self) -> dict[str, object]:
        return {
            "decision": self.decision.to_data(),
            "previous_entry_id": self.previous_entry_id,
            "revision": self.revision,
            "sequence": self.sequence,
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:equivalence-ledger-entry", self.to_data())


class AppendOnlyLedger:
    """Verifying append-only ledger over immutable, transitively pinned records."""

    def __init__(
        self,
        *,
        packages: Iterable[FrozenPackageRef],
        capabilities: Iterable[ExtractorCapability],
        roots: Iterable[ApplicationRoot],
        proofs: Iterable[ByteIdentityProof],
        pins: RoutingPins,
        trusted_direct_audits: Mapping[str, str],
        trusted_inventory_receipts: Mapping[str, str],
        entries: Iterable[LedgerEntry] = (),
        expected_head_id: str | None = None,
    ) -> None:
        _validate_pins(pins)
        self._pins = _copy_pins(pins)
        self._trusted_direct_audits = _trusted_direct_audits(trusted_direct_audits)
        self._trusted_inventory_receipts = _trusted_root_receipts(
            trusted_inventory_receipts, field="trusted_inventory_receipts"
        )
        self._packages = self._index(
            (_copy_package(item) for item in packages), "package", _MAX_LEDGER_RECORDS
        )
        self._capabilities = self._index(
            (_copy_capability(item) for item in capabilities),
            "capability",
            _MAX_LEDGER_RECORDS,
        )
        self._roots = self._index(
            (_copy_root(item) for item in roots), "root", _MAX_LEDGER_RECORDS
        )
        self._proofs = self._index(
            (_copy_proof(item) for item in proofs), "proof", _MAX_LEDGER_RECORDS
        )
        self._entries: list[LedgerEntry] = []
        self._decided_roots: set[str] = set()
        self._validate_graph()
        self._reuse_source_index = self._build_reuse_source_index()
        for entry in entries:
            self._append_existing(entry)
        if self.head_id != expected_head_id:
            _fail("ledger does not match the caller-pinned trusted head")

    @staticmethod
    def _index(records: Iterable[object], label: str, limit: int) -> dict[str, object]:
        indexed: dict[str, object] = {}
        for index, record in enumerate(records):
            if index >= limit:
                _fail(f"{label} record count exceeds {limit}")
            try:
                content_id = getattr(record, "content_id", None)
            except (TypeError, ValueError, UnicodeError) as error:
                raise EquivalenceError(f"{label} record cannot reproduce its content ID") from error
            if not isinstance(content_id, str) or _SHA256.fullmatch(content_id) is None:
                _fail(f"{label} record has no valid content ID")
            if content_id in indexed:
                _fail(f"duplicate {label} content ID")
            indexed[content_id] = record
        return indexed

    def _validate_graph(self) -> None:
        for item in self._packages.values():
            if not isinstance(item, FrozenPackageRef):
                _fail("package registry contains the wrong record type")
            item.__post_init__()
            if item.revision != self._pins.package_ref:
                _fail("frozen-package revision differs from the trusted pin")
        for item in self._capabilities.values():
            if not isinstance(item, ExtractorCapability):
                _fail("capability registry contains the wrong record type")
            item.__post_init__()
            if item.revision != self._pins.extractor_capability:
                _fail("extractor-capability revision differs from the trusted pin")
        occurrence_keys: set[tuple[str, str, str, str]] = set()
        for root_id, item in self._roots.items():
            if not isinstance(item, ApplicationRoot):
                _fail("root registry contains the wrong record type")
            item.__post_init__()
            if item.package_ref_id not in self._packages:
                _fail(f"root {root_id} references an unknown frozen package")
            if item.extractor_capability_id not in self._capabilities:
                _fail(f"root {root_id} references an unknown extractor capability")
            if item.revision != self._pins.application_root:
                _fail("application-root revision differs from the trusted pin")
            occurrence_key = (
                item.package_ref_id,
                item.root_kind,
                item.extractor_capability_id,
                item.occurrence_identity_sha256,
            )
            if occurrence_key in occurrence_keys:
                _fail("conflicting application roots claim the same package-local occurrence")
            occurrence_keys.add(occurrence_key)
        unknown_audits = set(self._trusted_direct_audits).difference(self._roots)
        if unknown_audits:
            _fail("trusted direct audit references an unknown application root")
        unknown_inventories = set(self._trusted_inventory_receipts).difference(self._roots)
        if unknown_inventories:
            _fail("trusted inventory receipt references an unknown application root")
        for proof_id, item in self._proofs.items():
            if not isinstance(item, ByteIdentityProof):
                _fail("proof registry contains the wrong record type")
            item.__post_init__()
            if item.revision != self._pins.byte_identity_proof:
                _fail("byte-identity-proof revision differs from the trusted pin")
            left = self._roots.get(item.left_root_id)
            right = self._roots.get(item.right_root_id)
            if not isinstance(left, ApplicationRoot) or not isinstance(right, ApplicationRoot):
                _fail(f"proof {proof_id} references an unknown application root")
            rebuilt = _build_byte_identity_proof_validated(
                left,
                right,
                pins=self._pins,
                inventory_receipts=self._trusted_inventory_receipts,
            )
            if rebuilt != item or rebuilt.content_id != proof_id:
                _fail(f"proof {proof_id} does not reproduce from its pinned roots")

    def _build_reuse_source_index(
        self,
    ) -> dict[tuple[str, str, str, str, str], tuple[ApplicationRoot, ...]]:
        grouped: dict[tuple[str, str, str, str, str], list[ApplicationRoot]] = {}
        for item in self._roots.values():
            if (
                isinstance(item, ApplicationRoot)
                and item.automatic_reuse_eligible
                and item.content_id in self._trusted_direct_audits
                and item.content_id in self._trusted_inventory_receipts
            ):
                grouped.setdefault(item.executable_identity, []).append(item)
        return {
            identity: tuple(sorted(items, key=lambda item: item.content_id))
            for identity, items in grouped.items()
        }

    def _validate_decision(self, decision: LedgerDecision) -> None:
        decision.__post_init__()
        _validate_pins(decision.pins)
        if decision.revision != self._pins.ledger_decision:
            _fail("ledger-decision revision differs from the trusted pin")
        if decision.pins != self._pins:
            _fail("decision revision pins differ from ledger pins")
        target = self._roots.get(decision.target_root_id)
        if not isinstance(target, ApplicationRoot):
            _fail("decision target root is not registered")
        if decision.target_root_id in self._decided_roots:
            _fail("an immutable application root already has a ledger decision")
        eligible_sources = self._reuse_source_index.get(target.executable_identity, ())
        if eligible_sources and eligible_sources[0].content_id == target.content_id:
            candidate_roots = eligible_sources[1:2]
        else:
            candidate_roots = eligible_sources[:1]
        expected, expected_proof = _route_application_root_validated(
            target,
            candidate_roots,
            pins=self._pins,
            audits=self._trusted_direct_audits,
            inventory_receipts=self._trusted_inventory_receipts,
        )
        if decision != expected:
            _fail("decision does not reproduce from the pinned deterministic routing inputs")
        if decision.route is Route.EXACT_REUSE:
            if decision.byte_identity_proof_id is None or decision.source_root_id is None:
                _fail("exact-reuse decision is missing mandatory references")
            proof = self._proofs.get(decision.byte_identity_proof_id)
            source = self._roots.get(decision.source_root_id)
            if not isinstance(proof, ByteIdentityProof) or not isinstance(source, ApplicationRoot):
                _fail("exact-reuse decision references an unknown proof or source root")
            if {proof.left_root_id, proof.right_root_id} != {
                decision.target_root_id,
                decision.source_root_id,
            }:
                _fail("exact-reuse decision proof does not bind target and source")
            if self._trusted_direct_audits.get(source.content_id) != (
                decision.source_audit_receipt_sha256
            ):
                _fail("source root is not pinned as an independently audited root")
            if target.executable_identity != source.executable_identity:
                _fail("exact-reuse roots no longer reproduce the same executable identity")
            if not target.automatic_reuse_eligible or not source.automatic_reuse_eligible:
                _fail("exact-reuse decision contains a tainted root")
            if expected_proof != proof:
                _fail("exact-reuse proof differs from the deterministic routing proof")
        else:
            if expected_proof is not None:
                _fail("internal non-reuse routing invariant failed")

    def _append_existing(self, entry: LedgerEntry) -> LedgerEntry:
        if len(self._entries) >= _MAX_LEDGER_RECORDS:
            _fail(f"ledger entry count exceeds {_MAX_LEDGER_RECORDS}")
        entry = _copy_entry(entry)
        entry.__post_init__()
        expected_previous = self._entries[-1].content_id if self._entries else None
        if entry.revision != self._pins.ledger_entry:
            _fail("ledger-entry revision differs from the trusted pin")
        if entry.sequence != len(self._entries) or entry.previous_entry_id != expected_previous:
            _fail("ledger entry sequence or hash-chain predecessor is invalid")
        self._validate_decision(entry.decision)
        self._entries.append(entry)
        self._decided_roots.add(entry.decision.target_root_id)
        return entry

    def append(self, decision: LedgerDecision, *, expected_head_id: str | None) -> LedgerEntry:
        """Append and return a newly hash-chained immutable decision."""
        if expected_head_id != self.head_id:
            _fail("ledger append expected head does not match the current trusted head")
        entry = LedgerEntry(
            sequence=len(self._entries),
            previous_entry_id=self._entries[-1].content_id if self._entries else None,
            decision=decision,
        )
        stored = self._append_existing(entry)
        return _copy_entry(stored)

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(_copy_entry(item) for item in self._entries)

    @property
    def head_id(self) -> str | None:
        return self._entries[-1].content_id if self._entries else None


def _trusted_direct_audits(value: Mapping[str, str]) -> dict[str, str]:
    return _trusted_root_receipts(value, field="trusted_direct_audits")


def _trusted_root_receipts(value: Mapping[str, str], *, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        _fail(f"{field} must be an externally supplied mapping")
    parsed: dict[str, str] = {}
    for index, (root_id, receipt_sha256) in enumerate(value.items()):
        if index >= _MAX_TRUSTED_SOURCE_ROOTS:
            _fail(f"{field} count exceeds {_MAX_TRUSTED_SOURCE_ROOTS}")
        parsed_root = _sha256(root_id, f"{field}.root_id")
        if parsed_root in parsed:
            _fail(f"{field} contains a duplicate root ID")
        parsed[parsed_root] = _sha256(
            receipt_sha256, f"{field}.receipt_sha256"
        )
    return parsed


def _copy_pins(item: RoutingPins) -> RoutingPins:
    if not isinstance(item, RoutingPins):
        _fail("pins must use the immutable RoutingPins type")
    return RoutingPins(
        equivalence=item.equivalence,
        package_ref=item.package_ref,
        extractor_capability=item.extractor_capability,
        application_root=item.application_root,
        byte_identity_proof=item.byte_identity_proof,
        ledger_decision=item.ledger_decision,
        ledger_entry=item.ledger_entry,
    )


def _copy_package(item: FrozenPackageRef) -> FrozenPackageRef:
    if not isinstance(item, FrozenPackageRef):
        _fail("packages must use the immutable FrozenPackageRef type")
    return FrozenPackageRef(
        package_name=item.package_name,
        version_code=item.version_code,
        artifact_digest=item.artifact_digest,
        preflight_sha256=item.preflight_sha256,
        validation_receipt_sha256=item.validation_receipt_sha256,
        revision=item.revision,
    )


def _copy_capability(item: ExtractorCapability) -> ExtractorCapability:
    if not isinstance(item, ExtractorCapability):
        _fail("capabilities must use the immutable ExtractorCapability type")
    return ExtractorCapability(
        name=item.name,
        implementation_sha256=item.implementation_sha256,
        configuration_sha256=item.configuration_sha256,
        capability_revision=item.capability_revision,
        revision=item.revision,
    )


def _copy_root(item: ApplicationRoot) -> ApplicationRoot:
    if not isinstance(item, ApplicationRoot):
        _fail("roots must use the immutable ApplicationRoot type")
    return ApplicationRoot(
        package_ref_id=item.package_ref_id,
        root_kind=item.root_kind,
        extractor_capability_id=item.extractor_capability_id,
        occurrence_identity_sha256=item.occurrence_identity_sha256,
        content_root_sha256=item.content_root_sha256,
        inventory_sha256=item.inventory_sha256,
        dependency_root_sha256=item.dependency_root_sha256,
        inventory_complete=item.inventory_complete,
        dependency_closure_complete=item.dependency_closure_complete,
        warnings=item.warnings,
        opaque_slices=item.opaque_slices,
        dynamic_slices=item.dynamic_slices,
        unresolved_slices=item.unresolved_slices,
        missing_tooling=item.missing_tooling,
        revision=item.revision,
    )


def _copy_proof(item: ByteIdentityProof) -> ByteIdentityProof:
    if not isinstance(item, ByteIdentityProof):
        _fail("proofs must use the immutable ByteIdentityProof type")
    return ByteIdentityProof(
        left_root_id=item.left_root_id,
        right_root_id=item.right_root_id,
        root_kind=item.root_kind,
        extractor_capability_id=item.extractor_capability_id,
        content_root_sha256=item.content_root_sha256,
        inventory_sha256=item.inventory_sha256,
        dependency_root_sha256=item.dependency_root_sha256,
        inventory_acceptance_sha256=item.inventory_acceptance_sha256,
        revision=item.revision,
    )


def _copy_decision(item: LedgerDecision) -> LedgerDecision:
    if not isinstance(item, LedgerDecision):
        _fail("decisions must use the immutable LedgerDecision type")
    return LedgerDecision(
        target_root_id=item.target_root_id,
        route=item.route,
        reason=item.reason,
        target_inventory_receipt_sha256=item.target_inventory_receipt_sha256,
        source_root_id=item.source_root_id,
        byte_identity_proof_id=item.byte_identity_proof_id,
        inherited_root_id=item.inherited_root_id,
        source_audit_receipt_sha256=item.source_audit_receipt_sha256,
        local_only_domains=item.local_only_domains,
        pins=_copy_pins(item.pins),
        revision=item.revision,
    )


def _copy_entry(item: LedgerEntry) -> LedgerEntry:
    if not isinstance(item, LedgerEntry):
        _fail("entries must use the immutable LedgerEntry type")
    return LedgerEntry(
        sequence=item.sequence,
        previous_entry_id=item.previous_entry_id,
        decision=_copy_decision(item.decision),
        revision=item.revision,
    )
