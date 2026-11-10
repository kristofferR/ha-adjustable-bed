"""Paramount P1: the accepted Bed Operation artifact's complete literals."""

from custom_components.adjustable_bed.profiles.paramount import ParamountProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.paramount_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={ParamountProfile: FROZEN_FRAMES},
    bed_types=frozenset({"paramount"}),
    guide=CodecGuide(
        path="docs/beds/paramount.md",
        spelled=spelled_frames(r"`(40(?: [0-9A-Fa-f]{2}){3,15})`"),
        frozen=FROZEN_FRAMES["paramount"],
    ),
)
