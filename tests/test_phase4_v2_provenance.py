"""Focused authentication tests for source and exact-reuse provenance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.equivalence.core as core
from tools.phase4_v2.equivalence import (
    ProvenanceAuthenticationError,
    authenticated_validator_envelope_payload,
    build_authenticated_source_report_registry,
    exact_reuse_provenance_payload,
    exact_reuse_provenance_signing_bytes,
    frozen_package_ref_from_validator_envelope,
    load_activated_validator_authority,
    load_authenticated_exact_reuse_provenance,
    load_authenticated_validator_envelope,
    source_report_root_completion,
    validator_authority_payload,
    validator_authority_pin_payload,
    validator_envelope_signing_bytes,
)
from tools.phase4_v2.validator import (
    BOUND_VALIDATION_PROFILE,
    CONTRACT_REVISION,
    VALIDATOR_REVISION,
)
from tools.phase4_v2.validator.binding import (
    ArtifactIdentityAttestation,
    EvidenceAnchorAttestation,
    EvidenceMemberAttestation,
    ValidatedRootEvidenceAttestation,
    ValidatedRootEvidenceMember,
)
from tools.phase4_v2.validator.bundle import ValidationReceipt

SHA = tuple(character * 64 for character in "123456789abcdef")


def _source(monkeypatch: pytest.MonkeyPatch):
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("7" * 64))
    authority_bytes = validator_authority_payload(
        authority_id="provenance-test",
        public_key=key.public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        .hex(),
        validator_revision=VALIDATOR_REVISION,
        contract_revision=CONTRACT_REVISION,
    )
    activation = json.loads(validator_authority_pin_payload(authority_bytes))["activation_sha256"]
    monkeypatch.setattr(core, "_read_protected_validator_pin", lambda: activation)
    authority = load_activated_validator_authority(authority_bytes)
    root = ValidatedRootEvidenceAttestation(
        SHA[6], SHA[7], SHA[8], (ValidatedRootEvidenceMember("evidence/a", SHA[5], ("a",)),)
    )
    initial = ValidationReceipt(
        validator_revision=VALIDATOR_REVISION,
        accepted=True,
        source_unchanged=True,
        bundle_sha256=SHA[0],
        report_manifest_sha256=SHA[1],
        discovered_members=1,
        declared_members=1,
        diagnostics=(),
        dependency_digests=tuple(
            sorted(
                {
                    "corpus": SHA[2],
                    "evidence_lineage": SHA[3],
                    "ir": SHA[4],
                    "preflight": SHA[9],
                    "schema": SHA[10],
                }.items()
            )
        ),
        evidence_anchors_checked=1,
        validation_profile=BOUND_VALIDATION_PROFILE,
        contract_revision=CONTRACT_REVISION,
        validated_artifact_identity=ArtifactIdentityAttestation(
            "org.example.source", "1", "1.0", SHA[11]
        ),
        validated_evidence_members=(EvidenceMemberAttestation("evidence/a", SHA[11], SHA[5]),),
        validated_evidence_anchors=(
            EvidenceAnchorAttestation(
                "a", SHA[11], "evidence/a", SHA[5], 0, 1, "/x", "utf8", SHA[12]
            ),
        ),
        validated_root_evidence=(root,),
    )
    receipt = replace(
        initial,
        validation_receipt_sha256=hashlib.sha256(
            json.dumps(initial.identity_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    receipt_bytes = receipt.to_json().encode()
    envelope_bytes = authenticated_validator_envelope_payload(
        receipt_bytes,
        authority,
        signature=key.sign(validator_envelope_signing_bytes(receipt_bytes, authority)).hex(),
    )
    envelope = load_authenticated_validator_envelope(envelope_bytes, authority=authority)
    package_ref = frozen_package_ref_from_validator_envelope(envelope)
    registry = build_authenticated_source_report_registry(((package_ref, envelope),))
    return key, authority, registry


def test_registry_retains_exact_signed_report_and_root_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _key, _authority, registry = _source(monkeypatch)
    source = registry.entries[0]
    root = source.report.validated_root_evidence[0]
    completion = source_report_root_completion(source, root)
    assert source.source_package.report == source.report
    assert completion.digest == source.report.validation_receipt_sha256


def test_exact_reuse_preimage_is_signed_and_target_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    key, authority, registry = _source(monkeypatch)
    source = registry.entries[0]
    root = source.report.validated_root_evidence[0]
    kwargs = {
        "authority": authority,
        "source": source,
        "source_root": root,
        "target_root_id": SHA[13],
        "target_occurrence_identity_sha256": SHA[14],
        "byte_identity_proof_id": SHA[3],
        "ledger_decision_completion_sha256": SHA[4],
        "root_plan_sha256": SHA[5],
    }
    unsigned = exact_reuse_provenance_payload(**kwargs, signature="0" * 128)  # type: ignore[arg-type]
    payload = json.loads(unsigned)["payload"]
    signed = exact_reuse_provenance_payload(
        **kwargs,  # type: ignore[arg-type]
        signature=key.sign(exact_reuse_provenance_signing_bytes(payload)).hex(),
    )
    authenticated = load_authenticated_exact_reuse_provenance(
        signed, authority=authority, registry=registry
    )
    assert authenticated.source_occurrence_identity_sha256 == root.target_occurrence_identity_sha256
    transplanted = json.loads(signed)
    transplanted["payload"]["target_root_id"] = SHA[2]
    with pytest.raises(ProvenanceAuthenticationError, match="signature"):
        load_authenticated_exact_reuse_provenance(
            json.dumps(transplanted, sort_keys=True, separators=(",", ":")).encode(),
            authority=authority,
            registry=registry,
        )
