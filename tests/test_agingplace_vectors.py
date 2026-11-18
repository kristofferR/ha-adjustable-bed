"""Aging in Place 1.1.0 (87) frames through the production JSON codec."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec.keeson import json_packet

FIXTURES = Path(__file__).parent / "fixtures/agingplace"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_literal_envelope(row):
    fields = json.loads(row["expected_utf8"])
    actual = json_packet(fields["code"], fields["cmd"], row["inputs"]["dvid"])
    assert actual == bytes.fromhex(row["expected_bytes"])
    assert actual.decode("utf-8") == row["expected_utf8"]

