"""Unit141 accepted literals, encoded by the existing Richmat codec."""

import json
from datetime import datetime
from pathlib import Path

from custom_components.adjustable_bed.codec import richmat as codec

FIXTURES = Path(__file__).parent / "fixtures/luniosmart"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
OUTBOUND = [row for row in VECTORS if row["inputs"]["builder"] != "literal_notification"]
FROZEN_FRAMES = {"luniosmart": frozenset(row["expected_bytes"] for row in OUTBOUND)}


def encode(row):
    inputs = row["inputs"]
    match inputs["builder"]:
        case "control":
            return codec.command(inputs["key"])
        case "capability_query":
            return codec.function(0, action="deviceFunctionItemExitLimit", single=inputs["nordic"])
        case "clock_sync":
            year, *parts = inputs["parts"]
            return codec.calendar(datetime(year + 1970, *parts), build=codec.record_20_len)
        case _:
            raise ValueError("Not an outbound vector")
