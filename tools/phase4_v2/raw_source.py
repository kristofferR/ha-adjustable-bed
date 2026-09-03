"""Authenticated raw-evidence genesis for Phase 4 semantic claims.

The raw-source authority is deliberately independent of the analyst and the
validator.  It attests the first finite mapping from preparation output bytes
to a canonical JSON scalar, before that value is admitted into protocol IR.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Never, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.phase4_v2.preflight.execution import PreparationError
from tools.phase4_v2.preflight.registry import (
    ActivatedPreparationAuthority,
    PreparationReceipt,
    validate_preparation_receipt_authority,
)

if TYPE_CHECKING:
    from tools.phase4_v2.equivalence.core import ApplicationRoot, FrozenPackageRef
    from tools.phase4_v2.equivalence.inventory import AuthenticatedTargetInventoryEnvelope

type RawSourceReauthenticationInput = tuple[
    FrozenPackageRef,
    ApplicationRoot,
    PreparationReceipt,
    ActivatedPreparationAuthority,
    AuthenticatedTargetInventoryEnvelope,
]
type PackageLocalEvidenceReauthenticationInput = tuple[
    FrozenPackageRef,
    PreparationReceipt,
    ActivatedPreparationAuthority,
    AuthenticatedTargetInventoryEnvelope,
]

RAW_SOURCE_AUTHORITY_SCHEMA = "phase4-v2-raw-source-authority-v1"
RAW_SOURCE_ENVELOPE_SCHEMA = "phase4-v2-authenticated-raw-source-v1"
RAW_SOURCE_COLLECTION_REVISION = "phase4-v2-raw-source-collection-v1"
PACKAGE_LOCAL_EVIDENCE_ENVELOPE_SCHEMA = (
    "phase4-v2-authenticated-package-local-evidence-v1"
)
PACKAGE_LOCAL_EVIDENCE_REVISION = "phase4-v2-package-local-evidence-v1"
_AUTHORITY_PATH = Path("/etc/ha-adjustable-bed/phase4-v2-raw-source-authority.json")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_MAX_AUTHORITY_BYTES = 4 * 1024
_MAX_ENVELOPE_BYTES = 64 * 1024**2
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 1_000_000
_MAX_MEMBERS = 250_000
_MAX_ANCHORS = 1_000_000
_MAX_RAW_ANCHOR_BYTES = 16 * 1024**2
_MAX_RAW_BYTES = 64 * 1024**2
_MAX_PATH_BYTES = 8_192
_MAX_POINTER_BYTES = 8_192
_MAX_REGISTRY_COLLECTIONS = 4_096
_MAX_REGISTRY_ENVELOPE_BYTES = 64 * 1024**2
_MAX_REGISTRY_MEMBERS = 4_096
_MAX_REGISTRY_ANCHORS = 4_096
_MAX_REGISTRY_RAW_BYTES = 64 * 1024**2

type JsonScalar = str | int | bool


class RawSourceAuthenticationError(ValueError):
    """A raw-source authority, collection, or binding failed closed."""


def _fail(message: str) -> Never:
    raise RawSourceAuthenticationError(message)


def _validate_preparation(
    receipt: PreparationReceipt,
    authority: ActivatedPreparationAuthority,
) -> PreparationReceipt:
    try:
        return validate_preparation_receipt_authority(receipt, authority)
    except PreparationError as error:
        raise RawSourceAuthenticationError(
            "raw-source preparation authentication failed"
        ) from error


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as error:
        raise RawSourceAuthenticationError("raw-source value is not canonical JSON") from error


def canonical_scalar_bytes(value: JsonScalar) -> bytes:
    """Return the one canonical representation accepted for semantic scalars."""

    if type(value) not in {str, int, bool}:
        _fail("raw-source decoded value must be a string, integer, or boolean")
    if type(value) is int and not -(2**63) <= value <= 2**63 - 1:
        _fail("raw-source decoded integer is outside the signed 64-bit range")
    return _canonical(value)


def canonical_scalar_sha256(value: JsonScalar) -> str:
    """Match the IR's exact canonical semantic-value hash contract."""

    return hashlib.sha256(canonical_scalar_bytes(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"raw-source JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _validate_shape(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            _fail("raw-source JSON exceeds its node limit")
        if depth > _MAX_JSON_DEPTH:
            _fail("raw-source JSON exceeds its depth limit")
        if type(current) is dict:
            pending.extend((item, depth + 1) for item in cast(dict[str, object], current).values())
        elif type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
        elif current is None or type(current) in {str, int, bool}:
            if type(current) is int and not -(2**63) <= current <= 2**63 - 1:
                _fail("raw-source JSON integer is outside the signed 64-bit range")
        else:
            _fail("raw-source JSON contains a non-scalar number")


def _load_canonical(payload: bytes, *, maximum: int, label: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        _fail(f"{label} must be bounded exact bytes")
    try:
        raw = json.loads(payload, object_pairs_hook=_unique_object)
    except RawSourceAuthenticationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise RawSourceAuthenticationError(f"{label} is invalid JSON") from error
    _validate_shape(raw)
    if type(raw) is not dict or _canonical(raw) + b"\n" != payload:
        _fail(f"{label} is not canonical newline-terminated JSON")
    return cast(dict[str, object], raw)


def _sha(value: object, field: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256")
    return value


def _token(value: object, field: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        _fail(f"{field} must be a canonical token")
    return value


def _path(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > _MAX_PATH_BYTES:
        _fail(f"{field} must be a bounded path")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or candidate.as_posix() != value
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        _fail(f"{field} must be a canonical relative POSIX path")
    return value


def _pointer(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value.startswith("/")
        or len(value.encode("utf-8")) > _MAX_POINTER_BYTES
    ):
        _fail(f"{field} must be a bounded JSON pointer")
    for token in value[1:].split("/"):
        index = 0
        while index < len(token):
            if token[index] == "~" and (index + 1 >= len(token) or token[index + 1] not in "01"):
                _fail(f"{field} contains an invalid JSON-pointer escape")
            index += 2 if token[index] == "~" else 1
    return value


def _exact(value: object, fields: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        _fail(f"{label} must contain the exact expected fields")
    return cast(dict[str, object], value)


def _bounded_file(path: Path, maximum: int) -> bytes:
    directory = descriptor = None
    try:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        directory_before = os.fstat(directory)
        if (
            not stat.S_ISDIR(directory_before.st_mode)
            or directory_before.st_uid != 0
            or directory_before.st_mode & 0o022
        ):
            _fail("raw-source authority directory is not root protected")
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or before.st_mode & 0o022
            or before.st_nlink != 1
            or before.st_size > maximum
        ):
            _fail("raw-source authority is not a bounded root-protected regular file")
        payload = bytearray()
        while chunk := os.read(descriptor, min(1024 * 1024, maximum + 1 - len(payload))):
            payload.extend(chunk)
            if len(payload) > maximum:
                _fail("raw-source authority exceeds its byte limit")
        after = os.fstat(descriptor)
        directory_after = os.fstat(directory)
        if (
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_uid,
                before.st_gid,
                before.st_mode,
                before.st_nlink,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_uid,
                after.st_gid,
                after.st_mode,
                after.st_nlink,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            or (
                directory_before.st_dev,
                directory_before.st_ino,
                directory_before.st_size,
                directory_before.st_uid,
                directory_before.st_gid,
                directory_before.st_mode,
                directory_before.st_nlink,
                directory_before.st_mtime_ns,
                directory_before.st_ctime_ns,
            )
            != (
                directory_after.st_dev,
                directory_after.st_ino,
                directory_after.st_size,
                directory_after.st_uid,
                directory_after.st_gid,
                directory_after.st_mode,
                directory_after.st_nlink,
                directory_after.st_mtime_ns,
                directory_after.st_ctime_ns,
            )
        ):
            _fail("raw-source authority changed while reading")
        return bytes(payload)
    except OSError as error:
        raise RawSourceAuthenticationError("protected raw-source authority is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)


@dataclass(frozen=True, slots=True, init=False)
class ActivatedRawSourceAuthority:
    authority_id: str
    generation: int
    public_key: str
    canonical_bytes: bytes
    activation_sha256: str

    def __init__(self) -> None:
        _fail("raw-source authority requires protected activation")


def raw_source_authority_payload(*, authority_id: str, generation: int, public_key: str) -> bytes:
    """Render administrator-installable authority bytes without signing support."""

    _token(authority_id, "authority_id")
    if type(generation) is not int or generation < 1:
        _fail("authority generation must be a positive integer")
    if type(public_key) is not str or re.fullmatch(r"[0-9a-f]{64}", public_key) is None:
        _fail("authority public key is invalid")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
    return _canonical(
        {
            "authority_id": authority_id,
            "generation": generation,
            "public_key": public_key,
            "schema": RAW_SOURCE_AUTHORITY_SCHEMA,
        }
    ) + b"\n"


def load_protected_raw_source_authority() -> ActivatedRawSourceAuthority:
    """Reload the fixed OS authority config for every trust-boundary consumer."""

    payload = _read_protected_raw_source_authority()
    raw = _load_canonical(payload, maximum=_MAX_AUTHORITY_BYTES, label="raw-source authority")
    item = _exact(raw, {"authority_id", "generation", "public_key", "schema"}, "authority")
    if item["schema"] != RAW_SOURCE_AUTHORITY_SCHEMA:
        _fail("raw-source authority schema is unsupported")
    canonical = raw_source_authority_payload(
        authority_id=cast(str, item["authority_id"]),
        generation=cast(int, item["generation"]),
        public_key=cast(str, item["public_key"]),
    )
    if canonical != payload:
        _fail("raw-source authority did not reproduce")
    result = object.__new__(ActivatedRawSourceAuthority)
    for name, value in (
        ("authority_id", item["authority_id"]),
        ("generation", item["generation"]),
        ("public_key", item["public_key"]),
        ("canonical_bytes", payload),
        ("activation_sha256", hashlib.sha256(payload).hexdigest()),
    ):
        object.__setattr__(result, name, value)
    return result


def _read_protected_raw_source_authority() -> bytes:
    return _bounded_file(_AUTHORITY_PATH, _MAX_AUTHORITY_BYTES)


@dataclass(frozen=True, slots=True, order=True)
class RawSourceMember:
    id: str
    invocation_index: int
    path: str
    sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        _token(self.id, "raw member ID")
        _path(self.path, "raw member path")
        _sha(self.sha256, "raw member digest")
        if type(self.invocation_index) is not int or self.invocation_index < 0:
            _fail("raw member invocation index is invalid")
        if type(self.byte_length) is not int or not 0 <= self.byte_length <= 2**63 - 1:
            _fail("raw member byte length is invalid")

    def to_data(self) -> dict[str, object]:
        return {
            "byte_length": self.byte_length,
            "id": self.id,
            "invocation_index": self.invocation_index,
            "path": self.path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True, order=True)
class RawSourceAnchor:
    """Authority-attested exact slice of one accepted preparation output member."""

    id: str
    member_id: str
    start_byte: int
    end_byte: int
    raw_bytes: bytes
    representation: str
    decoded_value: JsonScalar
    value_sha256: str
    source_ir_pointer: str

    def __post_init__(self) -> None:
        _token(self.id, "raw anchor ID")
        _token(self.member_id, "raw anchor member ID")
        if (
            type(self.start_byte) is not int
            or type(self.end_byte) is not int
            or not 0 <= self.start_byte < self.end_byte
            or type(self.raw_bytes) is not bytes
            or len(self.raw_bytes) != self.end_byte - self.start_byte
            or len(self.raw_bytes) > _MAX_RAW_ANCHOR_BYTES
        ):
            _fail("raw anchor range or byte payload is invalid")
        _pointer(self.source_ir_pointer, "raw anchor source pointer")
        if self.representation == "utf8":
            try:
                reproduced: JsonScalar = self.raw_bytes.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise RawSourceAuthenticationError("raw anchor is not valid UTF-8") from error
        elif self.representation == "hex":
            reproduced = self.raw_bytes.hex()
        elif self.representation == "json-scalar":
            try:
                decoded = json.loads(self.raw_bytes, object_pairs_hook=_unique_object)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                raise RawSourceAuthenticationError("raw anchor JSON scalar is invalid") from error
            reproduced = cast(JsonScalar, decoded)
            if canonical_scalar_bytes(reproduced) != self.raw_bytes:
                _fail("raw anchor JSON scalar bytes are not canonical")
        else:
            _fail("raw anchor representation is unsupported")
        canonical_scalar_bytes(self.decoded_value)
        if reproduced != self.decoded_value or type(reproduced) is not type(self.decoded_value):
            _fail("raw anchor decoded value does not reproduce")
        if canonical_scalar_sha256(self.decoded_value) != self.value_sha256:
            _fail("raw anchor value digest is invalid")

    def to_data(self) -> dict[str, object]:
        return {
            "decoded_value": self.decoded_value,
            "end_byte": self.end_byte,
            "id": self.id,
            "member_id": self.member_id,
            "raw_hex": self.raw_bytes.hex(),
            "representation": self.representation,
            "source_ir_pointer": self.source_ir_pointer,
            "start_byte": self.start_byte,
            "value_sha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedRawSourceCollection:
    authority: ActivatedRawSourceAuthority
    package_ref_id: str
    package_name: str
    version_code: str
    artifact_digest: str
    target_root_id: str
    occurrence_identity_sha256: str
    preparation_receipt_sha256: str
    target_inventory_receipt_sha256: str
    output_manifest_sha256: str
    tool_lineage_sha256: str
    semantic_root_sha256: str
    upstream_digests: tuple[tuple[str, str], ...]
    members: tuple[RawSourceMember, ...]
    anchors: tuple[RawSourceAnchor, ...]
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        _fail("raw-source collections require signature authentication")


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedRawSourceRegistry:
    entries: tuple[AuthenticatedRawSourceCollection, ...]

    def __init__(self) -> None:
        _fail("raw-source registries require authenticated construction")


@dataclass(frozen=True, slots=True, order=True)
class PackageLocalEvidenceMember:
    """One raw-authority-attested output of an authenticated producer route."""

    id: str
    path: str
    sha256: str
    byte_length: int
    producer_name: str
    producer_revision: str
    producer_digest: str
    invocation_sha256: str

    def __post_init__(self) -> None:
        _token(self.id, "package-local member ID")
        _path(self.path, "package-local member path")
        _sha(self.sha256, "package-local member digest")
        _token(self.producer_name, "package-local producer name")
        _token(self.producer_revision, "package-local producer revision")
        _sha(self.producer_digest, "package-local producer digest")
        _sha(self.invocation_sha256, "package-local invocation digest")
        if type(self.byte_length) is not int or not 0 <= self.byte_length <= 2**63 - 1:
            _fail("package-local member byte length is invalid")

    def to_data(self) -> dict[str, object]:
        return {
            "byte_length": self.byte_length,
            "id": self.id,
            "invocation_sha256": self.invocation_sha256,
            "path": self.path,
            "producer_digest": self.producer_digest,
            "producer_name": self.producer_name,
            "producer_revision": self.producer_revision,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True, order=True)
class PackageLocalEvidenceAnchor:
    """One local-domain claim and its exact terminal semantic destination."""

    raw: RawSourceAnchor
    local_domain: str
    terminal_ir_pointer: str

    def __post_init__(self) -> None:
        if type(self.raw) is not RawSourceAnchor:
            _fail("package-local anchor requires an exact raw anchor")
        self.raw.__post_init__()
        _token(self.local_domain, "package-local anchor domain")
        _pointer(self.terminal_ir_pointer, "package-local terminal pointer")

    @property
    def id(self) -> str:
        return self.raw.id

    @property
    def member_id(self) -> str:
        return self.raw.member_id

    def to_data(self) -> dict[str, object]:
        return {
            **self.raw.to_data(),
            "local_domain": self.local_domain,
            "terminal_ir_pointer": self.terminal_ir_pointer,
        }


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedPackageLocalEvidence:
    """Root-independent target-package evidence with finite raw provenance."""

    authority: ActivatedRawSourceAuthority
    package_ref_id: str
    package_name: str
    version_code: str
    artifact_digest: str
    preparation_receipt_sha256: str
    target_inventory_receipt_sha256: str
    output_manifest_sha256: str
    tool_lineage_sha256: str
    upstream_digests: tuple[tuple[str, str], ...]
    mandatory_domains: tuple[str, ...]
    members: tuple[PackageLocalEvidenceMember, ...]
    anchors: tuple[PackageLocalEvidenceAnchor, ...]
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        _fail("package-local evidence requires signature authentication")


def _preparation_lineage(receipt: PreparationReceipt) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    if type(receipt) is not PreparationReceipt:
        _fail("raw source requires an exact accepted preparation receipt")
    try:
        receipt_data = receipt.to_data()
        receipt_sha = receipt.content_id
        invocations = receipt.invocations
    except (AttributeError, TypeError, ValueError) as error:
        raise RawSourceAuthenticationError("preparation receipt is invalid") from error
    if type(invocations) is not tuple:
        _fail("preparation invocations must be immutable")
    # Reproduce the exact receipt identity after any hostile attribute mutation.
    if hashlib.sha256(b"phase4-v2:preparation-receipt\0" + _canonical(receipt_data)).hexdigest() != receipt_sha:
        _fail("preparation receipt identity did not reproduce")
    output_manifest = [
        {
            "invocation_index": index,
            "member": invocation.member,
            "outputs": [item.to_data() for item in invocation.outputs],
            "route": invocation.route,
        }
        for index, invocation in enumerate(invocations)
    ]
    tool_lineage = [
        {
            "arguments": list(invocation.arguments),
            "cache_key": invocation.cache_key,
            "flags": list(invocation.flags),
            "input_sha256": invocation.input_sha256,
            "member": invocation.member,
            "route": invocation.route,
            "status": invocation.status,
            "tool": invocation.tool.to_data(),
        }
        for invocation in invocations
    ]
    upstream = tuple(
        sorted(
            {
                "candidate_contract": receipt.candidate_contract_sha256,
                "candidate_index": receipt.candidate_index_sha256,
                "execution_profile": receipt.execution_profile_sha256,
                "preflight": receipt.preflight_manifest_sha256,
                "preparation_authority": receipt.authority_sha256,
                "preparation_manifest": receipt.manifest_sha256,
                "tool_registry": receipt.tool_registry_sha256,
            }.items()
        )
    )
    return (
        hashlib.sha256(_canonical(output_manifest)).hexdigest(),
        hashlib.sha256(_canonical(tool_lineage)).hexdigest(),
        upstream,
    )


def raw_source_signing_bytes(payload: dict[str, object]) -> bytes:
    """Return domain-separated bytes for an external signer or test fixture."""

    return b"phase4-v2:signed-raw-source\0" + _canonical(payload)


def _semantic_root(anchors: tuple[RawSourceAnchor, ...] | list[RawSourceAnchor]) -> str:
    return hashlib.sha256(
        b"phase4-v2:raw-semantic-root\0"
        + _canonical(
            [
                {
                    "decoded_value": item.decoded_value,
                    "source_ir_pointer": item.source_ir_pointer,
                    "value_sha256": item.value_sha256,
                }
                for item in anchors
            ]
        )
    ).hexdigest()


def raw_source_collection_payload(
    *,
    package_ref: FrozenPackageRef,
    root: ApplicationRoot,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    members: tuple[RawSourceMember, ...],
    anchors: tuple[RawSourceAnchor, ...],
) -> dict[str, object]:
    """Render unsigned collection data for an external raw-source authority."""

    from tools.phase4_v2.equivalence.core import ApplicationRoot, validate_frozen_package_ref
    from tools.phase4_v2.equivalence.inventory import validate_target_inventory_envelope

    authority = load_protected_raw_source_authority()
    package_ref = validate_frozen_package_ref(package_ref)
    preparation_receipt = _validate_preparation(
        preparation_receipt, preparation_authority
    )
    target_inventory = validate_target_inventory_envelope(target_inventory)
    if type(root) is not ApplicationRoot:
        _fail("raw source requires an exact application root")
    root.__post_init__()
    if (
        root.package_ref_id != package_ref.content_id
        or target_inventory.package_ref != package_ref
        or not any(
            occurrence.target_root_id == root.content_id
            and occurrence.occurrence_identity_sha256 == root.occurrence_identity_sha256
            for occurrence in target_inventory.inventory.occurrences
        )
        or root.extractor_capability_id != target_inventory.extractor.content_id
    ):
        _fail("raw-source root is not authenticated by the target inventory")
    if type(members) is not tuple or type(anchors) is not tuple:
        _fail("raw-source payload inputs must be immutable tuples")
    if (
        not members
        or len(members) > _MAX_MEMBERS
        or not anchors
        or len(anchors) > _MAX_ANCHORS
        or any(type(item) is not RawSourceMember for item in members)
        or any(type(item) is not RawSourceAnchor for item in anchors)
    ):
        _fail("raw-source payload inputs are empty, over limit, or incorrectly typed")
    for item in members:
        item.__post_init__()
        if item.invocation_index >= len(preparation_receipt.invocations):
            _fail("raw-source member invocation index is invalid")
        outputs = preparation_receipt.invocations[item.invocation_index].outputs
        matches = tuple(output for output in outputs if output.path == item.path)
        if len(matches) != 1 or (matches[0].sha256, matches[0].bytes) != (
            item.sha256,
            item.byte_length,
        ):
            _fail("raw-source member differs from accepted preparation output")
    member_by_id = {item.id: item for item in members}
    raw_total = 0
    for item in anchors:
        item.__post_init__()
        member = member_by_id.get(item.member_id)
        if member is None or item.end_byte > member.byte_length:
            _fail("raw-source anchor range is outside its member")
        raw_total += len(item.raw_bytes)
    if (
        tuple(sorted(members)) != members
        or tuple(sorted(anchors)) != anchors
        or len(member_by_id) != len(members)
        or len({item.id for item in anchors}) != len(anchors)
        or len({item.source_ir_pointer for item in anchors}) != len(anchors)
        or len({(item.member_id, item.start_byte, item.end_byte) for item in anchors})
        != len(anchors)
        or raw_total > _MAX_RAW_BYTES
    ):
        _fail("raw-source payload records are noncanonical, duplicate, or over limit")
    output_sha, tool_sha, upstream = _preparation_lineage(preparation_receipt)
    return {
        "anchors": [item.to_data() for item in anchors],
        "artifact_digest": package_ref.artifact_digest,
        "authority_generation": authority.generation,
        "authority_id": authority.authority_id,
        "members": [item.to_data() for item in members],
        "occurrence_identity_sha256": root.occurrence_identity_sha256,
        "output_manifest_sha256": output_sha,
        "package_name": package_ref.package_name,
        "package_ref_id": package_ref.content_id,
        "preparation_receipt_sha256": preparation_receipt.content_id,
        "revision": RAW_SOURCE_COLLECTION_REVISION,
        "semantic_root_sha256": _semantic_root(anchors),
        "target_inventory_receipt_sha256": target_inventory.receipt_sha256,
        "target_root_id": root.content_id,
        "tool_lineage_sha256": tool_sha,
        "upstream_digests": dict(upstream),
        "version_code": package_ref.version_code,
    }


def raw_source_envelope_payload(payload: dict[str, object], signature: str) -> bytes:
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("raw-source signature is invalid")
    return _canonical(
        {"payload": payload, "schema": RAW_SOURCE_ENVELOPE_SCHEMA, "signature": signature}
    ) + b"\n"


def authenticate_raw_source_collection(
    envelope_bytes: bytes,
    *,
    package_ref: FrozenPackageRef,
    root: ApplicationRoot,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
) -> AuthenticatedRawSourceCollection:
    """Authenticate one exact raw collection against all upstream identities."""

    from tools.phase4_v2.equivalence.core import ApplicationRoot, validate_frozen_package_ref
    from tools.phase4_v2.equivalence.inventory import validate_target_inventory_envelope

    authority = load_protected_raw_source_authority()
    package_ref = validate_frozen_package_ref(package_ref)
    if type(root) is not ApplicationRoot:
        _fail("raw source requires an exact application root")
    root.__post_init__()
    if root.package_ref_id != package_ref.content_id:
        _fail("raw-source root belongs to another package")
    preparation_receipt = _validate_preparation(
        preparation_receipt, preparation_authority
    )
    target_inventory = validate_target_inventory_envelope(target_inventory)
    if target_inventory.package_ref != package_ref:
        _fail("raw-source target inventory belongs to another package")
    occurrence_matches = tuple(
        occurrence
        for occurrence in target_inventory.inventory.occurrences
        if occurrence.target_root_id == root.content_id
        and occurrence.occurrence_identity_sha256 == root.occurrence_identity_sha256
    )
    if len(occurrence_matches) != 1 or root.extractor_capability_id != target_inventory.extractor.content_id:
        _fail("raw-source root is absent from the authenticated target inventory")
    output_sha, tool_sha, upstream = _preparation_lineage(preparation_receipt)
    if (
        preparation_receipt.package_name,
        preparation_receipt.version_code,
        preparation_receipt.artifact_digest,
        preparation_receipt.preflight_manifest_sha256,
    ) != (
        package_ref.package_name,
        package_ref.version_code,
        package_ref.artifact_digest,
        package_ref.preflight_sha256,
    ):
        _fail("raw-source preparation receipt belongs to another package")
    envelope = _load_canonical(
        envelope_bytes, maximum=_MAX_ENVELOPE_BYTES, label="raw-source envelope"
    )
    envelope = _exact(envelope, {"payload", "schema", "signature"}, "raw-source envelope")
    if envelope["schema"] != RAW_SOURCE_ENVELOPE_SCHEMA:
        _fail("raw-source envelope schema is unsupported")
    signature = envelope["signature"]
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("raw-source signature is invalid")
    payload = _exact(
        envelope["payload"],
        {
            "anchors",
            "artifact_digest",
            "authority_id",
            "authority_generation",
            "members",
            "occurrence_identity_sha256",
            "output_manifest_sha256",
            "package_name",
            "package_ref_id",
            "preparation_receipt_sha256",
            "revision",
            "semantic_root_sha256",
            "target_inventory_receipt_sha256",
            "target_root_id",
            "tool_lineage_sha256",
            "upstream_digests",
            "version_code",
        },
        "raw-source payload",
    )
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), raw_source_signing_bytes(payload)
        )
    except (InvalidSignature, ValueError) as error:
        raise RawSourceAuthenticationError("raw-source signature verification failed") from error
    expected_identity = (
        authority.authority_id,
        authority.generation,
        package_ref.content_id,
        package_ref.package_name,
        package_ref.version_code,
        package_ref.artifact_digest,
        root.content_id,
        root.occurrence_identity_sha256,
        preparation_receipt.content_id,
        target_inventory.receipt_sha256,
        output_sha,
        tool_sha,
        dict(upstream),
        RAW_SOURCE_COLLECTION_REVISION,
    )
    actual_identity = (
        payload["authority_id"],
        payload["authority_generation"],
        payload["package_ref_id"],
        payload["package_name"],
        payload["version_code"],
        payload["artifact_digest"],
        payload["target_root_id"],
        payload["occurrence_identity_sha256"],
        payload["preparation_receipt_sha256"],
        payload["target_inventory_receipt_sha256"],
        payload["output_manifest_sha256"],
        payload["tool_lineage_sha256"],
        payload["upstream_digests"],
        payload["revision"],
    )
    if actual_identity != expected_identity:
        _fail("raw-source identity or upstream lineage differs from trusted inputs")
    raw_members = payload["members"]
    raw_anchors = payload["anchors"]
    if (
        type(raw_members) is not list
        or not raw_members
        or len(raw_members) > _MAX_MEMBERS
        or type(raw_anchors) is not list
        or not raw_anchors
        or len(raw_anchors) > _MAX_ANCHORS
    ):
        _fail("raw-source member or anchor collection is empty or exceeds its limit")
    members: list[RawSourceMember] = []
    output_lookup = {
        (index, item.path): item
        for index, invocation in enumerate(preparation_receipt.invocations)
        for item in invocation.outputs
    }
    for index, raw_member in enumerate(raw_members):
        item = _exact(
            raw_member,
            {"byte_length", "id", "invocation_index", "path", "sha256"},
            f"members[{index}]",
        )
        identifier = _token(item["id"], f"members[{index}].id")
        invocation_index = item["invocation_index"]
        byte_length = item["byte_length"]
        path = _path(item["path"], f"members[{index}].path")
        digest = _sha(item["sha256"], f"members[{index}].sha256")
        if type(invocation_index) is not int or not 0 <= invocation_index < len(preparation_receipt.invocations):
            _fail("raw-source member invocation index is invalid")
        if type(byte_length) is not int or not 0 <= byte_length <= 2**63 - 1:
            _fail("raw-source member byte length is invalid")
        output = output_lookup.get((invocation_index, path))
        if output is None or (output.sha256, output.bytes) != (digest, byte_length):
            _fail("raw-source member differs from accepted preparation output")
        members.append(RawSourceMember(identifier, invocation_index, path, digest, byte_length))
    if tuple(members) != tuple(sorted(members)) or len({item.id for item in members}) != len(members):
        _fail("raw-source members must be sorted with unique IDs")
    member_by_id = {item.id: item for item in members}
    anchors: list[RawSourceAnchor] = []
    raw_total = 0
    for index, raw_anchor in enumerate(raw_anchors):
        item = _exact(
            raw_anchor,
            {
                "decoded_value",
                "end_byte",
                "id",
                "member_id",
                "raw_hex",
                "representation",
                "source_ir_pointer",
                "start_byte",
                "value_sha256",
            },
            f"anchors[{index}]",
        )
        identifier = _token(item["id"], f"anchors[{index}].id")
        member_id = _token(item["member_id"], f"anchors[{index}].member_id")
        member = member_by_id.get(member_id)
        if member is None:
            _fail("raw-source anchor references an unknown member")
        start, end = item["start_byte"], item["end_byte"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= member.byte_length:
            _fail("raw-source anchor byte range is invalid")
        raw_hex = item["raw_hex"]
        if type(raw_hex) is not str or len(raw_hex) > _MAX_RAW_ANCHOR_BYTES * 2:
            _fail("raw-source anchor bytes exceed their limit")
        try:
            raw_bytes = bytes.fromhex(raw_hex)
        except ValueError as error:
            raise RawSourceAuthenticationError("raw-source anchor hex is invalid") from error
        if raw_bytes.hex() != raw_hex or len(raw_bytes) != end - start:
            _fail("raw-source anchor bytes do not match their exact range")
        raw_total += len(raw_bytes)
        if raw_total > _MAX_RAW_BYTES:
            _fail("raw-source anchor bytes exceed their aggregate limit")
        decoded = cast(JsonScalar, item["decoded_value"])
        canonical_scalar_bytes(decoded)
        representation = item["representation"]
        if representation == "utf8":
            try:
                reproduced: JsonScalar = raw_bytes.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise RawSourceAuthenticationError("raw-source UTF-8 anchor is invalid") from error
        elif representation == "hex":
            reproduced = raw_bytes.hex()
        elif representation == "json-scalar":
            try:
                scalar = json.loads(raw_bytes, object_pairs_hook=_unique_object)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                raise RawSourceAuthenticationError("raw-source JSON scalar is invalid") from error
            canonical_scalar_bytes(cast(JsonScalar, scalar))
            if canonical_scalar_bytes(cast(JsonScalar, scalar)) != raw_bytes:
                _fail("raw-source JSON scalar bytes are not canonical")
            reproduced = cast(JsonScalar, scalar)
        else:
            _fail("raw-source representation is unsupported")
        value_sha = _sha(item["value_sha256"], f"anchors[{index}].value_sha256")
        if reproduced != decoded or type(reproduced) is not type(decoded):
            _fail("raw-source decoded scalar does not reproduce from raw bytes")
        if canonical_scalar_sha256(decoded) != value_sha:
            _fail("raw-source decoded scalar digest is invalid")
        anchors.append(
            RawSourceAnchor(
                identifier,
                member_id,
                start,
                end,
                raw_bytes,
                cast(str, representation),
                decoded,
                value_sha,
                _pointer(item["source_ir_pointer"], f"anchors[{index}].source_ir_pointer"),
            )
        )
    if tuple(anchors) != tuple(sorted(anchors)) or len({item.id for item in anchors}) != len(anchors):
        _fail("raw-source anchors must be sorted with unique IDs")
    if len({item.source_ir_pointer for item in anchors}) != len(anchors):
        _fail("raw-source anchors contain duplicate semantic pointers")
    if len({(item.member_id, item.start_byte, item.end_byte) for item in anchors}) != len(anchors):
        _fail("raw-source anchors contain duplicate byte ranges")
    semantic_root_sha256 = _semantic_root(anchors)
    if payload["semantic_root_sha256"] != semantic_root_sha256:
        _fail("raw-source semantic root does not derive from the exact anchors")
    # Pin one authority for the complete parse, including across concurrent rotation.
    if load_protected_raw_source_authority() != authority:
        _fail("raw-source authority changed during authentication")
    result = object.__new__(AuthenticatedRawSourceCollection)
    values: dict[str, object] = {
        "authority": authority,
        "package_ref_id": package_ref.content_id,
        "package_name": package_ref.package_name,
        "version_code": package_ref.version_code,
        "artifact_digest": package_ref.artifact_digest,
        "target_root_id": root.content_id,
        "occurrence_identity_sha256": root.occurrence_identity_sha256,
        "preparation_receipt_sha256": preparation_receipt.content_id,
        "target_inventory_receipt_sha256": target_inventory.receipt_sha256,
        "output_manifest_sha256": output_sha,
        "tool_lineage_sha256": tool_sha,
        "semantic_root_sha256": semantic_root_sha256,
        "upstream_digests": upstream,
        "members": tuple(members),
        "anchors": tuple(anchors),
        "canonical_bytes": envelope_bytes,
        "receipt_sha256": hashlib.sha256(envelope_bytes).hexdigest(),
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def package_local_evidence_signing_bytes(payload: dict[str, object]) -> bytes:
    """Return domain-separated bytes for an external package-local signer."""

    return b"phase4-v2:signed-package-local-evidence\0" + _canonical(payload)


def _validated_package_local_records(
    *,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    members: tuple[PackageLocalEvidenceMember, ...],
    anchors: tuple[PackageLocalEvidenceAnchor, ...],
) -> tuple[tuple[str, ...], str]:
    from tools.phase4_v2.equivalence.core import LOCAL_ONLY_DOMAINS
    from tools.phase4_v2.equivalence.plan import (
        preparation_evidence_producer_capabilities,
    )

    if (
        type(members) is not tuple
        or not members
        or len(members) > _MAX_MEMBERS
        or any(type(item) is not PackageLocalEvidenceMember for item in members)
        or type(anchors) is not tuple
        or not anchors
        or len(anchors) > _MAX_ANCHORS
        or any(type(item) is not PackageLocalEvidenceAnchor for item in anchors)
    ):
        _fail("package-local evidence records are empty, over limit, or incorrectly typed")
    allowed = {
        (item.name, item.revision, item.digest)
        for item in preparation_evidence_producer_capabilities(
            preparation_receipt,
            preparation_authority,
        )
    }
    for member in members:
        member.__post_init__()
        if (
            member.producer_name,
            member.producer_revision,
            member.producer_digest,
        ) not in allowed:
            _fail("package-local member uses an unauthenticated producer route")
        matching_invocations = tuple(
            invocation
            for invocation in preparation_receipt.invocations
            if invocation.status == "COMPLETE"
            and invocation.route == member.producer_name
            and preparation_receipt.pipeline_revision == member.producer_revision
            and invocation.tool.binary_sha256 == member.producer_digest
            and hashlib.sha256(_canonical(invocation.to_data())).hexdigest()
            == member.invocation_sha256
            and sum(
                output.path == member.path
                and output.sha256 == member.sha256
                and output.bytes == member.byte_length
                for output in invocation.outputs
            )
            == 1
        )
        if len(matching_invocations) != 1:
            _fail("package-local member does not match one exact preparation output")
    for anchor in anchors:
        anchor.__post_init__()
    member_by_id = {item.id: item for item in members}
    raw_total = sum(len(item.raw.raw_bytes) for item in anchors)
    domains = tuple(sorted({item.local_domain for item in anchors}))
    if (
        tuple(sorted(members)) != members
        or tuple(sorted(anchors)) != anchors
        or len(member_by_id) != len(members)
        or len({item.path for item in members}) != len(members)
        or len({item.id for item in anchors}) != len(anchors)
        or len({item.raw.source_ir_pointer for item in anchors}) != len(anchors)
        or len({item.terminal_ir_pointer for item in anchors}) != len(anchors)
        or len({(item.member_id, item.raw.start_byte, item.raw.end_byte) for item in anchors})
        != len(anchors)
        or any(
            item.member_id not in member_by_id
            or item.raw.end_byte > member_by_id[item.member_id].byte_length
            for item in anchors
        )
        or {item.member_id for item in anchors} != set(member_by_id)
        or raw_total > _MAX_RAW_BYTES
        or domains != tuple(sorted(LOCAL_ONLY_DOMAINS))
    ):
        _fail("package-local evidence is not an exact canonical local-domain closure")
    output_manifest_sha256 = hashlib.sha256(
        _canonical([item.to_data() for item in members])
    ).hexdigest()
    return domains, output_manifest_sha256


def _package_local_payload(
    *,
    authority: ActivatedRawSourceAuthority,
    package_ref: FrozenPackageRef,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    members: tuple[PackageLocalEvidenceMember, ...],
    anchors: tuple[PackageLocalEvidenceAnchor, ...],
) -> dict[str, object]:
    from tools.phase4_v2.equivalence.core import validate_frozen_package_ref
    from tools.phase4_v2.equivalence.inventory import validate_target_inventory_envelope

    package_ref = validate_frozen_package_ref(package_ref)
    preparation_receipt = _validate_preparation(preparation_receipt, preparation_authority)
    target_inventory = validate_target_inventory_envelope(target_inventory)
    if (
        target_inventory.package_ref != package_ref
        or (
            preparation_receipt.package_name,
            preparation_receipt.version_code,
            preparation_receipt.artifact_digest,
            preparation_receipt.preflight_manifest_sha256,
        )
        != (
            package_ref.package_name,
            package_ref.version_code,
            package_ref.artifact_digest,
            package_ref.preflight_sha256,
        )
    ):
        _fail("package-local evidence upstream identity belongs to another package")
    domains, output_sha = _validated_package_local_records(
        preparation_receipt=preparation_receipt,
        preparation_authority=preparation_authority,
        members=members,
        anchors=anchors,
    )
    _preparation_output_sha, tool_sha, upstream = _preparation_lineage(preparation_receipt)
    return {
        "anchors": [item.to_data() for item in anchors],
        "artifact_digest": package_ref.artifact_digest,
        "authority_generation": authority.generation,
        "authority_id": authority.authority_id,
        "mandatory_domains": list(domains),
        "members": [item.to_data() for item in members],
        "output_manifest_sha256": output_sha,
        "package_name": package_ref.package_name,
        "package_ref_id": package_ref.content_id,
        "preparation_receipt_sha256": preparation_receipt.content_id,
        "revision": PACKAGE_LOCAL_EVIDENCE_REVISION,
        "target_inventory_receipt_sha256": target_inventory.receipt_sha256,
        "tool_lineage_sha256": tool_sha,
        "upstream_digests": dict(upstream),
        "version_code": package_ref.version_code,
    }


def package_local_evidence_payload(
    *,
    package_ref: FrozenPackageRef,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    members: tuple[PackageLocalEvidenceMember, ...],
    anchors: tuple[PackageLocalEvidenceAnchor, ...],
) -> dict[str, object]:
    """Render raw-authority data for target package-local execution outputs.

    By signing, the external authority attests that every retained byte range is
    an exact slice of the named output produced by its pinned invocation.
    """

    authority = load_protected_raw_source_authority()
    payload = _package_local_payload(
        authority=authority,
        package_ref=package_ref,
        preparation_receipt=preparation_receipt,
        preparation_authority=preparation_authority,
        target_inventory=target_inventory,
        members=members,
        anchors=anchors,
    )
    if load_protected_raw_source_authority() != authority:
        _fail("raw-source authority changed while building package-local evidence")
    return payload


def package_local_evidence_envelope_payload(
    payload: dict[str, object], signature: str
) -> bytes:
    """Wrap signed package-local evidence in its canonical envelope."""

    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("package-local evidence signature is invalid")
    return _canonical(
        {
            "payload": payload,
            "schema": PACKAGE_LOCAL_EVIDENCE_ENVELOPE_SCHEMA,
            "signature": signature,
        }
    ) + b"\n"


def _parse_package_local_records(
    payload: dict[str, object],
) -> tuple[
    tuple[PackageLocalEvidenceMember, ...], tuple[PackageLocalEvidenceAnchor, ...]
]:
    raw_members = payload["members"]
    raw_anchors = payload["anchors"]
    if type(raw_members) is not list or type(raw_anchors) is not list:
        _fail("package-local member and anchor records must be arrays")
    members = tuple(
        PackageLocalEvidenceMember(
            _token(item["id"], f"members[{index}].id"),
            _path(item["path"], f"members[{index}].path"),
            _sha(item["sha256"], f"members[{index}].sha256"),
            cast(int, item["byte_length"]),
            _token(item["producer_name"], f"members[{index}].producer_name"),
            _token(item["producer_revision"], f"members[{index}].producer_revision"),
            _sha(item["producer_digest"], f"members[{index}].producer_digest"),
            _sha(item["invocation_sha256"], f"members[{index}].invocation_sha256"),
        )
        for index, raw in enumerate(raw_members)
        for item in (
            _exact(
                raw,
                {
                    "byte_length",
                    "id",
                    "invocation_sha256",
                    "path",
                    "producer_digest",
                    "producer_name",
                    "producer_revision",
                    "sha256",
                },
                f"members[{index}]",
            ),
        )
    )
    anchors = tuple(
        PackageLocalEvidenceAnchor(
            RawSourceAnchor(
                _token(item["id"], f"anchors[{index}].id"),
                _token(item["member_id"], f"anchors[{index}].member_id"),
                cast(int, item["start_byte"]),
                cast(int, item["end_byte"]),
                bytes.fromhex(cast(str, item["raw_hex"])),
                cast(str, item["representation"]),
                cast(JsonScalar, item["decoded_value"]),
                _sha(item["value_sha256"], f"anchors[{index}].value_sha256"),
                _pointer(item["source_ir_pointer"], f"anchors[{index}].source_ir_pointer"),
            ),
            _token(item["local_domain"], f"anchors[{index}].local_domain"),
            _pointer(item["terminal_ir_pointer"], f"anchors[{index}].terminal_ir_pointer"),
        )
        for index, raw in enumerate(raw_anchors)
        for item in (
            _exact(
                raw,
                {
                    "decoded_value",
                    "end_byte",
                    "id",
                    "local_domain",
                    "member_id",
                    "raw_hex",
                    "representation",
                    "source_ir_pointer",
                    "start_byte",
                    "terminal_ir_pointer",
                    "value_sha256",
                },
                f"anchors[{index}]",
            ),
        )
    )
    return members, anchors


def authenticate_package_local_evidence(
    envelope_bytes: bytes,
    *,
    package_ref: FrozenPackageRef,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
) -> AuthenticatedPackageLocalEvidence:
    """Authenticate one exact target package-local raw-evidence receipt."""

    authority = load_protected_raw_source_authority()
    envelope = _exact(
        _load_canonical(
            envelope_bytes,
            maximum=_MAX_ENVELOPE_BYTES,
            label="package-local evidence envelope",
        ),
        {"payload", "schema", "signature"},
        "package-local evidence envelope",
    )
    if envelope["schema"] != PACKAGE_LOCAL_EVIDENCE_ENVELOPE_SCHEMA:
        _fail("package-local evidence envelope schema is unsupported")
    payload = _exact(
        envelope["payload"],
        {
            "anchors",
            "artifact_digest",
            "authority_generation",
            "authority_id",
            "mandatory_domains",
            "members",
            "output_manifest_sha256",
            "package_name",
            "package_ref_id",
            "preparation_receipt_sha256",
            "revision",
            "target_inventory_receipt_sha256",
            "tool_lineage_sha256",
            "upstream_digests",
            "version_code",
        },
        "package-local evidence payload",
    )
    signature = envelope["signature"]
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        _fail("package-local evidence signature is invalid")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), package_local_evidence_signing_bytes(payload)
        )
    except (InvalidSignature, ValueError) as error:
        raise RawSourceAuthenticationError(
            "package-local evidence signature verification failed"
        ) from error
    try:
        members, anchors = _parse_package_local_records(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise RawSourceAuthenticationError(
            "package-local evidence records are invalid"
        ) from error
    expected = _package_local_payload(
        authority=authority,
        package_ref=package_ref,
        preparation_receipt=preparation_receipt,
        preparation_authority=preparation_authority,
        target_inventory=target_inventory,
        members=members,
        anchors=anchors,
    )
    if payload != expected:
        _fail("package-local evidence differs from its authenticated inputs")
    if load_protected_raw_source_authority() != authority:
        _fail("raw-source authority changed during package-local authentication")
    result = object.__new__(AuthenticatedPackageLocalEvidence)
    for name, value in {
        "authority": authority,
        "package_ref_id": expected["package_ref_id"],
        "package_name": expected["package_name"],
        "version_code": expected["version_code"],
        "artifact_digest": expected["artifact_digest"],
        "preparation_receipt_sha256": expected["preparation_receipt_sha256"],
        "target_inventory_receipt_sha256": expected[
            "target_inventory_receipt_sha256"
        ],
        "output_manifest_sha256": expected["output_manifest_sha256"],
        "tool_lineage_sha256": expected["tool_lineage_sha256"],
        "upstream_digests": tuple(cast(dict[str, str], expected["upstream_digests"]).items()),
        "mandatory_domains": tuple(cast(list[str], expected["mandatory_domains"])),
        "members": members,
        "anchors": anchors,
        "canonical_bytes": envelope_bytes,
        "receipt_sha256": hashlib.sha256(envelope_bytes).hexdigest(),
    }.items():
        object.__setattr__(result, name, value)
    return result


def reauthenticate_package_local_evidence(
    evidence: AuthenticatedPackageLocalEvidence,
    *,
    inputs: PackageLocalEvidenceReauthenticationInput,
) -> AuthenticatedPackageLocalEvidence:
    """Reauthenticate retained package-local evidence at a consumer boundary."""

    if type(evidence) is not AuthenticatedPackageLocalEvidence:
        _fail("package-local evidence must use the exact authenticated type")
    if type(inputs) is not tuple or len(inputs) != 4:
        _fail("package-local evidence inputs must use one exact immutable tuple")
    restored = authenticate_package_local_evidence(
        evidence.canonical_bytes,
        package_ref=inputs[0],
        preparation_receipt=inputs[1],
        preparation_authority=inputs[2],
        target_inventory=inputs[3],
    )
    if restored != evidence:
        _fail("package-local evidence changed after authentication")
    return restored


def validate_authenticated_raw_source_collection(
    collection: AuthenticatedRawSourceCollection,
    *,
    package_ref: FrozenPackageRef,
    root: ApplicationRoot,
    preparation_receipt: PreparationReceipt,
    preparation_authority: ActivatedPreparationAuthority,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
) -> AuthenticatedRawSourceCollection:
    """Reauthenticate one retained collection and reject mutable-object drift."""

    if type(collection) is not AuthenticatedRawSourceCollection:
        _fail("exact authenticated raw-source collection is required")
    restored = authenticate_raw_source_collection(
        collection.canonical_bytes,
        package_ref=package_ref,
        root=root,
        preparation_receipt=preparation_receipt,
        preparation_authority=preparation_authority,
        target_inventory=target_inventory,
    )
    if restored != collection:
        _fail("raw-source collection changed after authentication")
    return restored


def build_authenticated_raw_source_registry(
    entries: tuple[
        tuple[
            bytes,
            FrozenPackageRef,
            ApplicationRoot,
            PreparationReceipt,
            ActivatedPreparationAuthority,
            AuthenticatedTargetInventoryEnvelope,
        ], ...
    ],
) -> AuthenticatedRawSourceRegistry:
    """Build an exact immutable registry, reloading authority for every entry."""

    if (
        type(entries) is not tuple
        or not entries
        or len(entries) > _MAX_REGISTRY_COLLECTIONS
    ):
        _fail("raw-source registry must be a bounded non-empty tuple")
    authority = load_protected_raw_source_authority()
    accepted: list[AuthenticatedRawSourceCollection] = []
    envelope_bytes = 0
    member_count = 0
    anchor_count = 0
    raw_bytes = 0
    for entry in entries:
        if type(entry) is not tuple or len(entry) != 6:
            _fail("raw-source registry entries must be exact six-tuples")
        envelope, package_ref, root, receipt, prep_authority, inventory = entry
        if type(envelope) is not bytes:
            _fail("raw-source registry envelopes must be exact bytes")
        envelope_bytes += len(envelope)
        if envelope_bytes > _MAX_REGISTRY_ENVELOPE_BYTES:
            _fail("raw-source registry exceeds its aggregate envelope byte limit")
        authenticated = authenticate_raw_source_collection(
            envelope,
            package_ref=package_ref,
            root=root,
            preparation_receipt=receipt,
            preparation_authority=prep_authority,
            target_inventory=inventory,
        )
        if authenticated.authority != authority:
            _fail("raw-source registry spans multiple authority activations")
        member_count += len(authenticated.members)
        anchor_count += len(authenticated.anchors)
        raw_bytes += sum(len(anchor.raw_bytes) for anchor in authenticated.anchors)
        if member_count > _MAX_REGISTRY_MEMBERS:
            _fail("raw-source registry exceeds its aggregate member limit")
        if anchor_count > _MAX_REGISTRY_ANCHORS:
            _fail("raw-source registry exceeds its aggregate anchor limit")
        if raw_bytes > _MAX_REGISTRY_RAW_BYTES:
            _fail("raw-source registry exceeds its aggregate raw byte limit")
        accepted.append(authenticated)
    accepted.sort(key=lambda item: (item.package_ref_id, item.occurrence_identity_sha256))
    if len({item.receipt_sha256 for item in accepted}) != len(accepted):
        _fail("raw-source registry contains duplicate receipts")
    if len({(item.package_ref_id, item.target_root_id) for item in accepted}) != len(accepted):
        _fail("raw-source registry contains duplicate package roots")
    package_pointers = [
        (item.package_ref_id, anchor.source_ir_pointer)
        for item in accepted
        for anchor in item.anchors
    ]
    if len(set(package_pointers)) != len(package_pointers):
        _fail("raw-source registry contains duplicate package semantic pointers")
    if load_protected_raw_source_authority() != authority:
        _fail("raw-source authority changed while building the registry")
    result = object.__new__(AuthenticatedRawSourceRegistry)
    object.__setattr__(result, "entries", tuple(accepted))
    return result


def reauthenticate_raw_source_registry(
    registry: AuthenticatedRawSourceRegistry,
    *,
    inputs: tuple[RawSourceReauthenticationInput, ...],
) -> AuthenticatedRawSourceRegistry:
    """Reauthenticate retained envelope bytes at a later validator/IR boundary."""

    if (
        type(registry) is not AuthenticatedRawSourceRegistry
        or type(registry.entries) is not tuple
        or not registry.entries
        or len(registry.entries) > _MAX_REGISTRY_COLLECTIONS
        or type(inputs) is not tuple
        or not inputs
        or len(inputs) > _MAX_REGISTRY_COLLECTIONS
    ):
        _fail("raw-source reauthentication inputs are missing or not exact immutable records")
    if any(type(item) is not tuple or len(item) != 5 for item in inputs):
        _fail("raw-source reauthentication inputs must be exact five-tuples")
    by_identity = {
        (package.content_id, root.content_id): (
            package,
            root,
            receipt,
            preparation_authority,
            inventory,
        )
        for package, root, receipt, preparation_authority, inventory in inputs
    }
    if len(by_identity) != len(inputs):
        _fail("raw-source reauthentication inputs contain duplicates")
    entries: list[
        tuple[
            bytes,
            FrozenPackageRef,
            ApplicationRoot,
            PreparationReceipt,
            ActivatedPreparationAuthority,
            AuthenticatedTargetInventoryEnvelope,
        ]
    ] = []
    for item in registry.entries:
        trusted = by_identity.get((item.package_ref_id, item.target_root_id))
        if trusted is None:
            _fail("raw-source registry contains an unexpected or missing-input package root")
        restored = validate_authenticated_raw_source_collection(
            item,
            package_ref=trusted[0],
            root=trusted[1],
            preparation_receipt=trusted[2],
            preparation_authority=trusted[3],
            target_inventory=trusted[4],
        )
        entries.append((restored.canonical_bytes, *trusted))
    if len(entries) != len(inputs):
        _fail("raw-source registry is missing a required package root")
    return build_authenticated_raw_source_registry(tuple(entries))
