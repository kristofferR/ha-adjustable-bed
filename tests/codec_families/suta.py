"""SUTA's paired P1/P2 wire formats and name-selected application layouts."""

from custom_components.adjustable_bed.profiles.suta import PROFILES, SutaProfile
from tests.codec_families import CodecFamily
from tests.suta_vectors import BINARY_LITERALS, VECTORS

FROZEN = frozenset(
    [*(v["expected_bytes"] for v in VECTORS), *(v["final_bytes"] for v in BINARY_LITERALS)]
)
FAMILY = CodecFamily(
    profiles={SutaProfile: dict.fromkeys((*PROFILES, "short-name"), FROZEN)},
    bed_types=frozenset({"suta"}),
)
