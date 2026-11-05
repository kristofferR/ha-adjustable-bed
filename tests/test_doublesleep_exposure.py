"""Setup route, physical selector and HA entity exposure for SleepEase."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, AdjustableBedButton
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
from custom_components.adjustable_bed.doublesleep_services import build_request
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, start_new_bed
from tests.test_doublesleep_controller import Bed


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_all_setup_routes_collect_separate_saved_model_and_driver(
    hass, mock_bluetooth_service_info, route
):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._discovery_info = mock_bluetooth_service_info
    result = await start_new_bed(flow, route, const.BED_TYPE_DOUBLESLEEP, "AA:BB:CC:01:02:03")
    assert result["step_id"] == "profile_questions"
    values = result["data_schema"]({"product_type": "11136", "protocol_variant": "p2"})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await finish_new_bed(
            flow,
            await flow.async_step_profile_questions(values),
            {"name": "SleepEase", "disconnect_after_command": False},
        )
    saved = finish.call_args.args[0]
    assert saved["product_type"] == "11136" and saved["protocol_variant"] == "p2"
    assert saved["disable_angle_sensing"] and saved["motor_pulse_delay_ms"] == 300


def test_profile_findability_and_per_address_options():
    assert "SleepEase" in BED_TYPE_DISPLAY_NAMES[const.BED_TYPE_DOUBLESLEEP]
    assert const.CONF_MOTOR_COUNT in hidden_generic_fields(const.BED_TYPE_DOUBLESLEEP, None)
    assert per_side_profile(const.BED_TYPE_DOUBLESLEEP, None).keys == const.DOUBLESLEEP_CONFIG_KEYS
    data = {
        "product_type": "11136",
        "protocol_variant": "p3",
        "bed_type": const.BED_TYPE_DOUBLESLEEP,
    }
    AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, const.BED_TYPE_DOUBLESLEEP)
    assert data["product_type"] == "11136" and data["protocol_variant"] == "p3"


def test_discovery_requires_platform_prefix_and_company_identity():
    def info(platform, adv, data):
        return SimpleNamespace(
            device=SimpleNamespace(name=platform),
            name=adv,
            address="AA:BB:CC:01:02:03",
            service_uuids=[],
            manufacturer_data=data,
        )

    assert (
        detect_bed_type_detailed(info("sLeEpBt", "osleepbts-A", {89: b""})).bed_type
        == const.BED_TYPE_DOUBLESLEEP
    )
    assert (
        detect_bed_type_detailed(info("Other", "osleepbts-A", {89: b""})).bed_type
        != const.BED_TYPE_DOUBLESLEEP
    )
    assert (
        detect_bed_type_detailed(info("sleepbt", "sleepbt", {89: bytes(6)})).bed_type
        != const.BED_TYPE_DOUBLESLEEP
    )
    assert (
        detect_bed_type_detailed(info("sleepbt", "osleepbts-A", {90: bytes(7)})).bed_type
        != const.BED_TYPE_DOUBLESLEEP
    )


async def test_factory_uses_advertisement_for_driver_and_saved_model_for_ui():
    bed = Bed()
    bed.coordinator.entry = SimpleNamespace(
        data={"product_type": "3", "ble_device_name": "sleepbt"}, options={}
    )
    bed.coordinator.hass.async_add_import_executor_job = AsyncMock()
    result = await create_controller(
        bed.coordinator,
        const.BED_TYPE_DOUBLESLEEP,
        "auto",
        bed.client,
        device_name="sleepbt",
        advertisement_name="osleepbts-A",
        manufacturer_data={89: bytes(7)},
    )
    assert result.protocol == "p3" and result.model == 3 and not result.supports_motor_control
    with pytest.raises(ConnectionError, match="live advertisement"):
        await create_controller(bed.coordinator, const.BED_TYPE_DOUBLESLEEP, "auto", None)


async def test_setup_model_default_uses_platform_name_independently_of_driver(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._manual_data = {"bed_type": const.BED_TYPE_DOUBLESLEEP}
    flow._discovery_info = SimpleNamespace(
        name="osleepbts-A",
        device=SimpleNamespace(name="sleepbt"),
        manufacturer_data={89: bytes([0, 0, 0, 0, 0, 0, 134])},
    )
    result = await flow.async_step_profile_questions()
    assert result["data_schema"] is not None
    defaults = result["data_schema"]({})
    assert defaults["product_type"] == "10135"
    assert defaults["protocol_variant"] == "auto"


def test_alarm_ui_values_and_anti_snore_operation_are_not_raw_commands():
    request = build_request(
        {
            "action": "alarm",
            "hour": 6,
            "minute": 30,
            "weekdays": ["mon", "fri"],
            "alarm_preset": "vibration",
            "alarm_massage": True,
        }
    )
    assert request.values == (6, 30, 162, 8, 1)
    assert build_request({"action": "anti_snore_demo", "mode": 3}).values == (2, 3, -1, -1)
    assert build_request({"action": "anti_snore", "mode": 2}).values == (1, 2, -1, -1)


def test_standard_button_exposes_p1_hold_without_changing_other_buttons():
    bed = Bed("p1", 3)
    runtime = SimpleNamespace(
        capability_controller=bed.bed,
        controller=bed.bed,
        entity_unique_id=lambda key: key,
        entity_translation_key=lambda key: key,
        device_info={},
        entry=SimpleNamespace(entry_id="entry"),
        side=None,
        entity_side=None,
    )
    flat = next(d for d in BUTTON_DESCRIPTIONS if d.key == "preset_flat")
    entity = AdjustableBedButton(runtime, flat)
    assert entity.extra_state_attributes["held_control"] == "doublesleep_26"
    bed.bed.protocol = "p2"
    assert "held_control" not in entity.extra_state_attributes


@pytest.mark.parametrize("driver", ("p1", "p2"))
def test_motor_covers_expose_the_shared_app_hold_owner(driver):
    bed = Bed(driver, 3)
    runtime = SimpleNamespace(
        capability_controller=None,
        device_info={},
        entity_side=None,
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
    )
    specs = bed.bed.motor_control_specs
    assert len(specs) == 5
    for spec in specs:
        entity = AdjustableBedCover(runtime, _build_cover_description(spec))
        assert entity.extra_state_attributes["held_stop_scope"] == "side"
        assert entity.extra_state_attributes["held_control_up"] == spec.hold.up_control
