"""Explicit app-profile setup and factory routing for the Jiecang app cluster."""

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
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_HAS_LIGHT,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
)
from custom_components.adjustable_bed.controller_factory import create_controller


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_all_setup_routes_collect_explicit_profile(hass, mock_bluetooth_service_info, step):
    """A user selecting the app type must choose its layout on every setup route."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")(
        {
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
            CONF_NAME: "App Bed",
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    assert result["step_id"] == "jiecang_app"
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    values = result["data_schema"](
        {
            CONF_JIECANG_APP_PROFILE: "dreamask",
            CONF_JIECANG_APP_LAYOUT: "split_after_bilateral",
        }
    )
    with patch.object(
        flow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
    ) as finish:
        await flow.async_step_jiecang_app(values)
    saved = finish.call_args.args[0]
    assert saved[CONF_JIECANG_APP_PROFILE] == "dreamask"
    assert saved[CONF_JIECANG_APP_LAYOUT] == "split_after_bilateral"
    assert saved[CONF_JIECANG_APP_TRANSPORT] == "auto"
    assert saved[CONF_JIECANG_APP_HAS_LIGHT] is True
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True
    assert saved[CONF_HAS_MASSAGE] is True


async def test_dreamask_can_select_g2_for_connection_time_validation(hass):
    """Only the connected GATT topology can prove whether ERGOBALANCE G2 is usable."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_JIECANG_APP}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_jiecang_app(
            {
                CONF_JIECANG_APP_PROFILE: "dreamask",
                CONF_JIECANG_APP_LAYOUT: "standard_2",
                CONF_JIECANG_APP_TRANSPORT: "g2",
            }
        )
    assert finish.call_args.args[0][CONF_JIECANG_APP_TRANSPORT] == "g2"


async def test_options_keep_app_layout_and_transport(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
            CONF_MOTOR_COUNT: 2,
            CONF_JIECANG_APP_PROFILE: "dreamotion",
            CONF_JIECANG_APP_LAYOUT: "standard_4_bilateral",
            CONF_JIECANG_APP_TRANSPORT: "g3",
            CONF_JIECANG_APP_HAS_LIGHT: False,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    defaults = {marker.schema: marker.default() for marker in result["data_schema"].schema}
    assert defaults[CONF_JIECANG_APP_LAYOUT] == "standard_4_bilateral"
    assert defaults[CONF_JIECANG_APP_HAS_LIGHT] is False
    result = await flow.async_step_settings(
        {
            CONF_JIECANG_APP_PROFILE: "dreamotion",
            CONF_JIECANG_APP_LAYOUT: "standard_3_hi_low",
            CONF_JIECANG_APP_TRANSPORT: "g2",
            CONF_JIECANG_APP_HAS_LIGHT: True,
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_JIECANG_APP_LAYOUT] == "standard_3_hi_low"
    assert entry.data[CONF_JIECANG_APP_TRANSPORT] == "g2"


async def test_options_switch_from_legacy_requires_explicit_app_selection(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_JIECANG, CONF_MOTOR_COUNT: 2}
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_JIECANG_APP})
    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_JIECANG


async def test_factory_passes_explicit_settings_without_affecting_legacy():
    coordinator = SimpleNamespace(
        entry=SimpleNamespace(
            data={
                CONF_JIECANG_APP_PROFILE: "dreamotion",
                CONF_JIECANG_APP_LAYOUT: "standard_3_hi_low",
                CONF_JIECANG_APP_TRANSPORT: "g2",
                CONF_JIECANG_APP_HAS_LIGHT: False,
            }
        )
    )
    with patch(
        "custom_components.adjustable_bed.beds.jiecang_app.JiecangAppController"
    ) as controller:
        await create_controller(coordinator, BED_TYPE_JIECANG_APP, None, None)
    controller.assert_called_once_with(
        coordinator,
        profile="dreamotion",
        layout="standard_3_hi_low",
        transport="g2",
        has_light=False,
    )
    assert BED_TYPE_JIECANG_APP not in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert BED_TYPE_JIECANG_APP in BEDS_WITHOUT_ANGLE_FEEDBACK
