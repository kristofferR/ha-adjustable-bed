"""HHC ``$#`` frames: the MotoMotion, MotoSleep and Power Bob apps."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.bedgear import BedgearProfile
from custom_components.adjustable_bed.profiles.l2motion import L2MotionProfile
from custom_components.adjustable_bed.profiles.motomotion import Profile
from custom_components.adjustable_bed.profiles.motosleep import MotoSleepProfile
from tests.bedgear_vectors import FROZEN_FRAMES as BEDGEAR_FRAMES
from tests.codec_families import CodecFamily
from tests.l2motion_vectors import FROZEN_FRAMES as L2MOTION_FRAMES
from tests.motomotion_vectors import FROZEN_FRAMES, MOTOSLEEP_FRAMES

FAMILY = CodecFamily(
    profiles={L2MotionProfile: L2MOTION_FRAMES, BedgearProfile: BEDGEAR_FRAMES, Profile: FROZEN_FRAMES, MotoSleepProfile: MOTOSLEEP_FRAMES},
    bed_types=frozenset({"motomotion", "motosleep", "bedgear", "l2motion"}),
)
