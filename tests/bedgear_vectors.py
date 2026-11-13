"""The accepted row A12's unchanged, nonempty wire literals."""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/bedgear/vectors.json").read_text())
FROZEN_FRAMES = {
    "bedgear": frozenset(
        row["expected_hex"]
        for key in ("transport", "decimal")
        for row in VECTORS[key]
        if row["expected_hex"] is not None
    )
}
