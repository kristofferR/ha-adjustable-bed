"""Smart Comfort seat protocol, both accepted cluster-024 apps."""

from custom_components.adjustable_bed.profiles.smart_comfort import SmartComfortProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.smart_comfort_vectors import WRITES

FROZEN = {
    key: frozenset(row[6] for row in WRITES if row[0] == key) for key in ("synargy", "synergy")
}
FAMILY = CodecFamily(
    profiles={SmartComfortProfile: FROZEN},
    bed_types=frozenset({"smart_comfort_synargy", "smart_comfort_synergy"}),
    guide=CodecGuide(
        path="docs/beds/smart-comfort.md",
        spelled=spelled_frames(r"`((?:E5 FE 16|A0 B1)(?: [0-9A-Fa-f]{2}){5,})`"),
        frozen=frozenset(frame for values in FROZEN.values() for frame in values),
    ),
)
