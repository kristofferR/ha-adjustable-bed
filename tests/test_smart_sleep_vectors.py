"""Every relevant accepted literal must reproduce, regardless of app naming."""

import pytest

from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.codec import smart_sleep as codec
from tests.smart_sleep_vectors import CATALOG_VECTORS, EXCLUDED, VECTORS, encode


@pytest.mark.parametrize(
    "row", [v for v in VECTORS if v["id"] not in EXCLUDED], ids=lambda v: v["id"]
)
def test_frozen_commands_and_formulas(row):
    assert encode(row) == bytes.fromhex(row["expected_bytes"])


def test_complete_corpus_and_reused_carrier():
    assert [v["id"] for v in VECTORS] == [f"V{i:03}" for i in range(1, 127)]
    for v in VECTORS:
        frozen = bytes.fromhex(v["expected_bytes"])
        if frozen[:2] == b"\x05\x02":
            assert keeson.p2(int.from_bytes(frozen[2:6], "big"), "p2_side") == frozen
    assert {
        v["id"]
        for v in VECTORS
        if bytes.fromhex(v["expected_bytes"])
        in (bytes.fromhex(h) for h in ("01b301", "01b101", "01b401", "01b102"))
    } == EXCLUDED
    assert codec.motion("p1", 5, True) != codec.motion("p2", 5, True)


@pytest.mark.parametrize("action,index,frozen", CATALOG_VECTORS)
def test_entire_finite_catalog(action, index, frozen):
    assert codec.massage("p2", action, index).hex() == frozen
