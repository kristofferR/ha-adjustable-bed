"""HHC ``$#`` frames: the MotoMotion, MotoSleep and Power Bob apps."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.bedgear import BedgearProfile
from custom_components.adjustable_bed.profiles.motomotion import Profile
from custom_components.adjustable_bed.profiles.motosleep import MotoSleepProfile
from tests.bedgear_vectors import FROZEN_FRAMES as BEDGEAR_FRAMES
from tests.codec_families import CodecFamily
from tests.motomotion_vectors import FROZEN_FRAMES, MOTOSLEEP_FRAMES

FAMILY = CodecFamily(
    profiles={BedgearProfile: BEDGEAR_FRAMES, Profile: FROZEN_FRAMES, MotoSleepProfile: MOTOSLEEP_FRAMES},
    bed_types=frozenset({"motomotion", "motosleep", "bedgear"}),
)
