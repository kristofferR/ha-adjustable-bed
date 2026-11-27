"""Frozen row175 command and parser vectors from the accepted report."""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/ronco_motion_vectors.json").read_text())
