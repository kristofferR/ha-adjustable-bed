"""SmartBed's five formats reuse four proven codecs."""

import json
from pathlib import Path

from custom_components.adjustable_bed.profiles.smartbed import PROFILES, SmartBedProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.smartbed_vectors import CATALOG_LITERALS

VECTORS = json.loads((Path(__file__).parents[1] / "fixtures/smartbed/builders.json").read_text())
FROZEN = {
    key: frozenset(
        v["expected_bytes"]
        for v in VECTORS
        if v["inputs"]["p"] in ({3, 4} if key == "cb24" else {profile.base_protocol})
    )
    for key, profile in PROFILES.items()
}
FAMILY = CodecFamily(
    profiles={SmartBedProfile: FROZEN},
    bed_types=frozenset({"okin_cb24"}),
    app_routes={"okin_cb24": ("protocol_variant", tuple(PROFILES))},
    guide=CodecGuide(
        path="docs/beds/smartbed.md",
        variant=lambda key, _bed: key,
        frozen=frozenset(v["expected_bytes"] for v in VECTORS) | frozenset(v[3] for v in CATALOG_LITERALS),
        spelled=spelled_frames(r"`((?:a55a|0502|e6fe16|2a0000|aa0000)[0-9a-f]+)`"),
    ),
)
