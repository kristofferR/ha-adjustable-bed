"""The CONF_* audit in docs/design/config-keys.md covers every key (#779)."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

from custom_components.adjustable_bed import V5_2_OBSOLETE_KEYS

_ROOT = Path(__file__).parents[1]
_PACKAGE = _ROOT / "custom_components" / "adjustable_bed"
_AUDIT = (_ROOT / "docs" / "design" / "config-keys.md").read_text()
_DEFINITION = re.compile(r"^(CONF_[A-Z0-9_]+)\s*(?::[^=]*)?=", re.MULTILINE)


def _section(title: str) -> str:
    return _AUDIT.split(f"\n## {title}\n", 1)[1].split("\n## ", 1)[0]


def _rows(title: str) -> dict[str, list[str]]:
    """Return each table row's cells by key, for every key its first cell names."""
    rows: dict[str, list[str]] = {}
    for line in _section(title).splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        for key in re.findall(r"`([a-z0-9_]+)`", cells[0]) if line.startswith("| `") else ():
            rows[key] = cells
    return rows


def _defined_keys() -> set[str]:
    """Return the stored name of every CONF_* constant the integration defines."""
    keys: set[str] = set()
    for path in _PACKAGE.rglob("*.py"):
        names = _DEFINITION.findall(path.read_text())
        if not names:
            continue
        module = importlib.import_module(
            ".".join(path.relative_to(_ROOT).with_suffix("").parts)
        )
        for name in names:
            value = getattr(module, name)
            keys.update(value if isinstance(value, tuple) else (value,))
    return keys


def test_every_key_is_audited():
    audited = set(_rows("Keys")) | set(_rows("Flow inputs"))
    assert _defined_keys() - audited == set()


def test_every_audited_key_exists_unless_obsolete():
    defined = _defined_keys() | {"address", "name"}
    keys = _rows("Keys")
    obsolete = {key for key, cells in keys.items() if cells[1] == "Obsolete"}
    assert set(keys) - obsolete <= defined
    assert set(_rows("Flow inputs")) <= defined
    # An obsolete key's constant and writers are gone.
    assert not obsolete & defined


def test_schema_5_2_drops_exactly_the_audited_obsolete_keys():
    keys = _rows("Keys")
    obsolete = {key for key, cells in keys.items() if cells[1] == "Obsolete"}
    dropped = set(_rows("Dropped by schema 5.2"))
    assert dropped == V5_2_OBSOLETE_KEYS
    assert obsolete <= dropped
    # A dropped key that still has a row is a setting stored elsewhere, never one
    # the entry's runtime reads.
    assert {keys[key][1] for key in dropped - obsolete} <= {"User"}


def test_configure_labels_only_keys_a_form_asks():
    """Every Configure label names a key the audit says a user or a profile question sets."""
    steps = json.loads((_PACKAGE / "strings.json").read_text())["options"]["step"]
    keys = _rows("Keys")
    # Each receiver step of a two-address pair asks its own profile's questions too.
    for step in ("settings", "left_settings", "right_settings"):
        for key in steps[step]["data"]:
            assert key in keys and keys[key][1] in {"User", "Profile"}, (step, key)
