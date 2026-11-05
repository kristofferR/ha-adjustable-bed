"""MotoMotion: the app's ASCII, binary, music, position and binding frames."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.motomotion import Profile
from tests.codec_families import CodecFamily
from tests.motomotion_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={Profile: FROZEN_FRAMES},
    bed_types=frozenset({"motomotion"}),
)
