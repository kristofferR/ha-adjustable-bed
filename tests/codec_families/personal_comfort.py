"""Personal Comfort owns its routes; Malouf delegates its frames to Richmat."""

from custom_components.adjustable_bed.profiles.instant_comfort import InstantComfortProfile
from custom_components.adjustable_bed.profiles.personal_comfort import PersonalComfortProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.instant_comfort_vectors import FROZEN_FRAMES as INSTANT_FRAMES
from tests.personal_comfort_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={PersonalComfortProfile: FROZEN_FRAMES, InstantComfortProfile: INSTANT_FRAMES},
    bed_types=frozenset({"personal_comfort", "instant_comfort"}),
    guide=CodecGuide(
        path="docs/beds/personal-comfort.md",
        spelled=spelled_frames(r"`([0-9a-fA-F]{2}(?: [0-9a-fA-F]{2})*)`"),
        frozen=frozenset().union(*FROZEN_FRAMES.values(), *INSTANT_FRAMES.values()),
        variant=lambda key, _bed: key,
        entry_data={"personal_comfort": {"product_type": "other"}},
    ),
)
