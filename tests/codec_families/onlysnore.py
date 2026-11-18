"""Snore Monitor 2.3.8 BED format, including the alarm preprocessing."""

import json
from pathlib import Path

from custom_components.adjustable_bed.profiles.onlysnore import OnlySnoreProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames

FIXTURES = Path(__file__).parents[1] / "fixtures" / "onlysnore"
FROZEN = frozenset(
    bytes.fromhex(row["expected_bytes"]).hex()
    for filename in ("commands.json", "alarms.json", "parameters.json")
    for row in json.loads((FIXTURES / filename).read_text())
)
FAMILY = CodecFamily(
    profiles={OnlySnoreProfile: {"onlysnore": FROZEN}},
    bed_types=frozenset({"onlysnore"}),
    guide=CodecGuide(
        path="docs/beds/onlysnore.md",
        frozen=FROZEN,
        entry_data={"onlysnore": {"product_type": "unKnow"}},
        spelled=spelled_frames(r"`((?:[0-9A-Fa-f]{2} ){1,}[0-9A-Fa-f]{2})`"),
    ),
)
