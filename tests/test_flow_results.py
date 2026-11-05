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


def test_every_flow_result_names_its_step():
    """A result without a step id is an error from Home Assistant 2027.5."""
    missing = []
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _RESULT_METHODS
                and not any(keyword.arg in ("step_id", None) for keyword in node.keywords)
            ):
                missing.append(f"{path.name}:{node.lineno}")
    assert not missing


def test_standard_abort_reasons_use_home_assistants_strings():
    """Our own text for these would never show: Home Assistant resolves them itself."""
    strings = json.loads((PACKAGE / "strings.json").read_text())
    for flow in ("config", "options"):
        assert not HOMEASSISTANT_REASONS & set(strings[flow].get("abort", {})), flow
