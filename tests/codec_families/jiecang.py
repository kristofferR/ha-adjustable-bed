"""J1 Jiecang F1: the legacy route and the Jiecang app profiles."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.jiecang import JiecangProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.jiecang_vectors import FROZEN_FRAMES
from tests.logicdata_vectors import FROZEN_FRAMES as LOGICDATA_FRAMES

FAMILY = CodecFamily(
    profiles={JiecangProfile: FROZEN_FRAMES},
    bed_types=frozenset({"comfort_motion", "jiecang", "jiecang_app"}),
    app_routes={
        const.BED_TYPE_JIECANG_APP: (
            const.CONF_JIECANG_APP_PROFILE,
            tuple(const.JIECANG_APP_PROFILES),
        ),
    },
    # The guide also holds the LOGICDATA app profiles over this codec.
    guide=CodecGuide(
        path="docs/beds/jiecang.md",
        spelled=spelled_frames(r"`(F1 ?F1(?: ?[0-9A-F]{2})+ ?7E)`", re.IGNORECASE),
        frozen=frozenset().union(*FROZEN_FRAMES.values(), *LOGICDATA_FRAMES.values()),
    ),
)
