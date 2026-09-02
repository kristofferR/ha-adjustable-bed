"""Fail-closed completeness gates over current Phase 4 v2 public contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import cast

from tools.phase4_v2.equivalence import (
    PACKAGE_REPORT_REVISION,
    PACKAGE_REPORT_SCHEMA_REVISION,
    PACKAGE_REPORT_SCHEMA_SHA256,
    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    FrozenPackageExecutionPlan,
    PackagePlanStatus,
    ValidatedPackageOutput,
    validate_frozen_package_execution_plan,
)
from tools.phase4_v2.preflight import CandidateRecord, InvocationRecord, PreparationResult
from tools.phase4_v2.reconciliation import (
    ClosureStatus,
    ComparisonDecision,
    ReconciliationResult,
    render_json,
    render_markdown,
    verify_render_agreement,
)

from .model import (
    CompletenessReceipt,
    CompletionAdapter,
    Diagnostic,
    ValidationError,
    ValidationPins,
    WarningStatus,
    candidate_occurrence_id,
    warning_occurrence_id,
)

_MAX_CANDIDATES = 250_000
_MAX_INVOCATIONS = 4_096
_MAX_WARNINGS = 250_000
_MAX_RENDER_BYTES = 256 * 1024**2


def _is_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _bounded_text(value: object, maximum: int = 8_192) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        return len(value.encode("utf-8", errors="strict")) <= maximum
    except UnicodeEncodeError:
        return False


class _Findings:
    def __init__(self) -> None:
        self.items: set[Diagnostic] = set()

    def add(self, code: str, path: str) -> None:
        self.items.add(Diagnostic(code, path))

    def guard(self, code: str, path: str, operation: Callable[[], object]) -> object | None:
        try:
            return operation()
        except AttributeError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError:
            self.add(code, path)
            return None


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_plan(plan: FrozenPackageExecutionPlan, findings: _Findings) -> None:
    if type(plan) is not FrozenPackageExecutionPlan:
        findings.add("PLAN_TYPE_INVALID", "/execution_plan")
        return
    if (
        findings.guard(
            "PLAN_STRUCTURE_INVALID",
            "/execution_plan",
            lambda: validate_frozen_package_execution_plan(plan),
        )
        is None
    ):
        findings.add("PLAN_STRUCTURE_INVALID", "/execution_plan")
    if type(plan.canonical_bytes) is not bytes or len(plan.canonical_bytes) > _MAX_RENDER_BYTES:
        findings.add("PLAN_PREIMAGE_INVALID", "/execution_plan/canonical_bytes")
        return
    try:
        decoded = json.loads(plan.canonical_bytes)
        canonical = json.dumps(
            decoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except TypeError, ValueError, UnicodeError, RecursionError:
        findings.add("PLAN_PREIMAGE_INVALID", "/execution_plan/canonical_bytes")
        return
    expected = _sha(b"phase4-v2:package-execution-plan\0" + plan.canonical_bytes)
    if canonical != plan.canonical_bytes or plan.digest != expected or not _is_digest(plan.digest):
        findings.add("PLAN_DIGEST_MISMATCH", "/execution_plan/digest")
    if type(decoded) is not dict:
        findings.add("PLAN_PREIMAGE_INVALID", "/execution_plan/canonical_bytes")
        return
    data = cast(dict[str, object], decoded)
    if data.get("target_package_ref_id") != plan.target_package_ref_id:
        findings.add("PLAN_TARGET_MISMATCH", "/execution_plan/target_package_ref_id")
    if data.get("cluster_id") != plan.cluster_id:
        findings.add("PLAN_CLUSTER_MISMATCH", "/execution_plan/cluster_id")
    if data.get("status") != getattr(plan.status, "value", None):
        findings.add("PLAN_STATUS_MISMATCH", "/execution_plan/status")
    if data.get("authoritative_root_count") != plan.root_count:
        findings.add("PLAN_ROOT_COUNT_MISMATCH", "/execution_plan/root_count")
    local = data.get("package_local")
    if type(local) is not dict or (
        local.get("package_name"),
        local.get("version_code"),
        local.get("version_name"),
        local.get("target_artifact_digest"),
    ) != (
        plan.package_name,
        plan.version_code,
        plan.version_name,
        plan.target_artifact_digest,
    ):
        findings.add("PLAN_IDENTITY_MISMATCH", "/execution_plan/package_local")
    if (
        not _is_digest(plan.target_package_ref_id)
        or not _is_digest(plan.target_artifact_digest)
        or not _bounded_text(plan.package_name, 256)
        or not _bounded_text(plan.version_code, 256)
        or not _bounded_text(plan.version_name, 256)
        or type(plan.root_count) is not int
        or not 0 < plan.root_count <= 4_096
    ):
        findings.add("PLAN_FIELDS_INVALID", "/execution_plan")
    for field in ("inherited_semantic_roots", "semantic_audit_completion_digests"):
        values = getattr(plan, field, None)
        if (
            type(values) is not tuple
            or len(values) > 256
            or any(not _is_digest(item) for item in values)
            or values != tuple(sorted(set(values)))
        ):
            findings.add("PLAN_FIELDS_INVALID", f"/execution_plan/{field}")
    for field, key in (
        ("required_capabilities", "name"),
        ("required_completions", "parent_unit_id"),
    ):
        values = getattr(plan, field, None)
        serialized: list[dict[str, str]] = []
        valid = type(values) is tuple and len(values) <= 256
        if valid:
            for item in cast(tuple[object, ...], values):
                if (
                    not isinstance(item, tuple)
                    or len(item) != 3
                    or not _bounded_text(item[0], 200)
                    or not _bounded_text(item[1], 200)
                    or not _is_digest(item[2])
                ):
                    valid = False
                    break
                serialized.append({key: item[0], "revision": item[1], "digest": item[2]})
            identities = [item[key] for item in serialized]
            if identities != sorted(set(identities)) or (
                field == "required_capabilities" and not identities
            ):
                valid = False
        if not valid or data.get(field) != serialized:
            findings.add("PLAN_REQUIREMENTS_INVALID", f"/execution_plan/{field}")
    if plan.status is not PackagePlanStatus.EXECUTABLE:
        findings.add("PLAN_BLOCKED", "/execution_plan/status")


def _candidate_sort_key(item: CandidateRecord) -> tuple[object, ...]:
    return (
        item.member,
        item.route,
        item.output_path,
        item.start_byte,
        item.end_byte,
        item.signal,
    )


def _validate_preparation(
    preparation: PreparationResult, findings: _Findings
) -> tuple[set[str], set[str]]:
    candidates: set[str] = set()
    warnings: set[str] = set()
    if type(preparation) is not PreparationResult:
        findings.add("PREPARATION_TYPE_INVALID", "/preparation")
        return candidates, warnings
    if preparation.status != "COMPLETE" or preparation.failures:
        findings.add("PREPARATION_INCOMPLETE", "/preparation/status")
    if (
        not _is_digest(preparation.artifact_digest)
        or not _is_digest(preparation.manifest_sha256)
        or not _is_digest(preparation.candidate_index_sha256)
        or not _bounded_text(preparation.pipeline_revision, 200)
        or type(preparation.failures) is not tuple
        or len(preparation.failures) > _MAX_INVOCATIONS
        or any(not _bounded_text(item) for item in preparation.failures)
    ):
        findings.add("PREPARATION_FIELDS_INVALID", "/preparation")
    if (
        type(preparation.invocations) is not tuple
        or len(preparation.invocations) > _MAX_INVOCATIONS
    ):
        findings.add("INVOCATION_SET_INVALID", "/preparation/invocations")
    else:
        for index, invocation in enumerate(preparation.invocations):
            if type(invocation) is not InvocationRecord:
                findings.add("INVOCATION_TYPE_INVALID", f"/preparation/invocations/{index}")
                continue
            if invocation.status not in {"COMPLETE", "FALLBACK"} or invocation.failures:
                findings.add("INVOCATION_INCOMPLETE", f"/preparation/invocations/{index}/status")
            if (
                not _bounded_text(invocation.member, 4_096)
                or not _bounded_text(invocation.route, 200)
                or not _is_digest(invocation.input_sha256)
                or (invocation.cache_key is not None and not _is_digest(invocation.cache_key))
                or type(invocation.failures) is not tuple
                or len(invocation.failures) > _MAX_INVOCATIONS
                or any(not _bounded_text(item) for item in invocation.failures)
            ):
                findings.add("INVOCATION_FIELDS_INVALID", f"/preparation/invocations/{index}")
            if type(invocation.warnings) is not tuple:
                findings.add("WARNING_SET_INVALID", f"/preparation/invocations/{index}/warnings")
                continue
            if len(warnings) + len(invocation.warnings) > _MAX_WARNINGS:
                findings.add("WARNING_SET_INVALID", "/preparation/invocations")
                break
            for warning_index, warning in enumerate(invocation.warnings):
                identity = findings.guard(
                    "WARNING_RECORD_INVALID",
                    f"/preparation/invocations/{index}/warnings/{warning_index}",
                    lambda invocation=invocation, warning=warning: warning_occurrence_id(
                        invocation, warning
                    ),
                )
                if type(identity) is str:
                    if identity in warnings:
                        findings.add(
                            "WARNING_OCCURRENCE_DUPLICATE",
                            f"/preparation/invocations/{index}/warnings/{warning_index}",
                        )
                    warnings.add(identity)
    if type(preparation.candidates) is not tuple or len(preparation.candidates) > _MAX_CANDIDATES:
        findings.add("CANDIDATE_SET_INVALID", "/preparation/candidates")
        return candidates, warnings
    if (
        all(type(item) is CandidateRecord for item in preparation.candidates)
        and tuple(sorted(preparation.candidates, key=_candidate_sort_key)) != preparation.candidates
    ):
        findings.add("CANDIDATE_ORDER_INVALID", "/preparation/candidates")
    for index, candidate in enumerate(preparation.candidates):
        identity = findings.guard(
            "CANDIDATE_RECORD_INVALID",
            f"/preparation/candidates/{index}",
            lambda candidate=candidate: candidate_occurrence_id(candidate),
        )
        if type(identity) is str:
            if identity in candidates:
                findings.add("CANDIDATE_OCCURRENCE_DUPLICATE", f"/preparation/candidates/{index}")
            candidates.add(identity)
    records_are_valid = len(candidates) == len(preparation.candidates)
    if not records_are_valid:
        findings.add("CANDIDATE_INDEX_INVALID", "/preparation/candidate_index_sha256")
    else:
        candidate_data = {
            "artifact_digest": preparation.artifact_digest,
            "candidates": [item.to_data() for item in preparation.candidates],
            "schema": "phase4-v2-ble-candidate-index-v1",
        }
        try:
            encoded = (
                json.dumps(
                    candidate_data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                ).encode()
                + b"\n"
            )
        except TypeError, ValueError, UnicodeError, RecursionError:
            findings.add("CANDIDATE_INDEX_INVALID", "/preparation/candidate_index_sha256")
        else:
            if _sha(encoded) != preparation.candidate_index_sha256:
                findings.add(
                    "CANDIDATE_INDEX_DIGEST_MISMATCH",
                    "/preparation/candidate_index_sha256",
                )
    return candidates, warnings


def _reconciliation_ledgers(
    result: ReconciliationResult, target: str, findings: _Findings
) -> tuple[set[str], set[str], set[str]]:
    ledgers = {"CANDIDATE": set(), "ACTION": set(), "VARIANT": set()}
    if type(result) is not ReconciliationResult:
        findings.add("RECONCILIATION_TYPE_INVALID", "/reconciliation")
        return ledgers["CANDIDATE"], ledgers["ACTION"], ledgers["VARIANT"]
    if findings.guard(
        "RECONCILIATION_STRUCTURE_INVALID", "/reconciliation", result.__post_init__
    ) is None and any(item.code == "RECONCILIATION_STRUCTURE_INVALID" for item in findings.items):
        return ledgers["CANDIDATE"], ledgers["ACTION"], ledgers["VARIANT"]
    package_ids = {item.package_ref_id for item in result.packages}
    if target not in package_ids:
        findings.add("RECONCILIATION_TARGET_MISSING", "/reconciliation/packages")
    if result.status is not ClosureStatus.COMPLETE:
        findings.add("RECONCILIATION_INCOMPLETE", "/reconciliation/status")
    if result.contradictions:
        findings.add("CONTRADICTIONS_REMAIN", "/reconciliation/contradictions")
    if result.required_full_promotions:
        findings.add("FULL_PROMOTIONS_REMAIN", "/reconciliation/required_full_promotions")
    if result.repairs_required:
        findings.add("REPAIRS_REMAIN", "/reconciliation/repairs_required")
    if any(item.decision is ComparisonDecision.INCOMPLETE for item in result.pair_decisions):
        findings.add("PAIR_DECISIONS_INCOMPLETE", "/reconciliation/pair_decisions")
    for atom in result.atoms:
        if atom.kind not in ledgers or not any(
            source.package_ref_id == target for source in atom.sources
        ):
            continue
        payload = atom.payload.to_data()
        if type(payload) is not dict or payload.get("status") not in {
            "ABSENT",
            "COVERED",
            "EXCLUDED",
        }:
            findings.add(
                f"{atom.kind}_DISPOSITION_INCOMPLETE", f"/reconciliation/atoms/{atom.content_id}"
            )
        if atom.identity in ledgers[atom.kind]:
            findings.add(
                f"{atom.kind}_IDENTITY_DUPLICATE", f"/reconciliation/atoms/{atom.content_id}"
            )
        ledgers[atom.kind].add(atom.identity)
    return ledgers["CANDIDATE"], ledgers["ACTION"], ledgers["VARIANT"]


def _validate_completion(
    *,
    preparation: PreparationResult,
    execution_plan: FrozenPackageExecutionPlan,
    validated_output: ValidatedPackageOutput,
    reconciliation: ReconciliationResult,
    reconciliation_json: bytes,
    reconciliation_markdown: str,
    adapter: CompletionAdapter,
    pins: ValidationPins,
) -> CompletenessReceipt:
    findings = _Findings()
    if type(adapter) is not CompletionAdapter:
        findings.add("ADAPTER_TYPE_INVALID", "/adapter")
        candidate_links: set[str] = set()
        linked_items: set[str] = set()
        warning_dispositions: dict[str, WarningStatus] = {}
    else:
        if findings.guard("ADAPTER_INVALID", "/adapter", adapter.__post_init__) is None and any(
            item.code == "ADAPTER_INVALID" for item in findings.items
        ):
            candidate_links, linked_items, warning_dispositions = set(), set(), {}
        else:
            candidate_links = {item.occurrence_id for item in adapter.candidate_links}
            linked_items = {item.report_item_id for item in adapter.candidate_links}
            warning_dispositions = {
                item.occurrence_id: item.status for item in adapter.warning_dispositions
            }

    expected_candidates, expected_warnings = _validate_preparation(preparation, findings)
    _validate_plan(execution_plan, findings)

    target = getattr(execution_plan, "target_package_ref_id", "")
    report_candidates, report_actions, report_variants = _reconciliation_ledgers(
        reconciliation, target, findings
    )
    if type(reconciliation) is ReconciliationResult and reconciliation.cluster_id != getattr(
        execution_plan, "cluster_id", None
    ):
        findings.add("RECONCILIATION_CLUSTER_MISMATCH", "/reconciliation/cluster_id")
    reconciliation_id = (
        findings.guard(
            "RECONCILIATION_STRUCTURE_INVALID",
            "/reconciliation",
            lambda: reconciliation.content_id,
        )
        if type(reconciliation) is ReconciliationResult
        else None
    )
    adapter_id = (
        findings.guard("ADAPTER_INVALID", "/adapter", lambda: adapter.content_id)
        if type(adapter) is CompletionAdapter
        else None
    )

    if candidate_links != expected_candidates:
        findings.add("CANDIDATE_SOURCE_SET_MISMATCH", "/adapter/candidate_links")
    if linked_items != report_candidates:
        findings.add("CANDIDATE_REPORT_SET_MISMATCH", "/adapter/candidate_links")
    if set(warning_dispositions) != expected_warnings:
        findings.add("WARNING_SET_MISMATCH", "/adapter/warning_dispositions")
    if any(status is WarningStatus.BLOCKING for status in warning_dispositions.values()):
        findings.add("WARNING_BLOCKING", "/adapter/warning_dispositions")

    if type(validated_output) is not ValidatedPackageOutput:
        findings.add("VALIDATED_OUTPUT_TYPE_INVALID", "/validated_output")
        output_id = ""
    else:
        output_id = findings.guard(
            "VALIDATED_OUTPUT_INVALID", "/validated_output", lambda: validated_output.content_id
        )
        if validated_output.target_package_ref_id != target:
            findings.add("OUTPUT_TARGET_MISMATCH", "/validated_output/target_package_ref_id")
        if validated_output.execution_plan_id != getattr(execution_plan, "digest", None):
            findings.add("OUTPUT_PLAN_MISMATCH", "/validated_output/execution_plan_id")
        receipt_unit = f"package-validation-receipt:{target}"
        completion_matches = [
            item
            for item in getattr(execution_plan, "required_completions", ())
            if getattr(item, "parent_unit_id", None) == receipt_unit
        ]
        if len(completion_matches) != 1 or (
            completion_matches[0].revision,
            completion_matches[0].digest,
        ) != (
            PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
            validated_output.validation_receipt_sha256,
        ):
            findings.add("OUTPUT_RECEIPT_MISMATCH", "/validated_output/validation_receipt_sha256")
        output_digests = (
            validated_output.target_package_ref_id,
            validated_output.execution_plan_id,
            validated_output.validation_receipt_sha256,
            validated_output.target_report_schema_sha256,
            validated_output.target_report_sha256,
        )
        if any(not _is_digest(item) for item in output_digests) or (
            validated_output.revision,
            validated_output.target_report_revision,
            validated_output.target_report_schema_revision,
            validated_output.target_report_schema_sha256,
        ) != (
            VALIDATED_PACKAGE_OUTPUT_REVISION,
            PACKAGE_REPORT_REVISION,
            PACKAGE_REPORT_SCHEMA_REVISION,
            PACKAGE_REPORT_SCHEMA_SHA256,
        ):
            findings.add("VALIDATED_OUTPUT_INVALID", "/validated_output")
        matching = (
            [item for item in reconciliation.packages if item.package_ref_id == target]
            if type(reconciliation) is ReconciliationResult
            else []
        )
        if len(matching) != 1 or matching[0].report_sha256 != validated_output.target_report_sha256:
            findings.add("OUTPUT_REPORT_MISMATCH", "/validated_output/target_report_sha256")

    if getattr(preparation, "artifact_digest", None) != getattr(
        execution_plan, "target_artifact_digest", None
    ):
        findings.add("ARTIFACT_DIGEST_MISMATCH", "/execution_plan/target_artifact_digest")
    if getattr(adapter, "target_package_ref_id", None) != target:
        findings.add("ADAPTER_TARGET_MISMATCH", "/adapter/target_package_ref_id")

    markdown_bytes: bytes | None = None
    if type(reconciliation_json) is not bytes or len(reconciliation_json) > _MAX_RENDER_BYTES:
        findings.add("RECONCILIATION_JSON_INVALID", "/render/json")
    if type(reconciliation_markdown) is not str:
        findings.add("RECONCILIATION_MARKDOWN_INVALID", "/render/markdown")
    else:
        try:
            markdown_bytes = reconciliation_markdown.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            findings.add("RECONCILIATION_MARKDOWN_INVALID", "/render/markdown")
            markdown_bytes = None
        if markdown_bytes is not None and len(markdown_bytes) > _MAX_RENDER_BYTES:
            findings.add("RECONCILIATION_MARKDOWN_INVALID", "/render/markdown")
    if (
        type(reconciliation) is ReconciliationResult
        and type(reconciliation_json) is bytes
        and len(reconciliation_json) <= _MAX_RENDER_BYTES
        and type(reconciliation_markdown) is str
        and markdown_bytes is not None
        and len(markdown_bytes) <= _MAX_RENDER_BYTES
    ):
        agreement = findings.guard(
            "RENDER_AGREEMENT_INVALID",
            "/render",
            lambda: verify_render_agreement(reconciliation_json, reconciliation_markdown),
        )
        expected_json = findings.guard(
            "RECONCILIATION_RENDER_INVALID", "/render/json", lambda: render_json(reconciliation)
        )
        expected_markdown = findings.guard(
            "RECONCILIATION_RENDER_INVALID",
            "/render/markdown",
            lambda: render_markdown(reconciliation),
        )
        if agreement != reconciliation_id:
            findings.add("RENDER_RESULT_MISMATCH", "/render")
        if expected_json != reconciliation_json or expected_markdown != reconciliation_markdown:
            findings.add("RENDER_RESULT_MISMATCH", "/render")

    actual_pins: dict[str, object] = {
        "preparation_manifest_sha256": getattr(preparation, "manifest_sha256", None),
        "candidate_index_sha256": getattr(preparation, "candidate_index_sha256", None),
        "execution_plan_sha256": getattr(execution_plan, "digest", None),
        "validated_package_output_sha256": output_id,
        "reconciliation_input_sha256": getattr(reconciliation, "input_id", None),
        "reconciliation_result_sha256": reconciliation_id,
        "reconciliation_json_sha256": (
            _sha(reconciliation_json) if type(reconciliation_json) is bytes else None
        ),
        "reconciliation_markdown_sha256": (
            _sha(markdown_bytes) if markdown_bytes is not None else None
        ),
        "completion_adapter_sha256": adapter_id,
    }
    for field, actual in actual_pins.items():
        if getattr(pins, field) != actual:
            findings.add("PIN_MISMATCH", f"/pins/{field}")

    diagnostics = tuple(sorted(findings.items))
    return CompletenessReceipt(
        accepted=not diagnostics,
        diagnostics=diagnostics,
        pins=pins,
        candidate_count=len(expected_candidates),
        action_count=len(report_actions),
        variant_count=len(report_variants),
        warning_count=len(expected_warnings),
    )


def validate_completion(
    *,
    preparation: PreparationResult,
    execution_plan: FrozenPackageExecutionPlan,
    validated_output: ValidatedPackageOutput,
    reconciliation: ReconciliationResult,
    reconciliation_json: bytes,
    reconciliation_markdown: str,
    adapter: CompletionAdapter,
    pins: ValidationPins,
) -> CompletenessReceipt:
    """Validate an entire synthetic-safe package/cluster closure chain."""
    if type(pins) is not ValidationPins:
        raise ValidationError("pins must use the exact ValidationPins type")
    pins.__post_init__()
    try:
        return _validate_completion(
            preparation=preparation,
            execution_plan=execution_plan,
            validated_output=validated_output,
            reconciliation=reconciliation,
            reconciliation_json=reconciliation_json,
            reconciliation_markdown=reconciliation_markdown,
            adapter=adapter,
            pins=pins,
        )
    except AttributeError, TypeError, ValueError, UnicodeError, RecursionError, OverflowError:
        return CompletenessReceipt(
            accepted=False,
            diagnostics=(Diagnostic("INPUT_STRUCTURE_INVALID", "/"),),
            pins=pins,
            candidate_count=0,
            action_count=0,
            variant_count=0,
            warning_count=0,
        )
