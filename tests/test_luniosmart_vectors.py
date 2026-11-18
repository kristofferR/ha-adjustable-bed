"""Byte-for-byte codec admission before adding a controller."""

import pytest

from .luniosmart_vectors import OUTBOUND, encode


@pytest.mark.parametrize("row", OUTBOUND, ids=lambda row: row["id"])
def test_existing_codec_reproduces_accepted_outbound_literals(row):
    assert encode(row).hex() == row["expected_bytes"]
