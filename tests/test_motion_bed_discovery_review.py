"""Accepted Motion app names remain visible without guessing from a shared UUID."""

import pytest
import voluptuous as vol
from homeassistant.const import CONF_NAME

from custom_components.adjustable_bed.config_flow import (
    BED_TYPE_AUTO_DETECT,
    AdjustableBedConfigFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_MOTION_BED_NAME,
    LINAK_CONTROL_SERVICE_UUID,
    SOLACE_SERVICE_UUID,
)
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.motion_bed_models import RAW_NAME_MARKERS
from tests.test_detection import _make_service_info


@pytest.mark.parametrize("name", RAW_NAME_MARKERS)
def test_every_accepted_app_name_is_offered_on_shared_transport(name):
    result = detect_bed_type_detailed(
        _make_service_info(name=name, service_uuids=[SOLACE_SERVICE_UUID])
    )
    assert BED_TYPE_MOTION_BED in (result.bed_type, *(result.ambiguous_types or ()))
    assert result.confidence < 0.7


@pytest.mark.parametrize("name", RAW_NAME_MARKERS)
@pytest.mark.parametrize("advertised", [False, True])
async def test_additional_accepted_names_require_explicit_choice(hass, name, advertised):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = _make_service_info(
        name=name, service_uuids=[SOLACE_SERVICE_UUID] if advertised else []
    )
    result = await flow.async_step_bluetooth_confirm()
    assert result["step_id"] == "bluetooth_disambiguate"
    assert flow._disambiguation_types is not None
    assert BED_TYPE_MOTION_BED in flow._disambiguation_types
    schema = result["data_schema"]
    assert isinstance(schema, vol.Schema)
    with pytest.raises(vol.MultipleInvalid):
        schema({})
    assert (await flow.async_step_bluetooth_disambiguate({}))["step_id"] == "bluetooth_disambiguate"
    assert (
        await flow.async_step_bluetooth_disambiguate({"bed_type_choice": BED_TYPE_MOTION_BED})
    )["step_id"] == "bluetooth_confirm"
    result = await flow.async_step_bluetooth_confirm(
        {CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_NAME: "Bedroom"}
    )
    assert result["step_id"] == "motion_bed"
    marker = next(key for key in result["data_schema"].schema if key.schema == CONF_MOTION_BED_NAME)
    assert marker.default() == name


@pytest.mark.parametrize("name", ["TL-Q", "QMS-430", "S5-Y"])
async def test_manual_auto_cannot_submit_an_additional_shared_app_name(hass, name):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = _make_service_info(name=name, service_uuids=[SOLACE_SERVICE_UUID])
    result = await flow.async_step_manual_config()
    marker = next(key for key in result["data_schema"].schema if key.schema == CONF_BED_TYPE)
    assert marker.default() == BED_TYPE_AUTO_DETECT
    result = await flow.async_step_manual_config({CONF_BED_TYPE: BED_TYPE_AUTO_DETECT})
    assert result["errors"] == {"base": "auto_detect_failed"}


@pytest.mark.parametrize("name", ["TL-Q", "QMS-430", "S5-Y"])
def test_incompatible_unique_transport_keeps_its_existing_detection(name):
    result = detect_bed_type_detailed(
        _make_service_info(name=name, service_uuids=[LINAK_CONTROL_SERVICE_UUID])
    )
    assert result.bed_type == BED_TYPE_LINAK
    assert BED_TYPE_MOTION_BED not in (result.ambiguous_types or ())


@pytest.mark.parametrize("name", ["Unknown device", "tl-q"])
def test_shared_transport_alone_does_not_offer_motion_app(name):
    result = detect_bed_type_detailed(
        _make_service_info(name=name, service_uuids=[SOLACE_SERVICE_UUID])
    )
    assert BED_TYPE_MOTION_BED not in (result.bed_type, *(result.ambiguous_types or ()))
