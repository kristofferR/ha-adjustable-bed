"""Saatva's native discovery and separate-side conversion admission."""

from copy import copy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    button,
    const,
    light,
)
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _confident_auto_detect,
)
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    build_single_address_pair_entry_data,
    supports_single_address_pairing,
)
from custom_components.adjustable_bed.pairing_candidates import active_pairing_candidates
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles.saatva import CHOICES, SERVICE_UUID, WRITE_UUID
from tests.test_saatva import runtime


@pytest.mark.parametrize("product", CHOICES)
async def test_native_configure_side_conversion_and_entity_exposure(
    hass, enable_custom_integrations, product
):
    c = await runtime(hass, product)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    supported = product.endswith("split_top")
    try:
        assert c._offline_controller is not None
        assert supports_single_address_pairing("saatva", product) is supported
        menu = await hass.config_entries.options.async_init(c.entry.entry_id)
        assert ("pair_sides" in menu["menu_options"]) is supported
        if not supported:
            with pytest.raises(ValueError):
                build_single_address_pair_entry_data(c.entry.data, name="Saatva")
            return
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "pair_sides"}
        )
        assert not result.get("errors")
        with (
            patch.object(hass.config_entries, "async_unload", AsyncMock(return_value=True)),
            patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)),
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], {"confirm": True}
            )
            await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert c.entry.data[const.CONF_PAIR_MODE] == const.PAIR_MODE_SINGLE_ADDRESS
        pair = SingleAddressPairedCoordinator(hass, c.entry, c)
        hass.data[const.DOMAIN][c.entry.entry_id] = pair
        _async_ensure_paired_device_registry(hass, c.entry, pair)
        buttons, lights = [], []
        await button.async_setup_entry(hass, c.entry, buttons.extend)
        await light.async_setup_entry(hass, c.entry, lights.extend)
        assert any(e.unique_id.endswith("test_head_left") for e in buttons)
        assert not any(e.unique_id.endswith("test_head_right") for e in buttons)
        assert lights == []
        for side in ("left", "right"):
            assert any(
                e.unique_id.endswith(f"toggle_light_{side}")
                for e in buttons
            )
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("product", CHOICES)
async def test_dual_bed_picker_and_data_builder_reject_one_receiver_models(hass, product):
    entries = []
    for index, chosen in enumerate((product, "bt2000_split")):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                "address": f"11:22:33:44:55:7{index}",
                "bed_type": "saatva",
                "protocol_variant": chosen,
            },
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        entries.append(entry)
    candidates = active_pairing_candidates(hass)
    if product.endswith("split_top"):
        assert candidates == []
        with pytest.raises(ServiceValidationError) as error:
            build_pair_entry_data(entries[0].data, entries[1].data, name="Saatva")
        assert error.value.translation_key == "not_supported_by_bed"
    else:
        assert candidates == entries
        assert (
            build_pair_entry_data(entries[0].data, entries[1].data, name="Saatva")["pair_mode"]
            == "separate_address"
        )


async def test_automatic_write_uuid_discovery_requires_explicit_app(
    hass, enable_custom_integrations, mock_bluetooth_service_info
):
    info = copy(mock_bluetooth_service_info)
    info.name, info.service_uuids, info.manufacturer_data = "Receiver", [WRITE_UUID], {}
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    # An uncertain match asks first, saying the device may not be a bed.
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "bluetooth_disambiguate"
    assert _confident_auto_detect(detect_bed_type_detailed(info)) is None


async def test_nearby_write_uuid_receiver_is_selectable(hass, mock_bluetooth_service_info):
    info = copy(mock_bluetooth_service_info)
    info.name, info.service_uuids, info.manufacturer_data = "Receiver", [WRITE_UUID], {}
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_setup_component",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            return_value=[info],
        ),
    ):
        result = await flow.async_step_user()
        assert info.address in flow._discovered_devices
        selected = await flow.async_step_user({"address": info.address})
    assert result["type"] == selected["type"] == FlowResultType.FORM
    assert selected["step_id"] == "bluetooth_disambiguate"


@pytest.mark.parametrize(
    "name,manufacturer",
    [("BedTech", {}), ("QRRM157738", {19543: bytes.fromhex("54307651")})],
)
async def test_shared_hint_keeps_confident_receiver_setup_suggestion(
    hass, mock_bluetooth_service_info, name, manufacturer
):
    info = copy(mock_bluetooth_service_info)
    info.name, info.service_uuids, info.manufacturer_data = name, [SERVICE_UUID], manufacturer
    result = detect_bed_type_detailed(info)
    assert result.bed_type == "bedtech" and result.confidence >= 0.7
    assert "saatva" in result.ambiguous_types
    assert _confident_auto_detect(result) == "bedtech"
    recommendation = recommend_profile({"bed_type": "richmat"}, info, {})
    assert recommendation is not None and recommendation.suggested == "bedtech"
    assert "saatva" not in recommendation.choices
    assert recommend_profile({"bed_type": "saatva"}, info, {}) is None
