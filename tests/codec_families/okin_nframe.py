"""O1 Okin N-frame: every command-word width (32, 40, 64 and 96 bits)."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.adjustable_bed import AdjustableAppProfile
from custom_components.adjustable_bed.profiles.comfort_enhancement3 import CHOICES as APEX_CHOICES
from custom_components.adjustable_bed.profiles.okin_nframe import OkinNFrameProfile
from tests.adjustable_bed_vectors import FROZEN_FRAMES as ADJUSTABLE_BED_FRAMES
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.okin_nframe_vectors import FIELD_FRAMES, FROZEN_FRAMES, GATEWAY_FRAMES
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS


def _variant(key: str, bed_type: str) -> str | None:
    """The protocol variant that reaches a profile on a bed type, where one does."""
    return {
        const.BED_TYPE_COMFORT_ENHANCEMENT3: key,
        const.BED_TYPE_LEGGETT_PLATT: const.LEGGETT_VARIANT_OKIN,
        # SIMMONS profile keys are the packet-format variants.
        const.BED_TYPE_SIMMONS: key,
        const.BED_TYPE_DOUBLESLEEP: "p1",
        # CST profile keys are the product variants; Z-Series keys name the page.
        const.BED_TYPE_OKIN_CST: key,
        const.BED_TYPE_ZSERIES: key.removeprefix("zseries_"),
        const.BED_TYPE_OKIN_64BIT: key.removeprefix("okin_64bit_"),
        # Adjustable bed (Lumbar) and eShine profile keys are their protocol variants.
        const.BED_TYPE_ADJUSTABLE_LUMBAR: key,
        const.BED_TYPE_ADJUSTABLE_BED: key,
        const.BED_TYPE_ESHINE_OKIN: key,
    }.get(bed_type)


FAMILY = CodecFamily(
    profiles={OkinNFrameProfile: FROZEN_FRAMES, AdjustableAppProfile: ADJUSTABLE_BED_FRAMES},
    bed_types=frozenset(
        {
            "adjustable_bed",
            "adjustable_lumbar",
            "customatic_clarity",
            "customatic_jeromes",
            "customatic_remedy",
            "customatic_zseries",
            "dewertokin",
            "doublesleep",
            "eshine_okin",
            "leggett_okin",
            "leggett_platt",
            "okimat",
            "resident",
            "comfort_enhancement3",
            "okin_64bit",
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
        const.BED_TYPE_COMFORT_ENHANCEMENT3: (const.CONF_PROTOCOL_VARIANT, tuple(APEX_CHOICES)),
        const.BED_TYPE_LEGGETT_OKIN: (
            const.CONF_LEGGETT_APP_PROFILE,
            tuple(const.LEGGETT_APP_PROFILES),
        ),
    },
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
            *ADJUSTABLE_BED_FRAMES.values(),
            *FIELD_FRAMES.values(),
            GATEWAY_FRAMES,
            {vector for *_, vector in BUILDER_VECTORS},
        ),
        variant=_variant,
    ),
)
