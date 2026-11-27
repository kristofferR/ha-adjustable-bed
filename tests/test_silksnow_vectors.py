"""Literal S&S Base 1.0.3 frames, before selecting the shared Richmat codec."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import richmat as codec

FROZEN = json.loads((Path(__file__).parent / "fixtures/silksnow.json").read_text())


def build(action, args):
    record = codec.record
    if action == "generic":
        return codec.function(
            args["opcode"],
            args.get("side", 0),
            single=args.get("raw", False),
            action=args.get("action", ""),
        )
    if action == "massage_text":
        return codec.function(
            0 if args["held_ms"] >= 3000 else args["short_opcode"], args["side"], single=args["raw"]
        )
    if action == "white_color":
        return codec.rgb(args["red"], args["green"], args["blue"])
    if action == "white_timer":
        seconds = args["seconds"] or 65535
        return codec.light_timer(seconds >> 8, seconds & 255)
    if action in ("clock_low", "clock_high"):
        return codec.countdown(args["minutes"], args.get("mode", 0))[action == "clock_high"]
    if action == "repeat_add":
        return record(5, 1, 1, args["fields"])
    if action == "repeat_delete":
        return record(5, 2, 1, (args["index"],))
    if action == "repeat_list":
        return record(5, 1, 0, (0,))
    if action == "time_sync":
        return record(8, 3, 1, args["parts"])
    payload = {
        "rgb_power": (4, (0, int(args.get("on", False)))),
        "rgb_color": (1, (0, args.get("red", 0), args.get("green", 0), args.get("blue", 0))),
        "rgb_timer": (2, (0, args.get("value", 0) >> 8, args.get("value", 0) & 255)),
        "rgb_groove": (5, (0, 2, args.get("mode", 0))),
        "rgb_mode": (5, (0, 1, args.get("mode", 0))),
        "rgb_breathe": (6, (0,)),
    }
    sub, fields = payload[action]
    return record(4, sub, 1, fields)


@pytest.mark.parametrize(
    "row", [v for v in FROZEN["vectors"] if v["action"] != "parse"], ids=lambda v: v["id"]
)
def test_literal_codec_match(row):
    assert build(row["action"], row["inputs"]).hex() == row["expected_bytes"]
