"""Relax Motion's two carriers and exceptional STOP, proven by literal vectors."""

from custom_components.adjustable_bed.profiles.relax_motion import RelaxMotionProfile
from tests.codec_families import CodecFamily
from tests.relax_motion_vectors import EXTRA, P1, P2

FAMILY = CodecFamily(
    profiles={
        RelaxMotionProfile: {
            "p1": frozenset(row[-1] for row in P1),
            "p2": frozenset(row[-1] for row in P2 + EXTRA) | {"0000000000"},
        }
    },
    bed_types=frozenset({"relax_motion"}),
)
