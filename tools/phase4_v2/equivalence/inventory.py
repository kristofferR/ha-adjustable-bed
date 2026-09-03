"""Authenticated target-root inventory acceptance boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .core import FrozenPackageRef, validate_frozen_package_ref
from .plan import (
    TARGET_ROOT_INVENTORY_REVISION,
    AcceptedTargetRootInventory,
    CapabilityPin,
    CompletionPin,
    ExtractorCapability,
    TargetRootInventory,
    TargetRootOccurrence,
)

INVENTORY_AUTHORITY_SCHEMA = "phase4-v2-target-inventory-authority-v1"
INVENTORY_AUTHORITY_PIN_SCHEMA = "phase4-v2-target-inventory-authority-pin-v1"
INVENTORY_ENVELOPE_SCHEMA = "phase4-v2-authenticated-target-inventory-v1"
INVENTORY_AUTHORITY_CAPABILITY = "phase4-v2-target-inventory-authority"
INVENTORY_QUEUE_UNIT_KIND = "trusted-target-root-inventory"
INVENTORY_QUEUE_UNIT_PREFIX = "target-root-inventory"
_PIN_PATH = Path("/etc/ha-adjustable-bed/phase4-v2-target-inventory-authority.pin.json")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class InventoryAuthenticationError(ValueError):
    """Target inventory authentication failed closed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _sha(value: object, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise InventoryAuthenticationError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True, init=False)
class ActivatedInventoryAuthority:
    authority_id: str
    public_key: str
    generation: int
    canonical_bytes: bytes
    activation_sha256: str

    def __init__(self) -> None:
        raise InventoryAuthenticationError("inventory authorities require protected activation")


def inventory_authority_payload(
    *, authority_id: str, public_key: str, generation: int
) -> bytes:
    return _canonical(
        {
            "authority_id": authority_id,
            "generation": generation,
            "public_key": public_key,
            "schema": INVENTORY_AUTHORITY_SCHEMA,
        }
    ) + b"\n"


def inventory_authority_pin_payload(authority_payload: bytes) -> bytes:
    return _canonical(
        {
            "activation_sha256": hashlib.sha256(authority_payload).hexdigest(),
            "schema": INVENTORY_AUTHORITY_PIN_SCHEMA,
        }
    ) + b"\n"


def _read_protected_inventory_pin() -> str:
    directory_descriptor: int | None = None
    descriptor: int | None = None
    try:
        directory_descriptor = os.open(
            _PIN_PATH.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        directory = os.fstat(directory_descriptor)
        if (
            directory.st_uid != 0
            or directory.st_mode & 0o022
            or not stat.S_ISDIR(directory.st_mode)
        ):
            raise InventoryAuthenticationError(
                "inventory authority directory is not root protected"
            )
        descriptor = os.open(
            _PIN_PATH.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_descriptor,
        )
        metadata = os.fstat(descriptor)
        if (
            metadata.st_uid != 0
            or metadata.st_mode & 0o022
            or metadata.st_nlink != 1
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
        ):
            raise InventoryAuthenticationError("inventory authority pin is not root protected")
        payload = os.read(descriptor, 4097)
    except OSError as error:
        raise InventoryAuthenticationError("protected inventory authority pin is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    if len(payload) > 4096:
        raise InventoryAuthenticationError("inventory authority pin exceeds its size limit")
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryAuthenticationError("inventory authority pin is invalid") from error
    if type(raw) is not dict or set(raw) != {"activation_sha256", "schema"}:
        raise InventoryAuthenticationError("inventory authority pin has an unexpected field set")
    if raw["schema"] != INVENTORY_AUTHORITY_PIN_SCHEMA:
        raise InventoryAuthenticationError("inventory authority pin schema is unsupported")
    return _sha(raw["activation_sha256"], "inventory activation")


def load_activated_inventory_authority(payload: bytes) -> ActivatedInventoryAuthority:
    if type(payload) is not bytes or not payload.endswith(b"\n"):
        raise InventoryAuthenticationError("inventory authority must be canonical newline JSON")
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryAuthenticationError("inventory authority is invalid") from error
    if type(raw) is not dict or set(raw) != {
        "authority_id", "generation", "public_key", "schema"
    } or _canonical(raw) + b"\n" != payload:
        raise InventoryAuthenticationError("inventory authority is not canonical")
    activation = hashlib.sha256(payload).hexdigest()
    if activation != _read_protected_inventory_pin():
        raise InventoryAuthenticationError("inventory authority differs from protected activation")
    if raw["schema"] != INVENTORY_AUTHORITY_SCHEMA:
        raise InventoryAuthenticationError("inventory authority schema is unsupported")
    authority_id = raw["authority_id"]
    public_key = raw["public_key"]
    generation = raw["generation"]
    if type(authority_id) is not str or not authority_id or len(authority_id) > 200:
        raise InventoryAuthenticationError("inventory authority ID is invalid")
    if type(public_key) is not str or re.fullmatch(r"[0-9a-f]{64}", public_key) is None:
        raise InventoryAuthenticationError("inventory authority public key is invalid")
    if type(generation) is not int or generation < 1:
        raise InventoryAuthenticationError("inventory authority generation is invalid")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
    result = object.__new__(ActivatedInventoryAuthority)
    for name, value in (
        ("authority_id", authority_id), ("public_key", public_key),
        ("generation", generation), ("canonical_bytes", payload),
        ("activation_sha256", activation),
    ):
        object.__setattr__(result, name, value)
    return result


def _reauthorize(authority: ActivatedInventoryAuthority) -> ActivatedInventoryAuthority:
    if type(authority) is not ActivatedInventoryAuthority:
        raise InventoryAuthenticationError("exact activated inventory authority is required")
    restored = load_activated_inventory_authority(authority.canonical_bytes)
    if restored != authority:
        raise InventoryAuthenticationError("inventory authority changed after activation")
    return restored


def inventory_authority_capability(authority: object) -> CapabilityPin:
    if type(authority) is not ActivatedInventoryAuthority:
        raise InventoryAuthenticationError("exact activated inventory authority is required")
    authority = _reauthorize(authority)
    return CapabilityPin(
        INVENTORY_AUTHORITY_CAPABILITY,
        f"{INVENTORY_AUTHORITY_SCHEMA}:generation:{authority.generation}",
        authority.activation_sha256,
    )


def inventory_extractor_capability(extractor: ExtractorCapability) -> CapabilityPin:
    extractor.__post_init__()
    return CapabilityPin(extractor.name, extractor.capability_revision, extractor.content_id)


def target_inventory_queue_unit_id(package_ref_id: str) -> str:
    return f"{INVENTORY_QUEUE_UNIT_PREFIX}:{_sha(package_ref_id, 'package reference')}"


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedTargetInventoryEnvelope:
    authority: ActivatedInventoryAuthority
    package_ref: FrozenPackageRef
    extractor: ExtractorCapability
    inventory: TargetRootInventory
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        raise InventoryAuthenticationError("inventory envelopes require signature verification")


def target_inventory_signing_bytes(payload: dict[str, object]) -> bytes:
    return b"phase4-v2:signed-target-inventory\0" + _canonical(payload)


def target_inventory_envelope_payload(
    *,
    package_ref: FrozenPackageRef,
    inventory: TargetRootInventory,
    extractor: ExtractorCapability,
    authority: ActivatedInventoryAuthority,
    signature: str,
) -> bytes:
    package_ref = validate_frozen_package_ref(package_ref)
    authority = _reauthorize(authority)
    extractor.__post_init__()
    inventory.__post_init__()
    payload = {
        "artifact_digest": package_ref.artifact_digest,
        "authority_sha256": authority.activation_sha256,
        "extractor": extractor.to_data(),
        "inventory": inventory.to_data(),
        "package_name": package_ref.package_name,
        "package_ref_id": package_ref.content_id,
        "preflight_sha256": package_ref.preflight_sha256,
        "schema": INVENTORY_ENVELOPE_SCHEMA,
        "version_code": package_ref.version_code,
    }
    return _canonical({"payload": payload, "signature": signature})


def load_authenticated_target_inventory_envelope(
    canonical_bytes: bytes,
    *,
    authority: ActivatedInventoryAuthority,
    package_ref: FrozenPackageRef,
) -> AuthenticatedTargetInventoryEnvelope:
    authority = _reauthorize(authority)
    package_ref = validate_frozen_package_ref(package_ref)
    try:
        document = json.loads(canonical_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryAuthenticationError("inventory envelope is invalid") from error
    if type(document) is not dict or set(document) != {"payload", "signature"} or _canonical(document) != canonical_bytes:
        raise InventoryAuthenticationError("inventory envelope is not canonical")
    payload, signature = document["payload"], document["signature"]
    if type(payload) is not dict or type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        raise InventoryAuthenticationError("inventory envelope shape is invalid")
    if set(payload) != {
        "artifact_digest",
        "authority_sha256",
        "extractor",
        "inventory",
        "package_name",
        "package_ref_id",
        "preflight_sha256",
        "schema",
        "version_code",
    }:
        raise InventoryAuthenticationError("inventory envelope payload has unexpected fields")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), target_inventory_signing_bytes(payload)
        )
    except InvalidSignature as error:
        raise InventoryAuthenticationError("inventory envelope signature is invalid") from error
    expected_identity = (
        authority.activation_sha256, package_ref.package_name, package_ref.version_code,
        package_ref.artifact_digest, package_ref.preflight_sha256, package_ref.content_id,
    )
    observed_identity = (
        payload.get("authority_sha256"), payload.get("package_name"), payload.get("version_code"),
        payload.get("artifact_digest"), payload.get("preflight_sha256"), payload.get("package_ref_id"),
    )
    if payload.get("schema") != INVENTORY_ENVELOPE_SCHEMA or observed_identity != expected_identity:
        raise InventoryAuthenticationError("inventory envelope belongs to another package or authority")
    extractor_raw = payload.get("extractor")
    inventory_raw = payload.get("inventory")
    if type(extractor_raw) is not dict or type(inventory_raw) is not dict:
        raise InventoryAuthenticationError("inventory envelope records are invalid")
    extractor = ExtractorCapability(**extractor_raw)
    occurrences_raw = inventory_raw.get("occurrences")
    target_package_ref_id = inventory_raw.get("target_package_ref_id")
    revision = inventory_raw.get("revision")
    if (
        type(occurrences_raw) is not list
        or type(target_package_ref_id) is not str
        or type(revision) is not str
    ):
        raise InventoryAuthenticationError("inventory occurrences are invalid")
    if any(
        type(item) is not dict
        or set(item) != {"occurrence_identity_sha256", "target_root_id"}
        for item in occurrences_raw
    ):
        raise InventoryAuthenticationError("inventory occurrence shape is invalid")
    inventory = TargetRootInventory(
        target_package_ref_id=target_package_ref_id,
        occurrences=tuple(TargetRootOccurrence(**item) for item in occurrences_raw),
        revision=revision,
    )
    if (
        inventory.target_package_ref_id != package_ref.content_id
        or inventory.to_data() != inventory_raw
    ):
        raise InventoryAuthenticationError("inventory envelope has derived-field drift")
    result = object.__new__(AuthenticatedTargetInventoryEnvelope)
    for name, value in (
        ("authority", authority), ("package_ref", package_ref), ("extractor", extractor),
        ("inventory", inventory), ("canonical_bytes", canonical_bytes),
        ("receipt_sha256", hashlib.sha256(canonical_bytes).hexdigest()),
    ):
        object.__setattr__(result, name, value)
    return result


def accept_target_inventory(
    envelope: AuthenticatedTargetInventoryEnvelope,
) -> AcceptedTargetRootInventory:
    envelope = validate_target_inventory_envelope(envelope)
    result = object.__new__(AcceptedTargetRootInventory)
    for name, value in (
        ("inventory", envelope.inventory),
        ("completion", CompletionPin(
            target_inventory_queue_unit_id(envelope.package_ref.content_id),
            TARGET_ROOT_INVENTORY_REVISION,
            envelope.inventory.content_id,
        )),
        ("authority_sha256", envelope.authority.activation_sha256),
        ("canonical_envelope", envelope.canonical_bytes),
        ("authority", envelope.authority),
        ("package_ref", envelope.package_ref),
        ("extractor", envelope.extractor),
    ):
        object.__setattr__(result, name, value)
    result.__post_init__()
    return result


def validate_target_inventory_envelope(
    envelope: AuthenticatedTargetInventoryEnvelope,
) -> AuthenticatedTargetInventoryEnvelope:
    if type(envelope) is not AuthenticatedTargetInventoryEnvelope:
        raise InventoryAuthenticationError("exact authenticated inventory envelope is required")
    restored = load_authenticated_target_inventory_envelope(
        envelope.canonical_bytes, authority=envelope.authority, package_ref=envelope.package_ref
    )
    if restored != envelope:
        raise InventoryAuthenticationError("inventory envelope changed after authentication")
    return restored


def validate_accepted_target_inventory(
    accepted: AcceptedTargetRootInventory,
) -> AcceptedTargetRootInventory:
    if type(accepted) is not AcceptedTargetRootInventory:
        raise InventoryAuthenticationError("exact accepted target inventory is required")
    if type(accepted.authority) is not ActivatedInventoryAuthority:
        raise InventoryAuthenticationError("accepted inventory authority is invalid")
    restored_envelope = load_authenticated_target_inventory_envelope(
        accepted.canonical_envelope,
        authority=accepted.authority,
        package_ref=accepted.package_ref,
    )
    restored = accept_target_inventory(restored_envelope)
    if restored != accepted:
        raise InventoryAuthenticationError(
            "accepted inventory differs from its authenticated provenance"
        )
    return restored
