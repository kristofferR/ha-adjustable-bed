"""Explicit app settings and independent physical-bed roles."""

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
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_PRIMARY,
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_setup_routes_require_app_and_model(hass, mock_bluetooth_service_info, step):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")({
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_NAME: "App bed",
        CONF_BED_TYPE: BED_TYPE_MALOUF_APP,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_DISCONNECT_AFTER_COMMAND: False,
        CONF_PREFERRED_ADAPTER: "auto",
    })
    assert result["step_id"] == "malouf_app"
    schema = result["data_schema"]
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    assert {marker.schema for marker in schema.schema} == {CONF_MALOUF_APP_PROFILE}
    result = await flow.async_step_malouf_app(schema({CONF_MALOUF_APP_PROFILE: "lucid"}))
    schema = result["data_schema"]
    assert schema is not None
    values = schema({CONF_MALOUF_APP_PROFILE: "lucid", CONF_MALOUF_APP_MODEL: "Premium"})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_malouf_app(values)
    saved = finish.call_args.args[0]
    assert saved[CONF_MALOUF_APP_PROFILE] == "lucid"
    assert saved[CONF_MALOUF_APP_MODEL] == "Premium"
    assert saved[CONF_MALOUF_APP_TRANSPORT] == "auto"
    assert saved[CONF_MALOUF_APP_PRIMARY] is True
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize("profile,models,rejected", [
    ("lucid", {"L300", "L600", "Premium"}, "S755"),
    ("malouf", {"E450", "E455", "M455", "M555", "S655", "S755", "Forte", "Altitude",
                "GoodLifeBase", "GoodLifePremierBase", "GoodLifeProBase", "L600", "M550", "S750"}, "Premium"),
])
async def test_fresh_model_picker_matches_app_and_rejects_cross_app_input(
    hass, profile, models, rejected
):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_MALOUF_APP}
    result = await flow.async_step_malouf_app({CONF_MALOUF_APP_PROFILE: profile})
    schema = result["data_schema"]
    assert schema is not None
    model_choices = next(
        validator.container for marker, validator in schema.schema.items()
        if marker.schema == CONF_MALOUF_APP_MODEL
    )
    assert set(model_choices) == models
    with pytest.raises(vol.Invalid):
        schema({CONF_MALOUF_APP_MODEL: rejected})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        result = await flow.async_step_malouf_app({CONF_MALOUF_APP_MODEL: rejected})
    assert result["errors"] == {CONF_MALOUF_APP_MODEL: "malouf_app_required"}
    finish.assert_not_called()


async def test_options_retain_only_stored_persisted_model_and_filter_app_changes(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_BED_TYPE: BED_TYPE_MALOUF_APP, CONF_MOTOR_COUNT: 2,
        CONF_MALOUF_APP_PROFILE: "lucid", CONF_MALOUF_APP_MODEL: "GoodLifeProBase",
        CONF_MALOUF_APP_TRANSPORT: "richmat_framed", CONF_MALOUF_APP_PRIMARY: False,
    })
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    choices = next(validator.container for marker, validator in result["data_schema"].schema.items()
                   if marker.schema == CONF_MALOUF_APP_MODEL)
    assert set(choices) == {"L300", "L600", "Premium", "GoodLifeProBase"}
    result = await flow.async_step_settings({CONF_MALOUF_APP_MODEL: "S755"})
    assert result["errors"] == {CONF_MALOUF_APP_MODEL: "malouf_app_required"}
    assert entry.data[CONF_MALOUF_APP_MODEL] == "GoodLifeProBase"
    result = await flow.async_step_settings({CONF_MALOUF_APP_PRIMARY: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MALOUF_APP_MODEL] == "GoodLifeProBase"

    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_MALOUF_APP_PROFILE: "malouf"})
    assert result["type"] == FlowResultType.FORM
    choices = next(validator.container for marker, validator in result["data_schema"].schema.items()
                   if marker.schema == CONF_MALOUF_APP_MODEL)
    assert "Premium" not in choices and "S755" in choices
    assert entry.data[CONF_MALOUF_APP_PROFILE] == "lucid"
    result = await flow.async_step_settings({CONF_MALOUF_APP_MODEL: "S755"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MALOUF_APP_PROFILE] == "malouf"
    assert entry.data[CONF_MALOUF_APP_MODEL] == "S755"


async def test_options_preserve_explicit_app_and_role(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_BED_TYPE: BED_TYPE_MALOUF_APP, CONF_MOTOR_COUNT: 2,
        CONF_MALOUF_APP_PROFILE: "malouf", CONF_MALOUF_APP_MODEL: "S755",
        CONF_MALOUF_APP_TRANSPORT: "richmat_framed", CONF_MALOUF_APP_PRIMARY: False,
    })
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    defaults = {marker.schema: marker.default() for marker in result["data_schema"].schema}
    assert defaults[CONF_MALOUF_APP_MODEL] == "S755"
    assert defaults[CONF_MALOUF_APP_PRIMARY] is False
    result = await flow.async_step_settings({CONF_MALOUF_APP_MODEL: "Altitude"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MALOUF_APP_MODEL] == "Altitude"
    assert entry.data[CONF_MALOUF_APP_PRIMARY] is False


async def test_options_app_change_requires_model_from_new_picker(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_BED_TYPE: BED_TYPE_MALOUF_APP, CONF_MOTOR_COUNT: 2,
        CONF_MALOUF_APP_PROFILE: "malouf", CONF_MALOUF_APP_MODEL: "S755",
    })
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_MALOUF_APP_PROFILE: "lucid"})
    schema = result["data_schema"]
    assert schema is not None
    model_marker, validator = next(
        (marker, validator) for marker, validator in schema.schema.items()
        if marker.schema == CONF_MALOUF_APP_MODEL
    )
    assert set(validator.container) == {"L300", "L600", "Premium"}
    assert model_marker.default is vol.UNDEFINED
    result = await flow.async_step_settings({CONF_MALOUF_APP_MODEL: "S755"})
    assert result["errors"] == {CONF_MALOUF_APP_MODEL: "malouf_app_required"}
    assert entry.data[CONF_MALOUF_APP_PROFILE] == "malouf"
    result = await flow.async_step_settings({CONF_MALOUF_APP_MODEL: "Premium"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MALOUF_APP_PROFILE] == "lucid"
    assert entry.data[CONF_MALOUF_APP_MODEL] == "Premium"


async def test_switching_from_legacy_requires_explicit_profile(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN, CONF_MOTOR_COUNT: 2})
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_MALOUF_APP})
    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid, match="required key"):
        schema({})
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_MALOUF_NEW_OKIN


async def test_pair_common_settings_keep_distinct_app_models_and_roles(hass):
    left = {CONF_ADDRESS: "11:22:33:44:55:66", CONF_BED_TYPE: BED_TYPE_MALOUF_APP,
            CONF_MOTOR_COUNT: 2, CONF_MALOUF_APP_PROFILE: "malouf", CONF_MALOUF_APP_MODEL: "S755",
            CONF_MALOUF_APP_TRANSPORT: "richmat_framed", CONF_MALOUF_APP_PRIMARY: True}
    right = {**left, CONF_ADDRESS: "11:22:33:44:55:77", CONF_MALOUF_APP_PROFILE: "lucid",
             CONF_MALOUF_APP_MODEL: "Premium", CONF_MALOUF_APP_TRANSPORT: "okin_new",
             CONF_MALOUF_APP_PRIMARY: False}
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    keys = {marker.schema for marker in result["data_schema"].schema}
    assert CONF_MALOUF_APP_PROFILE not in keys
    await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "12"})
    children = entry.data[CONF_PAIR_CHILDREN]
    assert [child[CONF_MALOUF_APP_MODEL] for child in children] == ["S755", "Premium"]
    assert [child[CONF_MALOUF_APP_PRIMARY] for child in children] == [True, False]
    assert CONF_MALOUF_APP_PROFILE not in entry.data


async def test_factory_forwards_explicit_profile(hass):
    coordinator = SimpleNamespace(hass=hass, entry=SimpleNamespace(data={
        CONF_MALOUF_APP_PROFILE: "lucid", CONF_MALOUF_APP_MODEL: "Premium",
        CONF_MALOUF_APP_TRANSPORT: "okin_new", CONF_MALOUF_APP_PRIMARY: False,
    }))
    with patch("custom_components.adjustable_bed.beds.malouf_app.MaloufAppController") as controller:
        await create_controller(coordinator, BED_TYPE_MALOUF_APP, None, None)
    controller.assert_called_once_with(coordinator, app_profile="lucid", model="Premium",
                                       transport="okin_new", primary=False)
