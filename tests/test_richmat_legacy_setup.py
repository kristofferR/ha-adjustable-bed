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
    # No position feedback: angle sensing stays off, stored only when it differs.
    assert saved.get(const.CONF_DISABLE_ANGLE_SENSING, True) is True


@pytest.mark.parametrize("app", ("sleep_evolution", "wsilver_legacy"))
async def test_configure_keeps_the_app_and_prefix_and_routes_validate(app, hass):
    # The app and prefix change in Reconfigure; Configure keeps them.
    entry = entry_for(
        hass, **{const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "Ml", const.CONF_RMCONTROL_PRODUCT: ""}
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow.async_step_settings()
    assert const.CONF_BED_TYPE not in form_fields(result["data_schema"])
    assert const.CONF_PROTOCOL_VARIANT not in form_fields(result["data_schema"])
    assert _bed_type_selector(app, show_saved_id=True)(app) == app
    profile = setup_profile_for({const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "Ml"})
    assert profile is not None and profile.validate is not None
    assert profile.validate({const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "MM"})
