"""Explicit app-profile setup and factory routing for the Logicdata app cluster."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, start_new_bed


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_all_setup_routes_collect_explicit_profile(hass, mock_bluetooth_service_info, route):
    """A user selecting the app row must choose the app and its layout on every setup route."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    settings = {
        CONF_NAME: "App Bed",
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_DISCONNECT_AFTER_COMMAND: False,
        CONF_PREFERRED_ADAPTER: "auto",
    }
    result = await start_new_bed(flow, route, BED_TYPE_LOGICDATA_APP)
    assert result["step_id"] == "logicdata_family"
    result = await flow.async_step_logicdata_family({"choice": "phone"})
    assert result["step_id"] == "profile_questions"
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    values = schema({CONF_LOGICDATA_APP_FAMILY: "p1", CONF_LOGICDATA_APP_LAYOUT: "standard_3_split_upper"})
    with patch.object(
        flow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
    ) as finish:
        result = await finish_new_bed(flow, await flow.async_step_profile_questions(values), settings)
    saved = finish.call_args.args[0]
    assert saved[CONF_LOGICDATA_APP_PROFILE] == "phone"
    assert saved[CONF_LOGICDATA_APP_LAYOUT] == "standard_3_split_upper"
    assert saved[CONF_LOGICDATA_APP_TRANSPORT] == "auto"
    assert saved[CONF_HAS_LIGHT] is True
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True
    assert saved[CONF_HAS_MASSAGE] is True


async def _app_questions(hass, app: str) -> AdjustableBedConfigFlow:
    """A flow on the app's own questions, chosen in the LOGICDATA question."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_ADDRESS: "11:22:33:44:55:66", CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP}
    result = await flow.async_step_logicdata_family({"choice": app})
    assert result["step_id"] == "profile_questions"
    return flow


async def test_transport_selection_preserves_explicit_family(hass):
    """Changing transports must not change the configured command family."""
    flow = await _app_questions(hass, "phone")
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {
                CONF_LOGICDATA_APP_FAMILY: "p1",
                CONF_LOGICDATA_APP_LAYOUT: "standard_2",
                "advanced": {CONF_LOGICDATA_APP_TRANSPORT: "t2"},
            }
        )
    saved = finish.call_args.args[0]
    assert (saved[CONF_LOGICDATA_APP_FAMILY], saved[CONF_LOGICDATA_APP_TRANSPORT]) == ("p1", "t2")


async def test_configure_leaves_the_app_and_layout_to_the_guided_change(hass):
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
            CONF_HAS_LIGHT: False,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    defaults = {marker.schema: marker.default() for marker in result["data_schema"].schema}
    assert defaults[CONF_HAS_LIGHT] is False
    assert not {
        CONF_LOGICDATA_APP_PROFILE,
        CONF_LOGICDATA_APP_FAMILY,
        CONF_LOGICDATA_APP_LAYOUT,
        CONF_LOGICDATA_APP_TRANSPORT,
    } & set(defaults)
    result = await flow.async_step_settings({CONF_LOGICDATA_APP_LAYOUT: "standard_3_hi_low"})
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[CONF_LOGICDATA_APP_LAYOUT] == "standard_4"
    result = await flow.async_step_settings({CONF_HAS_LIGHT: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_HAS_LIGHT] is True
    assert entry.data[CONF_LOGICDATA_APP_TRANSPORT] == "t3"


async def test_configure_sends_simplicityframe_to_the_app_through_the_guided_change(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_LOGICDATA, CONF_MOTOR_COUNT: 2}
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP})
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_LOGICDATA


async def test_factory_passes_explicit_settings_without_affecting_legacy(hass):
    coordinator = SimpleNamespace(
        hass=hass,
        entry=SimpleNamespace(
            data={
                CONF_LOGICDATA_APP_PROFILE: "tablet",
                CONF_LOGICDATA_APP_FAMILY: "p1",
                CONF_LOGICDATA_APP_LAYOUT: "standard_3_hi_low",
                CONF_LOGICDATA_APP_TRANSPORT: "t2",
                CONF_HAS_LIGHT: False,
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
    assert bed_traits(BED_TYPE_LOGICDATA_APP).no_angle_feedback


async def test_a_motionrelax_layout_belongs_to_p1_and_p2_runs_the_middle_layout(hass):
    """P2 is the middle layout, so it is never asked; every other layout is P1's."""
    flow = await _app_questions(hass, "tablet")
    result = await flow.async_step_profile_questions()
    layouts = result["data_schema"].schema[
        next(m for m in result["data_schema"].schema if m.schema == CONF_LOGICDATA_APP_LAYOUT)
    ].container
    assert "middle" not in layouts
    result = await flow.async_step_profile_questions(
        {CONF_LOGICDATA_APP_FAMILY: "p1", CONF_LOGICDATA_APP_LAYOUT: "middle"}
    )
    assert result["errors"] == {CONF_LOGICDATA_APP_LAYOUT: "logicdata_app_family_layout"}
    assert CONF_LOGICDATA_APP_FAMILY not in flow._manual_data
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({CONF_LOGICDATA_APP_FAMILY: "p2"})
    saved = finish.call_args.args[0]
    assert (saved[CONF_LOGICDATA_APP_FAMILY], saved[CONF_LOGICDATA_APP_LAYOUT]) == ("p2", "middle")


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
        CONF_HAS_LIGHT: False,
    }
    right = {
        **left,
        CONF_ADDRESS: "11:22:33:44:55:77",
        CONF_LOGICDATA_APP_PROFILE: "tablet",
        CONF_LOGICDATA_APP_FAMILY: "p2",
        CONF_LOGICDATA_APP_LAYOUT: "middle",
        CONF_LOGICDATA_APP_TRANSPORT: "t3",
        CONF_HAS_LIGHT: True,
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
        CONF_HAS_LIGHT,
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
    assert result["errors"] == {CONF_BED_TYPE: "app_profile_unpair_first"}
    assert entry.data == original
    assert flow._pending_data == {}
