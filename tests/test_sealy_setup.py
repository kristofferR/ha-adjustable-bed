"""The Sealy app, brand, product and per-physical-side configuration routes."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.sealy.controller import SealyController
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
    _family_rows,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.form_helpers import NEW_BED_ROUTES, form_fields, options_of, start_new_bed
from tests.test_detection import _make_service_info


def data(layout="0"):
    return {
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "Sealy",
        "bed_type": "sealy_posturematic",
        "protocol_variant": "auto",
        "product_type": layout,
        "profile_id": "sealy_posturematic",
    }


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_new_setup_asks_product(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = _make_service_info(name="sTaR123", service_uuids=[])
    flow._async_transport_note = AsyncMock(return_value="")
    result = await start_new_bed(flow, route, "sealy_posturematic")
    assert result["step_id"] == "profile_questions"
    question = next(
        value for marker, value in result["data_schema"].schema.items() if marker == "product_type"
    )
    assert options_of(question) == ["0", "1", "2"]
    result = await flow.async_step_profile_questions({"product_type": "1"})
    assert not result.get("errors")
    assert flow._manual_data["motor_count"] == 2
    assert flow._manual_data["motor_pulse_delay_ms"] == 300
    assert flow._manual_data["product_type"] == "1"


@pytest.mark.parametrize("layout", ("0", "1", "2"))
async def test_reconfigure_and_offline_factory(hass, layout):
    hass.config.components.add(DOMAIN)
    entry = MockConfigEntry(domain=DOMAIN, title="Sealy", data=data(), version=5)
    entry.add_to_hass(hass)
    assert "sealy_posturematic" in _bed_type_selector(None).rows().values()
    assert dict(_family_rows())["sealy_posturematic"] == "Sealy Posturematic"
    options = AdjustableBedOptionsFlow(entry)
    options.hass, options.handler = hass, entry.entry_id
    form = await options.async_step_settings()
    fields = {marker.schema for marker in form_fields(form["data_schema"])}
    assert not {"motor_count", "has_massage", "disable_angle_sensing"} & fields
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "reconfigure", "entry_id": entry.entry_id}
    await flow.async_step_reconfigure()
    result = await flow.async_step_reconfigure_bed_type({"bed_type": "sealy_posturematic"})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({"product_type": layout})
    if result["type"] == "abort":
        assert layout == "0" and result["reason"] == "migration_unchanged"
    else:
        assert result["step_id"] == "migration_confirm"
        with patch.object(hass.config_entries, "async_schedule_reload"):
            result = await flow.async_step_migration_confirm({"action": "apply"})
        assert result["reason"] == "migration_applied"
    coordinator = AdjustableBedCoordinator(hass, entry)
    try:
        controller = await create_controller(coordinator, "sealy_posturematic", "auto", None)
        assert isinstance(controller, SealyController)
        assert controller.profile.layout == layout
        profile = setup_profile_for(entry.data)
        assert profile is not None and profile.settled(entry.data)["motor_count"] == 2
    finally:
        await coordinator.async_shutdown()
    assert "product_type" in per_side_profile("sealy_posturematic", "auto").keys


@pytest.mark.parametrize("name", ["sTaR123", "STAR35", "star"])
def test_app_candidate_with_no_extra_filter(name):
    result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[]))
    assert "sealy_posturematic" in {result.bed_type, *(result.ambiguous_types or ())}
