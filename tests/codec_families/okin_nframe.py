"""O1 Okin N-frame: the 32-, 40- and 96-bit routes; the 64-bit routes are pending."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.okin_nframe import OkinNFrameProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.okin_nframe_vectors import FIELD_FRAMES, FROZEN_FRAMES, GATEWAY_FRAMES
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS

_O1 = "#745 O1 Okin N-frame"


def _variant(key: str, bed_type: str) -> str | None:
    """The protocol variant that reaches a profile on a bed type, where one does."""
    return {
        const.BED_TYPE_LEGGETT_PLATT: const.LEGGETT_VARIANT_OKIN,
        # SIMMONS profile keys are the packet-format variants.
        const.BED_TYPE_SIMMONS: key,
        const.BED_TYPE_DOUBLESLEEP: "p1",
        # CST profile keys are the product variants; Z-Series keys name the page.
        const.BED_TYPE_OKIN_CST: key,
        const.BED_TYPE_ZSERIES: key.removeprefix("zseries_"),
    }.get(bed_type)


FAMILY = CodecFamily(
    profiles={OkinNFrameProfile: FROZEN_FRAMES},
    bed_types=frozenset(
        {
            "customatic_clarity",
            "customatic_jeromes",
            "customatic_remedy",
            "customatic_zseries",
            "dewertokin",
            "doublesleep",
            "leggett_okin",
            "leggett_platt",
            "okimat",
            "okin_cb24",
            "okin_cst",
            "okin_dot",
            "okin_handle",
            "okin_rf_eco_bt",
            "okin_uuid",
            "serenity",
            "simmons",
            "sleepys_box25",
            "starcode_abm5_4",
            "tranquil",
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
            "okin_64bit",
        ),
        _O1,
    ),
    guide=CodecGuide(
        path="docs/beds/okin-nframe.md",
        spelled=spelled_frames(
            r"`(04 ?02(?: ?[0-9A-F]{2}){4}|05 ?02(?: ?[0-9A-F]{2}){5}|08 ?02(?: ?[0-9A-F]{2}){8}"
            r"|0C ?02(?: ?[0-9A-F]{2}){12}|E5 ?FE ?16(?: ?[0-9A-F]{2}){5}"
            r"|E6 ?FE ?16(?: ?[0-9A-F]{2}){6})`",
            re.IGNORECASE,
        ),
        # AdjustableM5X4's BOX15 selector moves with its app's frozen Keeson E6 frames.
        frozen=frozenset().union(
            *FROZEN_FRAMES.values(),
            *FIELD_FRAMES.values(),
            GATEWAY_FRAMES,
            {vector for *_, vector in BUILDER_VECTORS},
        ),
        variant=_variant,
    ),
)
