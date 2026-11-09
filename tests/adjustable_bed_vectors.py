"""Frozen unit087 literals, extracted from the accepted report, never the codec."""

import json
from pathlib import Path

ROWS = json.loads((Path(__file__).parent / "fixtures/adjustable_bed_vectors.json").read_text())
FROZEN_FRAMES = {
    key: frozenset(row["bytes"].replace(" ", "") for row in ROWS if row["table"] == table)
    for table, key in (
        ("25_42_02", "adjustable_bed_star"),
        ("35_22_01", "adjustable_bed_star_5a"),
        ("36_33_04a", "adjustable_bed_okin"),
    )
}
