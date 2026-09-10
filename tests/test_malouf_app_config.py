"""Explicit Malouf/Lucid app selection preserves existing routes and paired sides."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_NEW_OKIN,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_SIDE,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MALOUF_LAYOUT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data

APP_DATA = {
    CONF_BED_TYPE: BED_TYPE_MALOUF_APP,
    CONF_MALOUF_APP_PROFILE: "malouf",
    CONF_MALOUF_APP_MODEL: "l600",
    CONF_MALOUF_APP_TRANSPORT: "command32_new",
    CONF_MALOUF_APP_SIDE: "primary",
}
APP_KEYS = {
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MALOUF_APP_SIDE,
}


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_setup_requires_explicit_route_and_model_controls_capabilities(
    hass, mock_bluetooth_service_info, step
):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")(
        {
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_BED_TYPE: BED_TYPE_MALOUF_APP,
            CONF_NAME: "App Bed",
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    assert result["step_id"] == "malouf_app"
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid):
        schema({})
    values = schema(
        {
            CONF_MALOUF_APP_PROFILE: "lucid",
            CONF_MALOUF_APP_MODEL: "e450",
            CONF_MALOUF_APP_TRANSPORT: "opcode_legacy",
        }
    )
    assert values[CONF_MALOUF_APP_SIDE] == "primary"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_malouf_app(values)
    saved = finish.call_args.args[0]
    assert saved[CONF_MALOUF_APP_MODEL] == "e450"
    assert CONF_MOTOR_COUNT not in saved
    assert CONF_HAS_MASSAGE not in saved
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True
    assert not requires_pairing(BED_TYPE_MALOUF_APP)


async def test_auto_transport_is_not_accepted(hass):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_MALOUF_APP}
    result = await flow.async_step_malouf_app({**APP_DATA, CONF_MALOUF_APP_TRANSPORT: "auto"})
    assert result["errors"] == {CONF_MALOUF_APP_TRANSPORT: "malouf_app_required"}


async def test_options_preserve_model_authority_and_explicit_wire_selector(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=APP_DATA)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    keys = {marker.schema for marker in result["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in keys
    assert CONF_HAS_MASSAGE not in keys
    result = await flow.async_step_settings(
        {
            CONF_MALOUF_APP_MODEL: "e450",
            CONF_MALOUF_APP_SIDE: "secondary",
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: True,
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MALOUF_APP_MODEL] == "e450"
    assert entry.data[CONF_MALOUF_APP_SIDE] == "secondary"
    assert CONF_MOTOR_COUNT not in entry.data
    assert CONF_HAS_MASSAGE not in entry.data


async def test_existing_malouf_options_keep_manual_layout(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN,
            CONF_MALOUF_LAYOUT: "hilo",
            CONF_MOTOR_COUNT: 4,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    keys = {marker.schema for marker in result["data_schema"].schema}
    assert CONF_MALOUF_LAYOUT in keys
    assert CONF_MOTOR_COUNT in keys
    assert not APP_KEYS.intersection(keys)


@pytest.mark.parametrize("side,primary", [("primary", True), ("secondary", False)])
async def test_factory_maps_explicit_wire_side(side, primary):
    coordinator = SimpleNamespace(
        entry=SimpleNamespace(data={**APP_DATA, CONF_MALOUF_APP_SIDE: side})
    )
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.MaloufAppController"
    ) as controller:
        await create_controller(coordinator, BED_TYPE_MALOUF_APP, None, None)
    controller.assert_called_once_with(
        coordinator, app_profile="malouf", model="l600", transport="command32_new", primary=primary
    )
    assert BED_TYPE_MALOUF_APP in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert BED_TYPE_MALOUF_APP in BEDS_WITHOUT_ANGLE_FEEDBACK


async def test_paired_options_preserve_different_profiles_transports_and_sides(hass):
    left = {**APP_DATA, CONF_ADDRESS: "11:22:33:44:55:66"}
    right = {
        **APP_DATA,
        CONF_ADDRESS: "11:22:33:44:55:77",
        CONF_MALOUF_APP_PROFILE: "lucid",
        CONF_MALOUF_APP_MODEL: "premium",
        CONF_MALOUF_APP_TRANSPORT: "opcode_framed",
        CONF_MALOUF_APP_SIDE: "secondary",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    original = entry.data[CONF_PAIR_CHILDREN]
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    assert not APP_KEYS.intersection(marker.schema for marker in result["data_schema"].schema)
    await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "12"})
    for before, after in zip(original, entry.data[CONF_PAIR_CHILDREN], strict=True):
        assert {key: before[key] for key in APP_KEYS} == {key: after[key] for key in APP_KEYS}
        assert after[CONF_MOTOR_PULSE_COUNT] == 12
    assert not APP_KEYS.intersection(entry.data)


async def test_paired_type_change_requires_unpairing(hass):
    left = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN,
        CONF_MOTOR_COUNT: 2,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(left, {**left, CONF_ADDRESS: "11:22:33:44:55:77"}, name="Pair"),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_MALOUF_APP})
    assert result["errors"] == {CONF_BED_TYPE: "malouf_app_unpair_first"}
    assert flow._pending_data == {}
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_MALOUF_NEW_OKIN


async def test_switching_old_route_drops_pending_generic_capabilities(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN,
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: True,
            CONF_MALOUF_LAYOUT: "four_motor",
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_MALOUF_APP})
    assert result["type"] == FlowResultType.FORM
    result = await flow.async_step_settings(
        {
            CONF_MALOUF_APP_PROFILE: "lucid",
            CONF_MALOUF_APP_MODEL: "e450",
            CONF_MALOUF_APP_TRANSPORT: "opcode_legacy",
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_HAS_MASSAGE not in entry.data
    assert CONF_MOTOR_COUNT not in entry.data
    assert CONF_MALOUF_LAYOUT not in entry.data
