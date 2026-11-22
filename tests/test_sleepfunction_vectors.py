"""SleepFunction 1.3.0 literals through the existing Richmat codec."""

import gzip
import json
from pathlib import Path

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.codec import richmat as codec


def test_frozen_sleepfunction_frames_fit_richmat_codec():
    rows = json.loads(
        gzip.decompress(
            (Path(__file__).parent / "fixtures/sleepfunction/frames.json.gz").read_bytes()
        )
    )
    assert len(rows) == 679
    for row in rows:
        args = row["inputs"]
        match row["builder"]:
            case "command":
                result = p.control(
                    bytes.fromhex(args["code"]),
                    "FRAMED" if args.get("framed") else "RAW",
                    args.get("mode", 0),
                )
            case "additive":
                result = codec.frame(*args["values"])
            case "rgb":
                result = codec.rgb(args["red"], args["green"], args["blue"])
            case "alarm":
                result = b"".join(codec.countdown(args["minutes"], args["code"]))
            case "aroma":
                result = b"".join(
                    p.aroma(op, args[key])
                    for op, key in zip((27, 28, 29), ("mode2", "mode3", "pause"), strict=True)
                )
            case "fan":
                volume = 215 + args["volume"] // 20
                result = (
                    (p.direct(1, 208 + args["hours"]) + p.direct(1, volume))
                    if args["head"]
                    else p.direct(1, 1, volume) * 2
                )
            case _:
                raise AssertionError(row)
        assert result.hex() == row["expected_bytes"].lower(), row["id"]
