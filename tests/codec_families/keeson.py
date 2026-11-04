"""K1 Keeson E5/E6: the core routes, their aliases and the app profiles over the codec."""

from __future__ import annotations

import re

from custom_components.adjustable_bed.profiles.keeson import AppProfile, KeesonProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.keeson_vectors import FROZEN_FRAMES

_K1 = "#745 K1 Keeson E5/E6"

FAMILY = CodecFamily(
    # The cluster033 apps: one AppProfile per layout, vectors per app.
    profiles={KeesonProfile: FROZEN_FRAMES, AppProfile: FROZEN_FRAMES},
    bed_types=frozenset(
        {
            "ergomotion",
            "keeson",
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
        }
    ),
    pending={
        "ergomotion_4": _K1,
        "furnimove": f"{_K1}: frames use codec/keeson.py, handset catalog profile stays",
    },
    guide=CodecGuide(
        path="docs/beds/keeson.md",
        spelled=spelled_frames(
            r"`((?:E[56] ?FE ?16|0[45] ?02)(?: ?[0-9A-F]{2}){4,})`", re.IGNORECASE
        ),
        frozen=frozenset().union(*FROZEN_FRAMES.values()),
    ),
)
