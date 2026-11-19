"""Both full CheersSleep formats are proven independently by accepted literals."""

from custom_components.adjustable_bed.profiles.cheerssleep import CheersSleepProfile
from tests.cheerssleep_vectors import AUXILIARY, NUMERIC, VECTORS
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames

FROZEN = {
    key: frozenset(
        v["expected_bytes"]
        for v in VECTORS + NUMERIC + AUXILIARY
        if (v["builder"] == "p1") == (key == "p1")
    )
    for key in ("p1", "p2")
}
FAMILY = CodecFamily(
    profiles={CheersSleepProfile: FROZEN},
    bed_types=frozenset({"cheerssleep"}),
    guide=CodecGuide(
        path="docs/beds/cheerssleep.md",
        spelled=spelled_frames(r"`((?:EE (?:01|02|B0|D0)|0[1-5] 0[137])(?: [0-9A-Fa-f]{2})+)`"),
        frozen=frozenset().union(*FROZEN.values()),
        variant=lambda key, _bed: key,
    ),
)
