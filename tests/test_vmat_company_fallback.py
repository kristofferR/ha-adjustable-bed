"""Accepted V-MAT Basic E04 payload precedence over company-family hints."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from custom_components.adjustable_bed.const import (
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_LOGICDATA,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VMATBASIC,
    VIBRADORM_SERVICE_UUID,
)
from custom_components.adjustable_bed.detection import (
    detect_bed_type,
    detect_bed_type_detailed,
)


def _advertisement(records: dict[int, bytes]) -> MagicMock:
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.name = "Unknown"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = []
    info.service_data = {}
    info.manufacturer_data = records
    return info


@pytest.mark.parametrize("company", [0x066B, 0x0547, 0, 0xFFFF, 0x03B0, 0x1234])
@pytest.mark.parametrize("payload", ["babe11110000", "babea1f10000"])
def test_exact_sole_payload_precedes_company_without_selecting_product(
    company: int, payload: str
) -> None:
    """E04 ignores company and high nibbles; host AD ordering stays unknown."""
    info = _advertisement({company: bytes.fromhex(payload)})
    assert detect_bed_type(info) == BED_TYPE_VMATBASIC
    result = detect_bed_type_detailed(info)
    assert result.bed_type == BED_TYPE_VMATBASIC
    assert result.manufacturer_id == company
    assert result.requires_characteristic_check is True
    assert result.confidence == 0.6
    assert result.signals == [
        "manufacturer:vmatbasic_conditional_record",
        "raw_first_ad_order:unknown",
    ]


@pytest.mark.parametrize(
    ("company", "family"), [(0x066B, BED_TYPE_DEWERTOKIN), (0x0547, BED_TYPE_LOGICDATA)]
)
@pytest.mark.parametrize(
    "payload",
    [
        "babe111100",  # Too short for the accepted payload predicate.
        "baff11110000",  # The complete marker is required.
        "babe10110000",  # First low nibble does not match.
        "babe11020000",  # Frozen E04 A2 second-low-nibble rejection.
        "20000102",  # Different accepted VMAT app discovery payload is disjoint.
        "",  # A bare known company remains a company-family hint.
    ],
)
def test_nonmatching_payload_preserves_known_company_family(
    company: int, family: str, payload: str
) -> None:
    assert detect_bed_type(_advertisement({company: bytes.fromhex(payload)})) == family


@pytest.mark.parametrize(
    ("company", "family"), [(0x066B, BED_TYPE_DEWERTOKIN), (0x0547, BED_TYPE_LOGICDATA)]
)
@pytest.mark.parametrize("match_first", [False, True])
def test_multiple_records_preserve_company_fallback_without_guessing_raw_order(
    company: int, family: str, match_first: bool
) -> None:
    matching = (company, bytes.fromhex("babea1f10000"))
    nonmatching = (0x1234, bytes.fromhex("000011110000"))
    records = dict((matching, nonmatching) if match_first else (nonmatching, matching))
    assert detect_bed_type(_advertisement(records)) == family


@pytest.mark.parametrize("payload", ["babe111100", "baff11110000", "babe10110000", "babe11020000"])
def test_unknown_company_does_not_match_partial_predicate(payload: str) -> None:
    assert detect_bed_type(_advertisement({0x1234: bytes.fromhex(payload)})) is None


def test_payload_does_not_override_a_bed_identified_by_service_uuid() -> None:
    """Revision-3 VMAT hardware shares the BABE record; it stays on Vibradorm."""
    info = _advertisement({0x03B0: bytes.fromhex("babe11110000")})
    info.name = "VMAT 533"
    info.service_uuids = [VIBRADORM_SERVICE_UUID]
    result = detect_bed_type_detailed(info)
    assert result.bed_type == BED_TYPE_VIBRADORM
    assert result.ambiguous_types == [BED_TYPE_VMATBASIC]
