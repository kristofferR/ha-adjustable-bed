"""Every error a user can see is translated, with a key that exists in strings.json."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.adjustable_bed.errors import invalid, not_ready, rejected

PACKAGE = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
EXCEPTIONS = json.loads((PACKAGE / "strings.json").read_text())["exceptions"]
# Errors Home Assistant shows to users: action errors and the reason a bed is not ready.
SHOWN = frozenset({"ServiceValidationError", "HomeAssistantError", "ConfigEntryNotReady"})
# The shared builders in errors.py, whose first argument is the key.
BUILDERS = frozenset({"invalid", "_invalid", "failed", "not_ready"})


def _calls() -> list[tuple[str, ast.Call, str]]:
    calls = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name in SHOWN | BUILDERS:
                    calls.append((f"{path.relative_to(PACKAGE)}:{node.lineno}", node, name))
    return calls


def _key(node: ast.Call, name: str) -> ast.expr | None:
    if name in BUILDERS:
        return node.args[0] if node.args else None
    return next((kw.value for kw in node.keywords if kw.arg == "translation_key"), None)


def test_every_shown_error_has_a_translation_key() -> None:
    assert not [where for where, node, name in _calls() if _key(node, name) is None]


def test_errors_py_builds_every_shown_error() -> None:
    """One place writes messages, from en.json, so the English cannot drift from it."""
    assert not [
        where for where, _node, name in _calls() if name in SHOWN and not where.startswith("errors.py:")
    ]


@pytest.mark.parametrize("key", sorted(EXCEPTIONS))
def test_english_text_is_the_translation(key: str) -> None:
    message = EXCEPTIONS[key].get("message")
    if message is None:
        return
    placeholders = {name: f"<{name}>" for name in re.findall(r"\{(\w+)\}", message)}
    assert str(invalid(key, **placeholders)) == message.format(**placeholders)


def test_error_classes_carry_a_key() -> None:
    """The integration's own error classes build their message with errors.keyed()."""
    unkeyed = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef) and any(
                getattr(base, "id", getattr(base, "attr", None)) in SHOWN for base in node.bases
            ):
                calls = {getattr(c.func, "id", None) for c in ast.walk(node) if isinstance(c, ast.Call)}
                if "keyed" not in calls:
                    unkeyed.append(f"{path.relative_to(PACKAGE)}:{node.lineno} {node.name}")
    assert not unkeyed


def test_every_translation_key_is_in_strings() -> None:
    missing = [
        f"{where} {key.value}"
        for where, node, name in _calls()
        if isinstance(key := _key(node, name), ast.Constant) and key.value not in EXCEPTIONS
    ]
    assert not missing


def test_constant_keys_get_every_placeholder_their_text_names() -> None:
    wrong = []
    for where, node, name in _calls():
        key = _key(node, name)
        if name not in BUILDERS or not isinstance(key, ast.Constant):
            continue
        given = {kw.arg for kw in node.keywords}
        if None in given:  # **placeholders, checked where they are built
            continue
        wanted = set(re.findall(r"\{(\w+)\}", EXCEPTIONS[key.value]["message"]))
        if given != wanted:
            wrong.append(f"{where} {key.value}: {sorted(given)} != {sorted(wanted)}")
    assert not wrong


def test_builders_carry_the_key_and_placeholders() -> None:
    error = invalid("value_out_of_range", min=1, max=5, step=1)
    assert isinstance(error, ServiceValidationError)
    assert error.translation_key == "value_out_of_range"
    assert error.translation_placeholders == {"min": "1", "max": "5", "step": "1"}
    reason = rejected(ValueError("Choose a mode this bed offers"))
    assert reason.translation_key == "action_rejected"
    assert reason.translation_placeholders == {"reason": "Choose a mode this bed offers"}
    assert isinstance(not_ready("setup_retry"), HomeAssistantError)


@pytest.mark.parametrize("key", sorted(EXCEPTIONS))
def test_messages_read_plainly(key: str) -> None:
    message = EXCEPTIONS[key].get("message", "")
    assert "—" not in message
    assert not re.search(r"\bBLE\b|preflight|admission|\bBED\b|opcode|0x", message)


def _flow_error_keys(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(target := node.targets[0], ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "errors"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            used.add(node.value.value)
        if isinstance(node, ast.keyword) and node.arg == "errors" and isinstance(node.value, ast.Dict):
            used |= {v.value for v in node.value.values if isinstance(v, ast.Constant)}
    return used


def test_flow_errors_are_translated_in_their_own_flow() -> None:
    """Setup reads config.error and Configure options.error; a helper needs each flow that calls it."""
    strings = json.loads((PACKAGE / "strings.json").read_text())
    namespaces = {
        "AdjustableBedConfigFlow": set(strings["config"]["error"]),
        "AdjustableBedOptionsFlow": set(strings["options"]["error"]),
    }
    tree = ast.parse((PACKAGE / "config_flow.py").read_text())
    flows = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in namespaces]
    called = {
        flow.name: {n.func.id for n in ast.walk(flow) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        for flow in flows
    }
    missing = []
    for node in tree.body:
        name = getattr(node, "name", None)
        users = [name] if name in namespaces else [flow for flow, names in called.items() if name in names]
        for flow in users:
            missing += [f"{flow} via {name}: {key}" for key in sorted(_flow_error_keys(node) - namespaces[flow])]
    assert missing == []
