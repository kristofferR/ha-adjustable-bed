"""Deterministic human rendering for the canonical Phase 4 protocol IR."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from .model import IRDiagnostic, IRValidationError, ProtocolIRDocument, semantic_fingerprint

if TYPE_CHECKING:
    from .v1 import FinalProtocolIRDocument

_FINGERPRINT = re.compile(r"^Semantic fingerprint: `([0-9a-f]{64})`$", re.MULTILINE)


def render_ir_markdown(document: ProtocolIRDocument) -> str:
    """Render the canonical IR without adding independently authored semantics."""

    fingerprint = semantic_fingerprint(document)
    lines = [
        "# Protocol analysis",
        "",
        f"Schema: `{document.schema_revision}`  ",
        f"Semantic fingerprint: `{fingerprint}`",
        "",
    ]
    _definition_section(lines, "Variant spaces", document.variant_spaces)
    _definition_section(lines, "Protocols", document.protocols)
    _definition_section(lines, "Actions", document.actions)
    _definition_section(lines, "Expected action rules", document.expected_action_rules)
    _definition_section(lines, "Command bindings", document.command_bindings)
    lines.extend(
        [
            "## Provenance summary",
            "",
            "| Collection | Count |",
            "| --- | ---: |",
            f"| Source packages | {len(document.source_packages)} |",
            f"| Evidence files | {len(document.evidence_files)} |",
            f"| Evidence anchors | {len(document.evidence_anchors)} |",
            f"| Source sets | {len(document.source_sets)} |",
            f"| Evidence bindings | {len(document.evidence_bindings)} |",
            "",
        ]
    )
    return "\n".join(lines)


def validate_ir_markdown(document: ProtocolIRDocument, rendered: str) -> str:
    """Require exact deterministic rendering and return its semantic fingerprint."""

    if type(rendered) is not str:
        raise IRValidationError(
            (IRDiagnostic("markdown_invalid", "$", "Markdown render must be a string"),)
        )
    matches = _FINGERPRINT.findall(rendered)
    expected_fingerprint = semantic_fingerprint(document)
    if matches != [expected_fingerprint]:
        raise IRValidationError(
            (
                IRDiagnostic(
                    "markdown_fingerprint_mismatch",
                    "$.semantic_fingerprint",
                    "Markdown does not identify the canonical IR semantics",
                ),
            )
        )
    if rendered != render_ir_markdown(document):
        raise IRValidationError(
            (
                IRDiagnostic(
                    "markdown_render_mismatch",
                    "$",
                    "Markdown differs from the deterministic canonical render",
                ),
            )
        )
    return expected_fingerprint


def render_final_ir_markdown(document: FinalProtocolIRDocument) -> str:
    """Render every closed final-v1 domain from canonical IR semantics."""

    from .v1 import final_semantic_fingerprint

    fingerprint = final_semantic_fingerprint(document)
    lines = [
        "# Protocol analysis",
        "",
        f"Schema: `{document.schema_revision}`  ",
        f"Semantic fingerprint: `{fingerprint}`",
        "",
    ]
    for collection_name in document.semantic_collection_names:
        title = collection_name.replace("_", " ").capitalize()
        if collection_name == "domain_closure":
            _definition_section(lines, title, (("closure", document.domain_closure),))
        else:
            _definition_section(lines, title, getattr(document, collection_name))
    lines.extend(
        [
            "## Provenance summary",
            "",
            "| Collection | Count |",
            "| --- | ---: |",
            f"| Source packages | {len(document.source_packages)} |",
            f"| Evidence files | {len(document.evidence_files)} |",
            f"| Evidence anchors | {len(document.evidence_anchors)} |",
            f"| Source sets | {len(document.source_sets)} |",
            f"| Evidence bindings | {len(document.evidence_bindings)} |",
            "",
        ]
    )
    return "\n".join(lines)


def validate_final_ir_markdown(document: FinalProtocolIRDocument, rendered: str) -> str:
    """Require exact Markdown agreement with final-v1 canonical semantics."""

    from .v1 import final_semantic_fingerprint

    if type(rendered) is not str:
        raise IRValidationError(
            (IRDiagnostic("markdown_invalid", "$", "Markdown render must be a string"),)
        )
    fingerprint = final_semantic_fingerprint(document)
    if _FINGERPRINT.findall(rendered) != [fingerprint]:
        raise IRValidationError(
            (
                IRDiagnostic(
                    "markdown_fingerprint_mismatch",
                    "$.semantic_fingerprint",
                    "Markdown does not identify the canonical final IR semantics",
                ),
            )
        )
    if rendered != render_final_ir_markdown(document):
        raise IRValidationError(
            (
                IRDiagnostic(
                    "markdown_render_mismatch",
                    "$",
                    "Markdown differs from the deterministic canonical final render",
                ),
            )
        )
    return fingerprint


def _definition_section(
    lines: list[str],
    title: str,
    definitions: tuple[tuple[str, object], ...],
) -> None:
    lines.extend((f"## {title}", "", "| ID | Definition |", "| --- | --- |"))
    lines.extend(
        f"| {_cell(identifier)} | {_cell(_definition_json(definition))} |"
        for identifier, definition in definitions
    )
    if not definitions:
        lines.append("|  | `{}` |")
    lines.append("")


def _definition_json(definition: object) -> str:
    to_data = getattr(definition, "to_data", None)
    if not callable(to_data):
        raise TypeError("IR definition does not expose canonical data")
    return (
        "`"
        + json.dumps(
            to_data(), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).replace("`", "\\u0060")
        + "`"
    )


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", "\\r").replace("\n", "\\n")
