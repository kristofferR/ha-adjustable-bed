"""J1 LOGICDATA: the LOGICDATA app profiles over the Jiecang codec.

Their guide section lives in the Jiecang guide, which ``jiecang.py`` checks.
"""

from __future__ import annotations

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.logicdata import LogicdataProfile
from tests.codec_families import CodecFamily
from tests.logicdata_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={LogicdataProfile: FROZEN_FRAMES},
    bed_types=frozenset({"logicdata_app"}),
    app_routes={
        const.BED_TYPE_LOGICDATA_APP: (
            const.CONF_LOGICDATA_APP_PROFILE,
            tuple(const.LOGICDATA_APP_PROFILES),
        ),
    },
)
