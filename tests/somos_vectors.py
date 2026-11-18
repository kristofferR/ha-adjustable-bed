"""All 60 Somos 1.0.0/code1 (cn.com.somos) frame literals.

Frozen from the app's frames.
D/E axis names deliberately carry no anatomical or side assignment.
"""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/somos_vectors.json").read_text())
FROZEN_FRAMES = {
    variant.lower(): frozenset(
        bytes.fromhex(row["expected_bytes"]).hex() for row in VECTORS if row["variant"] == variant
    )
    for variant in "ABCDE"
}
