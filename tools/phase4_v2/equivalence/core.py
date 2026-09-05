"""Fail-closed exact-byte equivalence and append-only routing ledger.

This first slice deliberately has no representation for fuzzy or audited
non-identical equivalence.  A root either has an exact clean byte witness or it
is routed to full analysis (or blocked when analysis cannot safely start).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Never

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

if TYPE_CHECKING:
    from tools.phase4_v2.ir import ValidatedReport

EQUIVALENCE_SCHEMA_REVISION = "phase4-v2-exact-equivalence-v1"
PACKAGE_REF_REVISION = "phase4-v2-frozen-package-ref-v1"
VALIDATOR_AUTHORITY_SCHEMA = "phase4-v2-validator-authority-v1"
VALIDATOR_AUTHORITY_PIN_SCHEMA = "phase4-v2-validator-authority-pin-v1"
VALIDATOR_ENVELOPE_SCHEMA = "phase4-v2-authenticated-validator-envelope-v1"
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
_MAX_VALIDATOR_AUTHORITY_BYTES = 64 * 1024
_MAX_VALIDATOR_ENVELOPE_BYTES = 64 * 1024**2


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
    encoded = _canonical_json_bytes(data)
    return hashlib.sha256(domain.encode("ascii") + b"\0" + encoded).hexdigest()


def _canonical_json_bytes(value: object, *, trailing_newline: bool = False) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise EquivalenceError("canonical content contains an unsupported value") from error
    return encoded + (b"\n" if trailing_newline else b"")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"canonical JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _canonical_json_document(
    payload: object,
    label: str,
    *,
    trailing_newline: bool,
    maximum_bytes: int = _MAX_VALIDATOR_ENVELOPE_BYTES,
) -> dict[str, object]:
    if type(payload) is not bytes or not 0 < len(payload) <= maximum_bytes:
        _fail(f"{label} must be bounded exact bytes")
    try:
        value = json.loads(payload, object_pairs_hook=_unique_json_object)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise EquivalenceError(f"{label} is not valid JSON") from error
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 64 or nodes > 250_000:
            _fail(f"{label} exceeds JSON structural bounds")
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
    if type(value) is not dict or _canonical_json_bytes(
        value, trailing_newline=trailing_newline
    ) != payload:
        _fail(f"{label} is not canonical JSON")
    return value


def _token_value(value: object, field: str) -> str:
    if type(value) is not str:
        _fail(f"{field} must be a string")
    return _token(value, field)


def _sha_value(value: object, field: str) -> str:
    if type(value) is not str:
        _fail(f"{field} must be a string")
    return _sha256(value, field)


def _security_stat(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_uid, metadata.st_gid, metadata.st_mode, metadata.st_nlink,
        metadata.st_dev, metadata.st_ino, metadata.st_size,
        metadata.st_mtime_ns, metadata.st_ctime_ns,
    )


def _read_protected_validator_pin() -> str:
    """Read the fixed root-owned validator activation through a protected dirfd."""

    descriptor: int | None = None
    try:
        directory_descriptor = os.open(
            "/etc/ha-adjustable-bed",
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise EquivalenceError("protected validator authority directory is unavailable") from error
    try:
        directory = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != 0
            or stat.S_IMODE(directory.st_mode) & 0o022
        ):
            _fail("protected validator authority directory is not root-owned and immutable")
        descriptor = os.open(
            "phase4-v2-validator-authority.pin.json",
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_descriptor,
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or stat.S_IMODE(before.st_mode) & 0o222
            or before.st_nlink != 1
            or not 0 < before.st_size <= _MAX_VALIDATOR_AUTHORITY_BYTES
        ):
            _fail("validator authority pin is not a root-owned immutable regular file")
        payload = bytearray()
        while chunk := os.read(
            descriptor,
            min(64 * 1024, _MAX_VALIDATOR_AUTHORITY_BYTES + 1 - len(payload)),
        ):
            payload.extend(chunk)
            if len(payload) > _MAX_VALIDATOR_AUTHORITY_BYTES:
                _fail("validator authority pin exceeds its byte limit")
        after = os.fstat(descriptor)
        if len(payload) != before.st_size or _security_stat(before) != _security_stat(after):
            _fail("validator authority pin changed while reading")
        current_directory = os.fstat(directory_descriptor)
        if _security_stat(directory) != _security_stat(current_directory):
            _fail("protected validator authority directory changed while reading")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_descriptor)
    raw = _canonical_json_document(bytes(payload), "validator authority pin", trailing_newline=True)
    if set(raw) != {"activation_sha256", "schema"}:
        _fail("validator authority pin has an unexpected field set")
    if raw["schema"] != VALIDATOR_AUTHORITY_PIN_SCHEMA:
        _fail("validator authority pin schema is unsupported")
    return _sha_value(raw["activation_sha256"], "validator activation digest")


def _validate_validator_authority(
    authority: ActivatedValidatorAuthority,
) -> ActivatedValidatorAuthority:
    if type(authority) is not ActivatedValidatorAuthority:
        _fail("exact activated validator authority is required")
    restored = load_activated_validator_authority(authority.canonical_bytes)
    if restored != authority:
        _fail("validator authority fields changed after activation")
    return restored


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


@dataclass(frozen=True, slots=True, init=False)
class FrozenPackageRef:
    """Frozen package identity and its trusted package-local validation roots."""

    package_name: str
    version_code: str
    artifact_digest: str
    preflight_sha256: str
    validation_receipt_sha256: str
    validator_authority: ActivatedValidatorAuthority
    validator_envelope_bytes: bytes
    revision: str = PACKAGE_REF_REVISION

    def __init__(self) -> None:
        raise ValueError(
            "frozen package references derive only from an authenticated validator envelope"
        )

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
        if type(self.validator_authority) is not ActivatedValidatorAuthority:
            _fail("frozen package reference requires its exact validator authority")
        if type(self.validator_envelope_bytes) is not bytes:
            _fail("frozen package reference requires exact validator envelope bytes")
        if self.revision != PACKAGE_REF_REVISION:
            _fail("unsupported frozen package reference revision")

    def to_data(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "package_name": self.package_name,
            "preflight_sha256": self.preflight_sha256,
            "revision": self.revision,
            "validation_receipt_sha256": self.validation_receipt_sha256,
            "validator_authority_sha256": self.validator_authority.activation_sha256,
            "validator_envelope_sha256": hashlib.sha256(
                self.validator_envelope_bytes
            ).hexdigest(),
            "version_code": self.version_code,
        }

    @property
    def content_id(self) -> str:
        return _canonical_content_id("phase4-v2:frozen-package-ref", self.to_data())


@dataclass(frozen=True, slots=True, init=False)
class ActivatedValidatorAuthority:
    """Validator signing authority admitted by an OS-protected digest pin."""

    authority_id: str
    public_key: str
    validator_revision: str
    contract_revision: str
    canonical_bytes: bytes
    activation_sha256: str

    def __init__(self) -> None:
        _fail("validator authority must be loaded from a protected activation")


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedValidatorEnvelope:
    """A signed canonical validator receipt and its derived trusted report."""

    authority_sha256: str
    authority: ActivatedValidatorAuthority
    canonical_bytes: bytes
    receipt_payload: bytes
    receipt_sha256: str
    dependency_digests: tuple[tuple[str, str], ...]
    validator_revision: str
    contract_revision: str
    report: ValidatedReport

    def __init__(self) -> None:
        _fail("validator envelopes must be loaded through signature verification")


def validator_authority_payload(
    *,
    authority_id: str,
    public_key: str,
    validator_revision: str,
    contract_revision: str,
) -> bytes:
    """Render canonical bytes for an external validator-authority publisher."""

    _token(authority_id, "validator authority id")
    _sha256(public_key, "validator authority public key")
    _token(validator_revision, "validator revision")
    _token(contract_revision, "validator contract revision")
    return _canonical_json_bytes(
        {
            "authority_id": authority_id,
            "contract_revision": contract_revision,
            "public_key": public_key,
            "schema": VALIDATOR_AUTHORITY_SCHEMA,
            "validator_revision": validator_revision,
        },
        trailing_newline=True,
    )


def validator_authority_pin_payload(authority_payload: bytes) -> bytes:
    """Render the digest document that an operator installs as a protected pin."""

    if type(authority_payload) is not bytes or not authority_payload:
        _fail("validator authority payload must be exact bytes")
    return _canonical_json_bytes(
        {
            "activation_sha256": hashlib.sha256(authority_payload).hexdigest(),
            "schema": VALIDATOR_AUTHORITY_PIN_SCHEMA,
        },
        trailing_newline=True,
    )


def load_activated_validator_authority(
    payload: bytes,
) -> ActivatedValidatorAuthority:
    """Load one authority only when exact bytes match an OS-protected pin."""

    expected = _read_protected_validator_pin()
    if type(payload) is not bytes or not payload or len(payload) > _MAX_VALIDATOR_AUTHORITY_BYTES:
        _fail("validator authority must be bounded exact bytes")
    if hashlib.sha256(payload).hexdigest() != expected:
        _fail("validator authority does not match its protected activation")
    raw = _canonical_json_document(payload, "validator authority", trailing_newline=True)
    if set(raw) != {
        "authority_id",
        "contract_revision",
        "public_key",
        "schema",
        "validator_revision",
    }:
        _fail("validator authority has an unexpected field set")
    if raw["schema"] != VALIDATOR_AUTHORITY_SCHEMA:
        _fail("validator authority schema is unsupported")
    from tools.phase4_v2.ir import SUPPORTED_CONTRACT_REVISION, SUPPORTED_VALIDATOR_REVISION

    authority_id = _token_value(raw["authority_id"], "validator authority id")
    public_key = _sha_value(raw["public_key"], "validator authority public key")
    validator_revision = _token_value(raw["validator_revision"], "validator revision")
    contract_revision = _token_value(raw["contract_revision"], "validator contract revision")
    if validator_revision != SUPPORTED_VALIDATOR_REVISION:
        _fail("validator authority revision is unsupported")
    if contract_revision != SUPPORTED_CONTRACT_REVISION:
        _fail("validator authority contract is unsupported")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
    except ValueError as error:
        raise EquivalenceError("validator authority public key is invalid") from error
    result = object.__new__(ActivatedValidatorAuthority)
    for name, value in (
        ("authority_id", authority_id),
        ("public_key", public_key),
        ("validator_revision", validator_revision),
        ("contract_revision", contract_revision),
        ("canonical_bytes", payload),
        ("activation_sha256", expected),
    ):
        object.__setattr__(result, name, value)
    return result


def validator_envelope_signing_bytes(
    receipt_payload: bytes,
    authority: ActivatedValidatorAuthority,
) -> bytes:
    """Return the exact domain-separated bytes signed by a validator producer."""

    authority = _validate_validator_authority(authority)
    receipt = _canonical_json_document(
        receipt_payload, "validator receipt", trailing_newline=False
    )
    signed = {
        "authority_sha256": authority.activation_sha256,
        "receipt": receipt,
        "schema": VALIDATOR_ENVELOPE_SCHEMA,
    }
    return b"phase4-v2:authenticated-validator-envelope\0" + _canonical_json_bytes(signed)


def authenticated_validator_envelope_payload(
    receipt_payload: bytes,
    authority: ActivatedValidatorAuthority,
    *,
    signature: str,
) -> bytes:
    """Assemble a canonical envelope from an externally produced signature."""

    authority = _validate_validator_authority(authority)
    receipt = _canonical_json_document(
        receipt_payload, "validator receipt", trailing_newline=False
    )
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("validator envelope signature is invalid")
    return _canonical_json_bytes(
        {
            "authority_sha256": authority.activation_sha256,
            "receipt": receipt,
            "schema": VALIDATOR_ENVELOPE_SCHEMA,
            "signature": signature,
        }
    )


def load_authenticated_validator_envelope(
    payload: bytes,
    *,
    authority: ActivatedValidatorAuthority,
) -> AuthenticatedValidatorEnvelope:
    """Verify a signed validator receipt and derive every trusted input from it."""

    authority = _validate_validator_authority(authority)
    if type(payload) is not bytes or not payload or len(payload) > _MAX_VALIDATOR_ENVELOPE_BYTES:
        _fail("validator envelope must be bounded exact bytes")
    raw = _canonical_json_document(payload, "validator envelope", trailing_newline=False)
    if set(raw) != {"authority_sha256", "receipt", "schema", "signature"}:
        _fail("validator envelope has an unexpected field set")
    if raw["schema"] != VALIDATOR_ENVELOPE_SCHEMA:
        _fail("validator envelope schema is unsupported")
    if raw["authority_sha256"] != authority.activation_sha256:
        _fail("validator envelope belongs to another authority")
    signature = raw["signature"]
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("validator envelope signature is invalid")
    receipt = raw["receipt"]
    if type(receipt) is not dict:
        _fail("validator envelope receipt must be an object")
    receipt_payload = _canonical_json_bytes(receipt)
    signed = {
        "authority_sha256": authority.activation_sha256,
        "receipt": receipt,
        "schema": VALIDATOR_ENVELOPE_SCHEMA,
    }
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature),
            b"phase4-v2:authenticated-validator-envelope\0" + _canonical_json_bytes(signed),
        )
    except InvalidSignature as error:
        raise EquivalenceError("validator envelope signature is invalid") from error
    dependencies_raw = receipt.get("dependency_digests")
    if type(dependencies_raw) is not dict:
        _fail("validator receipt dependency pins are unavailable")
    dependencies = {
        _token_value(name, "validator dependency name"): _sha_value(
            digest, "validator dependency digest"
        )
        for name, digest in dependencies_raw.items()
    }
    embedded_digest = _sha_value(
        receipt.get("validation_receipt_sha256"), "validator receipt digest"
    )
    from tools.phase4_v2.ir import bind_validator_receipt

    report = bind_validator_receipt(
        receipt_payload,
        trusted_validator_revision=authority.validator_revision,
        trusted_contract_revision=authority.contract_revision,
        trusted_dependency_digests=dependencies,
        trusted_receipt_sha256=embedded_digest,
    )
    result = object.__new__(AuthenticatedValidatorEnvelope)
    for name, value in (
        ("authority_sha256", authority.activation_sha256),
        ("authority", authority),
        ("canonical_bytes", payload),
        ("receipt_payload", receipt_payload),
        ("receipt_sha256", report.validation_receipt_sha256),
        ("dependency_digests", tuple(sorted(report.dependency_digests))),
        ("validator_revision", report.validator_revision),
        ("contract_revision", report.contract_revision),
        ("report", report),
    ):
        object.__setattr__(result, name, value)
    _validate_validator_authority(authority)
    return result


def frozen_package_ref_from_validator_envelope(
    envelope: AuthenticatedValidatorEnvelope,
) -> FrozenPackageRef:
    """Derive the only package reference admitted to the execution pipeline."""

    envelope = validate_authenticated_validator_envelope(envelope)
    identity = envelope.report.validated_artifact_identity
    dependencies = dict(envelope.dependency_digests)
    preflight_sha256 = dependencies.get("preflight")
    if preflight_sha256 is None:
        _fail("authenticated validator envelope has no preflight dependency")
    result = object.__new__(FrozenPackageRef)
    for name, value in (
        ("package_name", identity.package_name),
        ("version_code", identity.version_code),
        ("artifact_digest", identity.artifact_digest),
        ("preflight_sha256", preflight_sha256),
        ("validation_receipt_sha256", envelope.receipt_sha256),
        ("validator_authority", envelope.authority),
        ("validator_envelope_bytes", envelope.canonical_bytes),
        ("revision", PACKAGE_REF_REVISION),
    ):
        object.__setattr__(result, name, value)
    result.__post_init__()
    return result


def validate_frozen_package_ref(package_ref: FrozenPackageRef) -> FrozenPackageRef:
    """Reauthenticate a package reference from its retained signed provenance."""

    if type(package_ref) is not FrozenPackageRef:
        _fail("exact frozen package reference is required")
    envelope = load_authenticated_validator_envelope(
        package_ref.validator_envelope_bytes,
        authority=package_ref.validator_authority,
    )
    restored = frozen_package_ref_from_validator_envelope(envelope)
    if restored != package_ref:
        _fail("frozen package reference differs from its authenticated provenance")
    return restored


def validate_authenticated_validator_envelope(
    envelope: AuthenticatedValidatorEnvelope,
) -> AuthenticatedValidatorEnvelope:
    """Reauthenticate an envelope at each production trust boundary."""

    if type(envelope) is not AuthenticatedValidatorEnvelope:
        _fail("exact authenticated validator envelope is required")
    restored = load_authenticated_validator_envelope(
        envelope.canonical_bytes,
        authority=envelope.authority,
    )
    if restored != envelope:
        _fail("validator envelope fields changed after authentication")
    return restored


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

    def _validate_decision(self, decision: LedgerDecision, *, replay: bool = False) -> None:
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
        if self._trusted_inventory_receipts.get(target.content_id) != (
            decision.target_inventory_receipt_sha256
        ):
            _fail("decision does not reproduce from the trusted target inventory receipt")
        expected_proof: ByteIdentityProof | None = None
        if replay and decision.route is not Route.EXACT_REUSE:
            expected, _ = _route_application_root_validated(
                target,
                (),
                pins=self._pins,
                audits=self._trusted_direct_audits,
                inventory_receipts=self._trusted_inventory_receipts,
            )
            if decision != expected:
                _fail("decision does not reproduce from the pinned target routing inputs")
        elif not replay:
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
            if not replay and expected_proof != proof:
                _fail("exact-reuse proof differs from the deterministic routing proof")
        else:
            if not replay and expected_proof is not None:
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
        self._validate_decision(entry.decision, replay=True)
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
        self._validate_decision(decision)
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
    return validate_frozen_package_ref(item)


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
