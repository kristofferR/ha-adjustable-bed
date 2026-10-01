"""Raw first-record predicate and conditional host projections remain distinct."""

from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.const import BED_TYPE_VMATBASIC
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.vmatbasic_discovery import manufacturer_diagnostics


@pytest.mark.parametrize("company", [0, 0xFFFF, 0x03B0, 0x1234])
@pytest.mark.parametrize("nibbles", [b"\x11\x11", b"\xa1\xf1"])
def test_conditional_scan_hint_ignores_company_and_high_nibbles_without_profile_proof(
    company, nibbles
):
    payload = b"\xba\xbe" + nibbles + b"\x00\x00"
    projected = manufacturer_diagnostics({company: payload})
    assert projected["source_first_manufacturer_known"] is False
    assert projected["source_filter_result"] is None
    assert projected["profile_inference"] is False
    assert projected["conditional_records"][0]["matches_if_source_selected_this_record"] is True
    result = detect_bed_type_detailed(
        SimpleNamespace(
            service_uuids=[],
            name="Unknown",
            address="AA:BB:CC:DD:EE:FF",
            manufacturer_data={company: payload},
        )
    )
    assert result.bed_type == BED_TYPE_VMATBASIC
    assert result.requires_characteristic_check is True


def test_host_map_cannot_select_later_match_or_reconstruct_first_raw_ad_record():
    records = {1: b"bad", 2: bytes.fromhex("babe11110000")}
    result = manufacturer_diagnostics(records)
    assert result["source_filter_result"] is None
    assert [
        row["matches_if_source_selected_this_record"] for row in result["conditional_records"]
    ] == [False, True]
    assert "AD order" in result["limitation"]
    assert (
        detect_bed_type_detailed(
            SimpleNamespace(
                service_uuids=[],
                service_data={},
                address="AA:BB:CC:DD:EE:FF",
                name="Unknown",
                manufacturer_data=records,
            )
        ).bed_type
        != BED_TYPE_VMATBASIC
    )


@pytest.mark.parametrize(
    "name,services",
    [("TT214H BlueFrog", ["00001523-0000-1000-8000-00805f9b34fb"]), ("Bluetooth Mouse", [])],
)
def test_conditional_hint_respects_explicit_nonbed_exclusions(name, services):
    result = detect_bed_type_detailed(
        SimpleNamespace(
            service_uuids=services,
            name=name,
            address="AA:BB:CC:DD:EE:FF",
            manufacturer_data={0x03B0: bytes.fromhex("babe11110000")},
        )
    )
    assert result.bed_type != BED_TYPE_VMATBASIC
