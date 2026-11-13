"""Symphony's saved app choices, discovery precedence and actual cover metadata."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type_detailed,
)
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, start_new_bed
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_symphony import bed


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_setup_routes_require_product_and_keep_fifth_axis(
    hass, mock_bluetooth_service_info, route
):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    result = await start_new_bed(flow, route, const.BED_TYPE_SYMPHONY, "AA:BB:CC:01:02:03")
    assert result["step_id"] == "profile_questions"
    values = result["data_schema"]({"product_type": "13", "protocol_variant": "9"})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await finish_new_bed(
            flow,
            await flow.async_step_profile_questions(values),
            {"name": "SS800", "disconnect_after_command": False},
        )
    saved = finish.call_args.args[0]
    assert saved["product_type"] == "13" and saved["protocol_variant"] == "9"
    assert saved["motor_count"] == 5 and saved["has_massage"]
    assert saved["disable_angle_sensing"]


def test_findability_side_owned_fields_and_options_preservation():
    assert "Symphony Sleep Sense" in BED_TYPE_DISPLAY_NAMES[const.BED_TYPE_SYMPHONY]
    assert const.CONF_MOTOR_COUNT in hidden_generic_fields(const.BED_TYPE_SYMPHONY, None)
    owned = per_side_profile(const.BED_TYPE_SYMPHONY, None).keys
    assert {
        "product_type",
        "protocol_variant",
        "symphony_side",
        "ble_device_name",
        "has_massage",
        "motor_count",
    } <= owned
    data = {
        "bed_type": const.BED_TYPE_SYMPHONY,
        "product_type": "15",
        "protocol_variant": "4",
        "symphony_side": "right",
    }
    AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, const.BED_TYPE_SYMPHONY)
    assert data["product_type"] == "15" and data["symphony_side"] == "right"


def test_shared_names_add_an_app_choice_without_claiming_the_model():
    info = SimpleNamespace(
        device=SimpleNamespace(name="SMARTBED7410"),
        name="SMARTBED7410",
        address="AA:BB:CC:01:02:03",
        service_uuids=[],
        manufacturer_data={},
    )
    result = detect_bed_type_detailed(info)
    assert const.BED_TYPE_SYMPHONY in [result.bed_type, *(result.ambiguous_types or ())]
    assert result.confidence < 0.9
    info.device.name = info.name = "OKIN-123"
    shared = detect_bed_type_detailed(info)
    assert const.BED_TYPE_SYMPHONY in [shared.bed_type, *(shared.ambiguous_types or ())]
    assert shared.bed_type != const.BED_TYPE_SYMPHONY


async def test_factory_restore_keeps_explicit_choices_and_unknown_numeric_fallback():
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = {"product_type": "999", "protocol_variant": "9"}
    controller = await create_controller(coordinator, const.BED_TYPE_SYMPHONY, "4", None)
    assert controller.app.product.value == 0 and controller.app.selector == 4
    coordinator.capability_controller = controller
    local = controller.controller_select_specs[0].local_select_fn
    assert local is not None
    local("on")
    replacement = await create_controller(coordinator, const.BED_TYPE_SYMPHONY, "4", None)
    assert replacement.local.child
    replacement.restore_persisted_app_state({"child": False})
    assert not controller.local.child
    coordinator.entry.data = {"product_type": "12", "protocol_variant": "9"}
    coordinator.capability_controller = await create_controller(
        coordinator, const.BED_TYPE_SYMPHONY, "9", None
    )
    with pytest.raises(ValueError, match="profile changed"):
        local("on")


def test_real_cover_attributes_advertise_renewable_movement_without_preset_leases():
    controller = bed("13", 9)
    runtime = SimpleNamespace(
        entity_unique_id=lambda key: key,
        name="Symphony",
        has_massage=True,
        bed_type=const.BED_TYPE_SYMPHONY,
        controller=controller,
        capability_controller=controller,
        controller_state={},
        position_data={},
        disable_angle_sensing=True,
        device_info={},
        entity_side=None,
    )
    for spec in controller.motor_control_specs:
        entity = AdjustableBedCover(runtime, _build_cover_description(spec))
        attrs = entity.extra_state_attributes
        assert attrs["held_control_up"] == spec.hold.up_control
        assert attrs["held_stop_scope"] == "side"
    assert all("memory" not in key and "flat" not in key for key in controller.held_control_options)
