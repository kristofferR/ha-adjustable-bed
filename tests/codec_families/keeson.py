"""K1 Keeson E5/E6: the core ``KeesonController`` routes and their aliases."""

from __future__ import annotations

import re

from custom_components.adjustable_bed.profiles.keeson import KeesonProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.keeson_vectors import FROZEN_FRAMES

_K1 = "#745 K1 Keeson E5/E6"

FAMILY = CodecFamily(
    profiles={KeesonProfile: FROZEN_FRAMES},
    bed_types=frozenset({"ergomotion", "keeson", "okin_ffe", "serta"}),
    pending=dict.fromkeys(
        (
            "adjustamattress",
            "bf",
            "cherish",
            "comfort_enhancements",
            "coolbase",
            "ergo_slim",
            "ergomotion_4",
            "ergomotion_app",
            "furnimove",
            "glideaway_motion",
            "malouf_legacy_okin",
            "omazz_adjusto_iii",
            "qplus_app",
            "rondure",
            "row_control",
            "sbi",
            "scott_living",
            "serta_mp_remote",
            "sleepys_box15",
            "tempur_au",
            "tempur_curve",
        ),
        _K1,
    ),
    guide=CodecGuide(
        path="docs/beds/keeson.md",
        spelled=spelled_frames(
            r"`((?:E[56] ?FE ?16|0[45] ?02)(?: ?[0-9A-F]{2}){4,})`", re.IGNORECASE
        ),
        frozen=frozenset().union(*FROZEN_FRAMES.values()),
    ),
)
