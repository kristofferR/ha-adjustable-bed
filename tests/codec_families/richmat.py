"""R1 Richmat 6E: Richmat, its app routes, BedTech, WiLinke, HJBed and the classic apps."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.richmat import RICHMAT_CLASSIC, RichmatProfile
from tests.codec_families import CodecFamily, CodecGuide
from tests.richmat_vectors import FROZEN_FRAMES

_SPELLED = re.compile(r"`((?:6E|5E|55|AA|04)(?: ?[0-9A-F]{2}){4,})`", re.IGNORECASE)
# Profiles reached through a protocol variant of their bed type.
_VARIANTS = {
    "richmat_wilinke": const.RICHMAT_VARIANT_WILINKE,
    "richmat_nordic": const.RICHMAT_VARIANT_NORDIC,
    "richmat_prefix55": const.RICHMAT_VARIANT_PREFIX55,
    "richmat_prefixaa": const.RICHMAT_VARIANT_PREFIXAA,
    "hjbed": "hj_bedbjrn",
    **{f"richmat_classic_{app}": app for app in RICHMAT_CLASSIC},
}


def _spelled(text: str) -> set[str]:
    """Fully spelled 6E/5E/55/AA/04 frames outside the Notifications sections."""
    sections = re.split(r"^(#+ .*)$", text, flags=re.M)
    sent = "".join(
        body
        for heading, body in zip(["", *sections[1::2]], sections[0::2], strict=True)
        if "Notifications" not in heading
    )
    frames = set()
    for literal in _SPELLED.findall(sent):
        data = bytes.fromhex(literal.replace(" ", ""))
        # One write may carry back-to-back 5-byte frames.
        if len(data) % 5 == 0 and sum(data[:-1]) & 255 != data[-1]:
            frames |= {data[i : i + 5].hex() for i in range(0, len(data), 5)}
        else:
            frames.add(data.hex())
    return frames


FAMILY = CodecFamily(
    profiles={RichmatProfile: FROZEN_FRAMES},
    bed_types=frozenset(
        {
            "bedtech",
            "hjbed",
            "leggett_wilinke",
            "richmat",
            "richmat_best_mattress",
            "richmat_blvd_home",
            "richmat_classic_apps",
            "richmat_harmony",
            "richmat_idealbed",
            "richmat_revive",
        }
    ),
    guide=CodecGuide(
        path="docs/beds/richmat.md",
        spelled=_spelled,
        frozen=frozenset().union(*FROZEN_FRAMES.values()),
        variant=lambda key, _bed_type: _VARIANTS.get(key),
        # A layout every classic app ships.
        entry_data={"richmat_classic_apps": {const.CONF_PRODUCT_TYPE: "6BRM"}},
    ),
)
