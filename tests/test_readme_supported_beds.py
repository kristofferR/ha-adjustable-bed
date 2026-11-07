"""The README's Supported Beds table names every bed and app setup offers (#909).

A row of the table is one setup family. Each label setup shows must have all of
its words in one row: the bed-type list's rows, every app label, every family
row's members and every supported bed type the list does not reach through a
family row. A new bed or app therefore cannot be left out of the table.
"""

from __future__ import annotations

import re
from pathlib import Path

from custom_components.adjustable_bed.app_families import FAMILY_STEP_ROUTES
from custom_components.adjustable_bed.const import BED_TYPE_DIAGNOSTIC, SUPPORTED_BED_TYPES
from custom_components.adjustable_bed.detection import (
    APP_VARIANT_CHOICES,
    BED_TYPE_DISPLAY_NAMES,
    get_bed_type_options,
)

README = Path(__file__).resolve().parents[1] / "README.md"

# A qualifier in parentheses, one level of nesting deep: "(MOTION 400 (GM-A4Z))".
_QUALIFIER = re.compile(r"\s*\((?:[^()]|\([^()]*\))*\)")
# "<Family>: A, B and C apps" lists the family's members.
_MEMBERS = re.compile(r",\s+(?:and\s+)?|\s+and\s+")
_TOKEN = re.compile(r"[\w'&+/.-]+")
# Words that only say what kind of thing a name is.
_GENERIC = frozenset(
    {
        "app",
        "apps",
        "remote",
        "remotes",
        "receiver",
        "receivers",
        "bases",
        "controls",
        "some",
        "beds",
    }
)


def _tokens(text: str) -> frozenset[str]:
    words = (word.strip(".-/'") for word in _TOKEN.findall(text.lower()))
    return frozenset(word for word in words if re.search(r"\w", word))


def _rows() -> list[frozenset[str]]:
    """Each table row's words, without link targets."""
    text = README.read_text(encoding="utf-8")
    section = text.split("\n## Supported Beds\n", 1)[1].split("\n## ", 1)[0]
    return [
        _tokens(re.sub(r"\]\([^)]*\)", "]", line))
        for line in section.splitlines()
        if line.startswith("| ") and not line.startswith(("| Family ", "|---"))
    ]


def _names(label: str) -> list[str]:
    """The names a setup label gives: its apps, its family and a family row's members.

    Labels read "<apps> · <Family>", "<Family>: <apps>" or "<Name> (<qualifier>)".
    """
    names = []
    for part in _QUALIFIER.sub("", label).split(" · "):
        for half in part.split(": ", 1):
            names.extend(_MEMBERS.split(half))
    return names


def _labels() -> set[str]:
    listed = {option["label"] for option in get_bed_type_options()}
    unlisted = {
        BED_TYPE_DISPLAY_NAMES[bed_type]
        for bed_type in SUPPORTED_BED_TYPES
        if bed_type in BED_TYPE_DISPLAY_NAMES and bed_type not in FAMILY_STEP_ROUTES
    }
    labels = listed | set(APP_VARIANT_CHOICES.values()) | unlisted
    return labels - {BED_TYPE_DISPLAY_NAMES[BED_TYPE_DIAGNOSTIC]}


def test_every_setup_label_has_a_row() -> None:
    rows = _rows()
    missing = sorted(
        {
            name
            for label in _labels()
            for name in _names(label)
            if (words := _tokens(name) - _GENERIC) and not any(words <= row for row in rows)
        }
    )
    assert not missing, (
        "Add these setup names to the README's Supported Beds table, in their family's row: "
        f"{missing}"
    )


def test_every_app_has_one_status_mark() -> None:
    text = README.read_text(encoding="utf-8")
    section = text.split("\n## Supported Beds\n", 1)[1].split("\n## ", 1)[0]
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith(("| Family ", "|---")):
            continue
        apps = line.split(" | ")[1]
        assert len(re.findall(r"\]\([^)]*\) (?:✅|🧪|⚠️)(?:,|$)", apps)) == apps.count("]("), line
