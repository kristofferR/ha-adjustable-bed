"""User docs name only actions, settings and labels the integration still has.

Renames that updated strings.json but not the guides left stale names in about
twenty places. The upgrade page is the one doc that names removed things on
purpose, so it is the source for the removed actions and is not checked itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from custom_components.adjustable_bed import V5_6_REMOVED_KEYS

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "adjustable_bed"
UPGRADE_PAGE = ROOT / "docs" / "V5_BREAKING_CHANGES.md"

DOCS = sorted(
    path
    for path in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    if path != UPGRADE_PAGE and "apk-analysis" not in path.parts
)

# Setting keys the 5.6 migration rewrites away. Disconnect-after-command became
# the Bluetooth connection setting.
RETIRED_KEYS = V5_6_REMOVED_KEYS | {"disconnect_after_command"}

# UI words that setup, Configure or the menus no longer show.
RETIRED_WORDS = (
    "motor pulse delay",
    "motor pulse settings",
    "advanced connection and timing",
    "advanced: receiver route",
    "enable left",
    "restore standalone controls",
    "auto-detect",
    "synchro mode",
    "settings → integrations",
    "settings > integrations",
    "position update mode",
    "change app or layout",
    "stop discovering new bluetooth devices",
    "disconnect after command",
    "disconnect after each command",
    "idle disconnect timeout",
    "quick handoff",
)
# The UI says Combine and Separate.
_UNPAIR = re.compile(r"\bunpair", re.IGNORECASE)
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def _actions() -> set[str]:
    services = yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8"))
    return set(services)


def _removed_actions() -> set[str]:
    """The first column of the upgrade page's 4.x action table."""
    section = UPGRADE_PAGE.read_text(encoding="utf-8").split("\n## Actions\n", 1)[1]
    rows = (line for line in section.split("\n## ", 1)[0].splitlines() if line.startswith("| `"))
    return {name for row in rows for name in re.findall(r"`([a-z0-9_]+)`", row.split(" | ")[0])}


def _ui_text() -> str:
    def leaves(value: object) -> list[str]:
        if isinstance(value, dict):
            return [text for item in value.values() for text in leaves(item)]
        return [value] if isinstance(value, str) else []

    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    return "\n".join(leaves(strings)).lower()


def _prose(path: Path) -> str:
    return _CODE.sub("", path.read_text(encoding="utf-8"))


def test_named_actions_exist() -> None:
    actions = _actions()
    missing = sorted(
        f"{path.relative_to(ROOT)}: {name}"
        for path in [*DOCS, UPGRADE_PAGE]
        for name in re.findall(r"adjustable_bed\.([a-z0-9_]+)", path.read_text(encoding="utf-8"))
        if name not in actions
    )
    assert not missing, f"Docs name actions services.yaml does not define: {missing}"


def test_removed_actions_appear_only_on_the_upgrade_page() -> None:
    removed = _removed_actions()
    assert len(removed) >= 20, "The upgrade page's Actions table moved; update this test"
    assert not removed & _actions(), "An action in the upgrade page's removed table still exists"
    stale = sorted(
        f"{path.relative_to(ROOT)}: {name}"
        for path in DOCS
        for name in removed
        if re.search(rf"`(?:adjustable_bed\.)?{name}`", path.read_text(encoding="utf-8"))
    )
    assert not stale, f"Docs name removed actions: {stale}"


def test_docs_use_no_retired_setting_keys_or_words() -> None:
    ui = _ui_text()
    assert not [word for word in RETIRED_WORDS if word in ui], "A retired word is back in the UI"
    stale = []
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        stale += [f"{path.relative_to(ROOT)}: {key}" for key in RETIRED_KEYS if key in text]
        if "design" in path.parts:
            # Design notes describe the code, whose operations keep their names.
            continue
        prose = _prose(path).lower()
        stale += [f"{path.relative_to(ROOT)}: {word}" for word in RETIRED_WORDS if word in prose]
        if _UNPAIR.search(prose):
            stale.append(f"{path.relative_to(ROOT)}: unpair (the UI says Separate)")
    assert not stale, f"Docs use names the UI no longer shows: {sorted(stale)}"
