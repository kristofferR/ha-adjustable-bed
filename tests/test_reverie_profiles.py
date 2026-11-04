"""Frozen source-vector checks for selectable Reverie app models."""

from __future__ import annotations

import hashlib
import json

from custom_components.adjustable_bed.beds.reverie_profiles import (
    REVERIE_MODEL_CHOICES,
    REVERIE_MODEL_PROFILES,
    resolve_reverie_model,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    bed_type_has_position_feedback,
)
from custom_components.adjustable_bed.validators import get_variants_for_bed_type

SELECTABLE_MODELS = (
    "3E",
    "3E Low Pro",
    "3EM",
    "3EMT",
    "3ET",
    "3EW",
    "4M",
    "4M Low Pro",
    "4MM",
    "5D",
    "6S",
    "7HT",
    "7S",
    "7T",
    "8Q",
    "8T",
    "8X",
    "9T",
    "Harmoniq Upgrade",
    "O300",
    "O300T",
    "O350LP",
    "O400",
    "Oasis 2.0",
    "Other",
    "Purple Power Base",
    "R310",
    "R310LP",
    "R310T",
    "R310TLP",
    "R350LP",
    "R400",
    "R410",
    "R410LP",
    "R450",
    "R450HT",
    "R510L",
    "R550",
    "R550L",
    "R650",
    "STK",
    "Skye 300",
    "Skye 500",
    "Skye 800",
)


def test_all_44_selectable_model_rows_match_the_frozen_matrix() -> None:
    """Model names and every capability bit match the accepted selector table."""
    assert tuple(sorted(REVERIE_MODEL_PROFILES)) == SELECTABLE_MODELS
    assert tuple(REVERIE_MODEL_CHOICES) == ("Other",) + tuple(
        name for name in REVERIE_MODEL_PROFILES if name != "Other"
    )

    rows = [
        {
            "id": profile.model_id,
            "category_id": profile.category_id,
            "nightlight": profile.nightlight,
            "tandem": profile.tandem,
            "presets": profile.presets,
            "memory_positions": profile.memory_positions,
            "positions": profile.positions,
            "massage": profile.massage,
            "comfort_settings": profile.comfort_settings,
            "routines": profile.routines,
            "alarms": profile.alarms,
            "dashboard_edit": profile.dashboard_edit,
            "lumbar": profile.lumbar,
            "pillow": profile.pillow,
            "body_tilt": profile.body_tilt,
        }
        for profile in REVERIE_MODEL_PROFILES.values()
    ]
    frozen_matrix = json.dumps(
        sorted(rows, key=lambda row: row["id"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert hashlib.sha256(frozen_matrix).hexdigest() == (
        "c7e61c853d240a75d84e084349ebce4276509d1b315ca5d8c217669dab3ef062"
    )


def test_unselectable_enums_are_not_offered_and_unknown_names_use_other() -> None:
    assert "O450" not in REVERIE_MODEL_CHOICES
    assert "Base" not in REVERIE_MODEL_CHOICES
    assert resolve_reverie_model("unrecognized model").model_id == "Other"
    assert resolve_reverie_model(None).model_id == "Other"


def test_model_selector_is_available_on_both_reverie_protocol_entries() -> None:
    for bed_type in (BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND):
        assert get_variants_for_bed_type(bed_type) == REVERIE_MODEL_CHOICES


def test_position_feedback_uses_the_selected_app_model() -> None:
    assert not bed_type_has_position_feedback(BED_TYPE_REVERIE_NIGHTSTAND, "3E")
    assert bed_type_has_position_feedback(BED_TYPE_REVERIE_NIGHTSTAND, "Other")
    assert bed_type_has_position_feedback(BED_TYPE_REVERIE, "R650")
