"""Superior sleep 1.0.0 (2), frozen live literals, without dead BOX15/1220 builders."""

import json
from pathlib import Path

VECTORS = json.loads((Path(__file__).parent / "fixtures/superior_sleep/vectors.json").read_text())
CONTROL_FRAMES = frozenset(
    row["expected_bytes"].replace(" ", "").lower()
    for row in VECTORS
    if row["expected_bytes"].startswith("05 02")
)
RECORD_FRAMES = frozenset(
    row["expected_bytes"].replace(" ", "").lower()
    for row in VECTORS
    if row["action"] != "parse" and not row["expected_bytes"].startswith("05 02")
)
FROZEN_FRAMES = dict.fromkeys(("superior_sleep_ss350", "superior_sleep_ss650"), CONTROL_FRAMES)
