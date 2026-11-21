"""Frozen VMAT manufacturer/raw AD vectors and honest host precision limits."""

from dataclasses import astuple

import pytest

from custom_components.adjustable_bed.beds.vibradorm.vmat_discovery import (
    parse_vmat_manufacturer,
    vmat_manufacturer_diagnostics,
)
from tests.test_vibradorm_vmat import VECTORS


@pytest.mark.parametrize("v", VECTORS["parsers"]["manufacturer"])
def test_complete_manufacturer_formulas(v):
    fields = parse_vmat_manufacturer(bytes.fromhex(v["input"]))
    assert list(astuple(fields)[:8]) == v["expected"]


@pytest.mark.parametrize(("payload", "expected"), [
    ("b003", (944, -1, -1, -1, True, False, -1, -1, 65535)),
    ("b00320000102", (944, 2, -1, -1, True, False, 1, -1, 65535)),
    ("123420000102", (13330, 2, -1, -1, False, False, -1, -1, 65535)),
    ("ffff20000102", (65535, 2, -1, -1, False, False, -1, -1, 65535)),
])
def test_independent_company_identifier_and_eligibility_getters(payload, expected):
    fields = parse_vmat_manufacturer(bytes.fromhex(payload))
    assert astuple(fields) == expected


def test_full_payload_decodes_the_customer_id():
    fields = parse_vmat_manufacturer(bytes.fromhex("b003000080fe01021234"))
    assert list(astuple(fields)[:8]) == [944, 0, 4, 8, 1, 1, 0, -2]
    assert fields.customer == 0x1234


def test_host_diagnostics_state_what_the_mapping_cannot_carry():
    observed = vmat_manufacturer_diagnostics({0x03B0: bytes.fromhex("000080fe")})
    assert observed["raw_teach_input_available"] is False
    assert observed["capability_inference"] is False
    assert "source_record_order_unavailable" in observed["limits"]
    assert "raw_advertising_flags_unavailable" in observed["limits"]
