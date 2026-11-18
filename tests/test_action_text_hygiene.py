"""Action names and fields read as plain bed controls: one naming pattern, no protocol values."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.test_setup_label_hygiene import _NAMED_VERSIONS, _VERSION

STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)
SERVICES = STRINGS["services"]

# Actions every bed shares; every other action belongs to one brand or app.
SHARED = frozenset(
    {
        "goto_preset",
        "save_preset",
        "stop_all",
        "set_position",
        "set_positions",
        "timed_move",
        "hold_control",
        "set_alarm",
        "sync_clock",
        "rename",
        "lower_to_flat",
        "estimate_save_position",
        "estimate_rename_position",
        "estimate_update_position",
        "estimate_delete_position",
        "estimate_recall_position",
        "estimate_set_reference",
        "estimate_confirm_unchanged",
        "estimate_mark_unknown",
        "generate_support_bundle",
    }
)
# "<Brand>: <what>", the what in lower case and never a generic stand-in for one
# of "settings", "press button" and "run control".
_BED_ACTION = re.compile(r"^[^:]+: [a-z][^:]*$")
_GENERIC = re.compile(r"\b(?:app|command|action|controls and)\b")
_PROTOCOL = re.compile(
    r"\bBLE\b|\b[Bb]ytes?\b|[Oo]pcode|[Bb]itmask|\bmask\b|\bPWM\b|\bHall\b|\bASCII\b|0x|"
    r"\bqueue\b|\bwriter\b|\bBED\b|[Aa]dmission|[Pp]reflight|\bSTK\b"
)


def _texts(node: object, path: str):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _texts(value, f"{path}.{key}")
    elif isinstance(node, str):
        yield path, node


def test_bed_actions_are_named_brand_then_what() -> None:
    assert SHARED <= set(SERVICES)
    bad = {
        key: entry["name"]
        for key, entry in SERVICES.items()
        if key not in SHARED
        and (not _BED_ACTION.match(entry["name"]) or _GENERIC.search(entry["name"].split(": ")[1]))
    }
    assert not bad


def test_action_names_carry_no_app_version() -> None:
    versioned = {}
    for key, entry in SERVICES.items():
        name = entry["name"]
        for named in _NAMED_VERSIONS:
            name = name.replace(named, "")
        if _VERSION.search(name):
            versioned[key] = entry["name"]
    assert not versioned


def test_action_text_names_no_protocol_values() -> None:
    assert not [path for path, text in _texts(SERVICES, "services") if _PROTOCOL.search(text)]


def test_choices_have_known_effects() -> None:
    """A choice offered only by the code it sends tells a user nothing."""
    unknown = re.compile(r"^(?:Action|Code|Option) \d+$")
    assert not [
        f"{name}.{key}"
        for name, selector in STRINGS["selector"].items()
        for key, label in selector.get("options", {}).items()
        if unknown.match(label)
    ]
