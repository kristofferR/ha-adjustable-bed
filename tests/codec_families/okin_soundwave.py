"""Symphony's three proven carriers: Keeson E6, Okin N-frame and AA/2A."""

import json
from pathlib import Path

from custom_components.adjustable_bed.profiles.symphony import SymphonyWordProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames

_LITERALS = json.loads((Path(__file__).parents[1] / "fixtures/symphony/literals.json").read_text())
FROZEN = frozenset(row["expected"] for row in _LITERALS)
FROZEN_FRAMES = {"symphony": FROZEN}
FAMILY = CodecFamily(
    profiles={SymphonyWordProfile: FROZEN_FRAMES},
    bed_types=frozenset({"symphony"}),
    guide=CodecGuide(
        path="docs/beds/okin-soundwave.md",
        spelled=spelled_frames(r"`([0-9A-F]{2}(?: [0-9A-F]{2}){1,})`"),
        frozen=FROZEN,
    ),
)
