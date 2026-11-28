"""JunaSleep 1.0.3: every frozen literal through the existing encoders."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import keeson as codec

VECTORS = json.loads(
    Path(__file__).with_name("fixtures").joinpath("junasleep_vectors.json").read_text()
)


@pytest.mark.parametrize("row", VECTORS["commands"], ids=lambda row: row["id"])
def test_existing_codec_reproduces_every_literal(row):
    if row["kind"] == "query":
        actual = codec.STATUS_QUERY if row["protocol"] == "P1" else codec.frame(0)
    else:
        word = int.from_bytes(
            bytes(row["inputs"][:4]), "big" if row["protocol"] == "P1" else "little"
        )
        actual = codec.p2(word) if row["protocol"] == "P1" else codec.frame(word)
    assert actual == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("row", VECTORS["parsers"], ids=lambda row: row["id"])
def test_every_frozen_parser_vector(row):
    from custom_components.adjustable_bed.profiles.junasleep import parse_status

    got = parse_status("a" if row["protocol"] == "P1" else "b", bytes.fromhex(row["input_bytes"]))
    expected = row["expected"]
    if not expected["accepted"]:
        assert got is None
        return
    assert got.light == (None if expected["light"] == "unchanged" else expected["light"])
    if "timer_error" in expected:
        assert got.seconds is got.indicator is None
    else:
        assert got.seconds == expected["timer_value"]
        assert got.indicator == (
            None if expected["timer_bucket_min"] == "unchanged" else expected["timer_bucket_min"]
        )
