"""Every CONF_* key is used, and dropped keys stay dropped (#779)."""

from __future__ import annotations

import ast
import importlib
import json
import re
from pathlib import Path

from custom_components.adjustable_bed import V5_2_OBSOLETE_KEYS
from custom_components.adjustable_bed.const import CONF_DISABLE_DISCOVERY

_ROOT = Path(__file__).parents[1]
_PACKAGE = _ROOT / "custom_components" / "adjustable_bed"
_DEFINITION = re.compile(r"^(CONF_[A-Z0-9_]+)\s*(?::[^=]*)?=", re.MULTILINE)
_SOURCES = {path: path.read_text() for path in _PACKAGE.rglob("*.py")}
# Saved-key names a test builds settings from; the runtime reads each key itself.
_TEST_HELPERS = {"CONF_SERTA_MP_MEMORIES"}


def _definitions() -> dict[str, Path]:
    return {name: path for path, text in _SOURCES.items() for name in _DEFINITION.findall(text)}


def _stored_keys() -> set[str]:
    """Return the stored name of every CONF_* constant."""
    keys: set[str] = set()
    for name, path in _definitions().items():
        module = importlib.import_module(".".join(path.relative_to(_ROOT).with_suffix("").parts))
        value = getattr(module, name)
        keys.update(value if isinstance(value, tuple) else (value,))
    return keys


def _loaded_names() -> set[str]:
    """Names integration code reads: loads and attribute access, not imports or comments."""
    names: set[str] = set()
    for text in _SOURCES.values():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                names.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                names.add(node.attr)
    return names


def test_every_key_constant_is_used():
    """A CONF_* constant that no integration code reads is a dead key."""
    assert _definitions().keys() - _TEST_HELPERS - _loaded_names() == set()


def test_dropped_keys_have_no_constant():
    """Schema 5.2 drops these keys, so no entry writes them again.

    Disable discovery keeps its constant: per-entry cleanup still drops the
    legacy key, and the integration-wide Store saves the setting under that name.
    """
    assert V5_2_OBSOLETE_KEYS & _stored_keys() == {CONF_DISABLE_DISCOVERY}


def test_configure_labels_only_name_defined_keys():
    """Every Configure field label names a saved key, not a typo or a removed one."""
    stored = _stored_keys()
    steps = json.loads((_PACKAGE / "strings.json").read_text())["options"]["step"]
    # Each receiver step of a two-address pair asks its own profile's questions too.
    for step in ("settings", "left_settings", "right_settings"):
        assert set(steps[step]["data"]) <= stored, step
