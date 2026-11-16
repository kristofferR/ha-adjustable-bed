"""Actual HA new-install and Configure routes for both fixed ASCII apps."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, form_fields, start_new_bed, suggested
from tests.test_richmat_family_flow import entry_for


@pytest.mark.parametrize("app", ("sleep_evolution", "wsilver_legacy"))
@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_actual_new_install(app, route, hass, mock_bluetooth_service_info):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    mock_bluetooth_service_info.name = "GV123"
    flow._discovery_info = mock_bluetooth_service_info
    with patch("homeassistant.components.bluetooth.async_last_service_info", return_value=None):
        result = await start_new_bed(flow, route, app)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "profile_questions"
    assert const.CONF_PROTOCOL_VARIANT in form_fields(result["data_schema"])
    if route != "typed":
        assert suggested(result, const.CONF_PROTOCOL_VARIANT) == "GV"
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "GV"})
    assert not result.get("errors")
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await finish_new_bed(flow, result, {CONF_NAME: "Bed"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == app
    assert saved[const.CONF_PROTOCOL_VARIANT] == "GV"
    assert resolve_profile_id(saved) == f"{app}:GV"
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize("app", ("sleep_evolution", "wsilver_legacy"))
async def test_configure_explicit_app_prefix_and_invalid_routes(app, hass):
    entry = entry_for(hass, **{const.CONF_RMCONTROL_PRODUCT: ""})
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow.async_step_settings()
    selector = result["data_schema"].schema[const.CONF_BED_TYPE]
    assert app in selector.rows().values()
    result = await flow.async_step_settings({const.CONF_BED_TYPE: app})
    assert const.CONF_PROTOCOL_VARIANT in form_fields(result["data_schema"])
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_RICHMAT
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow.async_step_settings({const.CONF_PROTOCOL_VARIANT: "Ml"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BED_TYPE] == app
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == "Ml"
    from custom_components.adjustable_bed import _async_sync_profile_ids

    _async_sync_profile_ids(hass, entry)  # Normal reload synchronizes the stored route.
    assert entry.data[const.CONF_PROFILE_ID] == f"{app}:Ml"
    assert _bed_type_selector(app, show_saved_id=True)(app) == app
    profile = setup_profile_for({const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "Ml"})
    assert profile is not None and profile.validate is not None
    assert profile.validate({const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "MM"})
