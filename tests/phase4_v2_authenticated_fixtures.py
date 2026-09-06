"""Test-only factories for production-authenticated Phase 4 identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.phase4_v2.equivalence.core import (
    ExtractorCapability,
    FrozenPackageRef,
    authenticated_validator_envelope_payload,
    frozen_package_ref_from_validator_envelope,
    load_activated_validator_authority,
    load_authenticated_validator_envelope,
    validator_authority_payload,
    validator_authority_pin_payload,
    validator_envelope_signing_bytes,
)
from tools.phase4_v2.equivalence.inventory import (
    accept_target_inventory,
    inventory_authority_payload,
    inventory_authority_pin_payload,
    load_activated_inventory_authority,
    load_authenticated_target_inventory_envelope,
    target_inventory_envelope_payload,
    target_inventory_signing_bytes,
)
from tools.phase4_v2.equivalence.plan import AcceptedTargetRootInventory, TargetRootInventory
from tools.phase4_v2.validator import (
    BOUND_VALIDATION_PROFILE,
    CONTRACT_REVISION,
    VALIDATOR_REVISION,
    ValidationReceipt,
)
from tools.phase4_v2.validator.binding import (
    ArtifactIdentityAttestation,
    EvidenceAnchorAttestation,
    EvidenceMemberAttestation,
)


def authenticated_package_ref(
    *, package_name: str, version_code: str, artifact_digest: str, preflight_sha256: str
) -> tuple[FrozenPackageRef, str]:
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("7" * 64))
    authority_payload = validator_authority_payload(
        authority_id="phase4-test-validator",
        public_key=key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex(),
        validator_revision=VALIDATOR_REVISION,
        contract_revision=CONTRACT_REVISION,
    )
    activation = json.loads(validator_authority_pin_payload(authority_payload))[
        "activation_sha256"
    ]
    initial = ValidationReceipt(
        validator_revision=VALIDATOR_REVISION,
        accepted=True,
        source_unchanged=True,
        bundle_sha256="8" * 64,
        report_manifest_sha256="9" * 64,
        discovered_members=1,
        declared_members=1,
        diagnostics=(),
        dependency_digests=tuple(
            sorted(
                {
                    "corpus": "1" * 64,
                    "evidence_lineage": "2" * 64,
                    "ir": "3" * 64,
                    "preflight": preflight_sha256,
                    "schema": "4" * 64,
                }.items()
            )
        ),
        validation_profile=BOUND_VALIDATION_PROFILE,
        contract_revision=CONTRACT_REVISION,
        validated_artifact_identity=ArtifactIdentityAttestation(
            package_name, version_code, "test", artifact_digest
        ),
        evidence_anchors_checked=1,
        validated_evidence_members=(
            EvidenceMemberAttestation("evidence/source.txt", artifact_digest, "5" * 64),
        ),
        validated_evidence_anchors=(
            EvidenceAnchorAttestation(
                "source",
                artifact_digest,
                "evidence/source.txt",
                "5" * 64,
                0,
                1,
                "/schema_revision",
                "utf8",
                "6" * 64,
            ),
        ),
    )
    receipt = replace(
        initial,
        validation_receipt_sha256=hashlib.sha256(
            json.dumps(
                initial.identity_payload(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest(),
    )
    with patch(
        "tools.phase4_v2.equivalence.core._read_protected_validator_pin",
        return_value=activation,
    ):
        authority = load_activated_validator_authority(authority_payload)
        receipt_payload = receipt.to_json().encode()
        canonical = authenticated_validator_envelope_payload(
            receipt_payload,
            authority,
            signature=key.sign(
                validator_envelope_signing_bytes(receipt_payload, authority)
            ).hex(),
        )
        envelope = load_authenticated_validator_envelope(canonical, authority=authority)
        return frozen_package_ref_from_validator_envelope(envelope), activation


def authenticated_inventory(
    package_ref: FrozenPackageRef,
    inventory: TargetRootInventory,
) -> tuple[AcceptedTargetRootInventory, str]:
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("6" * 64))
    authority_payload = inventory_authority_payload(
        authority_id="phase4-test-inventory",
        public_key=key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex(),
        generation=1,
    )
    activation = json.loads(inventory_authority_pin_payload(authority_payload))[
        "activation_sha256"
    ]
    extractor = ExtractorCapability("test-inventory", "a" * 64, "b" * 64, "test-v1")
    with patch(
        "tools.phase4_v2.equivalence.inventory._read_protected_inventory_pin",
        return_value=activation,
    ):
        authority = load_activated_inventory_authority(authority_payload)
        unsigned = target_inventory_envelope_payload(
            package_ref=package_ref,
            inventory=inventory,
            extractor=extractor,
            authority=authority,
            signature="0" * 128,
        )
        payload = json.loads(unsigned)["payload"]
        canonical = target_inventory_envelope_payload(
            package_ref=package_ref,
            inventory=inventory,
            extractor=extractor,
            authority=authority,
            signature=key.sign(target_inventory_signing_bytes(payload)).hex(),
        )
        envelope = load_authenticated_target_inventory_envelope(
            canonical, authority=authority, package_ref=package_ref
        )
        return accept_target_inventory(envelope), activation
