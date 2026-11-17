"""All 60 accepted row099 literals, cn.com.somos 1.0.0/code1.

Frozen from the repaired accepted report, without replaying its reproducer.
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
