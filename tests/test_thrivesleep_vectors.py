"""Thrive Sleep 1.1.2 literals prove reuse of the existing Richmat codec."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import richmat as codec

FIXTURES = Path(__file__).parent / "fixtures/thrivesleep"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_existing_codec(row):
    i = row["inputs"]
    match i["builder"]:
        case "generic":
            result = codec.function(i["opcode"], i.get("side", 0), single=i.get("nordic", False))
        case "time":
            seconds = i["seconds"] or 65535
            result = codec.light_timer(seconds >> 8, seconds & 255)
        case "channels":
            result = codec.rgb(*i["channels"])
        case "extended":
            result = codec.record_20_len(
                i["category"], i["subcommand"], i["operation"], i["payload"]
            )
        case "clock":
            result = b"".join(codec.countdown(i["value"], i["mode"]))
        case "literal_checksum":
            result = codec.frame(*i["prefix"])
        case "repeat_ui":
            mask = int(i["enabled"]) | sum(
                1 << (7 - DAYS.index(d)) for d in i["days"] if d != "Once"
            )
            result = codec.record_20_len(
                5, 1, 1, (i["id"], 0, i["hour"], i["minute"], i["mode"], mask)
            )
        case _:
            pytest.fail(i["builder"])
    assert result.hex() == row["expected_bytes"]
