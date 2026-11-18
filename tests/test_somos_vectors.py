"""Literal proof before selecting Somos profiles or controller glue."""

import pytest

from custom_components.adjustable_bed.codec import keeson as codec
from tests.somos_vectors import VECTORS


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_all_accepted_literals(row):
    if row["action"] == "status_query":
        actual = {
            "B": codec.STATUS_QUERY,
            "C": codec.frame(0, header=0xE6, side=0),
            "E": codec.SOMOS_SPLIT_STATUS_QUERY,
        }[row["variant"]]
    else:
        fields = row["inputs"]
        word = int.from_bytes(bytes(fields[key] & 255 for key in ("i", "i2", "i3", "i4")), "big")
        actual = (
            codec.frame(word, header=0xE6, side=0)
            if row["protocol"] == "P1"
            else codec.p2(word, "p2" if row["protocol"] == "P2" else "p2_side")
        )
    assert actual == bytes.fromhex(row["expected_bytes"])
