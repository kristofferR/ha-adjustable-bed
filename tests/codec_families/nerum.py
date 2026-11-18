"""Nerum's proven ORE, Keeson and N-frame profiles, one selectable app route."""

import gzip
import json
from pathlib import Path

from custom_components.adjustable_bed.profiles.nerum import NerumProfile
from tests.codec_families import CodecFamily

_ROWS = json.loads(
    gzip.decompress((Path(__file__).parents[1] / "fixtures/nerum/builders.json.gz").read_bytes())
)
FAMILY = CodecFamily(
    profiles={
        NerumProfile: {
            key: frozenset(
                row["expected"]
                for row in _ROWS
                if row["protocol"].lower() == key
                and row["expected"]
                and not row["expected"].startswith("EXCEPTION:")
            )
            for key in ("p1", "p2", "p3")
        }
    },
    bed_types=frozenset({"nerum"}),
)
