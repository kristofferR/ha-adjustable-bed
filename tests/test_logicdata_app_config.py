"""Explicit app-profile setup and factory routing for the Logicdata app cluster."""

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
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_APP,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_HAS_LIGHT,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data


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
            CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
            CONF_NAME: "App Bed",
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    assert result["step_id"] == "logicdata_app"
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    values = result["data_schema"](
        {
            CONF_LOGICDATA_APP_PROFILE: "phone",
            CONF_LOGICDATA_APP_FAMILY: "p1",
            CONF_LOGICDATA_APP_LAYOUT: "standard_3_split_upper",
        }
    )
    with patch.object(
        flow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
    ) as finish:
        await flow.async_step_logicdata_app(values)
    saved = finish.call_args.args[0]
    assert saved[CONF_LOGICDATA_APP_PROFILE] == "phone"
    assert saved[CONF_LOGICDATA_APP_LAYOUT] == "standard_3_split_upper"
    assert saved[CONF_LOGICDATA_APP_TRANSPORT] == "auto"
    assert saved[CONF_LOGICDATA_APP_HAS_LIGHT] is True
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True
    assert saved[CONF_HAS_MASSAGE] is True


async def test_transport_selection_preserves_explicit_family(hass):
    """Changing transports must not change the configured command family."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_logicdata_app(
            {
                CONF_LOGICDATA_APP_PROFILE: "phone",
                CONF_LOGICDATA_APP_FAMILY: "p1",
                CONF_LOGICDATA_APP_LAYOUT: "standard_2",
                CONF_LOGICDATA_APP_TRANSPORT: "t2",
            }
        )
    assert finish.call_args.args[0][CONF_LOGICDATA_APP_TRANSPORT] == "t2"


async def test_options_keep_app_layout_and_transport(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
            CONF_MOTOR_COUNT: 2,
            CONF_LOGICDATA_APP_PROFILE: "tablet",
            CONF_LOGICDATA_APP_FAMILY: "p1",
            CONF_LOGICDATA_APP_LAYOUT: "standard_4",
            CONF_LOGICDATA_APP_TRANSPORT: "t3",
            CONF_LOGICDATA_APP_HAS_LIGHT: False,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    defaults = {marker.schema: marker.default() for marker in result["data_schema"].schema}
    assert defaults[CONF_LOGICDATA_APP_LAYOUT] == "standard_4"
    assert defaults[CONF_LOGICDATA_APP_HAS_LIGHT] is False
    result = await flow.async_step_settings(
        {
            CONF_LOGICDATA_APP_PROFILE: "tablet",
            CONF_LOGICDATA_APP_FAMILY: "p1",
            CONF_LOGICDATA_APP_LAYOUT: "standard_3_hi_low",
            CONF_LOGICDATA_APP_TRANSPORT: "t2",
            CONF_LOGICDATA_APP_HAS_LIGHT: True,
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LOGICDATA_APP_LAYOUT] == "standard_3_hi_low"
    assert entry.data[CONF_LOGICDATA_APP_TRANSPORT] == "t2"


async def test_options_switch_from_legacy_requires_explicit_app_selection(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_LOGICDATA, CONF_MOTOR_COUNT: 2}
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP})
    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_LOGICDATA


async def test_factory_passes_explicit_settings_without_affecting_legacy():
    coordinator = SimpleNamespace(
        entry=SimpleNamespace(
            data={
                CONF_LOGICDATA_APP_PROFILE: "tablet",
                CONF_LOGICDATA_APP_FAMILY: "p1",
                CONF_LOGICDATA_APP_LAYOUT: "standard_3_hi_low",
                CONF_LOGICDATA_APP_TRANSPORT: "t2",
                CONF_LOGICDATA_APP_HAS_LIGHT: False,
            }
        )
    )
    with patch(
        "custom_components.adjustable_bed.beds.logicdata_app.LogicdataAppController"
    ) as controller:
        await create_controller(coordinator, BED_TYPE_LOGICDATA_APP, None, None)
    controller.assert_called_once_with(
        coordinator,
        profile="tablet",
        command_family="p1",
        layout="standard_3_hi_low",
        transport="t2",
        has_light=False,
        has_massage=False,
    )
    assert BED_TYPE_LOGICDATA_APP in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert BED_TYPE_LOGICDATA_APP in BEDS_WITHOUT_ANGLE_FEEDBACK


@pytest.mark.parametrize("family,layout", [("p2", "split_series"), ("p1", "middle")])
async def test_setup_rejects_unsupported_family_layout(hass, family, layout):
    """The app's final product routing overrides split/standard UI for P2."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP}
    result = await flow.async_step_logicdata_app(
        {
            CONF_LOGICDATA_APP_PROFILE: "phone",
            CONF_LOGICDATA_APP_FAMILY: family,
            CONF_LOGICDATA_APP_LAYOUT: layout,
        }
    )
    assert result["errors"] == {CONF_LOGICDATA_APP_LAYOUT: "logicdata_app_family_layout"}
    assert CONF_LOGICDATA_APP_FAMILY not in flow._manual_data


async def test_options_rejects_unsupported_family_layout(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
            CONF_LOGICDATA_APP_PROFILE: "tablet",
            CONF_LOGICDATA_APP_FAMILY: "p1",
            CONF_LOGICDATA_APP_LAYOUT: "split_series",
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_LOGICDATA_APP_FAMILY: "p2"})
    assert result["errors"] == {CONF_LOGICDATA_APP_LAYOUT: "logicdata_app_family_layout"}
    assert entry.data[CONF_LOGICDATA_APP_FAMILY] == "p1"


async def test_paired_options_preserve_distinct_app_packet_selectors(hass):
    left = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
        CONF_MOTOR_COUNT: 2,
        CONF_MOTOR_PULSE_COUNT: 10,
        CONF_LOGICDATA_APP_PROFILE: "phone",
        CONF_LOGICDATA_APP_FAMILY: "p1",
        CONF_LOGICDATA_APP_LAYOUT: "standard_2",
        CONF_LOGICDATA_APP_TRANSPORT: "t1",
        CONF_LOGICDATA_APP_HAS_LIGHT: False,
    }
    right = {
        **left,
        CONF_ADDRESS: "11:22:33:44:55:77",
        CONF_LOGICDATA_APP_PROFILE: "tablet",
        CONF_LOGICDATA_APP_FAMILY: "p2",
        CONF_LOGICDATA_APP_LAYOUT: "middle",
        CONF_LOGICDATA_APP_TRANSPORT: "t3",
        CONF_LOGICDATA_APP_HAS_LIGHT: True,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    original_children = entry.data[CONF_PAIR_CHILDREN]
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    schema = result["data_schema"]
    assert schema is not None
    app_keys = {
        CONF_LOGICDATA_APP_PROFILE,
        CONF_LOGICDATA_APP_FAMILY,
        CONF_LOGICDATA_APP_LAYOUT,
        CONF_LOGICDATA_APP_TRANSPORT,
        CONF_LOGICDATA_APP_HAS_LIGHT,
    }
    assert not app_keys.intersection(marker.schema for marker in schema.schema)
    with pytest.raises(vol.Invalid, match=CONF_LOGICDATA_APP_PROFILE):
        schema({CONF_LOGICDATA_APP_PROFILE: "tablet"})
    result = await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "12"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for before, after in zip(original_children, entry.data[CONF_PAIR_CHILDREN], strict=True):
        assert {key: after[key] for key in app_keys} == {key: before[key] for key in app_keys}
        assert after[CONF_MOTOR_PULSE_COUNT] == 12
    assert not app_keys.intersection(entry.data)


async def test_paired_options_require_unpair_before_selecting_app_type(hass):
    left = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_BED_TYPE: BED_TYPE_LOGICDATA,
        CONF_MOTOR_COUNT: 2,
    }
    right = {**left, CONF_ADDRESS: "11:22:33:44:55:77"}
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    original = dict(entry.data)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP})
    assert result["errors"] == {CONF_BED_TYPE: "logicdata_app_unpair_first"}
    assert entry.data == original
    assert flow._pending_data == {}
