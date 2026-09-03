"""Protected, signed authority for pre-plan EXACT_REUSE queue prerequisites."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Never

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.phase4_v2.preflight.registry import (
    ActivatedPreparationAuthority,
    PreparationReceipt,
)
from tools.phase4_v2.raw_source import (
    AuthenticatedRawSourceCollection,
    authenticate_raw_source_collection,
)

from .core import (
    ApplicationRoot,
    ByteIdentityProof,
    ExtractorCapability,
    LedgerDecision,
    Route,
    route_application_root,
)
from .inventory import (
    AuthenticatedTargetInventoryEnvelope,
    accept_target_inventory,
    inventory_authority_capability,
    inventory_extractor_capability,
    validate_target_inventory_envelope,
)
from .plan import (
    EQUIVALENCE_SCHEMA_REVISION,
    EXACT_REUSE_PIPELINE_CAPABILITY,
    LEDGER_DECISION_REVISION,
    SEMANTIC_ROOT_COMPLETION_REVISION,
    CapabilityPin,
    CompletionPin,
    SemanticRootAudit,
    build_semantic_root_audit,
    build_semantic_root_completion,
    package_validation_receipt_completion,
)
from .provenance import (
    AuthenticatedSourceReport,
    build_authenticated_source_report_registry,
)

EXACT_REUSE_AUTHORITY_SCHEMA = "phase4-v2-exact-reuse-authority-v1"
EXACT_REUSE_AUTHORITY_PIN_SCHEMA = "phase4-v2-exact-reuse-authority-pin-v1"
EXACT_REUSE_PREREQUISITE_SCHEMA = "phase4-v2-authenticated-exact-reuse-prerequisite-v1"
EXACT_REUSE_AUTHORITY_CAPABILITY = "phase4-v2-exact-reuse-authority"
EXACT_REUSE_SEMANTIC_ROOT_QUEUE_KIND = "trusted-exact-reuse-semantic-root"
EXACT_REUSE_LEDGER_DECISION_QUEUE_KIND = "trusted-exact-reuse-ledger-decision"
EXACT_REUSE_DIRECT_AUDIT_QUEUE_KIND = "trusted-exact-reuse-direct-audit"
EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX = "exact-reuse-semantic-root"
EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX = "exact-reuse-ledger-decision"
EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX = "exact-reuse-direct-audit"
_PIN_PATH = Path("/etc/ha-adjustable-bed/phase4-v2-exact-reuse-authority.pin.json")
_MAX_AUTHORITY_BYTES = 64 * 1024
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ExactReuseAuthenticationError(ValueError):
    """An EXACT_REUSE prerequisite failed closed."""


def _fail(message: str) -> Never:
    raise ExactReuseAuthenticationError(message)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise ExactReuseAuthenticationError("exact-reuse document is not canonical JSON") from error


def _sha(value: object, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail(f"{label} must be a lowercase SHA-256 digest")
    return value


def _bounded_json(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    seen = 0
    while pending:
        item, depth = pending.pop()
        seen += 1
        if seen > _MAX_JSON_NODES:
            _fail("exact-reuse document exceeds its node limit")
        if depth > _MAX_JSON_DEPTH:
            _fail("exact-reuse document exceeds its depth limit")
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)


def _load_canonical_document(payload: bytes, *, maximum: int, label: str) -> object:
    if type(payload) is not bytes or len(payload) > maximum:
        _fail(f"{label} must be bounded exact bytes")
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise ExactReuseAuthenticationError(f"{label} is invalid") from error
    _bounded_json(value)
    if _canonical(value) != payload:
        _fail(f"{label} is not canonical")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("exact-reuse document contains a duplicate key")
        result[key] = value
    return result


def _stat_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


@dataclass(frozen=True, slots=True, init=False)
class ActivatedExactReuseAuthority:
    authority_id: str
    public_key: str
    generation: int
    canonical_bytes: bytes
    activation_sha256: str

    def __init__(self) -> None:
        _fail("exact-reuse authorities require protected activation")


def exact_reuse_authority_payload(
    *, authority_id: str, public_key: str, generation: int
) -> bytes:
    return _canonical(
        {
            "authority_id": authority_id,
            "generation": generation,
            "public_key": public_key,
            "schema": EXACT_REUSE_AUTHORITY_SCHEMA,
        }
    ) + b"\n"


def exact_reuse_authority_pin_payload(authority_payload: bytes) -> bytes:
    return _canonical(
        {
            "activation_sha256": hashlib.sha256(authority_payload).hexdigest(),
            "schema": EXACT_REUSE_AUTHORITY_PIN_SCHEMA,
        }
    ) + b"\n"


def _read_protected_exact_reuse_authority_pin() -> str:
    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        directory_fd = os.open(
            _PIN_PATH.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        directory_before = os.fstat(directory_fd)
        if (
            directory_before.st_uid != 0
            or directory_before.st_mode & 0o022
            or not stat.S_ISDIR(directory_before.st_mode)
        ):
            _fail("exact-reuse authority directory is not root protected")
        file_fd = os.open(
            _PIN_PATH.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
        file_before = os.fstat(file_fd)
        if (
            file_before.st_uid != 0
            or file_before.st_mode & 0o022
            or file_before.st_nlink != 1
            or not stat.S_ISREG(file_before.st_mode)
            or file_before.st_size > _MAX_AUTHORITY_BYTES
        ):
            _fail("exact-reuse authority pin is not root protected")
        chunks: list[bytes] = []
        remaining = _MAX_AUTHORITY_BYTES + 1
        while remaining:
            chunk = os.read(file_fd, min(remaining, 16 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        file_after = os.fstat(file_fd)
        directory_after = os.fstat(directory_fd)
        if (
            _stat_identity(file_before) != _stat_identity(file_after)
            or _stat_identity(directory_before) != _stat_identity(directory_after)
        ):
            _fail("exact-reuse authority pin changed while reading")
        payload = b"".join(chunks)
    except OSError as error:
        raise ExactReuseAuthenticationError(
            "protected exact-reuse authority pin is unavailable"
        ) from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)
    if len(payload) > _MAX_AUTHORITY_BYTES:
        _fail("exact-reuse authority pin exceeds its size limit")
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        _fail("exact-reuse authority pin must have one canonical newline")
    raw = _load_canonical_document(
        payload[:-1], maximum=_MAX_AUTHORITY_BYTES, label="authority pin"
    )
    if type(raw) is not dict or set(raw) != {"activation_sha256", "schema"}:
        _fail("exact-reuse authority pin has an unexpected field set")
    if raw["schema"] != EXACT_REUSE_AUTHORITY_PIN_SCHEMA:
        _fail("exact-reuse authority pin schema is unsupported")
    return _sha(raw["activation_sha256"], "exact-reuse activation")


def load_activated_exact_reuse_authority(payload: bytes) -> ActivatedExactReuseAuthority:
    if type(payload) is not bytes or not payload.endswith(b"\n"):
        _fail("exact-reuse authority must be canonical newline JSON")
    raw = _load_canonical_document(
        payload[:-1], maximum=_MAX_AUTHORITY_BYTES, label="exact-reuse authority"
    )
    if type(raw) is not dict or set(raw) != {"authority_id", "generation", "public_key", "schema"}:
        _fail("exact-reuse authority has an unexpected field set")
    activation = hashlib.sha256(payload).hexdigest()
    if activation != _read_protected_exact_reuse_authority_pin():
        _fail("exact-reuse authority differs from protected activation")
    if raw["schema"] != EXACT_REUSE_AUTHORITY_SCHEMA:
        _fail("exact-reuse authority schema is unsupported")
    authority_id, public_key, generation = raw["authority_id"], raw["public_key"], raw["generation"]
    if type(authority_id) is not str or not authority_id or len(authority_id) > 200:
        _fail("exact-reuse authority ID is invalid")
    if type(public_key) is not str or re.fullmatch(r"[0-9a-f]{64}", public_key) is None:
        _fail("exact-reuse authority public key is invalid")
    if type(generation) is not int or generation < 1:
        _fail("exact-reuse authority generation is invalid")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
    result = object.__new__(ActivatedExactReuseAuthority)
    for name, value in (
        ("authority_id", authority_id),
        ("public_key", public_key),
        ("generation", generation),
        ("canonical_bytes", payload),
        ("activation_sha256", activation),
    ):
        object.__setattr__(result, name, value)
    return result


def _reauthorize(authority: ActivatedExactReuseAuthority) -> ActivatedExactReuseAuthority:
    if type(authority) is not ActivatedExactReuseAuthority:
        _fail("exact activated exact-reuse authority is required")
    restored = load_activated_exact_reuse_authority(authority.canonical_bytes)
    if restored != authority:
        _fail("exact-reuse authority changed after activation")
    return restored


def exact_reuse_authority_capability(authority: object) -> CapabilityPin:
    if type(authority) is not ActivatedExactReuseAuthority:
        _fail("exact activated exact-reuse authority is required")
    authority = _reauthorize(authority)
    return CapabilityPin(
        EXACT_REUSE_AUTHORITY_CAPABILITY,
        f"{EXACT_REUSE_AUTHORITY_SCHEMA}:generation:{authority.generation}",
        authority.activation_sha256,
    )


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedExactReusePrerequisite:
    authority: ActivatedExactReuseAuthority
    source: AuthenticatedSourceReport
    source_raw: AuthenticatedRawSourceCollection
    source_inventory: AuthenticatedTargetInventoryEnvelope
    source_preparation_receipt: PreparationReceipt
    source_preparation_authority: ActivatedPreparationAuthority
    source_root: ApplicationRoot
    target_inventory: AuthenticatedTargetInventoryEnvelope
    target_root: ApplicationRoot
    extractor: ExtractorCapability
    proof: ByteIdentityProof
    decision: LedgerDecision
    equivalence_pipeline: CapabilityPin
    inherited_semantic_root_sha256: str
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        _fail("exact-reuse prerequisites require signature verification")


def _authenticated_source(source: AuthenticatedSourceReport) -> AuthenticatedSourceReport:
    if type(source) is not AuthenticatedSourceReport:
        _fail("exact authenticated source report is required")
    registry = build_authenticated_source_report_registry(((source.package_ref, source.envelope),))
    restored = registry.entries[0]
    if restored != source:
        _fail("source report changed after authentication")
    return restored


def _validate_inputs(
    *,
    source: AuthenticatedSourceReport,
    source_raw: AuthenticatedRawSourceCollection,
    source_inventory: AuthenticatedTargetInventoryEnvelope,
    source_preparation_receipt: PreparationReceipt,
    source_preparation_authority: ActivatedPreparationAuthority,
    source_root: ApplicationRoot,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    target_root: ApplicationRoot,
    extractor: ExtractorCapability,
    proof: ByteIdentityProof,
    decision: LedgerDecision,
    equivalence_pipeline: CapabilityPin,
) -> str:
    source = _authenticated_source(source)
    source_inventory = validate_target_inventory_envelope(source_inventory)
    target_inventory = validate_target_inventory_envelope(target_inventory)
    if type(source_root) is not ApplicationRoot or type(target_root) is not ApplicationRoot:
        _fail("exact ApplicationRoot records are required")
    if type(extractor) is not ExtractorCapability or type(proof) is not ByteIdentityProof:
        _fail("exact extractor and ByteIdentityProof records are required")
    if type(decision) is not LedgerDecision or type(equivalence_pipeline) is not CapabilityPin:
        _fail("exact LedgerDecision and equivalence CapabilityPin records are required")
    source_root.__post_init__()
    target_root.__post_init__()
    extractor.__post_init__()
    proof.__post_init__()
    decision.__post_init__()
    equivalence_pipeline.__post_init__()
    if source_root.package_ref_id != source.package_ref.content_id:
        _fail("source root belongs to another authenticated package")
    if type(source_raw) is not AuthenticatedRawSourceCollection:
        _fail("exact authenticated raw-source collection is required")
    restored_raw = authenticate_raw_source_collection(
        source_raw.canonical_bytes,
        package_ref=source.package_ref,
        root=source_root,
        preparation_receipt=source_preparation_receipt,
        preparation_authority=source_preparation_authority,
        target_inventory=source_inventory,
    )
    if restored_raw != source_raw:
        _fail("raw-source collection changed after authentication")
    if (
        source_raw.package_ref_id != source.package_ref.content_id
        or source_raw.target_root_id != source_root.content_id
        or source_raw.occurrence_identity_sha256 != source_root.occurrence_identity_sha256
    ):
        _fail("raw-source collection does not bind the exact source package root occurrence")
    inherited_semantic = _sha(source_raw.semantic_root_sha256, "inherited semantic root")
    accepted = accept_target_inventory(target_inventory)
    if target_root.package_ref_id != target_inventory.package_ref.content_id:
        _fail("target root belongs to another authenticated package")
    occurrences = tuple(
        item
        for item in accepted.inventory.occurrences
        if item.target_root_id == target_root.content_id
        and item.occurrence_identity_sha256 == target_root.occurrence_identity_sha256
    )
    if len(occurrences) != 1:
        _fail("target root and occurrence are not uniquely present in the signed inventory")
    if source_inventory.extractor != extractor or target_inventory.extractor != extractor:
        _fail("source or target inventory was produced by another extractor")
    if (
        source_root.extractor_capability_id != extractor.content_id
        or target_root.extractor_capability_id != extractor.content_id
    ):
        _fail("application roots do not bind the authenticated extractor")
    if (
        equivalence_pipeline.name != EXACT_REUSE_PIPELINE_CAPABILITY
        or equivalence_pipeline.revision != EQUIVALENCE_SCHEMA_REVISION
    ):
        _fail("equivalence pipeline capability is not the exact supported revision")
    reproduced_decision, reproduced_proof = route_application_root(
        target_root,
        (source_root,),
        pins=decision.pins,
        trusted_direct_audits={source_root.content_id: source_raw.receipt_sha256},
        trusted_inventory_receipts={
            source_root.content_id: source_inventory.receipt_sha256,
            target_root.content_id: target_inventory.receipt_sha256,
        },
    )
    if (
        reproduced_decision.route is not Route.EXACT_REUSE
        or reproduced_decision != decision
        or reproduced_proof is None
        or reproduced_proof != proof
    ):
        _fail("byte-identity proof or ledger decision does not replay from authenticated inputs")
    return inherited_semantic


def exact_reuse_prerequisite_payload(
    *,
    source: AuthenticatedSourceReport,
    source_raw: AuthenticatedRawSourceCollection,
    source_inventory: AuthenticatedTargetInventoryEnvelope,
    source_preparation_receipt: PreparationReceipt,
    source_preparation_authority: ActivatedPreparationAuthority,
    source_root: ApplicationRoot,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    target_root: ApplicationRoot,
    extractor: ExtractorCapability,
    proof: ByteIdentityProof,
    decision: LedgerDecision,
    equivalence_pipeline: CapabilityPin,
    authority: ActivatedExactReuseAuthority,
) -> dict[str, object]:
    authority = _reauthorize(authority)
    inherited_semantic = _validate_inputs(
        source=source,
        source_raw=source_raw,
        source_inventory=source_inventory,
        source_preparation_receipt=source_preparation_receipt,
        source_preparation_authority=source_preparation_authority,
        source_root=source_root,
        target_inventory=target_inventory,
        target_root=target_root,
        extractor=extractor,
        proof=proof,
        decision=decision,
        equivalence_pipeline=equivalence_pipeline,
    )
    return {
        "authority_sha256": authority.activation_sha256,
        "decision": decision.to_data(),
        "equivalence_pipeline": equivalence_pipeline.to_data(),
        "extractor": extractor.to_data(),
        "inherited_semantic_root_sha256": inherited_semantic,
        "proof": proof.to_data(),
        "schema": EXACT_REUSE_PREREQUISITE_SCHEMA,
        "source_package_ref_id": source.package_ref.content_id,
        "source_raw_receipt_sha256": source_raw.receipt_sha256,
        "source_inventory_envelope_sha256": source_inventory.receipt_sha256,
        "source_preparation_receipt_sha256": source_preparation_receipt.content_id,
        "source_root": source_root.to_data(),
        "source_validation_receipt_sha256": source.envelope.receipt_sha256,
        "source_validator_envelope_sha256": hashlib.sha256(
            source.envelope.canonical_bytes
        ).hexdigest(),
        "target_inventory_envelope_sha256": target_inventory.receipt_sha256,
        "target_package_ref_id": target_inventory.package_ref.content_id,
        "target_root": target_root.to_data(),
    }


def exact_reuse_prerequisite_signing_bytes(payload: dict[str, object]) -> bytes:
    if type(payload) is not dict:
        _fail("exact-reuse signing payload must be an exact object")
    _bounded_json(payload)
    return b"phase4-v2:signed-exact-reuse-prerequisite\0" + _canonical(payload)


def exact_reuse_prerequisite_envelope_payload(
    payload: dict[str, object], *, signature: str
) -> bytes:
    if type(payload) is not dict:
        _fail("exact-reuse envelope payload must be an exact object")
    _bounded_json(payload)
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("exact-reuse signature must be canonical Ed25519 hex")
    canonical = _canonical({"payload": payload, "signature": signature})
    if len(canonical) > _MAX_RECEIPT_BYTES:
        _fail("exact-reuse prerequisite receipt exceeds its size limit")
    return canonical


def load_authenticated_exact_reuse_prerequisite(
    canonical_bytes: bytes,
    *,
    authority: ActivatedExactReuseAuthority,
    source: AuthenticatedSourceReport,
    source_raw: AuthenticatedRawSourceCollection,
    source_inventory: AuthenticatedTargetInventoryEnvelope,
    source_preparation_receipt: PreparationReceipt,
    source_preparation_authority: ActivatedPreparationAuthority,
    source_root: ApplicationRoot,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    target_root: ApplicationRoot,
    extractor: ExtractorCapability,
    proof: ByteIdentityProof,
    decision: LedgerDecision,
    equivalence_pipeline: CapabilityPin,
) -> AuthenticatedExactReusePrerequisite:
    authority = _reauthorize(authority)
    document = _load_canonical_document(
        canonical_bytes, maximum=_MAX_RECEIPT_BYTES, label="exact-reuse prerequisite receipt"
    )
    if type(document) is not dict or set(document) != {"payload", "signature"}:
        _fail("exact-reuse prerequisite receipt has an unexpected field set")
    payload, signature = document["payload"], document["signature"]
    if type(payload) is not dict or type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("exact-reuse prerequisite receipt fields are invalid")
    expected = exact_reuse_prerequisite_payload(
        source=source,
        source_raw=source_raw,
        source_inventory=source_inventory,
        source_preparation_receipt=source_preparation_receipt,
        source_preparation_authority=source_preparation_authority,
        source_root=source_root,
        target_inventory=target_inventory,
        target_root=target_root,
        extractor=extractor,
        proof=proof,
        decision=decision,
        equivalence_pipeline=equivalence_pipeline,
        authority=authority,
    )
    if payload != expected:
        _fail("exact-reuse prerequisite receipt differs from its authenticated inputs")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), exact_reuse_prerequisite_signing_bytes(payload)
        )
    except (InvalidSignature, ValueError) as error:
        raise ExactReuseAuthenticationError("exact-reuse prerequisite signature is invalid") from error
    result = object.__new__(AuthenticatedExactReusePrerequisite)
    values = (
        ("authority", authority),
        ("source", source),
        ("source_raw", source_raw),
        ("source_inventory", source_inventory),
        ("source_preparation_receipt", source_preparation_receipt),
        ("source_preparation_authority", source_preparation_authority),
        ("source_root", source_root),
        ("target_inventory", target_inventory),
        ("target_root", target_root),
        ("extractor", extractor),
        ("proof", proof),
        ("decision", decision),
        ("equivalence_pipeline", equivalence_pipeline),
        ("inherited_semantic_root_sha256", expected["inherited_semantic_root_sha256"]),
        ("canonical_bytes", canonical_bytes),
        ("receipt_sha256", hashlib.sha256(canonical_bytes).hexdigest()),
    )
    for name, value in values:
        object.__setattr__(result, name, value)
    return result


def validate_authenticated_exact_reuse_prerequisite(
    receipt: AuthenticatedExactReusePrerequisite,
) -> AuthenticatedExactReusePrerequisite:
    if type(receipt) is not AuthenticatedExactReusePrerequisite:
        _fail("exact authenticated exact-reuse prerequisite is required")
    restored = load_authenticated_exact_reuse_prerequisite(
        receipt.canonical_bytes,
        authority=receipt.authority,
        source=receipt.source,
        source_raw=receipt.source_raw,
        source_inventory=receipt.source_inventory,
        source_preparation_receipt=receipt.source_preparation_receipt,
        source_preparation_authority=receipt.source_preparation_authority,
        source_root=receipt.source_root,
        target_inventory=receipt.target_inventory,
        target_root=receipt.target_root,
        extractor=receipt.extractor,
        proof=receipt.proof,
        decision=receipt.decision,
        equivalence_pipeline=receipt.equivalence_pipeline,
    )
    if restored != receipt:
        _fail("exact-reuse prerequisite changed after authentication")
    return restored


def exact_reuse_prerequisite_completions(
    receipt: AuthenticatedExactReusePrerequisite,
) -> tuple[CompletionPin, CompletionPin, CompletionPin]:
    receipt = validate_authenticated_exact_reuse_prerequisite(receipt)
    semantic_unit = f"{EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX}:{receipt.receipt_sha256}"
    semantic = build_semantic_root_completion(
        source_root=receipt.source_root,
        inherited_semantic_root_sha256=receipt.inherited_semantic_root_sha256,
        parent_unit_id=semantic_unit,
    ).completion
    ledger = CompletionPin(
        f"{EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX}:{receipt.receipt_sha256}",
        LEDGER_DECISION_REVISION,
        receipt.decision.content_id,
    )
    direct = CompletionPin(
        f"{EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX}:{receipt.receipt_sha256}",
        SEMANTIC_ROOT_COMPLETION_REVISION,
        receipt.source_raw.receipt_sha256,
    )
    return semantic, ledger, direct


def exact_reuse_prerequisite_capabilities(
    receipt: AuthenticatedExactReusePrerequisite,
) -> tuple[CapabilityPin, ...]:
    receipt = validate_authenticated_exact_reuse_prerequisite(receipt)
    return (
        exact_reuse_authority_capability(receipt.authority),
        inventory_authority_capability(receipt.target_inventory.authority),
        inventory_extractor_capability(receipt.extractor),
        receipt.equivalence_pipeline,
    )


def exact_reuse_prerequisite_dependencies(
    receipt: AuthenticatedExactReusePrerequisite,
) -> tuple[CompletionPin, CompletionPin, CompletionPin]:
    receipt = validate_authenticated_exact_reuse_prerequisite(receipt)
    return (
        package_validation_receipt_completion(receipt.source.package_ref),
        accept_target_inventory(receipt.source_inventory).completion,
        accept_target_inventory(receipt.target_inventory).completion,
    )


def semantic_root_audit_from_authenticated_prerequisite(
    receipt: AuthenticatedExactReusePrerequisite,
) -> SemanticRootAudit:
    receipt = validate_authenticated_exact_reuse_prerequisite(receipt)
    semantic, ledger, direct = exact_reuse_prerequisite_completions(receipt)
    return build_semantic_root_audit(
        source_root=receipt.source_root,
        ledger_decision=receipt.decision,
        extractor=receipt.extractor,
        accepted_target_inventory=accept_target_inventory(receipt.target_inventory),
        inherited_semantic_root_sha256=receipt.inherited_semantic_root_sha256,
        inherited_semantic_root_completion=build_semantic_root_completion(
            source_root=receipt.source_root,
            inherited_semantic_root_sha256=receipt.inherited_semantic_root_sha256,
            parent_unit_id=semantic.parent_unit_id,
        ),
        target_inventory_completion=accept_target_inventory(receipt.target_inventory).completion,
        ledger_decision_completion=ledger,
        direct_semantic_audit_completion=direct,
        extractor_capability=inventory_extractor_capability(receipt.extractor),
        equivalence_pipeline=receipt.equivalence_pipeline,
    )


def load_authenticated_exact_reuse_semantic_root(
    canonical_bytes: bytes,
    *,
    authority: ActivatedExactReuseAuthority,
    source: AuthenticatedSourceReport,
    source_raw: AuthenticatedRawSourceCollection,
    source_inventory: AuthenticatedTargetInventoryEnvelope,
    source_preparation_receipt: PreparationReceipt,
    source_preparation_authority: ActivatedPreparationAuthority,
    source_root: ApplicationRoot,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    target_root: ApplicationRoot,
    extractor: ExtractorCapability,
    proof: ByteIdentityProof,
    decision: LedgerDecision,
    equivalence_pipeline: CapabilityPin,
) -> tuple[SemanticRootAudit, AuthenticatedExactReusePrerequisite]:
    """Authenticate pre-plan evidence and derive its exact semantic audit together."""

    receipt = load_authenticated_exact_reuse_prerequisite(
        canonical_bytes,
        authority=authority,
        source=source,
        source_raw=source_raw,
        source_inventory=source_inventory,
        source_preparation_receipt=source_preparation_receipt,
        source_preparation_authority=source_preparation_authority,
        source_root=source_root,
        target_inventory=target_inventory,
        target_root=target_root,
        extractor=extractor,
        proof=proof,
        decision=decision,
        equivalence_pipeline=equivalence_pipeline,
    )
    return semantic_root_audit_from_authenticated_prerequisite(receipt), receipt
