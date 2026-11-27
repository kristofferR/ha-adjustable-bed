"""Choose S&S Base explicitly and keep app-owned settings on their physical side."""

import pytest
import voluptuous as vol

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.profiles.silksnow import CHOICES
from tests.test_setup_entry import _app_then_address, app_question, app_rows


async def test_silksnow_app_and_current_products_come_first(hass, enable_custom_integrations):
    assert app_rows(await app_question(hass))["Silk & Snow (S&S Base app)"] == "silksnow"
    result = await _app_then_address(hass, "silksnow")
    assert result["step_id"] == "profile_questions"
    markers = {str(marker): marker for marker in result["data_schema"].schema}
    marker = markers[const.CONF_PROTOCOL_VARIANT]
    assert list(result["data_schema"].schema[marker].rows().values()) == list(CHOICES)
    assert list(CHOICES)[:3] == ["slikcore", "slikenhanced", "slikpremier"]
    assert marker.default is vol.UNDEFINED
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "slikpremier"}
    )
    assert result["step_id"] == "finish_settings"
    assert per_side_profile("silksnow", "slikpremier").variant_owned


@pytest.mark.parametrize("label", ["CORE", "ENHANCED", "PREMIER"])
def test_current_product_labels_are_not_marked_stored(label):
    assert label in CHOICES.values()
