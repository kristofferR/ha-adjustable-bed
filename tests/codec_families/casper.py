"""Casper 6E: the Casper Base and Hush Base apps' shared library frames."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.hush import HushProfile
from tests.codec_families import CodecFamily
from tests.hush_vectors import FROZEN_FRAMES

FAMILY = CodecFamily(
    profiles={HushProfile: FROZEN_FRAMES},
    bed_types=frozenset({"hush_base"}),
    pending={
        "casper_base": "#745 Casper Base: its frames come from codec/casper.py; freeze its"
        " row101 vectors and move its product catalog to a profile",
    },
)
