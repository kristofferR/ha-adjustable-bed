"""Adversarial coverage for signed EXACT_REUSE prerequisite publication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.equivalence.core as equivalence_core_module
import tools.phase4_v2.equivalence.inventory as inventory_module
import tools.phase4_v2.equivalence.prerequisite as prerequisite_module
import tools.phase4_v2.preflight.registry as preparation_registry_module
import tools.phase4_v2.raw_source as raw_source_module
from tests.phase4_v2_orchestration_testing import (
    IncompleteSyntheticPackage,
    SyntheticTrust,
    build_synthetic_package_inputs,
    protected_fixture_trust,
)
from tools.phase4_v2.equivalence import (
    EQUIVALENCE_SCHEMA_REVISION,
    EXACT_REUSE_DIRECT_AUDIT_QUEUE_KIND,
    EXACT_REUSE_LEDGER_DECISION_QUEUE_KIND,
    EXACT_REUSE_PIPELINE_CAPABILITY,
    EXACT_REUSE_SEMANTIC_ROOT_QUEUE_KIND,
    ActivatedExactReuseAuthority,
    ApplicationRoot,
    AuthenticatedExactReusePrerequisite,
    AuthenticatedSourceReport,
    AuthenticatedTargetInventoryEnvelope,
    CapabilityPin,
    ExactReuseAuthenticationError,
    ExtractorCapability,
    RoutingPins,
    TargetRootInventory,
    TargetRootOccurrence,
    build_authenticated_source_report_registry,
    exact_reuse_authority_capability,
    exact_reuse_authority_payload,
    exact_reuse_authority_pin_payload,
    exact_reuse_prerequisite_capabilities,
    exact_reuse_prerequisite_completions,
    exact_reuse_prerequisite_dependencies,
    exact_reuse_prerequisite_envelope_payload,
    exact_reuse_prerequisite_payload,
    exact_reuse_prerequisite_signing_bytes,
    finish_exact_reuse_prerequisite,
    finish_package_validation_receipt,
    finish_target_inventory,
    inventory_authority_capability,
    inventory_extractor_capability,
    load_activated_exact_reuse_authority,
    load_authenticated_exact_reuse_prerequisite,
    load_authenticated_target_inventory_envelope,
    materialize_exact_reuse_prerequisites,
    materialize_package_validation_receipt,
    materialize_target_inventory,
    route_application_root,
    semantic_root_audit_from_authenticated_prerequisite,
    target_inventory_envelope_payload,
    target_inventory_signing_bytes,
)
from tools.phase4_v2.queue import (
    CapabilityPin as QueueCapabilityPin,
)
from tools.phase4_v2.queue import (
    CompletionDependencyPin,
    Queue,
    QueueConflictError,
    TerminalOutcome,
)
from tools.phase4_v2.raw_source import (
    AuthenticatedRawSourceCollection,
    RawSourceAnchor,
    RawSourceMember,
    authenticate_raw_source_collection,
    raw_source_authority_payload,
    raw_source_collection_payload,
    raw_source_envelope_payload,
    raw_source_signing_bytes,
)

_HEX = tuple(character * 64 for character in "123456789abcdef")


@dataclass(frozen=True, slots=True)
class ExactReuseFixture:
    receipt: AuthenticatedExactReusePrerequisite
    source: AuthenticatedSourceReport
    source_package: IncompleteSyntheticPackage
    source_inventory: AuthenticatedTargetInventoryEnvelope
    target_inventory: AuthenticatedTargetInventoryEnvelope
    raw_source: AuthenticatedRawSourceCollection
    trust: SyntheticTrust
    exact_key: Ed25519PrivateKey
    exact_authority: ActivatedExactReuseAuthority
    exact_activation: str


def _public_key(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _inventory(
    package: IncompleteSyntheticPackage,
    root: ApplicationRoot,
    extractor: ExtractorCapability,
    trust: SyntheticTrust,
) -> AuthenticatedTargetInventoryEnvelope:
    inventory = TargetRootInventory(
        package.package_ref.content_id,
        (TargetRootOccurrence(root.content_id, root.occurrence_identity_sha256),),
    )
    unsigned = target_inventory_envelope_payload(
        package_ref=package.package_ref,
        inventory=inventory,
        extractor=extractor,
        authority=trust.inventory_authority,
        signature="0" * 128,
    )
    payload = json.loads(unsigned)["payload"]
    canonical = target_inventory_envelope_payload(
        package_ref=package.package_ref,
        inventory=inventory,
        extractor=extractor,
        authority=trust.inventory_authority,
        signature=trust.inventory_key.sign(target_inventory_signing_bytes(payload)).hex(),
    )
    return load_authenticated_target_inventory_envelope(
        canonical,
        authority=trust.inventory_authority,
        package_ref=package.package_ref,
    )


def _build_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ExactReuseFixture:
    with protected_fixture_trust(tmp_path / "trust") as trust:
        source_package = build_synthetic_package_inputs(
            tmp_path / "packages", cluster_id="exact-reuse", package_index=1, trust=trust
        )
        target_package = build_synthetic_package_inputs(
            tmp_path / "packages", cluster_id="exact-reuse", package_index=2, trust=trust
        )
        extractor = ExtractorCapability("exact-test-extractor", _HEX[0], _HEX[1], "extractor-v1")
        source_root = ApplicationRoot(
            source_package.package_ref.content_id,
            "DEX",
            extractor.content_id,
            _HEX[2],
            _HEX[3],
            _HEX[4],
            _HEX[5],
            True,
            True,
        )
        target_root = replace(
            source_root,
            package_ref_id=target_package.package_ref.content_id,
            occurrence_identity_sha256=_HEX[6],
        )
        source_inventory = _inventory(source_package, source_root, extractor, trust)
        target_inventory = _inventory(target_package, target_root, extractor, trust)

        raw_key = Ed25519PrivateKey.from_private_bytes(b"r" * 32)
        raw_authority_bytes = raw_source_authority_payload(
            authority_id="raw-source-test", generation=1, public_key=_public_key(raw_key)
        )
        monkeypatch.setattr(
            raw_source_module, "_bounded_file", lambda _path, _maximum: raw_authority_bytes
        )
        output = source_package.preparation_receipt.invocations[0].outputs[0]
        members = (RawSourceMember("member", 0, output.path, output.sha256, output.bytes),)
        anchors = (
            RawSourceAnchor(
                "anchor",
                "member",
                0,
                1,
                b"x",
                "utf8",
                "x",
                hashlib.sha256(b'"x"').hexdigest(),
                "/protocol/value",
            ),
        )
        raw_payload = raw_source_collection_payload(
            package_ref=source_package.package_ref,
            root=source_root,
            preparation_receipt=source_package.preparation_receipt,
            preparation_authority=source_package.preparation_authority,
            target_inventory=source_inventory,
            members=members,
            anchors=anchors,
        )
        raw_envelope = raw_source_envelope_payload(
            raw_payload, raw_key.sign(raw_source_signing_bytes(raw_payload)).hex()
        )
        raw_source = authenticate_raw_source_collection(
            raw_envelope,
            package_ref=source_package.package_ref,
            root=source_root,
            preparation_receipt=source_package.preparation_receipt,
            preparation_authority=source_package.preparation_authority,
            target_inventory=source_inventory,
        )
        source = build_authenticated_source_report_registry(
            ((source_package.package_ref, source_package.source_envelope),)
        ).entries[0]
        decision, proof = route_application_root(
            target_root,
            (source_root,),
            pins=RoutingPins(),
            trusted_direct_audits={source_root.content_id: raw_source.receipt_sha256},
            trusted_inventory_receipts={
                source_root.content_id: source_inventory.receipt_sha256,
                target_root.content_id: target_inventory.receipt_sha256,
            },
        )
        assert proof is not None
        pipeline = CapabilityPin(
            EXACT_REUSE_PIPELINE_CAPABILITY, EQUIVALENCE_SCHEMA_REVISION, _HEX[7]
        )
        exact_key = Ed25519PrivateKey.from_private_bytes(b"q" * 32)
        authority_bytes = exact_reuse_authority_payload(
            authority_id="exact-reuse-test", public_key=_public_key(exact_key), generation=1
        )
        exact_activation = json.loads(exact_reuse_authority_pin_payload(authority_bytes))[
            "activation_sha256"
        ]
        monkeypatch.setattr(
            prerequisite_module,
            "_read_protected_exact_reuse_authority_pin",
            lambda: exact_activation,
        )
        authority = load_activated_exact_reuse_authority(authority_bytes)
        kwargs = {
            "source": source,
            "source_raw": raw_source,
            "source_inventory": source_inventory,
            "source_preparation_receipt": source_package.preparation_receipt,
            "source_preparation_authority": source_package.preparation_authority,
            "source_root": source_root,
            "target_inventory": target_inventory,
            "target_root": target_root,
            "extractor": extractor,
            "proof": proof,
            "decision": decision,
            "equivalence_pipeline": pipeline,
            "authority": authority,
        }
        payload = exact_reuse_prerequisite_payload(**kwargs)
        canonical = exact_reuse_prerequisite_envelope_payload(
            payload, signature=exact_key.sign(exact_reuse_prerequisite_signing_bytes(payload)).hex()
        )
        receipt = load_authenticated_exact_reuse_prerequisite(canonical, **kwargs)
        fixture = ExactReuseFixture(
            receipt,
            source,
            source_package,
            source_inventory,
            target_inventory,
            raw_source,
            trust,
            exact_key,
            authority,
            exact_activation,
        )
    monkeypatch.setattr(
        equivalence_core_module,
        "_read_protected_validator_pin",
        lambda: trust.validator_authority.activation_sha256,
    )
    monkeypatch.setattr(
        inventory_module,
        "_read_protected_inventory_pin",
        lambda: trust.inventory_authority.activation_sha256,
    )
    monkeypatch.setattr(
        preparation_registry_module,
        "_read_protected_activation_digest",
        lambda: trust.preparation_authority.activation_sha256,
    )
    return fixture


def _queue(tmp_path: Path) -> Queue:
    queue = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    queue.initialize()
    return queue


def _activate(queue: Queue, fixture: ExactReuseFixture) -> None:
    pins = (
        inventory_authority_capability(fixture.target_inventory.authority),
        inventory_extractor_capability(fixture.target_inventory.extractor),
        exact_reuse_authority_capability(fixture.exact_authority),
        fixture.receipt.equivalence_pipeline,
    )
    for pin in pins:
        queue.register_capability(pin.name, pin.revision, pin.digest)
        queue.activate_capability_from_absent(pin.name, pin.revision, pin.digest)


def _publish_dependencies(queue: Queue, fixture: ExactReuseFixture) -> None:
    materialize_package_validation_receipt(queue, fixture.source.envelope)
    lease = queue.claim("source-validator", allowed_kinds=("trusted-package-validation-receipt",))
    assert lease is not None
    finish_package_validation_receipt(queue, lease, envelope=fixture.source.envelope)
    for envelope in (fixture.source_inventory, fixture.target_inventory):
        materialize_target_inventory(queue, envelope)
        lease = queue.claim("inventory", allowed_kinds=("trusted-target-root-inventory",))
        assert lease is not None
        finish_target_inventory(queue, lease, envelope=envelope)


def test_signed_prerequisites_materialize_and_finish_exact_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    queue = _queue(tmp_path)
    _activate(queue, fixture)
    _publish_dependencies(queue, fixture)

    work = materialize_exact_reuse_prerequisites(queue, fixture.receipt)
    assert work.completions == exact_reuse_prerequisite_completions(fixture.receipt)
    assert semantic_root_audit_from_authenticated_prerequisite(fixture.receipt).target_root_id
    for kind, completion in zip(
        (
            EXACT_REUSE_SEMANTIC_ROOT_QUEUE_KIND,
            EXACT_REUSE_LEDGER_DECISION_QUEUE_KIND,
            EXACT_REUSE_DIRECT_AUDIT_QUEUE_KIND,
        ),
        work.completions,
        strict=True,
    ):
        lease = queue.claim("prerequisite", allowed_kinds=(kind,))
        assert lease is not None and lease.unit_id == completion.parent_unit_id
        result = finish_exact_reuse_prerequisite(queue, lease, receipt=fixture.receipt)
        assert result.output_digest == completion.digest


def test_receipt_rejects_transplant_extra_missing_and_forgery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    kwargs = {
        "authority": fixture.exact_authority,
        "source": fixture.source,
        "source_raw": fixture.raw_source,
        "source_inventory": fixture.source_inventory,
        "source_preparation_receipt": fixture.source_package.preparation_receipt,
        "source_preparation_authority": fixture.source_package.preparation_authority,
        "source_root": fixture.receipt.source_root,
        "target_inventory": fixture.target_inventory,
        "target_root": fixture.receipt.target_root,
        "extractor": fixture.receipt.extractor,
        "proof": fixture.receipt.proof,
        "decision": fixture.receipt.decision,
        "equivalence_pipeline": fixture.receipt.equivalence_pipeline,
    }
    document = json.loads(fixture.receipt.canonical_bytes)
    for mutate in (
        lambda payload: payload.__setitem__("extra", _HEX[0]),
        lambda payload: payload.pop("proof"),
        lambda payload: payload.__setitem__("target_package_ref_id", _HEX[0]),
    ):
        changed = json.loads(json.dumps(document))
        mutate(changed["payload"])
        canonical = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
        with pytest.raises(ExactReuseAuthenticationError):
            load_authenticated_exact_reuse_prerequisite(canonical, **kwargs)
    forged = json.loads(json.dumps(document))
    forged["signature"] = "0" * 128
    with pytest.raises(ExactReuseAuthenticationError, match="signature"):
        load_authenticated_exact_reuse_prerequisite(
            json.dumps(forged, sort_keys=True, separators=(",", ":")).encode(), **kwargs
        )


def test_wrong_unit_input_rotation_and_generic_finish_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    queue = _queue(tmp_path)
    _activate(queue, fixture)
    _publish_dependencies(queue, fixture)
    materialize_exact_reuse_prerequisites(queue, fixture.receipt)
    lease = queue.claim("prerequisite", allowed_kinds=(EXACT_REUSE_SEMANTIC_ROOT_QUEUE_KIND,))
    assert lease is not None
    with pytest.raises(QueueConflictError, match="trusted publication adapter"):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest=_HEX[0],
            completion_revision="forged-v1",
        )
    with pytest.raises(QueueConflictError, match="lease is not"):
        finish_exact_reuse_prerequisite(
            queue, replace(lease, unit_id="ordinary:wrong"), receipt=fixture.receipt
        )
    with pytest.raises(QueueConflictError, match="publication does not belong"):
        finish_exact_reuse_prerequisite(
            queue, replace(lease, input_digest=_HEX[0]), receipt=fixture.receipt
        )
    monkeypatch.setattr(
        prerequisite_module,
        "_read_protected_exact_reuse_authority_pin",
        lambda: _HEX[0],
    )
    with pytest.raises(ExactReuseAuthenticationError, match="protected activation"):
        finish_exact_reuse_prerequisite(queue, lease, receipt=fixture.receipt)
    rotated_queue = _queue(tmp_path / "rotated")
    with pytest.raises(ExactReuseAuthenticationError, match="protected activation"):
        materialize_exact_reuse_prerequisites(rotated_queue, fixture.receipt)
    assert rotated_queue.snapshot().units == ()


def test_three_row_materialization_rolls_back_on_partial_existing_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    queue = _queue(tmp_path)
    _activate(queue, fixture)
    _publish_dependencies(queue, fixture)
    first, second, third = exact_reuse_prerequisite_completions(fixture.receipt)
    queue._materialize_authenticated_row(
        second.parent_unit_id,
        authentication=fixture.receipt,
        kind=EXACT_REUSE_LEDGER_DECISION_QUEUE_KIND,
        capability_pins=tuple(
            QueueCapabilityPin(pin.name, pin.revision, pin.digest)
            for pin in exact_reuse_prerequisite_capabilities(fixture.receipt)
        ),
        dependency_pins=tuple(
            CompletionDependencyPin(pin.parent_unit_id, pin.revision, pin.digest)
            for pin in exact_reuse_prerequisite_dependencies(fixture.receipt)
        ),
        input_digest=fixture.receipt.receipt_sha256,
        priority=1,
    )
    with pytest.raises(QueueConflictError, match="changed"):
        materialize_exact_reuse_prerequisites(queue, fixture.receipt)
    with sqlite3.connect(queue.database) as connection:
        rows = connection.execute(
            "SELECT unit_id FROM work_units WHERE unit_id IN (?, ?)",
            (first.parent_unit_id, third.parent_unit_id),
        ).fetchall()
    assert rows == []


def test_authority_rejects_constructor_and_noncanonical_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ExactReuseAuthenticationError):
        ActivatedExactReuseAuthority()
    with pytest.raises(ExactReuseAuthenticationError):
        AuthenticatedExactReusePrerequisite()
    key = Ed25519PrivateKey.from_private_bytes(b"z" * 32)
    payload = exact_reuse_authority_payload(
        authority_id="authority", public_key=_public_key(key), generation=1
    )
    activation = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        prerequisite_module,
        "_read_protected_exact_reuse_authority_pin",
        lambda: activation,
    )
    assert load_activated_exact_reuse_authority(payload).activation_sha256 == activation
