"""Authenticated source-report and per-root provenance authorities."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Never, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.phase4_v2.ir import (
    AttestedEvidenceAnchor,
    AttestedEvidenceMember,
    SourcePackage,
    ValidatedReport,
)
from tools.phase4_v2.ir.model import AttestedRootEvidence, AttestedRootEvidenceMember

from .core import (
    ActivatedValidatorAuthority,
    AuthenticatedValidatorEnvelope,
    ByteIdentityProof,
    FrozenPackageRef,
    LedgerDecision,
    Route,
    RoutingPins,
    validate_authenticated_validator_envelope,
    validate_frozen_package_ref,
)
from .plan import (
    CompletionPin,
    FrozenPackageExecutionPlan,
    package_validation_receipt_completion,
    validate_frozen_package_execution_plan,
)

SOURCE_REPORT_ROOT_COMPLETION_REVISION = "phase4-v2-package-validation-receipt-v1"
EXACT_REUSE_PROVENANCE_SCHEMA = "phase4-v2-authenticated-exact-reuse-provenance-v1"
_MAX_SOURCE_REPORTS = 4_096
_MAX_EXACT_REUSE_RECEIPT_BYTES = 4 * 1024 * 1024


class ProvenanceAuthenticationError(ValueError):
    """A source report or root binding failed closed."""


def _fail(message: str) -> Never:
    raise ProvenanceAuthenticationError(message)


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedSourceReport:
    """One validator-signed report bound to its exact frozen package reference."""

    package_ref: FrozenPackageRef
    envelope: AuthenticatedValidatorEnvelope
    report: ValidatedReport
    source_package: SourcePackage

    def __init__(self) -> None:
        _fail("authenticated source reports require the trusted registry factory")


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedSourceReportRegistry:
    """Canonical closed registry of independently authenticated source reports."""

    entries: tuple[AuthenticatedSourceReport, ...]

    def __init__(self) -> None:
        _fail("authenticated source report registries require the trusted factory")


def build_authenticated_source_report_registry(
    entries: Iterable[tuple[FrozenPackageRef, AuthenticatedValidatorEnvelope]],
) -> AuthenticatedSourceReportRegistry:
    """Reauthenticate every source and admit no caller-authored receipt fields."""

    accepted: list[AuthenticatedSourceReport] = []
    for package_ref, envelope in entries:
        if len(accepted) >= _MAX_SOURCE_REPORTS:
            _fail("source report registry exceeds its entry limit")
        package_ref = validate_frozen_package_ref(package_ref)
        envelope = validate_authenticated_validator_envelope(envelope)
        if (
            package_ref.validator_envelope_bytes != envelope.canonical_bytes
            or package_ref.validation_receipt_sha256 != envelope.receipt_sha256
        ):
            _fail("source package reference and validator envelope differ")
        identity = envelope.report.validated_artifact_identity
        if (
            identity.package_name,
            identity.version_code,
            identity.artifact_digest,
        ) != (
            package_ref.package_name,
            package_ref.version_code,
            package_ref.artifact_digest,
        ):
            _fail("source report artifact differs from its frozen package reference")
        item = object.__new__(AuthenticatedSourceReport)
        object.__setattr__(item, "package_ref", package_ref)
        object.__setattr__(item, "envelope", envelope)
        object.__setattr__(item, "report", envelope.report)
        object.__setattr__(item, "source_package", SourcePackage(identity, envelope.report))
        accepted.append(item)
    accepted.sort(key=lambda item: item.package_ref.content_id)
    if not accepted:
        _fail("source report registry cannot be empty")
    if len({item.package_ref.content_id for item in accepted}) != len(accepted):
        _fail("source report registry contains duplicate package references")
    if len({item.report.validation_receipt_sha256 for item in accepted}) != len(accepted):
        _fail("source report registry contains duplicate validator receipts")
    result = object.__new__(AuthenticatedSourceReportRegistry)
    object.__setattr__(result, "entries", tuple(accepted))
    return result


def source_report_root_unit_id(
    source: AuthenticatedSourceReport, root: AttestedRootEvidence
) -> str:
    """Derive the compact queue identity which pins one exact source-report root."""

    if type(source) is not AuthenticatedSourceReport or type(root) is not AttestedRootEvidence:
        _fail("source-root completion requires exact authenticated records")
    if root not in source.report.validated_root_evidence:
        _fail("source root is absent from the authenticated report")
    return package_validation_receipt_completion(source.package_ref).parent_unit_id


def source_report_root_completion(
    source: AuthenticatedSourceReport, root: AttestedRootEvidence
) -> CompletionPin:
    """Create the plan dependency pin for one exact authenticated report root."""

    if root not in source.report.validated_root_evidence:
        _fail("source root is absent from the authenticated report")
    completion = package_validation_receipt_completion(source.package_ref)
    if completion.parent_unit_id != source_report_root_unit_id(source, root):
        _fail("source report completion identity did not reproduce")
    return completion


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedRootProvenance:
    """Plan-bound root provenance derived exclusively from authenticated sources."""

    target_root_id: str
    target_occurrence_identity_sha256: str
    route: Route
    source_package_ref_id: str
    source_validation_receipt_sha256: str
    source_bundle_sha256: str
    source_package: SourcePackage
    source_root_id: str
    source_occurrence_identity_sha256: str
    semantic_root_sha256: str
    evidence_members: tuple[AttestedRootEvidenceMember, ...]
    attested_evidence_members: tuple[AttestedEvidenceMember, ...]
    attested_evidence_anchors: tuple[AttestedEvidenceAnchor, ...]

    def __init__(self) -> None:
        _fail("authenticated root provenance requires trusted plan binding")


def bind_authenticated_plan_root_provenance(
    execution_plan: FrozenPackageExecutionPlan,
    registry: AuthenticatedSourceReportRegistry,
    *,
    exact_reuse_receipts: Iterable[AuthenticatedExactReuseProvenance] = (),
) -> tuple[AuthenticatedRootProvenance, ...]:
    """Bind every executable plan root to exactly one signed source attestation."""

    plan = validate_frozen_package_execution_plan(execution_plan)
    if type(registry) is not AuthenticatedSourceReportRegistry:
        _fail("exact authenticated source report registry is required")
    # Rebuild the registry to reauthenticate all retained envelopes at this boundary.
    registry = build_authenticated_source_report_registry(
        (item.package_ref, item.envelope) for item in registry.entries
    )
    raw = json.loads(plan.canonical_bytes)
    expected_reuse_count = sum(
        item["route"] == Route.EXACT_REUSE.value for item in raw["root_plans"]
    )
    receipt_items: list[AuthenticatedExactReuseProvenance] = []
    for item in exact_reuse_receipts:
        if len(receipt_items) >= expected_reuse_count:
            _fail("exact-reuse provenance receipt set exceeds the planned root count")
        if type(item) is not AuthenticatedExactReuseProvenance:
            _fail("exact authenticated exact-reuse provenance is required")
        restored = _load_authenticated_exact_reuse_provenance(
            item.canonical_bytes,
            authority=item.authority,
            registry=registry,
            reauthenticate_registry=False,
        )
        if restored != item:
            _fail("exact-reuse provenance changed after authentication")
        receipt_items.append(restored)
    receipts = tuple(receipt_items)
    if len({item.canonical_bytes for item in receipts}) != len(receipts):
        _fail("exact-reuse provenance receipt set contains duplicates")
    consumed_receipts: set[bytes] = set()
    bindings: list[AuthenticatedRootProvenance] = []
    for root in raw["root_plans"]:
        route = Route(root["route"])
        if route is Route.BLOCKED:
            _fail("blocked roots cannot produce authenticated provenance")
        matches: list[tuple[AuthenticatedSourceReport, AttestedRootEvidence]] = []
        if route is Route.FULL_ANALYSIS:
            dependencies = root["analysis_dependencies"]
            target_root_id = root["target_root_id"]
            target_occurrence = root["target_occurrence_identity_sha256"]
            for source in registry.entries:
                if source.package_ref.content_id != plan.target_package_ref_id:
                    continue
                for attestation in source.report.validated_root_evidence:
                    if (
                        attestation.target_root_id == target_root_id
                        and attestation.target_occurrence_identity_sha256 == target_occurrence
                        and source_report_root_completion(source, attestation).to_data()
                        in dependencies
                    ):
                        matches.append((source, attestation))
        else:
            reuse = root["reuse"]
            target_root_id = reuse["target_root_id"]
            target_occurrence = reuse["target_occurrence_identity_sha256"]
            matching_receipts = [
                item
                for item in receipts
                if item.target_root_id == target_root_id
                and item.target_occurrence_identity_sha256 == target_occurrence
                and item.source_root_id == reuse["source_root_id"]
                and item.inherited_semantic_root_sha256 == reuse["inherited_semantic_root_sha256"]
                and item.source_validation_receipt_sha256
                == reuse["direct_semantic_audit_completion"]["digest"]
                and item.ledger_decision_completion_sha256
                == reuse["ledger_decision_completion"]["digest"]
                and item.byte_identity_proof_id == reuse["byte_identity_proof_id"]
                and item.root_plan_sha256
                == hashlib.sha256(
                    json.dumps(root, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            ]
            if len(matching_receipts) != 1:
                _fail("EXACT_REUSE root does not bind one signed audit preimage")
            audit = matching_receipts[0]
            consumed_receipts.add(audit.canonical_bytes)
            for source in registry.entries:
                if source.package_ref.content_id != audit.source_package_ref_id:
                    continue
                for attestation in source.report.validated_root_evidence:
                    if (
                        attestation.target_root_id == audit.source_root_id
                        and attestation.target_occurrence_identity_sha256
                        == audit.source_occurrence_identity_sha256
                        and attestation.semantic_root_sha256 == audit.inherited_semantic_root_sha256
                    ):
                        matches.append((source, attestation))
        if len(matches) != 1:
            _fail("plan root does not bind exactly one authenticated source root")
        source, attestation = matches[0]
        member_names = {item.member for item in attestation.evidence_members}
        anchor_ids = {
            anchor_id
            for item in attestation.evidence_members
            for anchor_id in item.evidence_anchor_ids
        }
        attested_members = tuple(
            item for item in source.report.validated_evidence_members if item.member in member_names
        )
        attested_anchors = tuple(
            item for item in source.report.validated_evidence_anchors if item.id in anchor_ids
        )
        if {item.member for item in attested_members} != member_names or {
            item.id for item in attested_anchors
        } != anchor_ids:
            _fail("source root evidence is not an exact partition of retained report facts")
        binding = object.__new__(AuthenticatedRootProvenance)
        values = (
            ("target_root_id", cast(str, target_root_id)),
            ("target_occurrence_identity_sha256", cast(str, target_occurrence)),
            ("route", route),
            ("source_package_ref_id", source.package_ref.content_id),
            ("source_validation_receipt_sha256", source.report.validation_receipt_sha256),
            ("source_bundle_sha256", source.report.bundle_sha256),
            ("source_package", source.source_package),
            ("source_root_id", attestation.target_root_id),
            ("source_occurrence_identity_sha256", attestation.target_occurrence_identity_sha256),
            ("semantic_root_sha256", attestation.semantic_root_sha256),
            ("evidence_members", attestation.evidence_members),
            ("attested_evidence_members", attested_members),
            ("attested_evidence_anchors", attested_anchors),
        )
        for name, value in values:
            object.__setattr__(binding, name, value)
        bindings.append(binding)
    if not bindings:
        _fail("executable plan must contain at least one provenance-bound root")
    if consumed_receipts != {item.canonical_bytes for item in receipts}:
        _fail("exact-reuse provenance receipt set contains an unused receipt")
    return tuple(
        sorted(
            bindings, key=lambda item: (item.target_root_id, item.target_occurrence_identity_sha256)
        )
    )


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedExactReuseProvenance:
    """Signed non-circular audit preimage for one EXACT_REUSE root."""

    authority: ActivatedValidatorAuthority
    canonical_bytes: bytes
    source_package_ref_id: str
    source_validation_receipt_sha256: str
    source_bundle_sha256: str
    source_root_id: str
    source_occurrence_identity_sha256: str
    inherited_semantic_root_sha256: str
    target_root_id: str
    target_occurrence_identity_sha256: str
    byte_identity_proof_id: str
    byte_identity_proof: ByteIdentityProof
    ledger_decision: LedgerDecision
    ledger_decision_completion_sha256: str
    root_plan_sha256: str

    def __init__(self) -> None:
        _fail("exact-reuse provenance requires signature verification")


def exact_reuse_provenance_signing_bytes(payload: dict[str, object]) -> bytes:
    return (
        b"phase4-v2:signed-exact-reuse-provenance\0"
        + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )


def exact_reuse_provenance_payload(
    *,
    authority: ActivatedValidatorAuthority,
    source: AuthenticatedSourceReport,
    source_root: AttestedRootEvidence,
    target_root_id: str,
    target_occurrence_identity_sha256: str,
    byte_identity_proof_id: str,
    byte_identity_proof: ByteIdentityProof,
    ledger_decision: LedgerDecision,
    ledger_decision_completion_sha256: str,
    root_plan_sha256: str,
    signature: str,
) -> bytes:
    """Render the canonical externally signed exact-reuse audit preimage."""

    envelope = validate_authenticated_validator_envelope(source.envelope)
    if envelope.authority != authority or source_root not in source.report.validated_root_evidence:
        _fail("exact-reuse source is not authenticated by the signing authority")
    if (
        type(byte_identity_proof) is not ByteIdentityProof
        or type(ledger_decision) is not LedgerDecision
        or byte_identity_proof.content_id != byte_identity_proof_id
        or ledger_decision.byte_identity_proof_id != byte_identity_proof_id
        or ledger_decision.content_id != ledger_decision_completion_sha256
        or ledger_decision.target_root_id != target_root_id
        or ledger_decision.source_root_id != source_root.target_root_id
        or ledger_decision.source_audit_receipt_sha256 != source.report.validation_receipt_sha256
        or {byte_identity_proof.left_root_id, byte_identity_proof.right_root_id}
        != {target_root_id, source_root.target_root_id}
    ):
        _fail("exact-reuse proof and ledger decision do not close the signed audit")
    values = {
        "authority_sha256": authority.activation_sha256,
        "byte_identity_proof_id": byte_identity_proof_id,
        "byte_identity_proof": byte_identity_proof.to_data(),
        "inherited_semantic_root_sha256": source_root.semantic_root_sha256,
        "ledger_decision_completion_sha256": ledger_decision_completion_sha256,
        "ledger_decision": ledger_decision.to_data(),
        "root_plan_sha256": root_plan_sha256,
        "schema": EXACT_REUSE_PROVENANCE_SCHEMA,
        "source_bundle_sha256": source.report.bundle_sha256,
        "source_occurrence_identity_sha256": source_root.target_occurrence_identity_sha256,
        "source_package_ref_id": source.package_ref.content_id,
        "source_root_id": source_root.target_root_id,
        "source_validation_receipt_sha256": source.report.validation_receipt_sha256,
        "target_occurrence_identity_sha256": target_occurrence_identity_sha256,
        "target_root_id": target_root_id,
    }
    for name, value in values.items():
        if name not in {"schema", "byte_identity_proof", "ledger_decision"} and (
            type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
        ):
            _fail(f"{name} must be an exact digest")
    if re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("exact-reuse provenance signature is invalid")
    return json.dumps(
        {"payload": values, "signature": signature}, sort_keys=True, separators=(",", ":")
    ).encode()


def load_authenticated_exact_reuse_provenance(
    canonical_bytes: bytes,
    *,
    authority: ActivatedValidatorAuthority,
    registry: AuthenticatedSourceReportRegistry,
) -> AuthenticatedExactReuseProvenance:
    """Verify a signed audit preimage against its independently signed source report."""

    return _load_authenticated_exact_reuse_provenance(
        canonical_bytes,
        authority=authority,
        registry=registry,
        reauthenticate_registry=True,
    )


def _load_authenticated_exact_reuse_provenance(
    canonical_bytes: bytes,
    *,
    authority: ActivatedValidatorAuthority,
    registry: AuthenticatedSourceReportRegistry,
    reauthenticate_registry: bool,
) -> AuthenticatedExactReuseProvenance:
    if (
        type(canonical_bytes) is not bytes
        or not canonical_bytes
        or len(canonical_bytes) > _MAX_EXACT_REUSE_RECEIPT_BYTES
    ):
        _fail("exact-reuse provenance must be bounded exact bytes")

    try:
        document = json.loads(canonical_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceAuthenticationError("exact-reuse provenance is invalid JSON") from error
    if json.dumps(document, sort_keys=True, separators=(",", ":")).encode() != canonical_bytes:
        _fail("exact-reuse provenance is not canonical")
    if type(document) is not dict or set(document) != {"payload", "signature"}:
        _fail("exact-reuse provenance has unexpected fields")
    payload, signature = document["payload"], document["signature"]
    expected = set(AuthenticatedExactReuseProvenance.__dataclass_fields__) - {
        "authority",
        "canonical_bytes",
    }
    expected |= {"authority_sha256", "schema"}
    if (
        type(payload) is not dict
        or set(payload) != expected
        or payload["schema"] != EXACT_REUSE_PROVENANCE_SCHEMA
    ):
        _fail("exact-reuse provenance payload has unexpected fields")
    if payload["authority_sha256"] != authority.activation_sha256 or type(signature) is not str:
        _fail("exact-reuse provenance authority is invalid")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), exact_reuse_provenance_signing_bytes(payload)
        )
    except (InvalidSignature, ValueError) as error:
        raise ProvenanceAuthenticationError(
            "exact-reuse provenance signature is invalid"
        ) from error
    if reauthenticate_registry:
        registry = build_authenticated_source_report_registry(
            (item.package_ref, item.envelope) for item in registry.entries
        )
    sources = [
        item
        for item in registry.entries
        if item.package_ref.content_id == payload["source_package_ref_id"]
    ]
    if len(sources) != 1:
        _fail("exact-reuse provenance source package is absent from the registry")
    source = sources[0]
    if source.envelope.authority != authority:
        _fail("exact-reuse signing authority differs from the source validator authority")
    roots = [
        item
        for item in source.report.validated_root_evidence
        if item.target_root_id == payload["source_root_id"]
        and item.target_occurrence_identity_sha256 == payload["source_occurrence_identity_sha256"]
        and item.semantic_root_sha256 == payload["inherited_semantic_root_sha256"]
    ]
    if (
        len(roots) != 1
        or source.report.validation_receipt_sha256 != payload["source_validation_receipt_sha256"]
        or source.report.bundle_sha256 != payload["source_bundle_sha256"]
    ):
        _fail("exact-reuse provenance differs from its authenticated source report")
    try:
        proof_data = payload["byte_identity_proof"]
        decision_data = payload["ledger_decision"]
        if type(proof_data) is not dict or type(decision_data) is not dict:
            raise TypeError
        proof = ByteIdentityProof(**proof_data)
        decision_values = dict(decision_data)
        decision_values["route"] = Route(decision_values["route"])
        decision_values["local_only_domains"] = tuple(decision_values["local_only_domains"])
        decision_values["pins"] = RoutingPins(**decision_values["pins"])
        decision = LedgerDecision(**decision_values)
    except (TypeError, ValueError, KeyError) as error:
        raise ProvenanceAuthenticationError("exact-reuse typed proof is invalid") from error
    if (
        proof.content_id != payload["byte_identity_proof_id"]
        or decision.byte_identity_proof_id != proof.content_id
        or decision.content_id != payload["ledger_decision_completion_sha256"]
        or decision.target_root_id != payload["target_root_id"]
        or decision.source_root_id != payload["source_root_id"]
        or decision.source_audit_receipt_sha256 != payload["source_validation_receipt_sha256"]
        or {proof.left_root_id, proof.right_root_id}
        != {payload["target_root_id"], payload["source_root_id"]}
    ):
        _fail("exact-reuse typed proof and decision do not reproduce")
    result = object.__new__(AuthenticatedExactReuseProvenance)
    object.__setattr__(result, "authority", authority)
    object.__setattr__(result, "canonical_bytes", canonical_bytes)
    for name in AuthenticatedExactReuseProvenance.__dataclass_fields__:
        if name not in {"authority", "canonical_bytes"}:
            object.__setattr__(
                result,
                name,
                proof
                if name == "byte_identity_proof"
                else decision
                if name == "ledger_decision"
                else payload[name],
            )
    return result


def validate_authenticated_exact_reuse_provenance(
    value: AuthenticatedExactReuseProvenance,
    registry: AuthenticatedSourceReportRegistry,
) -> AuthenticatedExactReuseProvenance:
    if type(value) is not AuthenticatedExactReuseProvenance:
        _fail("exact authenticated exact-reuse provenance is required")
    restored = load_authenticated_exact_reuse_provenance(
        value.canonical_bytes, authority=value.authority, registry=registry
    )
    if restored != value:
        _fail("exact-reuse provenance changed after authentication")
    return restored
