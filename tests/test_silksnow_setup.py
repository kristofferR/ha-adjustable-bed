"""Choose S&S Base explicitly and keep app-owned settings on their physical side."""

from unittest.mock import AsyncMock

import pytest
import voluptuous as vol

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profiles.silksnow import CHOICES
from tests.form_helpers import select_options
from tests.test_mlily0_hosted_corrections import advertisement
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


@pytest.mark.parametrize("keyword", ["QRRM", "COOL", "MPE_", "209A", "BED-"])
def test_shared_scan_terms_offer_explicit_silksnow_without_replacing_receiver(keyword):
    info = advertisement("prefix-" + keyword + "-suffix", [const.LINAK_CONTROL_SERVICE_UUID])
    result = detect_bed_type_detailed(info)
    baseline = detect_bed_type_detailed(advertisement("Test", [const.LINAK_CONTROL_SERVICE_UUID]))
    assert (result.bed_type, result.confidence) == (baseline.bed_type, baseline.confidence)
    assert "silksnow" in result.ambiguous_types
    assert "silksnow" not in {
        r.bed_type
        for r in (
            detect_bed_type_detailed(advertisement("Mouse-" + keyword)),
            detect_bed_type_detailed(
                advertisement("Other device", [const.NORDIC_UART_SERVICE_UUID])
            ),
        )
    }


async def test_discovered_shared_receiver_can_choose_silksnow_without_guessing_product(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._async_transport_note = AsyncMock(return_value="")
    result = await flow.async_step_bluetooth(advertisement("prefix-209A-suffix"))
    assert result["step_id"] == "bluetooth_disambiguate"
    assert "silksnow" in select_options(result, "bed_type_choice")
    result = await flow.async_step_bluetooth_disambiguate({"bed_type_choice": "silksnow"})
    assert result["step_id"] == "bluetooth_confirm"
    result = await flow.async_step_bluetooth_confirm({const.CONF_BED_TYPE: "silksnow"})
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data.get(const.CONF_PROTOCOL_VARIANT) in (None, "auto")


@pytest.mark.parametrize("keyword", ["QRRM", "COOL", "MPE_", "209A", "BED-"])
async def test_not_sure_keeps_confident_receiver_controls(hass, keyword):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._discovery_info = advertisement(
        "prefix-" + keyword + "-suffix", [const.LINAK_CONTROL_SERVICE_UUID]
    )
    flow._app_after_device = "device"
    result = await flow.async_step_select_family({const.CONF_BED_TYPE: "not_sure"})
    assert result["type"] == "menu"
    assert result["menu_options"] == ["not_sure_detected", "diagnostic"]
    assert result["description_placeholders"]["detected"].startswith("Linak")
