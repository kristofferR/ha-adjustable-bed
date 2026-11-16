"""Unchanged 39 accepted unit079 literals, used against production encoders only."""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/linx/vectors.json").read_text())
FROZEN = frozenset(row["expected_bytes"].lower() for row in VECTORS)
