"""Motion forms and service selectors follow the registered public contract."""

from pathlib import Path

import pytest
import voluptuous as vol
import yaml
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    DOMAIN,
)
from custom_components.adjustable_bed.motion_bed_services import async_register_motion_bed_services
from tests.test_detection import _make_service_info

resources = yaml.safe_load(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/services.yaml").read_text()
)
names = sorted(key for key in resources if key.startswith("motion_bed_"))


@pytest.mark.parametrize(
    ("stored", "observed", "title", "expected"),
    [
        (None, "QMS4", "Bedroom", "QMS4"),
        ("SealyMF", "QMS4", "Bedroom", "SealyMF"),
        (None, None, "QMS4", "QMS4"),
    ],
)
async def test_original_name_prefill_survives_editable_title(
    hass, stored, observed, title, expected
):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {
        CONF_NAME: title,
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_BED_TYPE: BED_TYPE_MOTION_BED,
    }
    if stored is not None:
        flow._manual_data[CONF_BLE_DEVICE_NAME] = stored
    if observed is not None:
        flow._discovery_info = _make_service_info(name=observed)
    result = await flow.async_step_motion_bed()
    marker = next(k for k in result["data_schema"].schema if k.schema == CONF_BLE_DEVICE_NAME)
    assert marker.default() == expected


@pytest.mark.parametrize("name", names)
async def test_motion_ui_matches_registered_multiple_target_contract(hass, name):
    async_register_motion_bed_services(hass)
    service = hass.services.async_services()[DOMAIN][name]
    marker = next(k for k in service.schema.schema if k.schema == "device_id")
    target_validator = service.schema.schema[marker]
    assert target_validator(["left", "right"]) == ["left", "right"]
    field = resources[name]["fields"]["device_id"]
    assert field["required"] is True
    assert field["selector"]["device"]["integration"] == DOMAIN
    assert field["selector"]["device"]["multiple"] is True


@pytest.mark.parametrize(
    ("name", "field"), [("motion_bed_alarm", "mode"), ("motion_bed_thermal_schedule", "gear")]
)
async def test_motion_ui_required_matches_actual_registered_schema(hass, name, field):
    async_register_motion_bed_services(hass)
    service = hass.services.async_services()[DOMAIN][name]
    marker = next(k for k in service.schema.schema if k.schema == field)
    assert resources[name]["fields"][field].get("required", False) == isinstance(
        marker, vol.Required
    )
    if field == "mode":
        assert marker.default() == 1
