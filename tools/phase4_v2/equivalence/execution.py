"""Protected signer boundary for validated package execution outputs."""

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

from .core import EquivalenceError, _canonical_json_document, _security_stat

EXECUTION_AUTHORITY_SCHEMA = "phase4-v2-validator-execution-authority-v1"
EXECUTION_AUTHORITY_PIN_SCHEMA = "phase4-v2-validator-execution-authority-pin-v1"
EXECUTION_ENVELOPE_SCHEMA = "phase4-v2-authenticated-validator-execution-v1"
EXECUTION_AUTHORITY_CAPABILITY = "phase4-v2-validator-execution-authority"
_PIN_PATH = Path("/etc/ha-adjustable-bed/phase4-v2-validator-execution-authority.pin.json")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ExecutionAuthenticationError(ValueError):
    """Validator execution authentication failed closed."""


def _document(
    payload: bytes, *, trailing_newline: bool = False, maximum_bytes: int = 16 * 1024 * 1024
) -> dict[str, object]:
    try:
        return _canonical_json_document(
            payload, "execution JSON", trailing_newline=trailing_newline,
            maximum_bytes=maximum_bytes,
        )
    except EquivalenceError as error:
        raise ExecutionAuthenticationError(str(error)) from error


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _sha(value: object, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ExecutionAuthenticationError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True, init=False)
class ActivatedExecutionAuthority:
    authority_id: str
    public_key: str
    generation: int
    canonical_bytes: bytes
    activation_sha256: str

    def __init__(self) -> None:
        raise ExecutionAuthenticationError("execution authorities require protected activation")


def execution_authority_payload(*, authority_id: str, public_key: str, generation: int) -> bytes:
    return (
        _canonical(
            {
                "authority_id": authority_id,
                "generation": generation,
                "public_key": public_key,
                "schema": EXECUTION_AUTHORITY_SCHEMA,
            }
        )
        + b"\n"
    )


def execution_authority_pin_payload(authority_payload: bytes) -> bytes:
    return (
        _canonical(
            {
                "activation_sha256": hashlib.sha256(authority_payload).hexdigest(),
                "schema": EXECUTION_AUTHORITY_PIN_SCHEMA,
            }
        )
        + b"\n"
    )


def _read_protected_execution_pin() -> str:
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
            raise ExecutionAuthenticationError("execution authority directory is not protected")
        descriptor = os.open(
            _PIN_PATH.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_descriptor,
        )
        metadata = os.fstat(descriptor)
        if (
            metadata.st_uid != 0
            or metadata.st_mode & 0o222
            or metadata.st_nlink != 1
            or not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= 4096
        ):
            raise ExecutionAuthenticationError("execution authority pin is not protected")
        payload = os.read(descriptor, 4097)
        if (
            len(payload) != metadata.st_size
            or _security_stat(metadata) != _security_stat(os.fstat(descriptor))
            or _security_stat(directory) != _security_stat(os.fstat(directory_descriptor))
        ):
            raise ExecutionAuthenticationError("execution authority pin changed while reading")
    except OSError as error:
        raise ExecutionAuthenticationError(
            "protected execution authority pin is unavailable"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    try:
        raw = _document(payload, trailing_newline=True, maximum_bytes=4096)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionAuthenticationError("execution authority pin is invalid") from error
    if type(raw) is not dict or set(raw) != {"activation_sha256", "schema"}:
        raise ExecutionAuthenticationError("execution authority pin has unexpected fields")
    if raw["schema"] != EXECUTION_AUTHORITY_PIN_SCHEMA:
        raise ExecutionAuthenticationError("execution authority pin schema is unsupported")
    return _sha(raw["activation_sha256"], "execution authority activation")


def load_activated_execution_authority(payload: bytes) -> ActivatedExecutionAuthority:
    if type(payload) is not bytes or not payload.endswith(b"\n"):
        raise ExecutionAuthenticationError("execution authority must be canonical newline JSON")
    try:
        raw = _document(payload, trailing_newline=True, maximum_bytes=4096)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionAuthenticationError("execution authority is invalid") from error
    if (
        type(raw) is not dict
        or set(raw) != {"authority_id", "generation", "public_key", "schema"}
        or _canonical(raw) + b"\n" != payload
    ):
        raise ExecutionAuthenticationError("execution authority is not canonical")
    activation = hashlib.sha256(payload).hexdigest()
    if activation != _read_protected_execution_pin():
        raise ExecutionAuthenticationError("execution authority differs from protected activation")
    authority_id, public_key, generation = (
        raw["authority_id"],
        raw["public_key"],
        raw["generation"],
    )
    if raw["schema"] != EXECUTION_AUTHORITY_SCHEMA:
        raise ExecutionAuthenticationError("execution authority schema is unsupported")
    if type(authority_id) is not str or not authority_id or len(authority_id) > 200:
        raise ExecutionAuthenticationError("execution authority ID is invalid")
    if type(public_key) is not str or re.fullmatch(r"[0-9a-f]{64}", public_key) is None:
        raise ExecutionAuthenticationError("execution authority public key is invalid")
    if type(generation) is not int or generation < 1:
        raise ExecutionAuthenticationError("execution authority generation is invalid")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
    result = object.__new__(ActivatedExecutionAuthority)
    for name, value in (
        ("authority_id", authority_id),
        ("public_key", public_key),
        ("generation", generation),
        ("canonical_bytes", payload),
        ("activation_sha256", activation),
    ):
        object.__setattr__(result, name, value)
    return result


def _reauthorize(authority: ActivatedExecutionAuthority) -> ActivatedExecutionAuthority:
    if type(authority) is not ActivatedExecutionAuthority:
        raise ExecutionAuthenticationError("exact activated execution authority is required")
    restored = load_activated_execution_authority(authority.canonical_bytes)
    if restored != authority:
        raise ExecutionAuthenticationError("execution authority changed after activation")
    return restored


def execution_authority_capability(authority: ActivatedExecutionAuthority) -> tuple[str, str, str]:
    authority = _reauthorize(authority)
    return (
        EXECUTION_AUTHORITY_CAPABILITY,
        f"{EXECUTION_AUTHORITY_SCHEMA}:generation:{authority.generation}",
        authority.activation_sha256,
    )


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedPackageExecutionEnvelope:
    authority: ActivatedExecutionAuthority
    canonical_bytes: bytes
    receipt_bytes: bytes
    receipt_sha256: str
    package_ref_id: str
    execution_plan_sha256: str
    execution_plan_id: str
    output_content_id: str
    report_bundle_sha256: str
    corpus_sha256: str
    evidence_lineage_sha256: str
    ir_sha256: str

    def __init__(self) -> None:
        raise ExecutionAuthenticationError("execution envelopes require signature verification")


def execution_envelope_signing_bytes(payload: dict[str, object]) -> bytes:
    return b"phase4-v2:signed-validator-execution\0" + _canonical(payload)


def execution_envelope_payload(
    *,
    authority: ActivatedExecutionAuthority,
    receipt_bytes: bytes,
    package_ref_id: str,
    execution_plan_sha256: str,
    execution_plan_id: str,
    output_content_id: str,
    report_bundle_sha256: str,
    corpus_sha256: str,
    evidence_lineage_sha256: str,
    ir_sha256: str,
    signature: str,
) -> bytes:
    authority = _reauthorize(authority)
    try:
        receipt = _document(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionAuthenticationError("execution receipt is invalid") from error
    if _canonical(receipt) != receipt_bytes:
        raise ExecutionAuthenticationError("execution receipt is not canonical")
    payload = {
        "authority_sha256": authority.activation_sha256,
        "corpus_sha256": _sha(corpus_sha256, "corpus"),
        "evidence_lineage_sha256": _sha(evidence_lineage_sha256, "evidence lineage"),
        "execution_plan_id": _sha(execution_plan_id, "execution plan ID"),
        "execution_plan_sha256": _sha(execution_plan_sha256, "execution plan"),
        "ir_sha256": _sha(ir_sha256, "IR"),
        "output_content_id": _sha(output_content_id, "output"),
        "package_ref_id": _sha(package_ref_id, "package reference"),
        "receipt": receipt,
        "report_bundle_sha256": _sha(report_bundle_sha256, "report bundle"),
        "schema": EXECUTION_ENVELOPE_SCHEMA,
    }
    return _canonical({"payload": payload, "signature": signature})


def load_authenticated_package_execution_envelope(
    canonical_bytes: bytes,
    *,
    authority: ActivatedExecutionAuthority,
) -> AuthenticatedPackageExecutionEnvelope:
    authority = _reauthorize(authority)
    try:
        document = _document(canonical_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionAuthenticationError("execution envelope is invalid") from error
    if (
        type(document) is not dict
        or set(document) != {"payload", "signature"}
        or _canonical(document) != canonical_bytes
    ):
        raise ExecutionAuthenticationError("execution envelope is not canonical")
    payload, signature = document["payload"], document["signature"]
    if (
        type(payload) is not dict
        or type(signature) is not str
        or re.fullmatch(r"[0-9a-f]{128}", signature) is None
    ):
        raise ExecutionAuthenticationError("execution envelope shape is invalid")
    expected_fields = {
        "authority_sha256",
        "corpus_sha256",
        "evidence_lineage_sha256",
        "execution_plan_id",
        "execution_plan_sha256",
        "ir_sha256",
        "output_content_id",
        "package_ref_id",
        "receipt",
        "report_bundle_sha256",
        "schema",
    }
    if (
        set(payload) != expected_fields
        or payload.get("schema") != EXECUTION_ENVELOPE_SCHEMA
        or payload.get("authority_sha256") != authority.activation_sha256
    ):
        raise ExecutionAuthenticationError("execution envelope fields are invalid")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), execution_envelope_signing_bytes(payload)
        )
    except InvalidSignature as error:
        raise ExecutionAuthenticationError("execution envelope signature is invalid") from error
    receipt = payload["receipt"]
    if type(receipt) is not dict:
        raise ExecutionAuthenticationError("execution envelope receipt is invalid")
    receipt_bytes = _canonical(receipt)
    result = object.__new__(AuthenticatedPackageExecutionEnvelope)
    values = {
        "authority": authority,
        "canonical_bytes": canonical_bytes,
        "receipt_bytes": receipt_bytes,
        "receipt_sha256": _sha(receipt.get("validation_receipt_sha256"), "receipt"),
        **{
            name: _sha(payload[name], name)
            for name in expected_fields - {"authority_sha256", "receipt", "schema"}
        },
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    _reauthorize(authority)
    return result


def validate_package_execution_envelope(
    envelope: AuthenticatedPackageExecutionEnvelope,
) -> AuthenticatedPackageExecutionEnvelope:
    if type(envelope) is not AuthenticatedPackageExecutionEnvelope:
        raise ExecutionAuthenticationError("exact authenticated execution envelope is required")
    restored = load_authenticated_package_execution_envelope(
        envelope.canonical_bytes, authority=envelope.authority
    )
    if restored != envelope:
        raise ExecutionAuthenticationError("execution envelope changed after authentication")
    return restored


def validate_authenticated_package_output(
    output: object,
    envelope: AuthenticatedPackageExecutionEnvelope,
) -> object:
    """Reauthenticate an output, including its retained root provenance."""

    from .plan import ValidatedPackageOutput

    envelope = validate_package_execution_envelope(envelope)
    if type(output) is not ValidatedPackageOutput:
        raise ExecutionAuthenticationError("exact validated package output is required")
    if (
        output.content_id != envelope.output_content_id
        or output.target_package_ref_id != envelope.package_ref_id
        or output.execution_plan_id != envelope.execution_plan_id
        or output.validation_receipt_sha256 != envelope.receipt_sha256
        or output.target_report_sha256 != envelope.report_bundle_sha256
        or output.target_final_ir_json_sha256 != envelope.ir_sha256
    ):
        raise ExecutionAuthenticationError("package output differs from its signed envelope")
    _reauthorize(envelope.authority)
    return output
