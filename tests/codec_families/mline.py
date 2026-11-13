"""M Line's independently accepted row147 control and auxiliary format."""

import json
from pathlib import Path

from custom_components.adjustable_bed.profiles.mline import PROFILES, MLineProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames

_ROOT = Path(__file__).parents[1] / "fixtures/mline"
_VECTORS = [
    *json.loads((_ROOT / "controls.json").read_text()),
    *json.loads((_ROOT / "parameters.json").read_text()),
]
FROZEN = frozenset(row["expected_bytes"].replace(" ", "").lower() for row in _VECTORS)
FAMILY = CodecFamily(
    profiles={MLineProfile: dict.fromkeys(PROFILES, FROZEN)},
    bed_types=frozenset({"mline"}),
    guide=CodecGuide(
        path="docs/beds/mline.md",
        spelled=spelled_frames(r"`((?:[0-9a-fA-F]{2} ){3,}[0-9a-fA-F]{2})`"),
        frozen=FROZEN,
        entry_data={"mline": {"product_type": "two"}},
        variant=lambda key, bed_type: key,
    ),
)
