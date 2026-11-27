"""Frozen APK literals against the existing codecs, before controller implementation."""

import json
from pathlib import Path

import pytest

from tests.berun_builders import encode

FROZEN = json.loads((Path(__file__).parent / "fixtures/berun/vectors.json").read_text())
VECTORS = FROZEN["vectors"]
ENCODINGS = [v for v in VECTORS if v["id"].startswith(("H", "calendar-"))]


@pytest.mark.parametrize("row", ENCODINGS, ids=lambda row: row["id"])
def test_existing_codecs_reproduce_every_literal(row):
    assert encode(row).hex() == row["expected_bytes"]
