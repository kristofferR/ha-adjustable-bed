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


# Configure's own forms; setup's steps and their sections are the other source.
_CONFIGURE_STEPS = ("settings", "left_settings", "right_settings")
# Keys whose setup wording depends on the step. Configure matches one of them.
_STEP_WORDED = frozenset({"confirm", "protocol_variant"})


def _setup_texts(kind: str) -> dict[str, set[str]]:
    texts: dict[str, set[str]] = {}
    for step in STRINGS["config"]["step"].values():
        for form in (step, *step.get("sections", {}).values()):
            for key, text in form.get(kind, {}).items():
                texts.setdefault(key, set()).add(text)
    return texts


@pytest.mark.parametrize("kind", ["data", "data_description"])
def test_configure_says_what_setup_says(kind: str) -> None:
    """A field setup and Configure share reads the same in both, from one wording."""
    setup = _setup_texts(kind)
    drift = {}
    for name in _CONFIGURE_STEPS:
        for key, text in STRINGS["options"]["step"][name].get(kind, {}).items():
            if key not in setup:
                continue
            if text not in setup[key] or (len(setup[key]) > 1 and key not in _STEP_WORDED):
                drift[f"{name}.{key}"] = (text, sorted(setup[key]))
    assert not drift


def test_configure_errors_are_setup_errors() -> None:
    config, options = STRINGS["config"]["error"], STRINGS["options"]["error"]
    assert {key: text for key, text in options.items() if key in config and config[key] != text} == {}


_JARGON = re.compile(
    r"\bBLE\b|GATT|protocol variant|[Rr]etained|ordinal|telemetry|descriptor|selector|"
    r"company ID|wire side|Disable angle sensing|OCTO\b|Okin CST|Okin UUID|Okin DOT with"
)


def test_setup_configure_and_repairs_speak_plainly() -> None:
    bad = [
        path
        for section in ("config", "options", "issues", "selector")
        for path, text in _strings(section)
        if _JARGON.search(text)
    ]
    assert not bad


def test_errors_in_configure_name_what_users_see() -> None:
    jargon = re.compile(r"protocol variant|boolean|signed 32-bit|UTF-8|capability word|Android")
    assert not [path for path, text in _strings("options") if ".error." in path and jargon.search(text)]


def test_one_wording_keeps_the_current_setup() -> None:
    from custom_components.adjustable_bed.app_families import KEEP_LABEL

    keeps = {
        name: options["keep"]
        for name, selector in STRINGS["selector"].items()
        if "keep" in (options := selector.get("options", {}))
    }
    assert set(keeps.values()) == {KEEP_LABEL}
    assert {family.keep_label for family in APP_FAMILIES} <= {"keep", KEEP_LABEL}


def test_app_and_brand_rows_name_no_protocol() -> None:
    from custom_components.adjustable_bed.config_flow import _bed_type_selector, _family_rows

    rows = [*_bed_type_selector(None).rows(), *(label for _choice, label in _family_rows())]
    protocol = re.compile(r"\b(?:CST|MM|SXB|Kaidi|Jalon|ELEVATE|64-Bit|7-Byte|CB24|CB35|FFE|ORE\))")
    assert [row for row in rows if protocol.search(row)] == []


# Version numbers that are part of an app's or product's own name.
_NAMED_VERSIONS = (
    "Ergomotion 4.0",
    "VIP 3.0",
    "Freestyle 2.0",
    "ELEVATE 2.0",
    "Oasis 2.0",
    "3.0 (IARM)",
    "4.0 (VDRM)",
    "5.0 (VORM)",
)
_VERSION = re.compile(r"\b(?:v?\d+\.\d+(?:\.\d+)*|\d+\.x)\b", re.IGNORECASE)
# Control box part numbers such as CB.24.42.17 are not versions.
_PART_NUMBER = re.compile(r"\bCB\.[\w./]+")


def test_offered_labels_name_no_app_version() -> None:
    """Two apps that share a store name read "older" and "newer", never a version."""
    from custom_components.adjustable_bed.config_flow import _family_rows

    labels = {**_offered_labels(), **{f"brand:{c}": label for c, label in _family_rows()}}
    labels |= {
        f"{name}:{key}": label
        for name, selector in STRINGS["selector"].items()
        if name.endswith("_choice")
        for key, label in selector.get("options", {}).items()
    }
    versioned = {}
    for where, label in labels.items():
        text = _PART_NUMBER.sub("", label)
        for name in _NAMED_VERSIONS:
            text = text.replace(name, "")
        if _VERSION.search(text):
            versioned[where] = label
    assert not versioned
