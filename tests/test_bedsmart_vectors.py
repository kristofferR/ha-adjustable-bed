"""BedSmart's frozen bytes must fit the shared codec before runtime reuse."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import protocol
from custom_components.adjustable_bed.codec import richmat

WIRE = json.loads((Path(__file__).parent / "fixtures/bedsmart/wire.json").read_text())


@pytest.mark.parametrize("row", WIRE)
def test_frozen_wire(row):
    args = row["inputs"]
    kind = row["kind"]
    if kind == "control":
        result = protocol.control(
            bytes((args["code"],)), "RAW" if args.get("raw") else "FRAMED", args.get("mode", 0)
        )
    elif kind == "framed":
        result = protocol.direct(args["a"], args["b"], args["c"])
    elif kind == "rgb":
        result = richmat.rgb(*bytes.fromhex(args["value"]))
    elif kind == "alarm":
        assert (
            " ".join(p.hex() for p in richmat.countdown(args["minutes"], args["action"]))
            == row["expected"]
        )
        return
    else:
        result = protocol.aroma(args["op"], args["value"])
    assert result.hex() == row["expected"]
