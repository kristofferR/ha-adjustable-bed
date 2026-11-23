"""All accepted P1/P2 final frames and original P2 constructor literals."""

import pytest

from custom_components.adjustable_bed.codec import suta as codec
from tests.suta_vectors import BINARY_LITERALS, VECTORS


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
def test_final_frames(vector):
    inputs = vector["inputs"]
    packet = codec.text(inputs["command"]) if vector["protocol"] == "P1" else codec.from_prefix(bytes.fromhex(inputs["prefix"]))
    assert packet.hex() == vector["expected_bytes"]


@pytest.mark.parametrize("vector", BINARY_LITERALS, ids=lambda v: v["label"])
def test_constructor_literals(vector):
    assert codec.from_prefix(bytes.fromhex(vector["prefix"])).hex() == vector["final_bytes"]
