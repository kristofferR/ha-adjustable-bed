"""Vibradorm VMAT: the generic route, the Caresse, Werkmeister and VMAT apps and V-MAT Basic."""

from __future__ import annotations

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.vibradorm import (
    VibradormAppProfile,
    VibradormProfile,
)
from custom_components.adjustable_bed.profiles.vmatbasic import VMatBasicProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.vibradorm_vectors import FROZEN, VALUE_FRAMES


def _frames(key: str) -> frozenset[str]:
    return frozenset().union(*FROZEN[key].values())


_VMATBASIC = ("basic", "cbi", "xtbox")

FAMILY = CodecFamily(
    profiles={
        VibradormProfile: {"legacy": _frames("legacy")},
        VibradormAppProfile: {key: _frames(key) for key in ("caresse", "werkmeister", "vmat")},
        VMatBasicProfile: {key: _frames(key) for key in _VMATBASIC},
    },
    bed_types=frozenset(
        {const.BED_TYPE_VIBRADORM, const.BED_TYPE_VIBRADORM_APP, const.BED_TYPE_VMATBASIC}
    ),
    app_routes={const.BED_TYPE_VMATBASIC: (const.CONF_VMATBASIC_PROFILE, _VMATBASIC)},
    guide=CodecGuide(
        path="docs/beds/vibradorm.md",
        # Complete frames of two or more bytes; templates with placeholders are not frames.
        spelled=spelled_frames(r"`((?:[0-9A-Fa-f]{2} )+[0-9A-Fa-f]{2})`"),
        frozen=frozenset().union(*(_frames(key) for key in FROZEN), *VALUE_FRAMES.values()),
    ),
)
