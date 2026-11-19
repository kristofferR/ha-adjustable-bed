"""ComfortFurniture 2.3 frame literals, never hardware captures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import keeson

VECTORS = json.loads((Path(__file__).parent / "fixtures/comfortfurniture/vectors.json").read_text())
COMMANDS = [v for v in VECTORS if v["kind"] == "command"]
NOTIFICATIONS = [v for v in VECTORS if v["kind"] == "notification"]


@pytest.mark.parametrize("vector", COMMANDS, ids=lambda v: v["id"])
def test_existing_codec_reproduces_every_frozen_literal(vector) -> None:
    assert (
        keeson.frame(int(vector["inputs"]["command"], 16), order="big").hex()
        == vector["expected_bytes"]
    )


@pytest.mark.parametrize("vector", NOTIFICATIONS, ids=lambda v: v["id"])
def test_bed_notification_branches_preserve_priority(vector) -> None:
    if vector["inputs"].get("view", "bedding") != "bedding":
        # This accepted fixture belongs solely to the excluded accessory route.
        return
    assert keeson.comfortfurniture_cancels_hold(bytes.fromhex(vector["expected_bytes"])) is (
        vector["expected_result"] == "cancel_repeater_without_stop"
    )


def test_profile_builders_match_the_frozen_surface() -> None:
    from custom_components.adjustable_bed.profiles.comfortfurniture import PROFILE
    from custom_components.adjustable_bed.profiles.keeson import encode
    from tests.keeson_vectors import FROZEN_FRAMES

    assert {encode(PROFILE.wire, word).hex() for word in PROFILE.words} == FROZEN_FRAMES[
        "comfortfurniture"
    ]
    for slider in ("wave", "intensity"):
        expected = [
            v["expected_bytes"] for v in COMMANDS if v["action"].startswith(f"massage_{slider}_bin")
        ]
        for progress in range(30):
            assert (
                encode(PROFILE.wire, PROFILE.slider_word(slider, progress)).hex()
                == expected[progress // 10]
            )
