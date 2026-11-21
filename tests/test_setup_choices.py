"""Choices setup offers: every family answer has a label, and catalog labels are cleaned."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.app_families import APP_FAMILIES, Form, keep_never
from custom_components.adjustable_bed.choice_labels import clean_choice_label

STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)


@pytest.mark.parametrize("family", APP_FAMILIES, ids=lambda family: family.step)
def test_every_family_answer_is_translated(family) -> None:
    """An answer without a label shows its raw key in the setup list."""
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
