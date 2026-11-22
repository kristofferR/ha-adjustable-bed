"""Literal production codec tests for Sleep Assistant's valid input projections."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import sleep_assistant as codec

FIXTURES = Path(__file__).parent / "fixtures" / "sleep_assistant"
BUILDERS = json.loads((FIXTURES / "builders.json").read_text())
PARSERS = json.loads((FIXTURES / "parsers.json").read_text())


@pytest.mark.parametrize("row", BUILDERS, ids=lambda r: r["id"])
def test_builder(row):
    actual = (
        getattr(codec, row["inputs"]["name"])
        if row["builder"] == "constant"
        else getattr(codec, row["builder"])(**row["inputs"])
    )
    assert actual == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("row", PARSERS, ids=lambda r: r["id"])
def test_parser(row):
    assert getattr(codec, row["parser"])(**row["inputs"]) == row["expected_state"]


def test_unlisted_mask_and_callback_split():
    assert codec.instruction(3) == codec.instruction(0)
    assert codec.split_notifications(bytes.fromhex("ddee01eeddddee02eedd")) == [
        bytes.fromhex("ddee01eedd"),
        bytes.fromhex("ddee02eedd"),
    ]
    assert codec.split_notifications(bytes.fromhex("880001")) == [bytes.fromhex("880001")]
    assert codec.split_notifications(bytes.fromhex("ddee01")) == [bytes.fromhex("ddee01")]


def test_short_notifications_and_excluded_history_are_ignored():
    for data in ("", "dd", "ddee", "8a", "81", "89000000", "8700000000000000"):
        assert codec.raw_fields(data) == {}
        assert codec.scalar_fields(data) == {}
        assert codec.remote_fields(data) == {}
