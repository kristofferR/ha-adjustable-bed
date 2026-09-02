"""Deterministic JSON and Markdown renderers with exact agreement verification."""

from __future__ import annotations

from typing import cast

from .engine import RESULT_REVISION, ReconciliationResult
from .model import (
    ReconciliationError,
    canonical_content_id,
    canonical_json_bytes,
    load_bounded_json,
)
from .schema import COMPARISON_AREAS

_START = "<!-- phase4-v2-reconciliation-json:START -->"
_END = "<!-- phase4-v2-reconciliation-json:END -->"
_DECISION_NAMES = ("SAME", "DIFFERENT", "INCOMPLETE")


def render_json(result: ReconciliationResult) -> bytes:
    """Render the exact canonical machine-readable reconciliation result."""
    if type(result) is not ReconciliationResult or result.revision != RESULT_REVISION:
        raise ReconciliationError("renderer requires the pinned ReconciliationResult type")
    result.__post_init__()
    return canonical_json_bytes(result.to_data())


def render_markdown(result: ReconciliationResult) -> str:
    """Render a readable summary carrying the exact canonical JSON payload."""
    payload = render_json(result)
    document = cast(dict[str, object], load_bounded_json(payload))
    return _render_markdown_document(document, payload)


def _render_markdown_document(document: dict[str, object], payload: bytes) -> str:
    cluster_id = _required_string(document.get("cluster_id"), "cluster_id")
    status = _required_string(document.get("status"), "status")
    content_id = _required_string(document.get("content_id"), "content_id")
    aggregates = _required_object_array(document.get("area_aggregates"), "area_aggregates")
    decisions = _required_object_array(document.get("pair_decisions"), "pair_decisions")
    promotions = _required_object_array(
        document.get("required_full_promotions"), "required_full_promotions"
    )
    repairs = _required_object_array(document.get("repairs_required"), "repairs_required")
    contradictions = _required_object_array(document.get("contradictions"), "contradictions")
    totals = dict.fromkeys(_DECISION_NAMES, 0)
    by_area = {area: dict.fromkeys(_DECISION_NAMES, 0) for area in COMPARISON_AREAS}
    for index, item in enumerate(decisions):
        area = _required_string(item.get("area"), f"pair_decisions[{index}].area")
        decision = _required_string(item.get("decision"), f"pair_decisions[{index}].decision")
        if area not in by_area or decision not in totals:
            raise ReconciliationError("Markdown input has an invalid pair decision")
        totals[decision] += 1
        by_area[area][decision] += 1
    lines = [
        f"# Cluster reconciliation: `{cluster_id}`",
        "",
        f"Status: **{status}**",
        "",
        f"Result SHA-256: `{content_id}`",
        "",
        "| Area | SAME | DIFFERENT | INCOMPLETE | Union | Intersection |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    aggregate_areas: list[str] = []
    for index, aggregate in enumerate(aggregates):
        area = _required_string(aggregate.get("area"), f"area_aggregates[{index}].area")
        aggregate_areas.append(area)
        union = _required_array(
            aggregate.get("union_atom_ids"), f"area_aggregates[{index}].union_atom_ids"
        )
        intersection = _required_array(
            aggregate.get("intersection_atom_ids"),
            f"area_aggregates[{index}].intersection_atom_ids",
        )
        if area not in by_area:
            raise ReconciliationError("Markdown input has an invalid aggregate area")
        lines.append(
            f"| `{area}` | "
            f"{by_area[area]['SAME']} | "
            f"{by_area[area]['DIFFERENT']} | "
            f"{by_area[area]['INCOMPLETE']} | "
            f"{len(union)} | "
            f"{len(intersection)} |"
        )
    if tuple(aggregate_areas) != COMPARISON_AREAS:
        raise ReconciliationError("Markdown input does not contain the ordered 11 areas")
    lines.extend(
        [
            "",
            "## Follow-up",
            "",
            f"- Required FULL promotions: {len(promotions)}",
            f"- Repairs required: {len(repairs)}",
            f"- Contradictions: {len(contradictions)}",
            "",
            "## Decision totals",
            "",
            f"- SAME: {totals['SAME']}",
            f"- DIFFERENT: {totals['DIFFERENT']}",
            f"- INCOMPLETE: {totals['INCOMPLETE']}",
            "",
            "## Canonical payload",
            "",
            _START,
            "```json",
            payload.decode("utf-8"),
            "```",
            _END,
            "",
        ]
    )
    return "\n".join(lines)


def verify_render_agreement(json_payload: bytes, markdown: str) -> str:
    """Verify canonical JSON, its content ID, and the exact Markdown embedding."""
    if type(json_payload) is not bytes or type(markdown) is not str:
        raise ReconciliationError("render agreement requires exact bytes and str")
    raw = load_bounded_json(json_payload)
    if type(raw) is not dict:
        raise ReconciliationError("reconciliation result JSON must be an object")
    document = cast(dict[str, object], raw)
    if canonical_json_bytes(document) != json_payload:
        raise ReconciliationError("reconciliation result JSON is not canonical")
    if set(document) != {
        "area_aggregates",
        "atoms",
        "cluster_id",
        "content_id",
        "contradictions",
        "input_id",
        "packages",
        "pair_decisions",
        "repairs_required",
        "required_full_promotions",
        "revision",
        "status",
    }:
        raise ReconciliationError("reconciliation result has an unexpected field set")
    if document.get("revision") != RESULT_REVISION:
        raise ReconciliationError("reconciliation result revision is unsupported")
    claimed = document.get("content_id")
    if type(claimed) is not str:
        raise ReconciliationError("reconciliation result content ID is missing")
    payload_document = {key: value for key, value in document.items() if key != "content_id"}
    actual = canonical_content_id("reconciliation-result", payload_document)
    if claimed != actual:
        raise ReconciliationError("reconciliation result content ID does not verify")

    prefix = f"{_START}\n```json\n"
    suffix = f"\n```\n{_END}"
    lines = markdown.splitlines()
    if lines.count(_START) != 1 or lines.count(_END) != 1:
        raise ReconciliationError("Markdown must contain one canonical payload block")
    start = markdown.find(prefix)
    if start < 0:
        raise ReconciliationError("Markdown canonical payload start is invalid")
    body_start = start + len(prefix)
    end = markdown.find(suffix, body_start)
    if end < 0:
        raise ReconciliationError("Markdown canonical payload end is invalid")
    embedded = markdown[body_start:end].encode("utf-8", errors="strict")
    if embedded != json_payload:
        raise ReconciliationError("JSON and Markdown canonical payloads disagree")
    if markdown != _render_markdown_document(document, json_payload):
        raise ReconciliationError("Markdown is not the deterministic rendering of its JSON")
    return actual


def _required_string(value: object, field: str) -> str:
    if type(value) is not str or not value:
        raise ReconciliationError(f"{field} must be a non-empty string")
    return value


def _required_array(value: object, field: str) -> list[object]:
    if type(value) is not list:
        raise ReconciliationError(f"{field} must be an array")
    return cast(list[object], value)


def _required_object_array(value: object, field: str) -> list[dict[str, object]]:
    raw = _required_array(value, field)
    if any(type(item) is not dict for item in raw):
        raise ReconciliationError(f"{field} must contain objects")
    return cast(list[dict[str, object]], raw)
