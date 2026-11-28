"""Frozen unitA22 builder rows, independent of the integration controller."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.motionflex.receive import Stream, parse
from custom_components.adjustable_bed.codec import richmat as codec

ROWS = json.loads(
    Path(__file__).with_name("fixtures").joinpath("motionflex_vectors.json").read_text()
)


@pytest.mark.parametrize(
    "row",
    [
        r
        for r in ROWS
        if r["reproducer"] in ("control", "query")
        or r.get("kind") in ("light_seconds", "clock", "rgb_wire", "sync_time")
    ],
    ids=lambda r: r["id"],
)
def test_codec_reproduces_frozen_motionflex_frames(row):
    inputs = row["inputs"]
    if row["reproducer"] == "control":
        code = (
            (inputs.get("long_opcode") or 0)
            if inputs.get("long_press")
            else inputs.get("override", inputs["opcode"])
        )
        actual = codec.function(
            code,
            inputs.get("side", 0),
            single=inputs.get("route_is_nordic", not inputs.get("framed", True)),
        )
    elif row["reproducer"] == "query":
        action, code = {
            "exit_limit": ("deviceFunctionItemExitLimit", 0),
            "check_clock": ("deviceFunctionItemCheckClock", 1),
            "check_light": ("deviceFunctionItemCheckLight", 1),
        }[inputs["name"]]
        actual = codec.function(code, action=action, single=inputs.get("route_is_nordic", False))
    elif row["kind"] == "light_seconds":
        seconds = inputs["seconds"] or 65535
        actual = codec.light_timer(seconds >> 8, seconds & 255)
    elif row["kind"] == "clock":
        actual = codec.countdown(inputs["minutes"], inputs["opcode"])
    elif row["kind"] == "rgb_wire":
        actual = codec.rgb(inputs["red"], inputs["green"], inputs["blue"])
    else:
        now = datetime.fromtimestamp(
            inputs["epoch_seconds"], timezone(timedelta(hours=inputs["zone_hours"]))
        )
        parts = inputs["local_parts"]
        # The two samples are independent in the artifact fixtures.
        actual = (
            codec.time_sync(now, build=codec.record_20_len, first_hex=True)[0],
            codec.calendar(datetime(*parts), build=codec.record_20_len),
        )
    rendered = [p.hex() for p in actual] if isinstance(actual, tuple) else actual.hex()
    assert rendered == row.get("expected", row.get("expected_bytes"))


@pytest.mark.parametrize(
    "row", [r for r in ROWS if r.get("kind") == "receive"], ids=lambda r: r["id"]
)
def test_frozen_selected_receive_rows(row):
    assert parse(bytes.fromhex(row["inputs"]["frame"])) == row["expected"]


@pytest.mark.parametrize(
    "row", [r for r in ROWS if r["reproducer"] == "extract"], ids=lambda r: r["id"]
)
def test_frozen_chunk_rows(row):
    stream = Stream()
    packets = [
        p.hex() for chunk in row["inputs"]["chunks"] for p in stream.feed(bytes.fromhex(chunk))
    ]
    assert {"frames": packets, "remaining": stream.buffer.hex()} == row["expected"]
