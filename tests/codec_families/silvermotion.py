"""SILVERmotion native custom-LDP, independent of raw LDP resemblance."""

from custom_components.adjustable_bed.profiles.silvermotion import SilvermotionProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.silvermotion_vectors import VECTORS

FROZEN = frozenset(row[5] for row in VECTORS)
FAMILY = CodecFamily(
    profiles={SilvermotionProfile: {"android": FROZEN}},
    bed_types=frozenset({"silvermotion"}),
    guide=CodecGuide(
        path="docs/beds/silvermotion.md",
        spelled=spelled_frames(r"`(C0 (?:[0-9A-F]{2} )+C0)`"),
        frozen=FROZEN,
        entry_data={"silvermotion": {"product_type": "queen"}},
    ),
)
