"""JMC400: the Jensen Adjustable Sleep app's JMC400 route and Svane Remote's frames.

``svane`` stays standalone: its default route writes the LinonPI multi-service
frames, so its controller's profile is a route name, not a ``JmcProfile``. Its
JMC400 route and its lamp frames are built by the codec from ``SVANE_REMOTE``.
"""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.jmc import JmcProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.jmc_vectors import FROZEN_FRAMES, FROZEN_REPORTS

FAMILY = CodecFamily(
    profiles={JmcProfile: FROZEN_FRAMES},
    bed_types=frozenset({const.BED_TYPE_JENSEN}),
    guide=CodecGuide(
        path="docs/beds/jmc.md",
        # Complete five- and six-byte frames and reports; templates and opcodes are not.
        spelled=spelled_frames(r"`((?:0A|1[0-4E])(?: [0-9A-F]{2}){4,5})`", re.IGNORECASE),
        frozen=FROZEN_REPORTS.union(*FROZEN_FRAMES.values()),
    ),
)
