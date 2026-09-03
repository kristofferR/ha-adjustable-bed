from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

import tools.phase4_v2.raw_source as raw_source_module
from tests.phase4_v2_orchestration_testing import (
    IncompleteSyntheticPackage,
    SyntheticTrust,
    build_synthetic_package_inputs,
    protected_fixture_trust,
)
from tools.phase4_v2.equivalence import (
    ApplicationRoot,
    AuthenticatedTargetInventoryEnvelope,
    ByteIdentityProof,
    ExtractorCapability,
    LedgerDecision,
    Route,
    TargetRootInventory,
    TargetRootOccurrence,
    authenticated_validator_envelope_payload,
    build_authenticated_raw_source_report_registry,
    exact_reuse_provenance_payload,
    exact_reuse_provenance_signing_bytes,
    load_authenticated_exact_reuse_provenance,
    load_authenticated_target_inventory_envelope,
    load_authenticated_validator_envelope,
    target_inventory_envelope_payload,
    target_inventory_signing_bytes,
    validator_envelope_signing_bytes,
)
from tools.phase4_v2.ir import final_schema_document
from tools.phase4_v2.raw_source import (
    AuthenticatedRawSourceCollection,
    AuthenticatedRawSourceRegistry,
    RawSourceAnchor,
    RawSourceAuthenticationError,
    RawSourceMember,
    RawSourceReauthenticationInput,
    authenticate_raw_source_collection,
    build_authenticated_raw_source_registry,
    canonical_scalar_sha256,
    raw_source_authority_payload,
    raw_source_collection_payload,
    raw_source_envelope_payload,
    raw_source_signing_bytes,
    reauthenticate_raw_source_registry,
    validate_authenticated_raw_source_collection,
)
from tools.phase4_v2.validator import derive_raw_source_validator_receipt


def _digest(label: str) -> str:
    import hashlib

    return hashlib.sha256(label.encode()).hexdigest()


def _public(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


@dataclass(frozen=True)
class GenesisFixture:
    trust: SyntheticTrust
    package: IncompleteSyntheticPackage
    root: ApplicationRoot
    inventory: AuthenticatedTargetInventoryEnvelope
    key: Ed25519PrivateKey
    authority_payload: bytes
    member: RawSourceMember
    anchor: RawSourceAnchor
    payload: dict[str, object]
    envelope: bytes
    collection: AuthenticatedRawSourceCollection

    @property
    def inputs(self) -> dict[str, object]:
        return {
            "package_ref": self.package.package_ref,
            "root": self.root,
            "preparation_receipt": self.package.preparation_receipt,
            "preparation_authority": self.package.preparation_authority,
            "target_inventory": self.inventory,
        }

    def sign(self, payload: dict[str, object]) -> bytes:
        signature = self.key.sign(raw_source_signing_bytes(payload)).hex()
        return raw_source_envelope_payload(payload, signature)


@pytest.fixture(scope="module")
def genesis(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GenesisFixture]:
    root_path = tmp_path_factory.mktemp("raw-source")
    protected = root_path / "protected"
    protected.mkdir(mode=0o700)
    key = Ed25519PrivateKey.from_private_bytes(b"r" * 32)
    authority_path = protected / "phase4-v2-raw-source-authority.json"
    authority_payload = raw_source_authority_payload(
        authority_id="synthetic-raw-source", generation=1, public_key=_public(key)
    )
    authority_path.write_bytes(authority_payload)
    os.chmod(authority_path, 0o444)
    os.chmod(protected, 0o555)
    with (
        patch.object(
            raw_source_module,
            "_read_protected_raw_source_authority",
            return_value=authority_payload,
        ),
        protected_fixture_trust(root_path / "trust", emit_candidates=False) as trust,
    ):
        package = build_synthetic_package_inputs(
            root_path / "packages", cluster_id="raw-genesis", package_index=1, trust=trust
        )
        extractor = ExtractorCapability(
            "synthetic-raw-extractor",
            trust.tool_sha256,
            _digest("raw-extractor-config"),
            "synthetic-raw-v1",
        )
        occurrence = _digest("raw-occurrence")
        app_root = ApplicationRoot(
            package.package_ref.content_id,
            "android",
            extractor.content_id,
            occurrence,
            _digest("raw-content-root"),
            _digest("raw-inventory"),
            _digest("raw-dependency-root"),
            True,
            True,
        )
        inventory = TargetRootInventory(
            package.package_ref.content_id,
            (TargetRootOccurrence(app_root.content_id, occurrence),),
        )
        unsigned = target_inventory_envelope_payload(
            package_ref=package.package_ref,
            inventory=inventory,
            extractor=extractor,
            authority=trust.inventory_authority,
            signature="0" * 128,
        )
        inventory_payload = json.loads(unsigned)["payload"]
        inventory_envelope = load_authenticated_target_inventory_envelope(
            target_inventory_envelope_payload(
                package_ref=package.package_ref,
                inventory=inventory,
                extractor=extractor,
                authority=trust.inventory_authority,
                signature=trust.inventory_key.sign(
                    target_inventory_signing_bytes(inventory_payload)
                ).hex(),
            ),
            authority=trust.inventory_authority,
            package_ref=package.package_ref,
        )
        invocation_index, output = next(
            (index, output)
            for index, invocation in enumerate(package.preparation_receipt.invocations)
            for output in invocation.outputs
        )
        raw = b"synthetic fixture"
        member = RawSourceMember(
            "decompiled-member",
            invocation_index,
            output.path,
            output.sha256,
            output.bytes,
        )
        anchor = RawSourceAnchor(
            "literal",
            member.id,
            0,
            len(raw),
            raw,
            "utf8",
            "synthetic fixture",
            canonical_scalar_sha256("synthetic fixture"),
            "/protocols/example/value",
        )
        payload = raw_source_collection_payload(
            package_ref=package.package_ref,
            root=app_root,
            preparation_receipt=package.preparation_receipt,
            preparation_authority=package.preparation_authority,
            target_inventory=inventory_envelope,
            members=(member,),
            anchors=(anchor,),
        )
        envelope = raw_source_envelope_payload(
            payload, key.sign(raw_source_signing_bytes(payload)).hex()
        )
        collection = authenticate_raw_source_collection(
            envelope,
            package_ref=package.package_ref,
            root=app_root,
            preparation_receipt=package.preparation_receipt,
            preparation_authority=package.preparation_authority,
            target_inventory=inventory_envelope,
        )
        yield GenesisFixture(
            trust,
            package,
            app_root,
            inventory_envelope,
            key,
            authority_payload,
            member,
            anchor,
            payload,
            envelope,
            collection,
        )


def test_genuine_raw_source_genesis_reauthenticates(genesis: GenesisFixture) -> None:
    restored = validate_authenticated_raw_source_collection(genesis.collection, **genesis.inputs)
    assert restored.receipt_sha256 == genesis.collection.receipt_sha256
    assert restored.semantic_root_sha256 == genesis.payload["semantic_root_sha256"]
    assert restored.anchors[0].decoded_value == "synthetic fixture"


def _raw_registry_inputs(
    genesis: GenesisFixture,
) -> tuple[
    AuthenticatedRawSourceRegistry,
    tuple[RawSourceReauthenticationInput, ...],
]:
    registry = build_authenticated_raw_source_registry(
        (
            (
                genesis.envelope,
                genesis.package.package_ref,
                genesis.root,
                genesis.package.preparation_receipt,
                genesis.package.preparation_authority,
                genesis.inventory,
            ),
        )
    )
    inputs = (
        (
            genesis.package.package_ref,
            genesis.root,
            genesis.package.preparation_receipt,
            genesis.package.preparation_authority,
            genesis.inventory,
        ),
    )
    return registry, inputs


def _enriched_envelope(genesis: GenesisFixture):
    registry, inputs = _raw_registry_inputs(genesis)
    receipt = derive_raw_source_validator_receipt(
        genesis.package.source_envelope,
        raw_source_registry=registry,
        raw_source_inputs=inputs,
    )
    canonical = authenticated_validator_envelope_payload(
        receipt,
        genesis.trust.validator_authority,
        signature=genesis.trust.validator_key.sign(
            validator_envelope_signing_bytes(receipt, genesis.trust.validator_authority)
        ).hex(),
    )
    return load_authenticated_validator_envelope(
        canonical, authority=genesis.trust.validator_authority
    )


def test_signed_enriched_validator_report_closes_raw_genesis(
    genesis: GenesisFixture,
) -> None:
    registry, inputs = _raw_registry_inputs(genesis)
    enriched = _enriched_envelope(genesis)
    source_registry = build_authenticated_raw_source_report_registry(
        ((genesis.package.package_ref, enriched),),
        raw_source_registry=registry,
        raw_source_inputs=inputs,
    )
    source = source_registry.entries[0]
    assert source.report.raw_source_receipt_sha256s == (
        genesis.collection.receipt_sha256,
    )
    assert source.report.validated_root_evidence[0].semantic_root_sha256 == (
        genesis.collection.semantic_root_sha256
    )
    assert source.raw_sources == (genesis.collection,)
    final_schema = final_schema_document()
    Draft202012Validator(
        {
            "$schema": final_schema["$schema"],
            "$ref": "#/$defs/validated_report",
            "$defs": final_schema["$defs"],
        }
    ).validate(source.report.to_data())


def test_v2_exact_reuse_provenance_binds_raw_receipt(genesis: GenesisFixture) -> None:
    registry, inputs = _raw_registry_inputs(genesis)
    enriched = _enriched_envelope(genesis)
    source_registry = build_authenticated_raw_source_report_registry(
        ((genesis.package.package_ref, enriched),),
        raw_source_registry=registry,
        raw_source_inputs=inputs,
    )
    source = source_registry.entries[0]
    source_root = source.report.validated_root_evidence[0]
    target_root_id = _digest("raw-v2-target-root")
    left_root, right_root = sorted((source_root.target_root_id, target_root_id))
    proof = ByteIdentityProof(
        left_root_id=left_root,
        right_root_id=right_root,
        root_kind="DEX",
        extractor_capability_id=_digest("raw-v2-extractor"),
        content_root_sha256=_digest("raw-v2-content"),
        inventory_sha256=_digest("raw-v2-inventory"),
        dependency_root_sha256=_digest("raw-v2-dependencies"),
        inventory_acceptance_sha256=_digest("raw-v2-proof-version"),
    )
    decision = LedgerDecision(
        target_root_id,
        Route.EXACT_REUSE,
        "raw_v2_exact",
        _digest("raw-v2-local"),
        source_root.target_root_id,
        proof.content_id,
        source_root.target_root_id,
        genesis.collection.receipt_sha256,
    )
    kwargs = {
        "authority": genesis.trust.validator_authority,
        "source": source,
        "source_root": source_root,
        "target_root_id": target_root_id,
        "target_occurrence_identity_sha256": _digest("raw-v2-target-occurrence"),
        "byte_identity_proof_id": proof.content_id,
        "byte_identity_proof": proof,
        "ledger_decision": decision,
        "ledger_decision_completion_sha256": decision.content_id,
        "root_plan_sha256": _digest("raw-v2-root-plan"),
    }
    unsigned = exact_reuse_provenance_payload(
        **kwargs, signature="0" * 128  # type: ignore[arg-type]
    )
    payload = json.loads(unsigned)["payload"]
    canonical = exact_reuse_provenance_payload(
        **kwargs,  # type: ignore[arg-type]
        signature=genesis.trust.validator_key.sign(
            exact_reuse_provenance_signing_bytes(payload)
        ).hex(),
    )
    restored = load_authenticated_exact_reuse_provenance(
        canonical,
        authority=genesis.trust.validator_authority,
        registry=source_registry,
    )
    assert restored.source_raw_receipt_sha256 == genesis.collection.receipt_sha256
    assert restored.source_validation_receipt_sha256 == enriched.receipt_sha256
    transplanted = json.loads(canonical)
    transplanted["payload"]["target_root_id"] = _digest("transplanted-target")
    with pytest.raises(ValueError, match="signature"):
        load_authenticated_exact_reuse_provenance(
            json.dumps(transplanted, sort_keys=True, separators=(",", ":")).encode(),
            authority=genesis.trust.validator_authority,
            registry=source_registry,
        )
    forged = json.loads(canonical)
    forged["payload"]["ledger_decision"]["target_root_id"] = _digest(
        "forged-decision-target"
    )
    forged["signature"] = genesis.trust.validator_key.sign(
        exact_reuse_provenance_signing_bytes(forged["payload"])
    ).hex()
    with pytest.raises(ValueError, match="reproduce"):
        load_authenticated_exact_reuse_provenance(
            json.dumps(forged, sort_keys=True, separators=(",", ":")).encode(),
            authority=genesis.trust.validator_authority,
            registry=source_registry,
        )
    unrelated_left, unrelated_right = sorted(
        (_digest("unrelated-a"), _digest("unrelated-b"))
    )
    unrelated_proof = ByteIdentityProof(
        left_root_id=unrelated_left,
        right_root_id=unrelated_right,
        root_kind="DEX",
        extractor_capability_id=_digest("unrelated-extractor"),
        content_root_sha256=_digest("unrelated-content"),
        inventory_sha256=_digest("unrelated-inventory"),
        dependency_root_sha256=_digest("unrelated-dependencies"),
        inventory_acceptance_sha256=_digest("unrelated-proof-version"),
    )
    unrelated_decision = LedgerDecision(
        target_root_id,
        Route.EXACT_REUSE,
        "raw_v2_unrelated",
        _digest("raw-v2-local"),
        source_root.target_root_id,
        unrelated_proof.content_id,
        source_root.target_root_id,
        genesis.collection.receipt_sha256,
    )
    with pytest.raises(ValueError, match="do not close"):
        exact_reuse_provenance_payload(
            authority=genesis.trust.validator_authority,
            source=source,
            source_root=source_root,
            target_root_id=target_root_id,
            target_occurrence_identity_sha256=_digest("raw-v2-target-occurrence"),
            byte_identity_proof_id=unrelated_proof.content_id,
            byte_identity_proof=unrelated_proof,
            ledger_decision=unrelated_decision,
            ledger_decision_completion_sha256=unrelated_decision.content_id,
            root_plan_sha256=_digest("raw-v2-root-plan"),
            signature="0" * 128,
        )


def test_raw_registry_cannot_cross_same_artifact_validator_envelopes(
    genesis: GenesisFixture,
) -> None:
    registry, inputs = _raw_registry_inputs(genesis)
    enriched = _enriched_envelope(genesis)
    with pytest.raises(ValueError, match="exactly cover this package"):
        derive_raw_source_validator_receipt(
            enriched,
            raw_source_registry=registry,
            raw_source_inputs=inputs,
        )


def test_raw_registry_enforces_aggregate_anchor_limit(
    genesis: GenesisFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(raw_source_module, "_MAX_REGISTRY_ANCHORS", 1)
    entry = (
        genesis.envelope,
        genesis.package.package_ref,
        genesis.root,
        genesis.package.preparation_receipt,
        genesis.package.preparation_authority,
        genesis.inventory,
    )
    with pytest.raises(RawSourceAuthenticationError, match="aggregate anchor"):
        build_authenticated_raw_source_registry((entry, entry))


def test_raw_registry_reauthentication_bounds_inputs(
    genesis: GenesisFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, inputs = _raw_registry_inputs(genesis)
    monkeypatch.setattr(raw_source_module, "_MAX_REGISTRY_COLLECTIONS", 1)
    with pytest.raises(RawSourceAuthenticationError, match="exact immutable"):
        reauthenticate_raw_source_registry(registry, inputs=inputs * 2)
    with pytest.raises(RawSourceAuthenticationError, match="five-tuples"):
        reauthenticate_raw_source_registry(
            registry,
            inputs=((genesis.package.package_ref,),),  # type: ignore[arg-type]
        )


def test_raw_source_forged_signature_fails(genesis: GenesisFixture) -> None:
    envelope = raw_source_envelope_payload(genesis.payload, "0" * 128)
    with pytest.raises(RawSourceAuthenticationError, match="signature"):
        authenticate_raw_source_collection(envelope, **genesis.inputs)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("package_name", "org.example.transplanted"),
        ("version_code", "999"),
        ("package_ref_id", "1" * 64),
        ("artifact_digest", "2" * 64),
        ("target_root_id", "3" * 64),
        ("occurrence_identity_sha256", "4" * 64),
        ("preparation_receipt_sha256", "5" * 64),
        ("target_inventory_receipt_sha256", "6" * 64),
        ("output_manifest_sha256", "7" * 64),
        ("tool_lineage_sha256", "8" * 64),
        ("semantic_root_sha256", "9" * 64),
        ("upstream_digests", ["a" * 64]),
    ],
)
def test_signed_identity_or_lineage_transplant_fails(
    genesis: GenesisFixture, field: str, replacement: object
) -> None:
    payload = dict(genesis.payload)
    payload[field] = replacement
    with pytest.raises(RawSourceAuthenticationError, match="identity|lineage|semantic"):
        authenticate_raw_source_collection(genesis.sign(payload), **genesis.inputs)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_missing_or_extra_raw_source_field_fails(
    genesis: GenesisFixture, mutation: str
) -> None:
    payload = dict(genesis.payload)
    if mutation == "missing":
        del payload["semantic_root_sha256"]
    else:
        payload["caller_trusted_value"] = "forbidden"
    with pytest.raises(RawSourceAuthenticationError, match="exact expected fields"):
        authenticate_raw_source_collection(genesis.sign(payload), **genesis.inputs)


@pytest.mark.parametrize(
    "mutation",
    [
        {"path": "other.java"},
        {"sha256": "a" * 64},
        {"byte_length": 1},
        {"invocation_index": 999},
    ],
)
def test_signed_member_transplant_fails(
    genesis: GenesisFixture, mutation: dict[str, object]
) -> None:
    payload = dict(genesis.payload)
    member = {**genesis.member.to_data(), **mutation}
    payload["members"] = [member]
    with pytest.raises(RawSourceAuthenticationError, match="member"):
        authenticate_raw_source_collection(genesis.sign(payload), **genesis.inputs)


@pytest.mark.parametrize(
    "mutation",
    [
        {"end_byte": 1},
        {"raw_hex": b"changed".hex()},
        {"representation": "hex"},
        {"decoded_value": "changed"},
        {"value_sha256": "a" * 64},
        {"source_ir_pointer": "not-a-pointer"},
    ],
)
def test_signed_anchor_transplant_fails(
    genesis: GenesisFixture, mutation: dict[str, object]
) -> None:
    payload = dict(genesis.payload)
    anchor = {**genesis.anchor.to_data(), **mutation}
    payload["anchors"] = [anchor]
    with pytest.raises(RawSourceAuthenticationError):
        authenticate_raw_source_collection(genesis.sign(payload), **genesis.inputs)


def test_duplicate_and_extra_raw_sources_fail(genesis: GenesisFixture) -> None:
    with pytest.raises(RawSourceAuthenticationError, match="duplicate"):
        build_authenticated_raw_source_registry(
            (
                (
                    genesis.envelope,
                    genesis.package.package_ref,
                    genesis.root,
                    genesis.package.preparation_receipt,
                    genesis.package.preparation_authority,
                    genesis.inventory,
                ),
            )
            * 2
        )
    registry = build_authenticated_raw_source_registry(
        (
            (
                genesis.envelope,
                genesis.package.package_ref,
                genesis.root,
                genesis.package.preparation_receipt,
                genesis.package.preparation_authority,
                genesis.inventory,
            ),
        )
    )
    with pytest.raises(RawSourceAuthenticationError, match="missing"):
        reauthenticate_raw_source_registry(registry, inputs=())


def test_mutated_authenticated_collection_fails(genesis: GenesisFixture) -> None:
    object.__setattr__(genesis.collection, "semantic_root_sha256", "f" * 64)
    try:
        with pytest.raises(RawSourceAuthenticationError, match="changed"):
            validate_authenticated_raw_source_collection(genesis.collection, **genesis.inputs)
    finally:
        object.__setattr__(
            genesis.collection,
            "semantic_root_sha256",
            genesis.payload["semantic_root_sha256"],
        )


def test_duplicate_json_and_oversize_envelope_fail(genesis: GenesisFixture) -> None:
    duplicate = genesis.envelope.replace(b'"schema":', b'"schema":"duplicate","schema":', 1)
    with pytest.raises(RawSourceAuthenticationError, match="duplicate"):
        authenticate_raw_source_collection(duplicate, **genesis.inputs)
    with pytest.raises(RawSourceAuthenticationError, match="bounded"):
        authenticate_raw_source_collection(
            b"{" + b" " * (64 * 1024**2) + b"}", **genesis.inputs
        )


@pytest.mark.parametrize("duplicate", ["pointer", "range"])
def test_duplicate_anchor_identity_fails(
    genesis: GenesisFixture, duplicate: str
) -> None:
    payload = dict(genesis.payload)
    second = genesis.anchor.to_data()
    second["id"] = "literal-two"
    if duplicate == "pointer":
        second["end_byte"] = 1
        second["raw_hex"] = b"s".hex()
        second["decoded_value"] = "s"
        second["value_sha256"] = canonical_scalar_sha256("s")
    else:
        second["source_ir_pointer"] = "/protocols/example/other"
    payload["anchors"] = [genesis.anchor.to_data(), second]
    with pytest.raises(RawSourceAuthenticationError, match="duplicate"):
        authenticate_raw_source_collection(genesis.sign(payload), **genesis.inputs)


def test_protected_authority_metadata_rotation_during_read_fails(tmp_path: Path) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    authority = protected / "authority.json"
    authority.write_bytes(b"{}\n")
    directory_stat = os.stat(protected)
    file_stat = os.stat(authority)

    def metadata(node: os.stat_result, **changes: int) -> SimpleNamespace:
        fields = {
            "st_dev": node.st_dev,
            "st_ino": node.st_ino,
            "st_size": node.st_size,
            "st_uid": 0,
            "st_gid": 0,
            "st_mode": node.st_mode & ~0o222,
            "st_nlink": 1,
            "st_mtime_ns": node.st_mtime_ns,
            "st_ctime_ns": node.st_ctime_ns,
        }
        fields.update(changes)
        return SimpleNamespace(**fields)

    with (
        patch.object(
            raw_source_module.os,
            "fstat",
            side_effect=(
                metadata(directory_stat),
                metadata(file_stat),
                metadata(file_stat, st_ctime_ns=file_stat.st_ctime_ns + 1),
                metadata(directory_stat),
            ),
        ),
        pytest.raises(RawSourceAuthenticationError, match="changed"),
    ):
        raw_source_module._bounded_file(authority, 4_096)


def test_authority_rotation_and_wrong_authority_fail(genesis: GenesisFixture) -> None:
    replacement = Ed25519PrivateKey.from_private_bytes(b"s" * 32)
    rotated = raw_source_authority_payload(
        authority_id="synthetic-raw-source", generation=2, public_key=_public(replacement)
    )
    with (
        patch.object(
            raw_source_module, "_read_protected_raw_source_authority", return_value=rotated
        ),
        pytest.raises(RawSourceAuthenticationError, match="signature|identity"),
    ):
        authenticate_raw_source_collection(genesis.envelope, **genesis.inputs)
