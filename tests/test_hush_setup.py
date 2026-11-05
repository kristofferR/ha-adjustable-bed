"""Hush Base setup: one app row, then the product the app shows (#906)."""

from unittest.mock import AsyncMock, patch

import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from tests.test_setup_entry import _app_then_address, app_question, app_rows


async def test_the_hush_base_app_is_one_row_of_the_app_question(hass, enable_custom_integrations):
    rows = app_rows(await app_question(hass))
    hush = {label: row for label, row in rows.items() if row == const.BED_TYPE_HUSH_BASE}
    assert list(hush) == ["Hush Base app (select product)"]


async def test_the_product_is_asked_with_the_apps_own_twelve_first(
    hass, enable_custom_integrations
):
    result = await _app_then_address(hass, const.BED_TYPE_HUSH_BASE)
    assert result["step_id"] == "profile_questions"
    markers = {str(marker): marker for marker in result["data_schema"].schema}
    products = list(result["data_schema"].schema[markers[const.CONF_PROTOCOL_VARIANT]].container)
    assert products[:2] == ["hushl400", "hushl400sh"]
    assert len(products) == len(const.HUSH_BASE_VARIANTS)
    # Nothing detects the product, so the question has no default.
    assert isinstance(markers[const.CONF_PROTOCOL_VARIANT], vol.Required)
    assert markers[const.CONF_PROTOCOL_VARIANT].default is vol.UNDEFINED
    with patch.object(
        AdjustableBedConfigFlow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.ABORT, "reason": "test"}),
    ) as finish:
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "hushs575sh"}
        )
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_HUSH_BASE
    assert saved[const.CONF_PROTOCOL_VARIANT] == "hushs575sh"
