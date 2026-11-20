"""O2 Okin 5A: the 5A key-frame profiles, and the StarCode frames its codec builds."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.okin_5a import Okin5AProfile
from custom_components.adjustable_bed.profiles.sealy import SealyProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.okin_5a_vectors import FROZEN_FRAMES, STARCODE_FRAMES
from tests.sealy_vectors import FROZEN_FRAMES as SEALY_FRAMES

FAMILY = CodecFamily(
    profiles={Okin5AProfile: FROZEN_FRAMES, SealyProfile: SEALY_FRAMES},
    bed_types=frozenset(
        {
            "sealy_posturematic",
            "mattressfirm",
            "nectar",
            "okin_7byte",
            "okin_cb35",
            "okin_nordic",
            "star_elevate",
        }
    ),
    app_routes={"sealy_posturematic": ("product_type", ("0", "1", "2"))},
    guide=CodecGuide(
        path="docs/beds/okin-5a.md",
        spelled=spelled_frames(r"`((?:5A|09)(?: [0-9A-F]{2}){3,10})`"),
        frozen=frozenset().union(
            *FROZEN_FRAMES.values(), *STARCODE_FRAMES.values(), *SEALY_FRAMES.values()
        ),
    ),
)
