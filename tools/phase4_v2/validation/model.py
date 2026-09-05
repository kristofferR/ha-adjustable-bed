"""Immutable bridge records for Phase 4 v2 completion validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum

from tools.phase4_v2.preflight import CandidateRecord, InvocationRecord, WarningRecord

VALIDATION_REVISION = "phase4-v2-completeness-validation-v2"
ADAPTER_REVISION = "phase4-v2-completion-adapter-v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_MAX_ITEMS = 250_000
_MAX_TEXT = 8_192


class ValidationError(ValueError):
    """A validation input does not satisfy the bounded typed contract."""


class WarningStatus(StrEnum):
    """The exhaustive decision for a preparation warning."""

    ACCEPTED = "ACCEPTED"
    BLOCKING = "BLOCKING"
    RESOLVED = "RESOLVED"


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _token(value: object, field: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValidationError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_TEXT:
        raise ValidationError(f"{field} must be a non-empty bounded string")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValidationError(f"{field} contains a control character")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValidationError(f"{field} is not valid Unicode") from error
    return value


def _bounded_exact_string(value: object, maximum: int, field: str) -> str:
    if type(value) is not str or not value:
        raise ValidationError(f"{field} must be an exact bounded string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValidationError(f"{field} is not valid Unicode") from error
    if len(encoded) > maximum:
        raise ValidationError(f"{field} must be an exact bounded string")
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ValidationError("value is not canonical JSON") from error


def _content_id(domain: str, value: object) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + _canonical_json(value)).hexdigest()


def candidate_occurrence_id(value: CandidateRecord) -> str:
    """Identify one exact preparation candidate without depending on IR internals."""
    if type(value) is not CandidateRecord:
        raise ValidationError("candidate must use the exact public CandidateRecord type")
    for field, maximum in (
        ("invocation_cache_key", 64),
        ("member", 4_096),
        ("route", 200),
        ("output_path", 4_096),
        ("output_sha256", 64),
        ("signal", 200),
    ):
        _bounded_exact_string(getattr(value, field), maximum, f"candidate.{field}")
    _digest(value.invocation_cache_key, "candidate.invocation_cache_key")
    _digest(value.output_sha256, "candidate.output_sha256")
    if (
        type(value.start_byte) is not int
        or type(value.end_byte) is not int
        or not 0 <= value.start_byte < value.end_byte <= 2**63 - 1
    ):
        raise ValidationError("candidate byte range is invalid")
    return _content_id("phase4-v2:candidate-occurrence", value.to_data())


def warning_occurrence_id(invocation: InvocationRecord, value: WarningRecord) -> str:
    """Identify a warning occurrence, including its invocation-local provenance."""
    if type(invocation) is not InvocationRecord or type(value) is not WarningRecord:
        raise ValidationError("warning identity requires exact public execution record types")
    for field, maximum in (("member", 4_096), ("route", 200)):
        _bounded_exact_string(getattr(invocation, field), maximum, f"invocation.{field}")
    if invocation.cache_key is not None:
        _digest(invocation.cache_key, "invocation.cache_key")
    if type(value.stream) is not str or value.stream not in {"stdout", "stderr"}:
        raise ValidationError("warning stream is invalid")
    if type(value.line) is not int or not 1 <= value.line <= 2**31 - 1:
        raise ValidationError("warning line is invalid")
    try:
        text_valid = type(value.text) is str and len(value.text.encode("utf-8")) <= 16 * 1024
    except UnicodeEncodeError:
        text_valid = False
    if not text_valid:
        raise ValidationError("warning text is invalid")
    _digest(value.sha256, "warning.sha256")
    return _content_id(
        "phase4-v2:warning-occurrence",
        {
            "invocation_cache_key": invocation.cache_key,
            "member": invocation.member,
            "route": invocation.route,
            "warning": value.to_data(),
        },
    )


@dataclass(frozen=True, slots=True, order=True)
class CandidateLink:
    """A bijective link from one preparation occurrence to one report item."""

    occurrence_id: str
    report_item_id: str

    def __post_init__(self) -> None:
        _digest(self.occurrence_id, "candidate_link.occurrence_id")
        _token(self.report_item_id, "candidate_link.report_item_id")

    def to_data(self) -> dict[str, str]:
        return {"occurrence_id": self.occurrence_id, "report_item_id": self.report_item_id}


@dataclass(frozen=True, slots=True, order=True)
class WarningDisposition:
    """An explicit, evidenced decision for one preparation warning."""

    occurrence_id: str
    status: WarningStatus
    reason_code: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _digest(self.occurrence_id, "warning_disposition.occurrence_id")
        if type(self.status) is not WarningStatus:
            raise ValidationError("warning_disposition.status must use WarningStatus")
        _token(self.reason_code, "warning_disposition.reason_code")
        _digest(self.evidence_sha256, "warning_disposition.evidence_sha256")

    def to_data(self) -> dict[str, str]:
        return {
            "evidence_sha256": self.evidence_sha256,
            "occurrence_id": self.occurrence_id,
            "reason_code": self.reason_code,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class CompletionAdapter:
    """Narrow boundary between preparation records and a normalized report."""

    target_package_ref_id: str
    candidate_links: tuple[CandidateLink, ...]
    warning_dispositions: tuple[WarningDisposition, ...]
    revision: str = ADAPTER_REVISION

    def __post_init__(self) -> None:
        _digest(self.target_package_ref_id, "adapter.target_package_ref_id")
        if self.revision != ADAPTER_REVISION:
            raise ValidationError("adapter revision is unsupported")
        if type(self.candidate_links) is not tuple or len(self.candidate_links) > _MAX_ITEMS:
            raise ValidationError("adapter candidate links must be a bounded tuple")
        if (
            type(self.warning_dispositions) is not tuple
            or len(self.warning_dispositions) > _MAX_ITEMS
        ):
            raise ValidationError("adapter warning dispositions must be a bounded tuple")
        if any(type(item) is not CandidateLink for item in self.candidate_links):
            raise ValidationError("adapter candidate links contain an invalid record")
        if any(type(item) is not WarningDisposition for item in self.warning_dispositions):
            raise ValidationError("adapter warning dispositions contain an invalid record")
        for item in self.candidate_links:
            item.__post_init__()
        for item in self.warning_dispositions:
            item.__post_init__()
        if self.candidate_links != tuple(sorted(self.candidate_links)):
            raise ValidationError("adapter candidate links must be sorted")
        if self.warning_dispositions != tuple(sorted(self.warning_dispositions)):
            raise ValidationError("adapter warning dispositions must be sorted")
        occurrences = [item.occurrence_id for item in self.candidate_links]
        report_items = [item.report_item_id for item in self.candidate_links]
        warnings = [item.occurrence_id for item in self.warning_dispositions]
        if len(set(occurrences)) != len(occurrences):
            raise ValidationError("adapter candidate occurrences must be unique")
        if len(set(report_items)) != len(report_items):
            raise ValidationError("adapter report candidate IDs must be unique")
        if len(set(warnings)) != len(warnings):
            raise ValidationError("adapter warning occurrences must be unique")

    def payload_data(self) -> dict[str, object]:
        return {
            "candidate_links": [item.to_data() for item in self.candidate_links],
            "revision": self.revision,
            "target_package_ref_id": self.target_package_ref_id,
            "warning_dispositions": [item.to_data() for item in self.warning_dispositions],
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:completion-adapter", self.payload_data())


@dataclass(frozen=True, slots=True)
class ValidationPins:
    """Externally trusted digests for every consumed input and rendered output."""

    preparation_receipt_sha256: str
    preflight_manifest_sha256: str
    preparation_manifest_sha256: str
    candidate_index_sha256: str
    candidate_contract_sha256: str
    preparation_authority_sha256: str
    tool_registry_sha256: str
    execution_profile_sha256: str
    execution_plan_sha256: str
    validated_package_output_sha256: str
    reconciliation_input_sha256: str
    reconciliation_result_sha256: str
    reconciliation_json_sha256: str
    reconciliation_markdown_sha256: str
    completion_adapter_sha256: str
    final_ir_schema_sha256: str
    final_ir_json_sha256: str
    final_ir_markdown_sha256: str
    final_package_surface_sha256: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _digest(getattr(self, name), f"pins.{name}")

    def to_data(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True, order=True)
class Diagnostic:
    """One stable fail-closed gate finding."""

    code: str
    path: str

    def __post_init__(self) -> None:
        _token(self.code, "diagnostic.code")
        _text(self.path, "diagnostic.path")

    def to_data(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path}


@dataclass(frozen=True, slots=True)
class CompletenessReceipt:
    """Deterministic terminal decision for the complete pre-bulk evidence chain."""

    accepted: bool
    diagnostics: tuple[Diagnostic, ...]
    pins: ValidationPins
    candidate_count: int
    action_count: int
    variant_count: int
    warning_count: int
    revision: str = VALIDATION_REVISION

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool or self.accepted is not (not self.diagnostics):
            raise ValidationError("receipt acceptance must exactly reflect diagnostics")
        if type(self.diagnostics) is not tuple or self.diagnostics != tuple(
            sorted(set(self.diagnostics))
        ):
            raise ValidationError("receipt diagnostics must be sorted and unique")
        if type(self.pins) is not ValidationPins:
            raise ValidationError("receipt pins must use ValidationPins")
        self.pins.__post_init__()
        for name in ("candidate_count", "action_count", "variant_count", "warning_count"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= _MAX_ITEMS:
                raise ValidationError(f"receipt {name} is invalid")
        if self.revision != VALIDATION_REVISION:
            raise ValidationError("receipt revision is unsupported")

    def payload_data(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "action_count": self.action_count,
            "candidate_count": self.candidate_count,
            "diagnostics": [item.to_data() for item in self.diagnostics],
            "pins": self.pins.to_data(),
            "revision": self.revision,
            "variant_count": self.variant_count,
            "warning_count": self.warning_count,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:completeness-receipt", self.payload_data())
