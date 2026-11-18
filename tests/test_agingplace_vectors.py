"""Unchanged accepted Dawn House literals through the production JSON codec."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec.keeson import json_packet

FIXTURES = Path(__file__).parent / "fixtures/agingplace"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
ASSIGNMENTS = json.loads((FIXTURES / "source-command-assignments.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_literal_envelope(row):
    """Use frozen semantic fields as inputs, never execute the analyst oracle."""
    fields = json.loads(row["expected_utf8"])
    actual = json_packet(fields["code"], fields["cmd"], row["inputs"]["dvid"])
    assert actual == bytes.fromhex(row["expected_bytes"])
    assert actual.decode("utf-8") == row["expected_utf8"]


@pytest.mark.parametrize("assignment", ASSIGNMENTS, ids=lambda row: row["action"])
def test_independent_action_assignment(assignment):
    row = next(row for row in VECTORS if row["action"] == assignment["action"])
    command = {key: assignment[key] for key in ("key", "ctrm", "km", "keykt")}
    assert json_packet(2, command, row["inputs"]["dvid"]).hex() == row["expected_bytes"]
