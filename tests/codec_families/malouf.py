"""Malouf: the ``malouf_new_okin`` route and the Malouf Base / Lucid Base apps."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.malouf import MaloufAppProfile, MaloufRouteProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.malouf_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={MaloufRouteProfile: FROZEN_FRAMES, MaloufAppProfile: FROZEN_FRAMES},
    bed_types=frozenset({"malouf_app", "malouf_new_okin"}),
    app_routes={
        const.BED_TYPE_MALOUF_APP: (const.CONF_MALOUF_APP_PROFILE, tuple(const.MALOUF_APP_PROFILES)),
    },
    guide=CodecGuide(
        path="docs/beds/malouf.md",
        spelled=spelled_frames(
            r"`((?:6E 01|E6 FE 16|0[45] 02)(?: [0-9A-F]{2}){3,})`", re.IGNORECASE
        ),
        frozen=frozenset().union(*FROZEN_FRAMES.values()),
    ),
)
