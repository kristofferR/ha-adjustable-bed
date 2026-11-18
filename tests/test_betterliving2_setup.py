"""BetterLiving2's actual setup/Configure/factory and per-side configuration paths."""

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.keeson.betterliving2 import BetterLiving2Controller
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profile_id import entry_profile_id, profile_route
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.form_helpers import NEW_BED_ROUTES, form_fields, start_new_bed
from tests.test_betterliving2_runtime import data
from tests.test_detection import _make_service_info


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_real_new_install_asks_explicit_wire_and_layout(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = _make_service_info(name="smartbed123", service_uuids=[])
    flow._async_transport_note = AsyncMock(return_value="")
    result = await start_new_bed(flow, route, "betterliving2")
    assert result["step_id"] == "profile_questions"
    fields = {marker.schema for marker in form_fields(result["data_schema"])}
    assert {"protocol_variant", "product_type"} <= fields
    result = await flow.async_step_profile_questions(
        {"protocol_variant": "p3", "product_type": "3"}
    )
    assert not result.get("errors")
    assert flow._manual_data["motor_count"] == 3
    assert flow._manual_data["motor_pulse_delay_ms"] == 200
    assert flow._manual_data["has_massage"] is True


@pytest.mark.parametrize("wire", ("p1", "p2", "p3"))
@pytest.mark.parametrize("layout", ("2", "3"))
async def test_real_configure_import_restore_and_factory(hass, wire, layout):
    hass.config.components.add(DOMAIN)
    entry = MockConfigEntry(domain=DOMAIN, title="BetterLiving2", data=data(), version=5)
    entry.add_to_hass(hass)
    selector = _bed_type_selector(None, show_saved_id=True)
    assert "betterliving2" in selector.rows().values()
    options = AdjustableBedOptionsFlow(entry)
    options.hass, options.handler = hass, entry.entry_id
    form = await options.async_step_settings()
    fields = {marker.schema for marker in form_fields(form["data_schema"])}
    assert {"protocol_variant", "product_type"} <= fields
    assert not {"motor_count", "has_massage", "disable_angle_sensing"} & fields
    result = await options.async_step_settings({"protocol_variant": wire, "product_type": layout})
    assert not result.get("errors")
    assert entry.data["protocol_variant"] == wire and entry.data["product_type"] == layout
    await async_migrate_entry(hass, entry)
    coordinator = AdjustableBedCoordinator(hass, entry)
    try:
        restored = profile_route(entry_profile_id(entry.data))
        controller = await create_controller(coordinator, restored.bed_type, restored.variant, None)
        assert isinstance(controller, BetterLiving2Controller)
        assert controller.profile.key == f"betterliving2_{wire}_{layout}"
        assert controller._link is None
        with pytest.raises(ConnectionError):
            await controller.lights_on()
        assert entry_profile_id(entry.data) == f"betterliving2:{wire}"
        profile = setup_profile_for(entry.data)
        assert profile is not None and profile.settled(entry.data)["motor_count"] == int(layout)
    finally:
        await coordinator.async_shutdown()


async def test_unknown_auto_and_bad_layout_cannot_mint_offline_capability(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={**data(), "protocol_variant": "auto", "product_type": "unknown"}
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    try:
        with pytest.raises(ValueError):
            await create_controller(coordinator, "betterliving2", "auto", None)
    finally:
        await coordinator.async_shutdown()


def test_side_owned_route_and_product_settings():
    profile = per_side_profile("betterliving2", "p1")
    assert profile is not None
    assert {"protocol_variant", "product_type"} <= profile.keys


def test_shared_name_hint_preserves_receiver_recommendations_and_explicit_app():
    info = _make_service_info(
        name="Smartbed428000193", service_uuids=["6e400001-b5a3-f393-e0a9-e50e24dcca9e"]
    )
    info.manufacturer_data = {89: bytes.fromhex("4142010204")}
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type == "malouf_new_okin"
    assert "betterliving2" not in (detected.ambiguous_types or ())
    assert recommend_profile({"bed_type": "malouf_new_okin"}, info, {}) is None
    assert recommend_profile(data("p3", "3"), info, {}) is None
