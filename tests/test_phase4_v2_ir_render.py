from __future__ import annotations

from dataclasses import replace

import pytest

from tools.phase4_v2.ir import (
    SCHEMA_REVISION,
    ActionDefinition,
    CommandBinding,
    ExpectedActionRule,
    IRValidationError,
    Predicate,
    ProtocolDefinition,
    ProtocolIRDocument,
    VariantSpace,
    render_ir_markdown,
    semantic_fingerprint,
    validate_ir_markdown,
)


def _document() -> ProtocolIRDocument:
    return ProtocolIRDocument(
        schema_revision=SCHEMA_REVISION,
        source_packages=(),
        evidence_files=(),
        evidence_anchors=(),
        source_sets=(),
        evidence_bindings=(),
        variant_spaces=(("default", VariantSpace((), ())),),
        protocols=(("protocol", ProtocolDefinition("default")),),
        actions=(("raise", ActionDefinition("Raise | `head`\nnow")),),
        expected_action_rules=(
            ("expected", ExpectedActionRule("protocol", "raise", Predicate("always"))),
        ),
        command_bindings=(("binding", CommandBinding("protocol", "raise", Predicate("always"))),),
    )


def test_markdown_is_deterministic_and_bound_to_semantics() -> None:
    document = _document()

    first = render_ir_markdown(document)
    second = render_ir_markdown(document)

    assert first == second
    assert validate_ir_markdown(document, first) == semantic_fingerprint(document)
    assert r"Raise \| \u0060head\u0060\nnow" in first


def test_markdown_rejects_semantic_fingerprint_substitution() -> None:
    document = _document()
    changed = replace(
        document,
        actions=(("raise", ActionDefinition("Different semantics")),),
    )

    with pytest.raises(IRValidationError) as caught:
        validate_ir_markdown(changed, render_ir_markdown(document))

    assert caught.value.diagnostics[0].code == "markdown_fingerprint_mismatch"


def test_markdown_rejects_human_edits_even_with_the_same_fingerprint() -> None:
    document = _document()
    rendered = render_ir_markdown(document)

    with pytest.raises(IRValidationError) as caught:
        validate_ir_markdown(document, rendered.replace("# Protocol analysis", "# Edited"))

    assert caught.value.diagnostics[0].code == "markdown_render_mismatch"


def test_empty_sections_have_a_stable_explicit_row() -> None:
    document = replace(
        _document(),
        variant_spaces=(),
        protocols=(),
        actions=(),
        expected_action_rules=(),
        command_bindings=(),
    )

    rendered = render_ir_markdown(document)

    assert rendered.count("|  | `{}` |") == 5
    assert validate_ir_markdown(document, rendered) == semantic_fingerprint(document)
