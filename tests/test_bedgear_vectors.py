"""Literal Bedgear 2.0.1 frames, frozen by the accepted row A12 report."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.bedgear.protocol import (
    Receiver,
    color_parameters,
    token_fields,
)
from custom_components.adjustable_bed.codec.motomotion import decimal_fields, short_transport
from custom_components.adjustable_bed.profiles.bedgear import eligible, panel

VECTORS = json.loads((Path(__file__).parent / "fixtures/bedgear/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS["transport"], ids=lambda row: row["id"])
def test_transport(row):
    result = short_transport(row["command"], wrapped=row["wrapped"])
    assert (result.hex() if result is not None else None) == row["expected_hex"]


@pytest.mark.parametrize("row", VECTORS["decimal"], ids=lambda row: row["id"])
def test_decimal(row):
    assert decimal_fields(row["left"], row["right"]).hex() == row["expected_hex"]


@pytest.mark.parametrize("row", VECTORS["rgb"], ids=lambda row: row["id"])
def test_rgb(row):
    assert color_parameters(tuple(row["input"])) == tuple(row["expected_parameters"])


@pytest.mark.parametrize("row", VECTORS["selectors"], ids=lambda row: row["id"])
def test_selector(row):
    assert eligible(row["name"]) == row["expected_scan"]
    assert panel(row["name"]) == row["expected_layout"]


@pytest.mark.parametrize("row", VECTORS["tokens"], ids=lambda row: row["id"])
def test_tokens(row):
    tokens = ["00000"] * row["length"]
    for key, value in row["set"].items():
        tokens[int(key)] = value
    assert token_fields(" ".join(tokens)) == row["expected_updates"]


@pytest.mark.parametrize("row", VECTORS["framing"], ids=lambda row: row["id"])
def test_framing(row):
    receiver = Receiver()
    texts = [text for chunk in row["chunks"] for text in receiver.feed(bytes.fromhex(chunk))]
    assert texts == row["expected"]["texts"]
    assert receiver.buffer.hex() == row["expected"]["buffer_hex"]
    assert receiver.collecting == row["expected"]["collecting"]
    if "updates" in row["expected"]:
        assert [token_fields(text) for text in texts] == row["expected"]["updates"]


def test_malformed_sync_preserves_prior_fields_without_a_success_event():
    tokens = ["00000"] * 39
    tokens[24], tokens[27] = "", "00065"
    fields = token_fields(" ".join(tokens))
    assert fields["bind"] == {"available": True, "active": True}
    assert "event" not in fields and "sync_type" not in fields


def test_receive_buffer_is_bounded():
    receiver = Receiver()
    receiver.feed(b"$" + b"1" * 8193)
    assert not receiver.buffer and not receiver.collecting
