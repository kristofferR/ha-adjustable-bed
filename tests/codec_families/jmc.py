"""JMC400: the Jensen Adjustable Sleep app's JMC400 route and Svane Remote's frames.

``svane`` stays standalone: its default route writes the LinonPI multi-service
frames, so its controller's profile is a route name, not a ``JmcProfile``. Its
JMC400 route and its lamp frames are built by the codec from ``SVANE_REMOTE``.
"""

from __future__ import annotations

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.jmc import JmcProfile
from tests.codec_families import CodecFamily
from tests.jmc_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={JmcProfile: FROZEN_FRAMES},
    bed_types=frozenset({const.BED_TYPE_JENSEN}),
)
