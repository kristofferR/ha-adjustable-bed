"""BedJet PowerLayer: the frame's two-byte key commands."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.bedjet_powerlayer import PowerLayerProfile
from tests.bedjet_powerlayer_vectors import FROZEN_FRAMES
from tests.codec_families import CodecFamily

FAMILY = CodecFamily(
    profiles={PowerLayerProfile: FROZEN_FRAMES},
    bed_types=frozenset({"bedjet_powerlayer"}),
)
