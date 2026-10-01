"""Accepted manufacturer formulas and honest host-observation diagnostics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_VIBRADORM_APP,
    CONF_BED_TYPE,
    CONF_PAIR_ID,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.diagnostics import async_get_config_entry_diagnostics
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.vibradorm_app_discovery import (
    ManufacturerRecord,
    manufacturer_discovery_diagnostics,
    parse_manufacturer_record,
    public_filter_verdict,
    sdk_first_manufacturer,
)


@pytest.mark.parametrize(
    "payload,customer,identifier,flags",
    [
        (None, 0xFFFE, 0, 0),
        (b"", 0xFFFF, 0, 0),
        (bytes.fromhex("ff"), 0xFFFF, 0, 0),
        (bytes.fromhex("ff80"), 0xFFFF, 0xFF80, 0),
        (bytes.fromhex("1234f0"), 0xFFFF, 0x1234, 0),
        (bytes.fromhex("1234abcf"), 0xFFFF, 0x1234, 0xAC),
        (bytes.fromhex("12343ff00018"), 0xFFFF, 0x1234, 0x3F),
        (bytes.fromhex("12343ff00018aa"), 0xFFFE, 0x1234, 0x3F),
        (bytes.fromhex("12343ff00018aabb"), 0xFFFE, 0x1234, 0x3F),
        (bytes.fromhex("12343ff00018aabbcc"), 0xFFFE, 0x1234, 0x3F),
        (bytes.fromhex("12343ff00018aabbccdd"), 0x0018, 0x1234, 0x3F),
        (bytes.fromhex("fffff00fff8000000000"), 0xFF80, 0xFFFF, 0xF0),
    ],
)
def test_literal_customer_identifier_and_high_nibble_vectors(payload, customer, identifier, flags):
    fields = parse_manufacturer_record(ManufacturerRecord(0x03B0, payload))
    assert (fields.customer, fields.identifier, fields.flags) == (customer, identifier, flags)
    assert fields.sync_flag is bool(flags & 0x10)
    assert fields.init_flag is bool(flags & 0x20)
    assert fields.payload_length == (None if payload is None else len(payload))


@pytest.mark.parametrize(
    "company,accepted",
    [
        (0x03B0, True),
        (0xFFFF, True),
        (-1, True),
        (0x103B0, True),
        (0xB003, False),
        (0, False),
        (0xFFFF0000, False),
    ],
)
def test_company_short_mask_is_not_payload_identifier(company, accepted):
    fields = parse_manufacturer_record(ManufacturerRecord(company, bytes.fromhex("03b0")))
    assert fields.company_accepted is accepted
    assert fields.company_id == company & 0xFFFF
    assert fields.identifier == 0x03B0


def test_sdk_selects_first_ordered_record_not_lowest_or_first_accepted_company():
    records = (
        ManufacturerRecord(0xFFFF, b"first"),
        ManufacturerRecord(0x03B0, b"second"),
        ManufacturerRecord(0xFFFF, b"duplicate"),
    )
    assert sdk_first_manufacturer(records) is records[0]
    reversed_records = tuple(reversed(records))
    assert sdk_first_manufacturer(reversed_records) is records[2]
    rejected_first = (ManufacturerRecord(1, b"rejected"), records[1])
    assert not parse_manufacturer_record(sdk_first_manufacturer(rejected_first)).company_accepted


def test_absent_sdk_record_uses_empty_payload_not_null_sentinel():
    absent = sdk_first_manufacturer(())
    assert absent == ManufacturerRecord(-1, b"")
    fields = parse_manufacturer_record(absent)
    assert fields.company_id == 0xFFFF
    assert fields.company_accepted
    assert fields.customer == 0xFFFF
    assert parse_manufacturer_record(ManufacturerRecord(-1, None)).customer == 0xFFFE


@pytest.mark.parametrize(
    "profile,customer,accepted",
    [
        ("caresse", 0xFFFE, True),
        ("caresse", 1, True),
        ("caresse", 0xFFFF, True),
        ("werkmeister", 0xFFFF, True),
        ("werkmeister", 0x0018, True),
        ("werkmeister", 0x0012, True),
        ("werkmeister", 0xFFFE, False),
        ("werkmeister", 1, False),
    ],
)
def test_public_customer_gate_is_flavor_specific(profile, customer, accepted):
    payload = b"\0\0\0\0" + customer.to_bytes(2, "big") + b"\0" * 4
    fields = parse_manufacturer_record(ManufacturerRecord(0x03B0, payload))
    verdict = public_filter_verdict(profile, fields, 1)
    assert verdict.status == ("accepted" if accepted else "rejected")
    if not accepted:
        assert verdict.reasons == ("customer_not_ffff_0018_or_0012",)


def test_public_flags_are_raw_ad_flags_not_manufacturer_sync_init_or_connectability():
    fields = parse_manufacturer_record(ManufacturerRecord(0x03B0, bytes.fromhex("00003ff0")))
    assert fields.sync_flag and fields.init_flag
    assert public_filter_verdict("caresse", fields, 0).status == "rejected"
    assert public_filter_verdict("caresse", fields, 2).status == "rejected"
    assert public_filter_verdict("caresse", fields, 3).status == "accepted"
    assert public_filter_verdict("caresse", fields, None).status == "unavailable"
    noncompany = parse_manufacturer_record(ManufacturerRecord(1, b""))
    assert public_filter_verdict("caresse", noncompany, 1).reasons == ("company_not_03b0_or_ffff",)


def test_host_map_order_never_claims_sdk_first_or_profile_even_with_one_record():
    forward = {0xFFFF: b"", 0x03B0: bytes.fromhex("123430f00018aabbccdd")}
    reverse = dict(reversed(list(forward.items())))
    first = manufacturer_discovery_diagnostics(forward)
    assert first == manufacturer_discovery_diagnostics(reverse)
    for mapping in ({}, {0x03B0: b""}, forward):
        diagnostic = manufacturer_discovery_diagnostics(mapping)
        assert diagnostic["sdk_first_record"] is None
        assert diagnostic["sdk_first_record_equivalent"] is False
        assert diagnostic["capability_inference"] is False
        assert "sdk_record_order_unavailable" in diagnostic["limits"]
        assert "duplicate_company_records_not_preserved" in diagnostic["limits"]
        assert (
            diagnostic["automatic_selection"] == "excluded_explicit_target_and_app_profile_required"
        )


def test_observed_rejection_reason_is_actionable_without_claiming_full_public_match():
    data = manufacturer_discovery_diagnostics({0x03B0: bytes.fromhex("12340000000100000000")})
    record = data["records"][0]
    verdicts = record["public_filter_if_this_were_sdk_selected"]
    assert verdicts["caresse"] == {
        "status": "unavailable",
        "reasons": ["raw_advertising_flags_unavailable"],
    }
    assert verdicts["werkmeister"] == {
        "status": "rejected",
        "reasons": ["customer_not_ffff_0018_or_0012"],
    }
    assert record["customer"] == 1


def test_host_map_never_falls_back_to_later_accepted_record():
    diagnostic = manufacturer_discovery_diagnostics({1: b"", 0x03B0: b""})
    assert diagnostic["sdk_first_record"] is None
    records = diagnostic["records"]
    assert len(records) == 2
    assert records[0]["public_filter_if_this_were_sdk_selected"]["caresse"] == {
        "status": "rejected",
        "reasons": ["company_not_03b0_or_ffff"],
    }
    assert (
        records[1]["public_filter_if_this_were_sdk_selected"]["caresse"]["status"] == "unavailable"
    )


def observed_info(payload):
    return SimpleNamespace(
        name="Observed",
        rssi=-60,
        service_uuids=["observed-service"],
        manufacturer_data={0x03B0: payload},
        source="adapter",
    )


@pytest.mark.parametrize("available", [False, True])
async def test_standalone_real_diagnostics_exposes_parser_and_observation_limits(hass, available):
    address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: address, CONF_BED_TYPE: BED_TYPE_VIBRADORM_APP}
    )
    entry.add_to_hass(hass)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.bed_type = BED_TYPE_VIBRADORM_APP
    coordinator.address = address
    coordinator.controller = coordinator.client = None
    coordinator.is_connected = coordinator.is_connecting = False
    coordinator.position_data = {}
    coordinator.connection_history = []
    coordinator.adapter_details = coordinator.command_timing = coordinator.pairing_diagnostics = {}
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    payload = bytes.fromhex("123430f00018aabbccdd")
    with (
        patch(
            "custom_components.adjustable_bed.diagnostics.async_get_integration",
            new=AsyncMock(return_value=SimpleNamespace(version="test")),
        ),
        patch(
            "custom_components.adjustable_bed.diagnostics.connection_reachability", return_value={}
        ),
        patch(
            "custom_components.adjustable_bed.diagnostics.find_service_info_by_address",
            return_value=(observed_info(payload) if available else None, True),
        ) as lookup,
    ):
        diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    lookup.assert_called_once_with(hass, address, allow_non_connectable=True)
    advertisement = diagnostic["advertisement"]
    assert advertisement["available"] is available
    parsed = advertisement["vibradorm_app_discovery"]
    assert parsed["sdk_first_record_equivalent"] is False
    if available:
        assert parsed["records"][0]["customer"] == 0x0018
        assert advertisement["service_uuids"] == ["observed-service"]
    else:
        assert parsed["records"] == []


async def test_paired_diagnostics_parse_each_observed_physical_side_and_redact_addresses(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "discovery-pair"})
    entry.add_to_hass(hass)
    addresses = {"left": "AA:BB:CC:DD:EE:01", "right": "AA:BB:CC:DD:EE:02"}
    children = {
        side: SimpleNamespace(
            address=address,
            bed_type=BED_TYPE_VIBRADORM_APP,
            controller=None,
            is_connected=False,
            position_data={},
            command_timing={},
            entry=SimpleNamespace(data={CONF_BED_TYPE: BED_TYPE_VIBRADORM_APP}),
        )
        for side, address in addresses.items()
    }
    coordinator = MagicMock(spec=PairedBedCoordinator)
    coordinator.children = children
    coordinator.name = "Pair"
    coordinator.connection_mode = "sequential"
    coordinator.is_connected = False
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    observations = {
        addresses["left"]: observed_info(bytes.fromhex("123430f00018aabbccdd")),
        addresses["right"]: observed_info(bytes.fromhex("123430f00001aabbccdd")),
    }
    with (
        patch(
            "custom_components.adjustable_bed.diagnostics.async_get_integration",
            new=AsyncMock(return_value=SimpleNamespace(version="test")),
        ),
        patch(
            "custom_components.adjustable_bed.diagnostics.connection_reachability", return_value={}
        ),
        patch(
            "custom_components.adjustable_bed.diagnostics.find_service_info_by_address",
            side_effect=lambda _hass, address, **kwargs: (observations[address], False),
        ) as lookup,
    ):
        diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    assert {call.args[1] for call in lookup.call_args_list} == set(addresses.values())
    for side, customer in (("left", 0x0018), ("right", 1)):
        observed = diagnostic["sides"][side]
        assert observed["address"] == "AA:BB:CC:**:**:**"
        parsed = observed["advertisement"]["vibradorm_app_discovery"]
        assert parsed["records"][0]["customer"] == customer
        assert parsed["sdk_first_record"] is None
