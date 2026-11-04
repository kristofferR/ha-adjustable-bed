"""S1 FFFF frame: the Solace routes (Woosa is a protocol variant), BedSense, Motion Bed."""

from __future__ import annotations

import re

from custom_components.adjustable_bed.codec.ff_frame import with_crc, with_sum
from custom_components.adjustable_bed.profiles.ff_frame import (
    BedSenseProfile,
    MotionBedProfile,
    SolaceProfile,
)
from tests.codec_families import CodecFamily, CodecGuide
from tests.ff_frame_vectors import ANOMALIES, FROZEN_FRAMES

_SPELLED = re.compile(r"`(FF ?FF ?FF ?FF(?: ?[0-9A-F]{2})+)`", re.IGNORECASE)
_ANOMALIES = frozenset().union(*ANOMALIES.values())


def _spelled(text: str) -> set[str]:
    """Spelled byte strings whose trailer is the codec's CRC or sum, or a listed anomaly.

    Shorter prefixes, such as reply patterns, are not frames.
    """
    frames = set()
    for value in _SPELLED.findall(text):
        data = bytes.fromhex(value.replace(" ", ""))
        if data.hex() in _ANOMALIES or data in (with_crc(data[:-2]), with_sum(data[:-2])):
            frames.add(data.hex())
    return frames


FAMILY = CodecFamily(
    profiles={
        SolaceProfile: FROZEN_FRAMES,
        BedSenseProfile: FROZEN_FRAMES,
        MotionBedProfile: FROZEN_FRAMES,
    },
    bed_types=frozenset({"bedsense", "motion_bed", "solace"}),
    guide=CodecGuide(
        path="docs/beds/ff_frame.md",
        spelled=_spelled,
        frozen=frozenset().union(*FROZEN_FRAMES.values()),
    ),
)
