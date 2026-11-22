"""Labels taken from apps and manuals become entity names."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.beds.richmat.labels import richmat_mh_name
from custom_components.adjustable_bed.labels import display_label


@pytest.mark.parametrize(
    ("label", "shown"),
    [
        ("Anti Snore (app gesture)", "Anti-snore"),
        ("Massage TIMER / ALL OFF", "Massage timer / all off"),
        ("Tv Iii", "TV III"),
        ("ZERO-G preset", "Zero G"),
        ("bed head-and-foot up pictogram", "Head and foot up"),
        ("Lumbar down (unlabeled touch area)", "Lumbar down"),
    ],
)
def test_display_label_drops_artifact_notes_and_shouting(label: str, shown: str) -> None:
    assert display_label(label) == shown


@pytest.mark.parametrize(
    ("code", "label", "name", "clear"),
    [
        # A label that says part of what its code does takes the code's name; a
        # timer keeps its own duration; one naming another feature is not established.
        (0x4C, "Head+", "Head massage intensity up", True),
        (0x5F, "Hour2", "Massage timer 2 hours", True),
        (0x4C, "Back Fan", "Back fan", False),
    ],
)
def test_richmat_mh_controls_are_named_by_their_code(code: int, label: str, name: str, clear: bool) -> None:
    assert richmat_mh_name(code, label) == (name, clear)
