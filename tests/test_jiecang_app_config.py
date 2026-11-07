"""Explicit app-profile setup and factory routing for the Jiecang app cluster."""

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
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, start_new_bed


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_all_setup_routes_collect_explicit_profile(hass, mock_bluetooth_service_info, route):
    """A user selecting the app type must choose its layout on every setup route."""
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
    result = await start_new_bed(flow, route, BED_TYPE_JIECANG_APP)
    # The app question comes first; the family row keeps nothing to keep.
    assert result["step_id"] == "jiecang_family"
    options = result["data_schema"].schema["choice"].config["options"]
    assert "keep" not in options and "dreamask" in options
    result = await flow.async_step_jiecang_family({"choice": "dreamask"})
    assert result["step_id"] == "profile_questions"
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    values = schema({CONF_JIECANG_APP_LAYOUT: "split_after_bilateral"})
    with patch.object(
        flow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
    ) as finish:
        result = await finish_new_bed(flow, await flow.async_step_profile_questions(values), settings)
    saved = finish.call_args.args[0]
    assert saved[CONF_JIECANG_APP_PROFILE] == "dreamask"
    assert saved[CONF_JIECANG_APP_LAYOUT] == "split_after_bilateral"
    assert saved[CONF_JIECANG_APP_TRANSPORT] == "auto"
    assert saved[CONF_HAS_LIGHT] is True
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True
    assert saved[CONF_HAS_MASSAGE] is True


async def test_dreamask_can_select_g2_for_connection_time_validation(hass):
    """Only the connected GATT topology can prove whether ERGOBALANCE G2 is usable."""
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    # The family step chose the app; this step asks its own questions.
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_JIECANG_APP_PROFILE: "dreamask"}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {
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
            CONF_HAS_LIGHT: False,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    defaults = {marker.schema: marker.default() for marker in result["data_schema"].schema}
    # Configure asks the app's own questions except its route, which the guided change owns.
    assert CONF_JIECANG_APP_LAYOUT not in defaults
    assert CONF_JIECANG_APP_TRANSPORT not in defaults
    assert defaults[CONF_HAS_LIGHT] is False
    # Layout and transport change through the guided change, never Configure.
    result = await flow.async_step_settings(
        {
            CONF_JIECANG_APP_PROFILE: "dreamotion",
            CONF_JIECANG_APP_LAYOUT: "standard_3_hi_low",
            CONF_JIECANG_APP_TRANSPORT: "g2",
            CONF_HAS_LIGHT: True,
        }
    )
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[CONF_JIECANG_APP_LAYOUT] == "standard_4_bilateral"
    # A preference still saves in Configure.
    result = await flow.async_step_settings(
        {
            CONF_JIECANG_APP_PROFILE: "dreamotion",
            CONF_JIECANG_APP_LAYOUT: "standard_4_bilateral",
            CONF_JIECANG_APP_TRANSPORT: "g3",
            CONF_HAS_LIGHT: True,
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_JIECANG_APP_LAYOUT] == "standard_4_bilateral"
    assert entry.data[CONF_JIECANG_APP_TRANSPORT] == "g3"
    assert entry.data[CONF_HAS_LIGHT] is True


async def test_options_switch_from_legacy_uses_the_guided_change(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_JIECANG, CONF_MOTOR_COUNT: 2}
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_JIECANG_APP})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_JIECANG


async def test_factory_passes_explicit_settings_without_affecting_legacy(hass):
    coordinator = SimpleNamespace(
        hass=hass,
        entry=SimpleNamespace(
            data={
                CONF_JIECANG_APP_PROFILE: "dreamotion",
                CONF_JIECANG_APP_LAYOUT: "standard_3_hi_low",
                CONF_JIECANG_APP_TRANSPORT: "g2",
                CONF_HAS_LIGHT: False,
            }
        ),
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
    assert bed_traits(BED_TYPE_JIECANG_APP).no_angle_feedback


async def test_paired_options_preserve_each_sides_app_profile(hass):
    app_fields = (
        CONF_JIECANG_APP_PROFILE,
        CONF_JIECANG_APP_LAYOUT,
        CONF_JIECANG_APP_TRANSPORT,
        CONF_HAS_LIGHT,
    )
    left = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
        CONF_JIECANG_APP_PROFILE: "dreamask",
        CONF_JIECANG_APP_LAYOUT: "standard_3_neck",
        CONF_JIECANG_APP_TRANSPORT: "g1",
        CONF_HAS_LIGHT: True,
    }
    right = {
        **left,
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        CONF_JIECANG_APP_PROFILE: "dreamotion",
        CONF_JIECANG_APP_LAYOUT: "standard_4_bilateral",
        CONF_JIECANG_APP_TRANSPORT: "g3",
        CONF_HAS_LIGHT: False,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    shown = {marker.schema for marker in result["data_schema"].schema}
    assert shown.isdisjoint(app_fields)
    # A side's own app profile is not part of the shared form.
    refused = await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "20", **right})
    assert refused["errors"] == {"base": "app_profile_unpair_first"}
    result = await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "20"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for child, original in zip(entry.data[CONF_PAIR_CHILDREN], (left, right), strict=True):
        assert {key: child[key] for key in app_fields} == {key: original[key] for key in app_fields}
        assert child[CONF_MOTOR_PULSE_COUNT] == 20
    assert set(entry.data).isdisjoint(app_fields)


async def test_paired_options_cannot_create_unconfigured_app_sides(hass):
    data = build_pair_entry_data(
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_JIECANG},
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:02", CONF_BED_TYPE: BED_TYPE_JIECANG},
        name="Pair",
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_JIECANG_APP})
    assert result["errors"] == {CONF_BED_TYPE: "app_profile_unpair_first"}
    assert entry.data == data


@pytest.mark.parametrize("layout", ["standard_4_bilateral", "split_after_bilateral"])
async def test_dreamhd_setup_rejects_other_apps_layouts(hass, layout):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    # The family step chose the app; this step asks its own questions.
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_JIECANG_APP_PROFILE: "dreamhd"}
    result = await flow.async_step_profile_questions(
        { CONF_JIECANG_APP_LAYOUT: layout}
    )
    assert result["errors"] == {CONF_JIECANG_APP_LAYOUT: "jiecang_app_required"}


@pytest.mark.parametrize(
    "layout",
    [
        "standard_2",
        "standard_3_neck",
        "standard_3_lumbar",
        "standard_3_hi_low",
        "standard_3_split_upper",
        "standard_4_legacy",
        "split_series",
    ],
)
async def test_dreamhd_setup_and_factory_keep_explicit_profile(hass, layout):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    # The family step chose the app; this step asks its own questions.
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_JIECANG_APP, CONF_JIECANG_APP_PROFILE: "dreamhd"}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {
                CONF_JIECANG_APP_LAYOUT: layout,
                CONF_JIECANG_APP_TRANSPORT: "g3",
                CONF_HAS_LIGHT: False,
            }
        )
    data = finish.call_args.args[0]
    assert data[CONF_JIECANG_APP_PROFILE] == "dreamhd"
    coordinator = SimpleNamespace(hass=hass, entry=SimpleNamespace(data=data))
    with patch(
        "custom_components.adjustable_bed.beds.jiecang_app.JiecangAppController"
    ) as controller:
        await create_controller(coordinator, BED_TYPE_JIECANG_APP, None, None)
    assert controller.call_args.kwargs == {
        "profile": "dreamhd",
        "layout": layout,
        "transport": "g3",
        "has_light": False,
    }
