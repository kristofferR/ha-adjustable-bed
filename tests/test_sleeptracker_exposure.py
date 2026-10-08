"""App findability, setup, typed actions, routing and secret-safe captures."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.sleeptracker import SleeptrackerController
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type_detailed,
)
from custom_components.adjustable_bed.redaction import (
    SLEEPTRACKER_SECRET_CHARACTERISTICS,
    redact_data,
    redact_pins_only,
    redact_sleeptracker_sessions,
)
from custom_components.adjustable_bed.services import async_register_services


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_every_setup_route_collects_processor_profile(
    hass, mock_bluetooth_service_info, step
):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, "async_step_" + step)(
        {
            "address": "AA:BB:CC:01:02:03",
            "bed_type": const.BED_TYPE_SLEEPTRACKER,
            "name": "Processor",
            "motor_count": 2,
            "has_massage": False,
            "disable_angle_sensing": False,
            "disconnect_after_command": False,
            "preferred_adapter": "auto",
        }
    )
    assert result["step_id"] == "sleeptracker"
    values = result["data_schema"](
        {"product_type": "activebreeze_small", "sleeptracker_unit_number": 2}
    )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_sleeptracker(values)
    data = finish.call_args.args[0]
    assert data["product_type"] == "activebreeze_small"
    assert data["sleeptracker_unit_number"] == 2
    assert data["sleeptracker_restricted"] is False
    assert data["has_massage"] is True and data["disable_angle_sensing"] is True
    assert data["motor_count"] == 3
    assert data["sleeptracker_foundation"] == "Unspecified"
    assert const.BED_TYPE_SLEEPTRACKER in const.BEDS_WITHOUT_ANGLE_FEEDBACK
    assert "Sleeptracker" in BED_TYPE_DISPLAY_NAMES[const.BED_TYPE_SLEEPTRACKER]


def test_profile_owns_selectors_and_options_keep_product():
    assert const.CONF_MOTOR_COUNT in hidden_generic_fields(const.BED_TYPE_SLEEPTRACKER, None)
    assert (
        per_side_profile(const.BED_TYPE_SLEEPTRACKER, None).keys == const.SLEEPTRACKER_CONFIG_KEYS
    )
    data = {
        "bed_type": const.BED_TYPE_SLEEPTRACKER,
        "product_type": "slim_prosmart",
        "sleeptracker_unit_number": 1,
    }
    AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, const.BED_TYPE_SLEEPTRACKER)
    assert data["product_type"] == "slim_prosmart" and data["sleeptracker_unit_number"] == 1
    AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, const.BED_TYPE_LINAK)
    assert "sleeptracker_unit_number" not in data


def test_unique_processor_service_wins_without_reclassifying_uart(mock_bluetooth_service_info):
    from custom_components.adjustable_bed import sleeptracker_protocol as p

    info = mock_bluetooth_service_info
    info.name = "KSSF05C"
    info.service_uuids = [p.SERVICE_UUID]
    info.manufacturer_data = {}
    assert detect_bed_type_detailed(info).bed_type == const.BED_TYPE_SLEEPTRACKER
    uart = info
    uart.service_uuids = [const.KEESON_KSBT_SERVICE_UUID]
    assert detect_bed_type_detailed(uart).bed_type != const.BED_TYPE_SLEEPTRACKER


def target(hass: HomeAssistant, model: str):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=model,
        data={
            "address": "AA:BB:CC:01:02:03",
            "bed_type": const.BED_TYPE_SLEEPTRACKER,
            "product_type": model,
        },
    )
    entry.add_to_hass(hass)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.entry = entry
    coordinator.name = model
    coordinator.address = entry.data["address"]
    coordinator.bed_type = const.BED_TYPE_SLEEPTRACKER
    coordinator.cancel_command = asyncio.Event()
    controller = SleeptrackerController(coordinator, model=model)
    controller.async_execute_sleeptracker_request = AsyncMock()
    coordinator.controller = controller
    coordinator.capability_controller = controller

    async def execute(fn, **kwargs):
        await fn(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


async def invoke(hass, targets, service, data):
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, "both") for coordinator, _ in targets], []),
    ):
        await hass.services.async_call(
            const.DOMAIN, service, {"device_id": "processor", **data}, blocking=True
        )


@pytest.mark.parametrize(
    "service,data",
    [
        ("sleeptracker_preset", {"preset": "tv_pc", "save": True}),
        (
            "sleeptracker_climate",
            {"mode": "cool", "level": 2, "fan_side": "right", "constant": False},
        ),
        ("sleeptracker_wave", {"frequency": 40, "minutes": 30}),
        ("sleeptracker_wave", {"frequency": "40", "minutes": 30}),
        ("sleeptracker_massage", {"action": "28Hz"}),
        ("sleeptracker_relaxation", {"action": "wind_down_2"}),
    ],
)
async def test_public_actions_execute_through_coordinator(hass, service, data):
    receiver = target(hass, "activebreeze_large")
    await invoke(hass, [receiver], service, data)
    receiver[0].async_execute_controller_command.assert_awaited_once()
    receiver[1].async_execute_sleeptracker_request.assert_awaited_once()
    assert receiver[0].async_execute_controller_command.call_args.kwargs["resource"] == "*"


async def test_all_receivers_preflight_before_first_climate_write(hass):
    breeze = target(hass, "activebreeze_large")
    generic = target(hass, "ergo")
    with pytest.raises(ServiceValidationError, match="ActiveBreeze"):
        await invoke(hass, [breeze, generic], "sleeptracker_climate", {"mode": "heat", "level": 1})
    breeze[1].async_execute_sleeptracker_request.assert_not_awaited()
    generic[1].async_execute_sleeptracker_request.assert_not_awaited()


async def test_two_address_service_targets_only_the_selected_physical_processor(hass):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left, right = target(hass, "activebreeze_large"), target(hass, "activebreeze_small")
    parent = MagicMock(spec=PairedBedCoordinator)
    parent.children = {"left": left[0], "right": right[0]}
    parent.child_for_side.side_effect = parent.children.get

    async def execute(fn, *, side, **kwargs):
        await fn(parent.children[side].controller)

    parent.async_execute_controller_command = AsyncMock(side_effect=execute)
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(parent, "right")], []),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "sleeptracker_climate",
            {"device_id": "right_child", "mode": "cool", "level": 2, "fan_side": "left"},
            blocking=True,
        )
    left[1].async_execute_sleeptracker_request.assert_not_awaited()
    request = right[1].async_execute_sleeptracker_request.call_args.args[0]
    assert request.fan_side == "left"
    assert parent.async_execute_controller_command.call_args.kwargs["side"] == "right"


@pytest.mark.parametrize(
    "service,data",
    [
        ("sleeptracker_wave", {"frequency": 41, "minutes": 30}),
        ("sleeptracker_wave", {"frequency": 28, "minutes": 6}),
        ("sleeptracker_climate", {"mode": "heat", "level": True}),
        ("sleeptracker_climate", {"mode": "heat", "level": 4}),
    ],
)
async def test_invalid_schemas_fail_before_connection(hass, service, data):
    receiver = target(hass, "activebreeze_small")
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await invoke(hass, [receiver], service, data)
    receiver[0].async_ensure_connected.assert_not_called()
    receiver[1].async_execute_sleeptracker_request.assert_not_awaited()


def test_secrets_redacted_in_captures_and_structured_diagnostics():
    secret = "private-secret"
    report = {
        "gatt_services": [
            {
                "characteristics": [
                    {
                        "uuid": uuid,
                        "read_result": {"hex": secret, "ascii_preview": secret, "length": 20},
                    }
                    for uuid in SLEEPTRACKER_SECRET_CHARACTERISTICS
                ]
            }
        ],
        "notifications": [
            {"characteristic": uuid, "data_hex": secret}
            for uuid in SLEEPTRACKER_SECRET_CHARACTERISTICS
        ],
        "notification_summary": {
            "by_characteristic": {
                uuid: {"ascii_previews": [secret], "top_repeated_payloads": [secret]}
                for uuid in SLEEPTRACKER_SECRET_CHARACTERISTICS
            }
        },
    }
    redact_sleeptracker_sessions(report)
    assert secret not in json.dumps(report)
    assert report["gatt_services"][0]["characteristics"][0]["read_result"]["length"] == 20
    assert secret not in json.dumps(
        redact_data({"authCode": secret, "authToken": secret, "token": secret, "password": secret})
    )
    bundle = redact_pins_only(
        {"name": "Processor", "address": "AA:BB:CC:01:02:03", "authToken": secret}
    )
    assert secret not in json.dumps(bundle)
    assert bundle["name"] == "Processor" and bundle["address"] == "AA:BB:CC:01:02:03"


def test_every_generated_entity_has_english_translation():
    strings = json.loads(Path("custom_components/adjustable_bed/strings.json").read_text())
    from custom_components.adjustable_bed.sleeptracker_protocol import MODELS

    for model in MODELS:
        controller = SleeptrackerController(MagicMock(), model=model, restricted=True)
        assert any(
            spec.key == "sleeptracker_wind_down_running"
            for spec in controller.controller_state_binary_sensor_specs
        ) is MODELS[model].premium
        for category, specs in (
            ("button", controller.controller_button_specs),
            ("select", controller.controller_select_specs),
            ("number", controller.controller_number_specs),
            ("sensor", controller.controller_state_sensor_specs),
            ("binary_sensor", controller.controller_state_binary_sensor_specs),
        ):
            for spec in specs:
                assert spec.translation_key in strings["entity"][category]


async def test_restricted_setup_requires_artifact_side_zero(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._manual_data = {"bed_type": const.BED_TYPE_SLEEPTRACKER}
    result = await flow.async_step_sleeptracker(
        {"product_type": "ergo", "sleeptracker_restricted": True, "sleeptracker_unit_number": 1}
    )
    assert result["errors"] == {"sleeptracker_unit_number": "sleeptracker_restricted_unit"}


def test_service_selectors_match_the_finite_action_schemas():
    import yaml

    services = yaml.safe_load(Path("custom_components/adjustable_bed/services.yaml").read_text())
    assert services["sleeptracker_wave"]["fields"]["frequency"]["selector"]["select"][
        "options"
    ] == ["28", "40", "52", "68", "88"]
    assert (
        services["sleeptracker_massage"]["fields"]["action"]["selector"]["select"]["options"][-1]
        == "off"
    )


async def test_platform_entities_route_actions_and_show_only_published_state(hass):
    from custom_components.adjustable_bed.binary_sensor import (
        AdjustableBedControllerStateBinarySensor,
    )
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.number import _number_entities_for
    from custom_components.adjustable_bed.select import _select_entities_for
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    runtime, controller = target(hass, "activebreeze_large")
    runtime.device_info = {}
    runtime.entity_side = None
    runtime.has_massage = True
    runtime.disable_angle_sensing = True
    runtime.controller_state = {}
    runtime.entity_unique_id.side_effect = lambda key: "processor_" + key
    runtime.entity_translation_key.side_effect = lambda key: key
    runtime.handle_controller_state_updates.side_effect = runtime.controller_state.update
    selects = {e.translation_key: e for e in _select_entities_for(hass, runtime)}
    numbers = {e.translation_key: e for e in _number_entities_for(hass, runtime)}
    assert set(selects) >= {
        "sleeptracker_left_mode",
        "sleeptracker_right_curve",
        "sleeptracker_wave_frequency",
    }
    assert set(numbers) >= {
        "sleeptracker_left_level",
        "sleeptracker_right_level",
        "sleeptracker_wave_minutes",
    }
    assert selects["sleeptracker_left_mode"].current_option is None
    assert numbers["sleeptracker_left_level"].native_value is None
    await selects["sleeptracker_left_mode"].async_select_option("heat")
    await numbers["sleeptracker_right_level"].async_set_native_value(3)
    requests = [
        call.args[0] for call in controller.async_execute_sleeptracker_request.await_args_list
    ]
    assert [(r.fan_side, r.level, r.heating) for r in requests] == [
        ("left", 1, True),
        ("right", 3, False),
    ]
    before = runtime.async_execute_controller_command.await_count
    await selects["sleeptracker_wave_frequency"].async_select_option("40")
    assert runtime.async_execute_controller_command.await_count == before
    assert selects["sleeptracker_wave_frequency"].current_option == "40"
    button = ControllerActionButton(
        runtime,
        next(s for s in controller.controller_button_specs if s.key == "sleeptracker_massage_28hz"),
    )
    await button.async_press()
    assert controller.async_execute_sleeptracker_request.call_args.args[0].massage_action == "28Hz"
    sensor = AdjustableBedControllerStateSensor(
        runtime,
        next(
            s
            for s in controller.controller_state_sensor_specs
            if s.key == "sleeptracker_massage_head_strength"
        ),
    )
    light = AdjustableBedControllerStateBinarySensor(
        runtime, controller.controller_state_binary_sensor_specs[0]
    )
    wind_down = AdjustableBedControllerStateBinarySensor(
        runtime,
        next(
            s
            for s in controller.controller_state_binary_sensor_specs
            if s.key == "sleeptracker_wind_down_running"
        ),
    )
    assert sensor.native_value is None and light.is_on is None
    assert wind_down.is_on is None
    controller._update_status(
        {"body": {"snapshots": [{"head": {"massage": {"strength": 4}}, "safetyLightOn": True}]}}
    )
    assert sensor.native_value == 4 and light.is_on is True
    assert numbers["sleeptracker_left_level"].native_value is None
    controller._update_status({"details": {"body": {"snapshots": [{"windDownMode": 2}]}}})
    assert wind_down.is_on is True
    controller._update_status({"details": {"body": {"snapshots": []}}})
    assert wind_down.is_on is True
    controller._update_status({"body": {"snapshots": [{"windDownMode": 0}]}})
    assert wind_down.is_on is True
    controller._update_status(
        {
            "details": {
                "body": {
                    "snapshots": [{"side": 0, "windDownMode": 0}, {"side": 1, "windDownMode": 2}]
                }
            }
        }
    )
    assert wind_down.is_on is False
    controller.on_disconnect()
    assert sensor.native_value is None and light.is_on is None
    assert wind_down.is_on is None
