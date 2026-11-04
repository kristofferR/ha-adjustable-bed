"""O1 Okin N-frame: the 32-bit routes; the other command-word widths are pending."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.okin_nframe import OkinNFrameProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.okin_nframe_vectors import FIELD_FRAMES, FROZEN_FRAMES, GATEWAY_FRAMES

_O1 = "#745 O1 Okin N-frame"


def _variant(_key: str, bed_type: str) -> str | None:
    """The generic Leggett & Platt bed type reaches the Okin profiles by variant."""
    return const.LEGGETT_VARIANT_OKIN if bed_type == const.BED_TYPE_LEGGETT_PLATT else None


FAMILY = CodecFamily(
    profiles={OkinNFrameProfile: FROZEN_FRAMES},
    bed_types=frozenset(
        {
            "customatic_clarity",
            "customatic_jeromes",
            "customatic_remedy",
            "dewertokin",
            "leggett_okin",
            "leggett_platt",
            "okimat",
            "okin_handle",
            "okin_rf_eco_bt",
            "okin_uuid",
        }
    ),
    app_routes={
        const.BED_TYPE_LEGGETT_OKIN: (
            const.CONF_LEGGETT_APP_PROFILE,
            tuple(const.LEGGETT_APP_PROFILES),
        ),
    },
    pending=dict.fromkeys(
        (
            "adjustable_lumbar",
            "customatic_zseries",
            "doublesleep",
            "okin_64bit",
            "okin_cb24",
            "okin_cst",
            "okin_dot",
            "serenity",
            "simmons",
            "sleepys_box25",
            "starcode_abm5_4",
            "tranquil",
        ),
        _O1,
    ),
    guide=CodecGuide(
        path="docs/beds/okin-nframe.md",
        spelled=spelled_frames(
            r"`(04 ?02(?: ?[0-9A-F]{2}){4}|E5 ?FE ?16(?: ?[0-9A-F]{2}){5})`", re.IGNORECASE
        ),
        frozen=frozenset().union(*FROZEN_FRAMES.values(), *FIELD_FRAMES.values(), GATEWAY_FRAMES),
        variant=_variant,
    ),
)
