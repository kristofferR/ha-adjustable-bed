"""FurniMove handset identity is independent of receiver identity and transport."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.bluetooth_freshness import FreshnessStatus
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _motor_count_options,
)
from custom_components.adjustable_bed.const import (
    ADAPTER_AUTO,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_SERENITY,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_FURNIMOVE_REMOTE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    requires_pairing,
)
from custom_components.adjustable_bed.detection import (
    detect_bed_type_detailed,
    refine_okin_shared_uuid_protocol_from_gatt,
)


@pytest.mark.parametrize("chosen", [BED_TYPE_FURNIMOVE, BED_TYPE_OKIN_RF_ECO_BT])
async def test_bluetooth_confirm_uses_the_selected_app_fields(hass, chosen):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._discovery_info = SimpleNamespace(
        name="OKIN-560024", address="AA:BB:CC:DD:EE:FF",
        service_uuids=["00001420-0000-1000-8000-00805f9b34fb"], manufacturer_data={},
    )
    flow._disambiguated_bed_type = chosen
    result = await flow.async_step_bluetooth_confirm()
    fields = {marker.schema for marker in result["data_schema"].schema}
    if chosen == BED_TYPE_FURNIMOVE:
        assert fields.isdisjoint({
            CONF_PROTOCOL_VARIANT, CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_MOTOR_PULSE_DELAY_MS,
        })
    else:
        assert CONF_PROTOCOL_VARIANT in fields


@pytest.mark.parametrize("scanner_available", [False, True])
async def test_every_finish_path_requires_the_app_handset_before_probe(hass, scanner_available):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._verification_possible = lambda: scanner_available
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FURNIMOVE}
    result = await flow._finish_with_verify(data, "Bed receiver")
    assert result["step_id"] == "furnimove"
    assert {marker.schema for marker in result["data_schema"].schema} == {CONF_FURNIMOVE_REMOTE}
    assert not requires_pairing(BED_TYPE_FURNIMOVE)
    result = await flow.async_step_furnimove({CONF_FURNIMOVE_REMOTE: "not-captured"})
    assert result["errors"] == {CONF_FURNIMOVE_REMOTE: "furnimove_remote_required"}
    assert flow._pending_entry is None


async def test_shipped_offline_layout_creates_both_axes_without_a_bond_gate(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._verification_possible = lambda: False
    flow._manual_data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
        CONF_NAME: "Bed", CONF_MOTOR_COUNT: 1,
    }
    result = await flow.async_step_furnimove({CONF_FURNIMOVE_REMOTE: "00000"})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_MOTOR_COUNT] == 2
    assert result["data"][CONF_HAS_MASSAGE] is False
    assert result["data"][CONF_DISABLE_ANGLE_SENSING] is True


async def test_options_change_from_stair_requires_a_handset_then_derives_layout(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_OKIN_RF_ECO_BT,
        CONF_MOTOR_COUNT: 1,
    })
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    rebuilt = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_FURNIMOVE}, step_id="settings")
    assert rebuilt["type"] == "form"
    saved = await flow._async_options_form({
        CONF_BED_TYPE: BED_TYPE_FURNIMOVE, CONF_FURNIMOVE_REMOTE: "00000",
    }, step_id="settings")
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_FURNIMOVE_REMOTE] == "00000"
    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE
    assert _motor_count_options(BED_TYPE_OKIN_RF_ECO_BT) == [1]


async def test_explicit_furnimove_offers_all_captured_handsets_without_a_bond_gate(hass):
    """A shared handset ID must not force the app onto a different bond policy."""
    from custom_components.adjustable_bed.beds.okin_uuid import (
        FURNIMOVE_DOT_HANDSETS,
        FURNIMOVE_STANDARD_HANDSETS,
    )
    from custom_components.adjustable_bed.const import (
        ALL_PROTOCOL_VARIANTS,
        OKIMAT_VARIANTS,
        OKIN_DOT_FURNIMOVE_VARIANTS,
    )
    from custom_components.adjustable_bed.furnimove_profiles import FURNIMOVE_PROFILES

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._verification_possible = lambda: False
    flow._manual_data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FURNIMOVE}
    result = await flow.async_step_furnimove()
    marker = next(iter(result["data_schema"].schema))
    offered = set(result["data_schema"].schema[marker].container)
    saved = await flow.async_step_furnimove({CONF_FURNIMOVE_REMOTE: "82417"})
    assert saved["type"] == "create_entry"
    assert saved["data"][CONF_FURNIMOVE_REMOTE] == "82417"
    assert saved["data"][CONF_MOTOR_COUNT] == 2
    assert saved["data"][CONF_HAS_MASSAGE] is False
    assert not requires_pairing(saved["data"][CONF_BED_TYPE])
    assert offered == set(FURNIMOVE_PROFILES)
    assert len(FURNIMOVE_STANDARD_HANDSETS) == 83
    assert FURNIMOVE_STANDARD_HANDSETS.issubset(offered)
    assert FURNIMOVE_STANDARD_HANDSETS.issubset(OKIMAT_VARIANTS)
    assert OKIN_DOT_FURNIMOVE_VARIANTS == FURNIMOVE_DOT_HANDSETS
    assert OKIN_DOT_FURNIMOVE_VARIANTS.isdisjoint(ALL_PROTOCOL_VARIANTS)


async def test_furnimove_options_can_correct_90167_to_the_app_82417(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
        CONF_FURNIMOVE_REMOTE: "90167", CONF_HAS_MASSAGE: True,
    })
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    saved = await flow._async_options_form({
        CONF_BED_TYPE: BED_TYPE_FURNIMOVE, CONF_FURNIMOVE_REMOTE: "82417",
    }, step_id="settings")
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_FURNIMOVE_REMOTE] == "82417"
    assert entry.data[CONF_HAS_MASSAGE] is False
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True


async def test_furnimove_setup_probe_waits_for_live_services(hass, mock_bleak_client):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    evidence = SimpleNamespace(
        status=FreshnessStatus.FRESH, is_fresh=True, rssi=-50, source=None, path=None,
    )
    device = MagicMock(address="AA:BB:CC:DD:EE:FF", name="OKIN-560024")
    with (
        patch("custom_components.adjustable_bed.config_flow.async_gate_connection", return_value=(evidence, device)),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=mock_bleak_client)) as establish,
    ):
        report = await flow._probe_capabilities(device.address, ADAPTER_AUTO, BED_TYPE_FURNIMOVE)
    assert report.connected
    assert establish.await_args.kwargs["use_services_cache"] is False
    assert "pair" not in establish.await_args.kwargs
    mock_bleak_client.disconnect.assert_awaited_once()


async def test_dot_options_keep_a_stored_furnimove_handset_only_for_that_entry(hass):
    from custom_components.adjustable_bed.const import BED_TYPE_OKIN_DOT

    def options_flow(stored: str) -> AdjustableBedOptionsFlow:
        entry = MockConfigEntry(domain=DOMAIN, data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_OKIN_DOT,
            CONF_PROTOCOL_VARIANT: stored, CONF_MOTOR_COUNT: 2,
        })
        entry.add_to_hass(hass)
        flow = AdjustableBedOptionsFlow(entry)
        flow.hass = hass
        flow.handler = entry.entry_id
        return flow

    for stored, expected in (("93558", True), ("97450", False)):
        flow = options_flow(stored)
        form = await flow._async_options_form(None, step_id="settings")
        marker = next(m for m in form["data_schema"].schema if m.schema == CONF_PROTOCOL_VARIANT)
        container = form["data_schema"].schema[marker].container
        assert ("93558" in container) is expected
        assert {"90167", "91983"}.isdisjoint(container)
        assert stored in container


@pytest.mark.parametrize("chosen", [BED_TYPE_FURNIMOVE, BED_TYPE_SERENITY])
def test_shared_gatt_does_not_replace_an_explicit_app(chosen):
    service = MagicMock()
    service.uuid = "62741523-52f9-8864-b1ab-3b3a8d65950b"
    characteristic = MagicMock()
    characteristic.uuid = "62741525-52f9-8864-b1ab-3b3a8d65950b"
    service.characteristics = [characteristic]
    assert refine_okin_shared_uuid_protocol_from_gatt(chosen, [service], ble_model="RF ECO BT") == chosen


def test_app_gateway_is_a_candidate_with_no_inferred_handset():
    info = MagicMock()
    info.name = "OKIN-560024"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["00001420-0000-1000-8000-00805f9b34fb"]
    info.manufacturer_data = {}
    result = detect_bed_type_detailed(info)
    assert result.bed_type == BED_TYPE_FURNIMOVE
    assert result.ambiguous_types
    assert result.detected_remote is None


@pytest.mark.parametrize(
    ("service_uuids", "manufacturer_data", "expected", "confident"),
    [
        # The app checks its manufacturer and 1523 predicates before the gateway.
        (["00001420-0000-1000-8000-00805f9b34fb"], {1643: b"\x01"}, "dewertokin", True),
        (
            ["00001420-0000-1000-8000-00805f9b34fb", "00001523-0000-1000-8000-00805f9b34fb"],
            {},
            "dewertokin",
            True,
        ),
        # Another bed's unique service UUID keeps its own route.
        (
            ["00001420-0000-1000-8000-00805f9b34fb", "00001234-0000-1000-8000-00805f9b34fb"],
            {},
            "jensen",
            True,
        ),
    ],
)
def test_gateway_service_never_outranks_another_match(
    service_uuids, manufacturer_data, expected, confident
):
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect

    info = MagicMock()
    info.name = "Bed"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = service_uuids
    info.manufacturer_data = manufacturer_data
    result = detect_bed_type_detailed(info)
    assert result.bed_type == expected
    assert BED_TYPE_FURNIMOVE in result.ambiguous_types
    assert (_confident_auto_detect(result) == expected) is confident
