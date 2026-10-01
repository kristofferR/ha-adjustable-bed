"""Frozen VMAT manufacturer/raw AD vectors and honest host precision limits."""

from dataclasses import astuple

import pytest

from custom_components.adjustable_bed.vibradorm_vmat_discovery import (
    VmatOnboardingReports,
    extract_vmat_raw_ad,
    parse_vmat_manufacturer,
    vmat_manufacturer_diagnostics,
    vmat_onboarding_eligible,
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
    assert vmat_onboarding_eligible(fields, 1) is fields.is_vib_device
    assert vmat_onboarding_eligible(fields, 0) is False


def test_unknown_revision_can_reach_third_eligible_report_without_profile_inference():
    reports = VmatOnboardingReports()
    raw = bytes.fromhex("02010107ffb00320000102")
    assert not reports.observe(raw)
    assert not reports.observe(raw)
    assert reports.observe(raw)


@pytest.mark.parametrize(("flags_ad", "expected_flags", "eligible"), [
    ("", -1, True),
    ("020100", 0, False),
    ("020101", 1, True),
    ("030101ff", 1, True),
    ("030100ff", 0, False),
])
def test_known_raw_absent_flags_use_sdk_default_and_first_payload_byte(flags_ad, expected_flags, eligible):
    raw = bytes.fromhex(flags_ad + "07ffb0032000010200")
    payload, flags = extract_vmat_raw_ad(raw)
    assert flags == expected_flags
    assert vmat_onboarding_eligible(parse_vmat_manufacturer(payload), flags) is eligible
    reports = VmatOnboardingReports()
    assert not reports.observe(raw)
    assert not reports.observe(raw)
    assert reports.observe(raw) is eligible
    # HA's company mapping still lacks the ordered raw Flags field.
    assert vmat_onboarding_eligible(parse_vmat_manufacturer(payload), None) is None
    diagnostics = vmat_manufacturer_diagnostics({944: bytes.fromhex("20000102")})
    assert diagnostics["raw_teach_input_available"] is False
    assert "raw_advertising_flags_unavailable" in diagnostics["limits"]


@pytest.mark.parametrize("v", VECTORS["parsers"]["manufacturer_raw"], ids=lambda v: v["id"])
def test_raw_order_repeated_records_and_safe_malformed_exclusions(v):
    expected = v["expected"]
    if "exception" in expected or "behavior" in expected or v["id"] == "RAW-AD-04":
        with pytest.raises(ValueError):
            extract_vmat_raw_ad(bytes.fromhex(v["raw_scan_hex"]))
        return
    payload, _ = extract_vmat_raw_ad(bytes.fromhex(v["raw_scan_hex"]))
    assert (None if payload is None else payload.hex()) == expected["payload_hex"]
    fields = parse_vmat_manufacturer(payload)
    assert list(astuple(fields)[:8]) == expected["fields"]
    assert fields.customer == expected["customer_id"]


def test_third_eligible_current_report_not_strongest_cached_report():
    reports = VmatOnboardingReports()
    raw = bytes.fromhex("07ffb003000080fe00")
    assert not reports.observe(bytes.fromhex("07ff12340000000000"))
    assert not reports.observe(raw)
    assert not reports.observe(raw)
    assert reports.observe(raw)
    assert not reports.observe(raw)


def test_missing_flags_are_not_silently_replaced_with_zero():
    ordinary = parse_vmat_manufacturer(bytes.fromhex("b003babe0102"))
    assert vmat_onboarding_eligible(ordinary, None) is None
    assert vmat_onboarding_eligible(ordinary, 1) is True
    observed = vmat_manufacturer_diagnostics({0x03B0: bytes.fromhex("000080fe")})
    assert observed["raw_teach_input_available"] is False
    assert observed["capability_inference"] is False
    assert "source_record_order_unavailable" in observed["limits"]
