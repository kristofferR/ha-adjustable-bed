"""Flow results the integration builds follow Home Assistant 2026.11's contract."""

import ast
import json
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "custom_components/adjustable_bed"
# Reasons Home Assistant resolves from its own translations.
HOMEASSISTANT_REASONS = frozenset(
    {
        "already_in_progress",
        "no_devices_found",
        "reauth_successful",
        "reconfigure_successful",
        "single_instance_allowed",
    }
)
_RESULT_METHODS = frozenset(
    {"async_show_form", "async_show_menu", "async_show_progress", "async_external_step"}
)
# Helpers whose default reason Home Assistant translates itself.
_UPDATE_AND_ABORT = frozenset({"async_update_and_abort", "async_update_reload_and_abort"})


def _calls(names: frozenset[str]) -> list[tuple[str, ast.Call]]:
    calls = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in names
            ):
                calls.append((f"{path.name}:{node.lineno}", node))
    return calls


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def test_every_flow_result_names_its_step():
    """A result without a step id is an error from Home Assistant 2027.5."""
    calls = _calls(_RESULT_METHODS)
    assert len(calls) > 50
    missing = [
        where
        for where, call in calls
        if (step_id := _keyword(call, "step_id")) is None
        or (isinstance(step_id, ast.Constant) and step_id.value is None)
    ]
    assert not missing


def test_standard_abort_reasons_use_home_assistants_strings():
    """Our own text for these would never show: Home Assistant resolves them itself."""
    strings = json.loads((PACKAGE / "strings.json").read_text())
    for flow in ("config", "options"):
        assert not HOMEASSISTANT_REASONS & set(strings[flow].get("abort", {})), flow


def test_no_flow_aborts_with_a_standard_reason_under_its_own_domain():
    """Without Home Assistant's domain the reason would show untranslated."""
    aborts = _calls(frozenset({"async_abort"}))
    assert len(aborts) > 20
    own = [
        where
        for where, call in aborts
        if isinstance(reason := _keyword(call, "reason"), ast.Constant)
        and reason.value in HOMEASSISTANT_REASONS
        and _keyword(call, "translation_domain") is None
    ]
    # Passing a reason replaces the helper's default and its domain.
    own += [
        where
        for where, call in _calls(_UPDATE_AND_ABORT)
        if isinstance(reason := _keyword(call, "reason"), ast.Constant)
        and reason.value in HOMEASSISTANT_REASONS
    ]
    assert not own


def test_no_string_has_leading_or_trailing_space():
    """Hassfest refuses a string with surrounding whitespace, newlines included."""

    def strings(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from strings(value, f"{path}.{key}" if path else key)
        elif isinstance(node, str):
            yield path, node

    for name in ("strings.json", "translations/en.json"):
        data = json.loads((PACKAGE / name).read_text())
        padded = [path for path, text in strings(data) if text != text.strip()]
        assert not padded, (name, padded)


def test_every_field_description_has_its_field_label():
    """Hassfest refuses a ``data_description`` key that the step's ``data`` lacks."""

    def flows(data):
        yield "config", data.get("config", {})
        yield "options", data.get("options", {})
        for issue, body in data.get("issues", {}).items():
            yield f"issues.{issue}.fix_flow", body.get("fix_flow", {})

    for name in ("strings.json", "translations/en.json"):
        data = json.loads((PACKAGE / name).read_text())
        missing = []
        for flow, body in flows(data):
            for step_id, step in body.get("step", {}).items():
                blocks = {step_id: step, **{
                    f"{step_id}.sections.{key}": block
                    for key, block in step.get("sections", {}).items()
                }}
                for where, block in blocks.items():
                    labels = block.get("data", {})
                    missing += [
                        f"{flow}.step.{where}.data_description.{key}"
                        for key in block.get("data_description", {})
                        if key not in labels
                    ]
        assert not missing, (name, missing)
