"""Super Colchones 1.0.2 frozen literals, never hardware captures."""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures/super_colchones"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
WIRE = [v for v in VECTORS if "opcode" in v.get("inputs", {})]
FROZEN_FRAMES = frozenset(bytes.fromhex(v["expected_bytes"]).hex() for v in WIRE)
