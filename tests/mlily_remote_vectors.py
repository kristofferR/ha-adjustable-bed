"""Unit162 frozen literals, adapted to the production Richmat codec."""

import json
from datetime import datetime
from pathlib import Path

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.mlily_remote import ACTIONS, STARTUP

ROOT = Path(__file__).parent / "fixtures/mlily_remote"
VECTORS = json.loads((ROOT / "vectors.json").read_text())
FROZEN_FRAMES = frozenset(bytes.fromhex(row["expected_bytes"]).hex() for row in VECTORS)


def encode(row):
    x = row["inputs"]
    if row["protocol"] != "P3":
        action = row["action"].removesuffix(".program")
        name = action.removeprefix("deviceFunctionItem")
        if name == "Stop":
            code = codec.STOP
        elif action in dict(STARTUP):
            code = dict(STARTUP)[action]
        else:
            pair = next((short, long) for label, short, long in ACTIONS if label == name)
            code = pair[int(row["action"].endswith(".program"))]
        assert code == x["code"]
        assert code is not None
        return codec.function(code, x["side"], action=action, single=x["raw"])
    if "date_parts" in x:
        return codec.calendar(datetime(*x["date_parts"]), build=codec.record_20_len)
    return codec.countdown(x["minutes"], x["code"])[int(x["part"] == "high")]
