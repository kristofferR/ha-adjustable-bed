"""The 39 Linx 1.0.7 frame literals, used against production encoders only."""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/linx/vectors.json").read_text())
FROZEN = frozenset(row["expected_bytes"].lower() for row in VECTORS)
