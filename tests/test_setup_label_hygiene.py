"""What setup offers reads as plain choices: no raw keys, catalog debris or protocol jargon."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.adjustable_bed.app_families import APP_FAMILIES, Form, keep_never
from custom_components.adjustable_bed.beds.furnimove.profiles import furnimove_handset_choices
from custom_components.adjustable_bed.choice_labels import clean_choice_label
from custom_components.adjustable_bed.const import AUTOMATIC_LABEL, VARIANT_AUTO
from custom_components.adjustable_bed.detection import (
    APP_VARIANT_CHOICES,
    BED_TYPE_DISPLAY_NAMES,
    get_bed_type_options,
)
from custom_components.adjustable_bed.validators import VARIANTS_BY_BED_TYPE

STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)
_PACKAGE_ID = re.compile(r"\b(?:com|de|no|cn)\.[a-z0-9_]+\.[A-Za-z0-9_.]+")


def _offered_labels() -> dict[str, str]:
    """Every label setup and Configure offer as a choice, by where it comes from."""
    labels = {f"list:{option['value']}": option["label"] for option in get_bed_type_options()}
    labels |= {f"bed_type:{key}": label for key, label in BED_TYPE_DISPLAY_NAMES.items()}
    labels |= {f"app:{key}": label for key, label in APP_VARIANT_CHOICES.items()}
    labels |= {
        f"variant:{bed_type}:{key}": label
        for bed_type, variants in VARIANTS_BY_BED_TYPE.items()
        for key, label in variants.items()
    }
    labels |= {f"handset:{key}": label for key, label in furnimove_handset_choices().items()}
    return labels


def test_offered_labels_are_clean() -> None:
    problems = {
        where: label
        for where, label in _offered_labels().items()
        if "\n" in label
        or "\\n" in label
        or label.rstrip().endswith(("...", "…"))
        or "0x" in label
        or "—" in label
        or _PACKAGE_ID.search(label)
    }
    assert not problems


# Bed types whose stored "auto" is a fixed app or layout, not a detection.
_AUTO_IS_A_CHOICE = frozenset(
    {"adjustamattress", "bedtech", "remacro", "simmons", "svane"}
)


def test_automatic_choices_read_the_same() -> None:
    odd = {
        bed_type: variants[VARIANT_AUTO]
        for bed_type, variants in VARIANTS_BY_BED_TYPE.items()
        if VARIANT_AUTO in variants
        and bed_type not in _AUTO_IS_A_CHOICE
        and variants[VARIANT_AUTO] != AUTOMATIC_LABEL
    }
    assert not odd


def test_app_list_has_no_walls_of_text() -> None:
    labels = [option["label"] for option in get_bed_type_options()]
    assert max(map(len, labels)) <= 110


@pytest.mark.parametrize("family", APP_FAMILIES, ids=lambda family: family.step)
def test_every_family_answer_is_translated(family) -> None:
    if family.form is Form.DROPDOWN:
        return
    options = STRINGS["selector"].get(f"{family.step}_choice", {}).get("options", {})
    offered = set(family.answers) | {"another"}
    if family.offers_keep is not keep_never:
        offered.add("keep")
    assert not sorted(offered - set(options))


def test_clean_choice_label() -> None:
    assert clean_choice_label("\\n  RF-TOPLINE\\n  SI/BK/BK/07\\n") == "RF-TOPLINE SI/BK/BK/07"
    assert clean_choice_label('"SET REMOTE CONTROL 2,4GHz ECO ..."') == "SET REMOTE CONTROL 2,4GHz ECO"
    assert clean_choice_label("RF-LITELINE/07/") == "RF-LITELINE/07"


def _strings(section: str):
    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from walk(value, (*path, key))
        else:
            yield ".".join(path), node

    yield from walk(STRINGS[section], (section,))


def test_setup_text_has_no_em_dashes_or_title_case() -> None:
    bad = []
    for section in ("config", "selector", "issues"):
        for path, text in _strings(section):
            if "—" in text:
                bad.append(path)
            words = [word for word in text.split() if word[:1].isalpha()]
            if path.endswith(".title") and len(words) >= 3 and all(w[0].isupper() for w in words):
                bad.append(path)
    assert not bad


def test_errors_name_what_users_see() -> None:
    jargon = re.compile(r"protocol variant|boolean|signed 32-bit|UTF-16|capability word|Android")
    assert not [path for path, text in _strings("config") if ".error." in path and jargon.search(text)]
