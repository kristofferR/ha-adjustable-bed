"""Smart Base 1.3.1 literals, including conditional and unreachable builders."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import richmat as codec

VECTORS = json.loads((Path(__file__).parent / "fixtures/smart_base/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_existing_codec_reproduces_every_frozen_literal(row):
    inputs = row["inputs"]
    kind = inputs["builder"]
    if kind in ("control", "control_sequence"):
        commands = inputs.get("commands", [inputs.get("command")])
        frames = [
            codec.function(int(code, 16), inputs["mode"], single=inputs["vendor"] == "NORDIC")
            for code in commands
        ]
    elif kind == "rgb":
        frames = [codec.rgb(*bytes.fromhex(inputs["rgb"]))]
    elif kind == "led_timeout":
        seconds = inputs["seconds"]
        value = 0xFFFF if seconds == 0 and inputs["event"] == "slider_release" else seconds
        frames = [codec.light_timer(value >> 8, value & 255)]
    elif kind == "sum_frame":
        frames = [codec.frame(*inputs["header"])]
    elif kind == "header_sequence":
        frames = [codec.frame(*header) for header in inputs["headers"]]
    else:
        raise AssertionError(kind)
    assert [frame.hex() for frame in frames] == row.get(
        "expected_gatt_values", [row["expected_bytes"]]
    )
