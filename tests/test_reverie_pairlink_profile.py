"""Focused tests for accepted Pairlink model advertisements."""

from types import SimpleNamespace

import pytest
from homeassistant.components import bluetooth

from custom_components.adjustable_bed import bluetooth_transport
from custom_components.adjustable_bed.beds.reverie_pairlink_profile import (
    build_pairlink_peripheral_profile,
    pairlink_host_adapter_inventory,
    parse_pairlink_manufacturer_data,
    resolve_pairlink_model,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_transport import (
    PairlinkGattFlag,
    PairlinkGattPermission,
    PairlinkHostAdapterInventoryEntry,
)


def test_type_one_advertisement_extracts_mesh_identity_and_model() -> None:
    data = bytearray(18)
    data[0:3] = b"\xff\xff\xc0"
    data[4] = 1
    data[5:9] = bytes.fromhex("78563412")
    data[9] = 144
    data[10:12] = bytes((2, 0x43))
    data[12:18] = bytes.fromhex("AABBCCDDEEFF")

    profile = parse_pairlink_manufacturer_data({0xFFFF: bytes(data[2:])})

    assert profile is not None
    assert profile.advertisement_type == 1
    assert profile.model_id == "R510L"
    assert profile.mesh_id == 0x12345678
    assert (profile.position_12, profile.position_1, profile.position_2) == (2, 3, 4)
    assert profile.device_address == "aa:bb:cc:dd:ee:ff"


def test_type_two_exact_and_extended_profiles_use_their_documented_offsets() -> None:
    exact = bytearray(25)
    exact[0:3] = b"\xb9\x05\xc0"
    exact[4] = 2
    exact[5:9] = bytes.fromhex("78563412")
    exact[17] = 145
    exact[18] = 0x05
    exact[19] = 0x53
    exact[20] = 0xA1
    extended = bytearray(27)
    extended[0:3] = b"\xff\xff\xc0"
    extended[4] = 2
    extended[5:9] = bytes.fromhex("01020304")
    extended[18] = 0x04
    extended[19] = 0x32
    extended[25] = 144

    exact_profile = parse_pairlink_manufacturer_data({0x05B9: bytes(exact[2:])})
    extended_profile = parse_pairlink_manufacturer_data({0xFFFF: bytes(extended[2:])})

    assert exact_profile is not None
    assert exact_profile.model_id == "Harmoniq Upgrade"
    assert exact_profile.mesh_id == 0x12345678
    assert (
        exact_profile.position_12,
        exact_profile.position_1,
        exact_profile.position_2,
    ) == (5, 3, 5)
    assert extended_profile is not None
    assert extended_profile.model_id == "R510L"
    assert extended_profile.mesh_id == 0x04030201
    assert (
        extended_profile.position_12,
        extended_profile.position_1,
        extended_profile.position_2,
    ) == (4, 2, 3)


def test_type_two_position_values_outside_the_source_domain_are_rejected() -> None:
    data = bytearray(25)
    data[0:3] = b"\xff\xff\xc0"
    data[4] = 2
    data[17] = 144
    data[18] = 6
    data[20] = 0xA0

    assert parse_pairlink_manufacturer_data({0xFFFF: bytes(data[2:])}) is None


def test_type_nine_requires_exact_length_and_company_identifier() -> None:
    data = bytearray(18)
    data[0:3] = b"\xff\xff\xc0"
    data[4] = 9
    data[9] = 0
    data[11:13] = (19268).to_bytes(2, "little")
    data[15] = 145
    data[16:18] = bytes((2, 0x43))

    profile = parse_pairlink_manufacturer_data({0xFFFF: bytes(data[2:])})

    assert profile is not None
    assert profile.model_id == "Harmoniq Upgrade"
    assert (profile.position_12, profile.position_1, profile.position_2) == (2, 3, 4)
    assert parse_pairlink_manufacturer_data({0xFFFF: bytes(data[2:]) + b"\x00"}) is None


def test_active_advertisement_overrides_foundation_name_fallback() -> None:
    data = bytearray(18)
    data[0:3] = b"\xff\xff\xc0"
    data[4] = 1
    data[9] = 145
    profile = parse_pairlink_manufacturer_data({0xFFFF: bytes(data[2:])})

    assert resolve_pairlink_model(profile, "R510L foundation") == "Harmoniq Upgrade"
    assert resolve_pairlink_model(None, "R450-Harmoniq bed") == "Harmoniq Upgrade"
    assert resolve_pairlink_model(None, "unknown") == "Other"


def test_other_manufacturer_payloads_do_not_claim_pairlink() -> None:
    data = bytearray(18)
    data[0:3] = b"\xff\xff\xc0"
    data[4] = 1
    data[9] = 144
    assert parse_pairlink_manufacturer_data({0x1234: bytes(data[2:])}) is None
    assert parse_pairlink_manufacturer_data({0x092D: bytes(data[2:])}) is None
    assert parse_pairlink_manufacturer_data({0xFFFF: b"\xc1" + bytes(data[3:])}) is None


def test_peripheral_profile_uses_source_owned_local_join_address() -> None:
    profile = build_pairlink_peripheral_profile(
        home_id=5566, local_join_bt_mac=bytes.fromhex("0001FE030405")
    )

    assert profile.service_uuid == "0000ffd0-0000-1000-8000-00805f9b34fb"
    assert profile.write_characteristic_uuid == "0000ffd1-0000-1000-8000-00805f9b34fb"
    assert profile.notify_characteristic_uuid == "0000ffd2-0000-1000-8000-00805f9b34fb"
    assert profile.write_flags == (PairlinkGattFlag.READ, PairlinkGattFlag.WRITE)
    assert [flag.value for flag in profile.write_flags] == ["read", "write"]
    assert [flag.value for flag in profile.notify_flags] == ["read", "notify"]
    assert profile.write_read_value == b"\x44"
    assert profile.notify_read_value == b"\x66"
    # BlueZ owns the live per-peer CCCD; exporting a second 0x2902 would
    # conflict with that daemon-managed descriptor.
    assert profile.notify_descriptor is None
    assert profile.write_permissions == (PairlinkGattPermission.READ, PairlinkGattPermission.WRITE)
    assert profile.notify_permissions == (
        PairlinkGattPermission.READ,
        PairlinkGattPermission.WRITE,
    )

    advertisement = profile.advertisement
    assert advertisement is not None
    assert advertisement.advertisement_type == "peripheral"
    assert advertisement.service_uuids == ()
    assert advertisement.local_name is None
    assert advertisement.includes == ()
    assert advertisement.start_delay_ms == 100
    assert advertisement.timeout_seconds == 0
    assert advertisement.source_advertise_mode == 2
    assert advertisement.source_tx_power_level == 3
    assert advertisement.source_include_tx_power is False
    assert advertisement.manufacturer_data == ((0, bytes.fromhex("C0FF05BE1500000001FE030405")),)


def test_peripheral_profile_requires_exact_home_and_local_join_inputs() -> None:
    with pytest.raises(ValueError, match="HomeID"):
        build_pairlink_peripheral_profile(
            home_id=True, local_join_bt_mac=bytes.fromhex("000102030405")
        )
    with pytest.raises(ValueError, match="six source-range octets"):
        build_pairlink_peripheral_profile(home_id=5566, local_join_bt_mac=b"\xff" * 6)


def test_local_join_mac_matches_the_source_generated_octet_range(monkeypatch) -> None:
    from custom_components.adjustable_bed.beds import reverie_pairlink_profile

    values = iter((0, 0.001, 0.25, 0.5, 0.75, 0.999999))
    monkeypatch.setattr(reverie_pairlink_profile.random, "random", lambda: next(values))

    assert reverie_pairlink_profile.generate_pairlink_local_join_bt_mac() == bytes(
        (0, 0, 63, 127, 191, 254)
    )


def test_host_inventory_uses_active_public_scanners_and_existing_classification(monkeypatch) -> None:
    local = SimpleNamespace(source="11:22:33:44:55:66", adapter="hci0")
    proxy = SimpleNamespace(source="proxy-source", adapter="proxy-adapter")
    transports = {
        id(local): bluetooth_transport.TransportClass.LOCAL,
        id(proxy): bluetooth_transport.TransportClass.PROXY,
    }
    monkeypatch.setattr(bluetooth, "async_current_scanners", lambda _hass: [local, proxy])
    monkeypatch.setattr(
        bluetooth_transport,
        "classify_scanner",
        lambda scanner: transports[id(scanner)],
    )

    inventory = pairlink_host_adapter_inventory(SimpleNamespace())

    assert inventory == (
        PairlinkHostAdapterInventoryEntry(
            source="11:22:33:44:55:66", transport="local", adapter="hci0", active=True
        ),
        PairlinkHostAdapterInventoryEntry(
            source="proxy-source", transport="proxy", adapter="proxy-adapter", active=True
        ),
    )


@pytest.mark.parametrize("advertisement_type", [1, 9])
@pytest.mark.parametrize("positions", [(6, 0x43), (2, 0x46), (2, 0x63)])
def test_type_one_and_nine_reject_invalid_source_position_fields(
    advertisement_type: int, positions: tuple[int, int]
) -> None:
    raw = bytearray(18)
    raw[:5] = bytes((0xFF, 0xFF, 0xC0, 0, advertisement_type))
    if advertisement_type == 1:
        raw[9] = 144
        raw[10:12] = bytes(positions)
        raw[12:18] = bytes.fromhex("AABBCCDDEEFF")
    else:
        raw[9] = 9  # The source ignores this byte; it must not mask rejection.
        raw[11:13] = (19268).to_bytes(2, "little")
        raw[15] = 144
        raw[16:18] = bytes(positions)
    assert parse_pairlink_manufacturer_data({0xFFFF: bytes(raw[2:])}) is None
