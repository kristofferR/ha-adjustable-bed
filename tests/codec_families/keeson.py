"""K1 Keeson E5/E6: the core routes, their aliases and the app profiles over the codec."""

from __future__ import annotations

import json
import re
from pathlib import Path

from custom_components.adjustable_bed.profiles.keeson import AppProfile, KeesonProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.keeson_vectors import FROZEN_FRAMES

# The guide's AdjustaMattress section also spells its P3/P4 Okin N-frames, which
# its accepted report (row067) freezes in this fixture.
_ADJUSTAMATTRESS = frozenset(
    row["expected_bytes"].replace(" ", "").lower()
    for row in json.loads(
        (Path(__file__).parents[1] / "fixtures/adjustamattress/commands.json").read_text()
    )
    if row["expected_bytes"] != "NO WRITE"
)

FAMILY = CodecFamily(
    # The Keeson layout apps: one AppProfile per layout, vectors per app.
    profiles={KeesonProfile: FROZEN_FRAMES, AppProfile: FROZEN_FRAMES},
    bed_types=frozenset(
        {
            "ergomotion",
            "keeson",
            "jalon_bed",
            "okin_ffe",
            "serta",
            "ergo_slim",
            "ergomotion_app",
            "omazz_adjusto_iii",
            "qplus_app",
            "row_control",
            "serta_mp_remote",
            "tempur_au",
            "tempur_curve",
            "adjustamattress",
            "glideaway_motion",
            "malouf_legacy_okin",
            "scott_living",
            "sleepys_box15",
            "sbi",
            "rondure",
            "coolbase",
            "bf",
            "cherish",
            "comfort_enhancements",
            "ergomotion_4",
        }
    ),
    guide=CodecGuide(
        path="docs/beds/keeson.md",
        spelled=spelled_frames(
            r"`((?:E[56] ?FE ?16|0[45] ?02)(?: ?[0-9A-F]{2}){4,})`", re.IGNORECASE
        ),
        frozen=frozenset().union(*FROZEN_FRAMES.values(), _ADJUSTAMATTRESS),
    ),
)
