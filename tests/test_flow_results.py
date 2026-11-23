"""An abort with one of Home Assistant's own reasons needs its domain, or it shows untranslated."""

import ast
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


