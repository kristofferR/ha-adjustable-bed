"""Explicit standalone004 app selection, original names and paired boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _starcode_app_errors,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import supports_single_address_pairing

ADDRESS = "11:22:33:44:55:66"


def app_data(**extra):
    return {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "User chosen label",
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
        const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
        const.CONF_STARCODE_UI_SELECTOR: "BOX15",
        **extra,
    }


@pytest.mark.parametrize(
    "step,pairing",
    [
        ("manual_entry", "manual_pairing"),
        ("manual_config", "manual_pairing"),
        ("bluetooth_confirm", "bluetooth_pairing"),
    ],
)
async def test_every_setup_route_collects_explicit_C_D_then_pairs(
    hass, mock_bluetooth_service_info, step, pairing
):
    flow = AdjustableBedConfigFlow()
    assert flow._starcode_bluetooth_pairing is False
    flow._starcode_bluetooth_pairing = True
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")(
        {
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "App bed",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    assert result["step_id"] == "starcode_app"
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert fields == {const.CONF_STARCODE_COMMAND_SELECTOR, const.CONF_STARCODE_TRANSPORT_SELECTOR}
    with patch.object(flow, f"async_step_{pairing}", new=AsyncMock()) as resume:
        await flow.async_step_starcode_app(
            {
                const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
                const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto",
            }
        )
    resume.assert_awaited_once()
    assert flow._manual_data[const.CONF_STARCODE_COMMAND_SELECTOR] == "BOX15"
    assert flow._manual_data[const.CONF_STARCODE_UI_SELECTOR] == "BOX15"
    assert const.CONF_STARCODE_TRANSPORT_SELECTOR not in flow._manual_data
    assert flow._manual_data[const.CONF_MOTOR_COUNT] == 2
    assert flow._manual_data[const.CONF_HAS_MASSAGE] is True
    assert flow._manual_data[const.CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(
    "name,expected", [("Star1", "BOX25"), ("star1", "BOX3633"), ("BLE1", "BOX1220")]
)
async def test_factory_uses_original_bluetooth_name_not_friendly_label(hass, name, expected):
    co = MagicMock()
    co.hass = hass
    co.entry = SimpleNamespace(data=app_data())
    co.name = "Star friendly label"
    co.ble_device_name = name
    co.address = ADDRESS
    controller = await create_controller(co, const.BED_TYPE_STARCODE_ABM5_4, None, None)
    assert controller.command_selector == "BOX15"
    assert controller.ui_selector == "BOX15"
    assert controller.transport_selector == expected
    assert not supports_single_address_pairing(const.BED_TYPE_STARCODE_ABM5_4)


@pytest.mark.parametrize(
    "extra,error",
    [
        ({const.CONF_STARCODE_COMMAND_SELECTOR: "BOX99"}, const.CONF_STARCODE_COMMAND_SELECTOR),
        ({const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX15"}, const.CONF_STARCODE_TRANSPORT_SELECTOR),
        ({const.CONF_STARCODE_UI_SELECTOR: "BOX99"}, const.CONF_STARCODE_COMMAND_SELECTOR),
    ],
)
def test_config_rejects_invalid_axes_and_unreachable_transport(extra, error):
    assert _starcode_app_errors(app_data(**extra)) == {error: "starcode_app_invalid"}


async def test_options_auto_transport_roundtrip_preserves_original_name_default(hass):
    entry = MockConfigEntry(
        domain=const.DOMAIN, data=app_data(**{const.CONF_STARCODE_TRANSPORT_SELECTOR: None})
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_settings()
    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert (
        next(
            k for k in schema.schema if k.schema == const.CONF_STARCODE_TRANSPORT_SELECTOR
        ).default()
        == "auto"
    )
    assert not _starcode_app_errors(entry.data)


@pytest.mark.parametrize(
    "stored_U,chosen_C,expected_U",
    [
        ("BOX99", "BOX15", "BOX15"),
        ("BOX99", "BOX25", "BOX25"),
        ("BOX25", "BOX15", "BOX25"),
    ],
)
async def test_explicit_options_choice_repairs_hidden_U_without_losing_valid_divergence(
    hass, stored_U, chosen_C, expected_U
):
    entry = MockConfigEntry(
        domain=const.DOMAIN, data=app_data(**{const.CONF_STARCODE_UI_SELECTOR: stored_U})
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock):
        result = await flow.async_step_settings({const.CONF_STARCODE_COMMAND_SELECTOR: chosen_C})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_STARCODE_UI_SELECTOR] == expected_U


async def test_two_address_options_cannot_copy_app_selectors_between_children(hass):
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left = app_data()
    right = app_data(
        **{
            CONF_ADDRESS: "11:22:33:44:55:77",
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX25_STAR",
            const.CONF_STARCODE_UI_SELECTOR: "BOX25",
        }
    )
    entry = MockConfigEntry(
        domain=const.DOMAIN, data=build_pair_entry_data(left, right, name="Pair")
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    assert not const.STARCODE_APP_CONFIG_KEYS.intersection(
        key.schema for key in result["data_schema"].schema
    )
    result = await flow.async_step_settings({const.CONF_STARCODE_COMMAND_SELECTOR: "BOX1220"})
    assert result["errors"] == {"base": "starcode_app_unpair_first"}
    assert [
        child[const.CONF_STARCODE_COMMAND_SELECTOR]
        for child in entry.data[const.CONF_PAIR_CHILDREN]
    ] == ["BOX15", "BOX25_STAR"]


def test_name_candidate_never_guesses_the_app_or_requires_manufacturer_payload():
    import fnmatch
    import itertools
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    manifest = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/manifest.json").read_text()
    )
    matchers = [row["local_name"] for row in manifest["bluetooth"] if "local_name" in row]
    for prefix in map("".join, itertools.product("sS", "tT", "aA", "rR")):
        name = prefix + "254202079996"
        assert any(fnmatch.fnmatchcase(name, matcher) for matcher in matchers)
        result = detect_bed_type_detailed(
            _make_service_info(name=name, manufacturer_data={89: b"arbitrary"}, service_uuids=[])
        )
        assert result.bed_type != const.BED_TYPE_STARCODE_ABM5_4
        assert const.BED_TYPE_STARCODE_ABM5_4 in result.ambiguous_types
