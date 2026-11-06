"""Casper 6E: the Casper Base and Hush Base apps' shared library frames."""

from __future__ import annotations

from custom_components.adjustable_bed.profiles.casper import CasperProfile
from custom_components.adjustable_bed.profiles.hush import HushProfile
from tests import casper_base_vectors, hush_vectors
from tests.codec_families import CodecFamily

FAMILY = CodecFamily(
    profiles={
        CasperProfile: casper_base_vectors.FROZEN_FRAMES,
        HushProfile: hush_vectors.FROZEN_FRAMES,
    },
    bed_types=frozenset({"casper_base", "hush_base"}),
)
