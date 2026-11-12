"""Two independently selected Smart Sleep bed formats from accepted row094."""

from custom_components.adjustable_bed.profiles.smart_sleep import SmartSleepProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.smart_sleep_vectors import CATALOG_VECTORS, EXCLUDED, VECTORS

FROZEN = {
    key: frozenset(
        bytes.fromhex(v["expected_bytes"]).hex()
        for v in VECTORS
        if v["id"] not in EXCLUDED and v["protocol"].lower() == key
    )
    for key in ("p1", "p2")
}
FROZEN["p2"] |= frozenset(frame for _, _, frame in CATALOG_VECTORS)
FAMILY = CodecFamily(
    profiles={SmartSleepProfile: FROZEN},
    bed_types=frozenset({"smart_sleep"}),
    guide=CodecGuide(
        path="docs/beds/smart-sleep.md",
        spelled=spelled_frames(
            r"`((?:05 02|AA 00 00|2A 00 00|00 B0|00 C0|01 B2|02 0B|01 0A)(?: [0-9A-Fa-f]{2})*)`"
        ),
        variant=lambda key, _bed: key,
        entry_data={"smart_sleep": {"product_type": "0"}},
        frozen=frozenset(frame for values in FROZEN.values() for frame in values),
    ),
)
