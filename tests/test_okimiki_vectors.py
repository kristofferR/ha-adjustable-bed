"""Okimiki 1.0.1 literals, evaluated against production codecs only."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import richmat as codec

FIXTURES = Path(__file__).parent / "fixtures" / "okimiki"
ORIGINAL = json.loads((FIXTURES / "vectors.json").read_text())
FOCUSED = json.loads((FIXTURES / "focused_vectors.json").read_text())


@pytest.mark.parametrize("row", ORIGINAL + FOCUSED, ids=lambda row: row["id"])
def test_accepted_literal(row):
    """No comparison to constructor names, UUID resemblance or report helpers."""
    data = row["inputs"]
    kind = row["kind"]
    if kind in ("command", "control"):
        code = data.get("long_opcode", 0) if data.get("long_press") else data["opcode"]
        actual = codec.function(code, data.get("side", 0), single=data.get("nordic", False))
    elif kind == "query":
        actual = codec.function(
            1,
            action="deviceFunctionItemCheck" + data["kind"].title(),
            single=data.get("nordic", False),
        )
    elif kind in ("fixed_notification", "common_event", "extra_alarm"):
        packet = bytes.fromhex(data["frame"])
        assert codec.is_valid(packet)
        actual = codec.frame(*packet[:-1])
    elif kind == "sleep_advertisement_query":
        actual = codec.record(6, 3, 0, (0,))
    elif kind == "light_seconds":
        high, low = (255, 255) if data["seconds"] == 0 else divmod(data["seconds"], 256)
        actual = codec.light_timer(high, low)
    elif kind == "light_color":
        actual = codec.rgb(data["red"], data["green"], data["blue"])
    elif kind == "one_shot":
        actual = b"".join(codec.countdown(data["minutes"], data["opcode"]))
    elif kind == "repeat_query":
        actual = codec.record(5, 1, 0, (0,))
    elif kind == "repeat_delete":
        actual = codec.record(5, 2, 1, (data["alarm_id"],))
    elif kind == "repeat_alarm":
        actual = codec.record(
            5,
            1,
            1,
            (data["alarm_id"], 0, data["hour"], data["minute"], data["opcode"], data["mask"]),
        )
    elif kind == "time_epoch":
        actual = codec.record(
            8, 2, 1, (*data["epoch_seconds"].to_bytes(4, "big"), int(data["timezone_minutes"] / 60))
        )
    elif kind == "time_calendar":
        actual = codec.record(
            8,
            3,
            1,
            (
                data["year"] - 1970,
                *(data[key] for key in ("month", "day", "hour", "minute", "second")),
            ),
        )
    else:
        raise AssertionError(kind)
    assert actual.hex() == row["expected_bytes"]
