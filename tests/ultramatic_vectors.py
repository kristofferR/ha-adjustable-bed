"""Ultramatic Smart Bed 1.1.2 send literals, read by codec contract and documentation checks."""

import json
from pathlib import Path

_PATH = Path(__file__).parent / "fixtures/ultramatic_smart_bed"
_ROWS = json.loads((_PATH / "vectors.json").read_text())["commands"]
_ROWS += json.loads((_PATH / "alarm_correction.json").read_text())["cases"]
FROZEN_FRAMES = {
    "ultramatic_smart_bed": frozenset(
        row["expected_bytes"].replace(" ", "").lower() for row in _ROWS
    )
}
