"""Row 052 setup, entities and services for the Tranquil and Z-Series app profiles."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.actuator_groups import get_actuator_group_for_bed_type
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import (
    _motor_count_options,
    _normalize_fixed_motor_count,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_SERENITY,
    BED_TYPE_TRANQUIL,
    BED_TYPE_ZSERIES_Z230,
    BED_TYPE_ZSERIES_Z280,
    DOMAIN,
    SIDE_BOTH,
    bed_type_has_position_feedback,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import _create_from_registry
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import async_register_services
from tests.conftest import make_controller_mock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_okin_bedding_apps import tranquil, written, zseries

ROOT = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
LABELS = {
    BED_TYPE_TRANQUIL: ("tranquil", "Jordan's Tranquil app", 2),
    BED_TYPE_ZSERIES_Z230: ("zseries_z230", "Customatic Z-Series app (Z-230)", 1),
    BED_TYPE_ZSERIES_Z280: ("zseries_z280", "Customatic Z-Series app (Z-280)", 2),
}


@pytest.mark.parametrize("bed_type", list(LABELS))
async def test_explicit_profile_is_offline_constructible_and_never_auto_detected(bed_type):
    profile, label, slots = LABELS[bed_type]
    controller = await _create_from_registry(_FactoryCoordinator(), bed_type)
    assert controller is not None
    assert controller.protocol_diagnostics["cst_profile"] == profile
    assert controller.memory_slot_count == slots
    assert get_actuator_group_for_bed_type(bed_type) == ("okin", label)
    assert next(o for o in get_bed_type_options() if o["value"] == bed_type)["label"] == label
    assert _motor_count_options(bed_type) == [2]
    assert _normalize_fixed_motor_count(bed_type, "auto", 4) == 2
    assert get_motor_pulse_defaults(bed_type) == (10, 100)
    assert not requires_pairing(bed_type)
    assert not bed_type_has_position_feedback(bed_type, "auto")
    for name in ("OKIN", "OKIN-003444", "okin example"):
        info = MagicMock()
        info.name = name
        info.address = "AA:BB:CC:DD:EE:FF"
        info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
        info.manufacturer_data = {}
        assert detect_bed_type(info) != bed_type


@pytest.mark.parametrize("bed_type", list(LABELS))
async def test_setup_hides_fixed_layout_and_refresh_delay(hass, bed_type):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = bed_type
    flow._disambiguated_bed_type = bed_type
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    form = await flow.async_step_manual_entry()
    markers = {marker.schema for marker in form["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers
    assert CONF_MOTOR_PULSE_DELAY_MS not in markers


@pytest.mark.parametrize(
    ("factory", "bed_type", "prefix"),
    [(tranquil, BED_TYPE_TRANQUIL, "tranquil"), (lambda: zseries("z280"), BED_TYPE_ZSERIES_Z280, "zseries")],
)
async def test_profile_change_retires_previous_app_buttons_and_sensors(hass, factory, bed_type, prefix):
    runtime = configure_entity_runtime(hass, factory(), bed_type)
    registry = er.async_get(hass)
    stale = [
        registry.async_get_or_create("button", DOMAIN, "bed_serenity_save_tv_left", config_entry=runtime.entry),
        registry.async_get_or_create("sensor", DOMAIN, "bed_serenity_status_code_left", config_entry=runtime.entry),
    ]
    buttons = {entity.unique_id for entity in _button_entities_for(hass, runtime)}
    sensors = {entity.unique_id for entity in _sensor_entities_for(hass, runtime)}
    assert all(registry.async_get(row.entity_id) is None for row in stale)
    assert f"bed_{prefix}_save_zero_g_left" in buttons
    assert f"bed_{prefix}_status_code_left" in sensors
    # Moving away from the app profile removes its namespace again.
    retired = configure_entity_runtime(
        hass,
        make_controller_mock(
            controller_button_specs=(),
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            position_number_specs=(),
        ),
        BED_TYPE_DIAGNOSTIC,
    )
    kept = [
        registry.async_get_or_create("button", DOMAIN, f"bed_{prefix}_save_zero_g_left", config_entry=retired.entry),
        registry.async_get_or_create("sensor", DOMAIN, f"bed_{prefix}_status_code_left", config_entry=retired.entry),
    ]
    _button_entities_for(hass, retired)
    _sensor_entities_for(hass, retired)
    assert all(registry.async_get(row.entity_id) is None for row in kept)


@pytest.mark.parametrize(("factory", "has_switch"), [(tranquil, True), (lambda: zseries("z230"), False)])
async def test_discrete_light_switch_only_where_the_app_has_on_off(hass, factory, has_switch):
    from custom_components.adjustable_bed.switch import _switch_entities_for

    controller = factory()
    bed_type = BED_TYPE_TRANQUIL if has_switch else BED_TYPE_ZSERIES_Z230
    runtime = configure_entity_runtime(hass, controller, bed_type)
    runtime.bed_type = bed_type
    switches = [
        switch for switch in _switch_entities_for(hass, runtime)
        if switch.entity_description.key == "under_bed_lights"
    ]
    assert bool(switches) is has_switch
    if switches:
        assert switches[0].is_on is None and switches[0].assumed_state is True


def _target(bed_type, controller):
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Bed"
    coordinator.bed_type = bed_type
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator


@pytest.mark.parametrize(
    ("service", "bed_type", "factory", "control", "error"),
    [
        ("tranquil_hold_control", BED_TYPE_TRANQUIL, tranquil, "save_lounge", None),
        ("tranquil_hold_control", BED_TYPE_SERENITY, tranquil, "save_lounge", "Tranquil action"),
        ("zseries_hold_control", BED_TYPE_ZSERIES_Z230, lambda: zseries("z230"), "head_foot_up", None),
        ("zseries_hold_control", BED_TYPE_ZSERIES_Z230, lambda: zseries("z230"), "memory_2", "combination"),
        ("zseries_hold_control", BED_TYPE_TRANQUIL, tranquil, "head_up", "Z-Series action"),
    ],
)
async def test_hold_services_preflight_profile_and_literal_action(
    hass, service, bed_type, factory, control, error
):
    await async_register_services(hass)
    controller = factory()
    controller.hold_control = AsyncMock()
    coordinator = _target(bed_type, controller)
    data = {"device_id": "bed", "control": control, "duration": 1.5}
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(DOMAIN, service, data, blocking=True)
            coordinator.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(DOMAIN, service, data, blocking=True)
            controller.hold_control.assert_awaited_once_with(control, 1500)


@pytest.mark.parametrize(
    ("bed_type", "available", "error"),
    [
        (BED_TYPE_ZSERIES_Z280, True, None),
        (BED_TYPE_ZSERIES_Z280, False, "does not support"),
        (BED_TYPE_TRANQUIL, True, "not a Customatic Z-Series"),
    ],
)
async def test_alarm_service_requires_zseries_and_manufacturer_enabled_page(
    hass, bed_type, available, error
):
    await async_register_services(hass)
    controller = zseries("z280")
    controller._alarm_available = available
    coordinator = _target(bed_type, controller)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, SIDE_BOTH)], []),
        ),
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.serenity.dt_util.now",
            return_value=datetime(2026, 10, 1, 13, 47, 59),
        ),
    ):
        data = {"device_id": "bed", "enabled": True, "time": "07:45:00", "wake_mode": "memory_1"}
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(DOMAIN, "zseries_set_alarm", data, blocking=True)
            assert written(controller) == []
            return
        with pytest.raises(ServiceValidationError, match="wake-up mode"):
            await hass.services.async_call(
                DOMAIN,
                "zseries_set_alarm",
                {key: value for key, value in data.items() if key != "wake_mode"},
                blocking=True,
            )
        assert written(controller) == []
        await hass.services.async_call(DOMAIN, "zseries_set_alarm", data, blocking=True)
        await hass.services.async_call(DOMAIN, "zseries_sync_clock", {"device_id": "bed"}, blocking=True)
    clock = "07061a0a01040d2f3b"
    assert written(controller) == [
        clock, "07052002072d000101", "00c0", "00c0", clock, "00c0", "00c0"
    ]
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]


def test_service_selectors_and_translations_match_controller_catalogs():
    services = yaml.safe_load((ROOT / "services.yaml").read_text())
    assert services["tranquil_hold_control"]["fields"]["control"]["selector"]["select"][
        "options"
    ] == list(tranquil().held_control_options)
    zseries_options = services["zseries_hold_control"]["fields"]["control"]["selector"]["select"]["options"]
    assert set(zseries_options) == {
        *zseries("z230").held_control_options,
        *zseries("z280").held_control_options,
    }
    for filename in ("strings.json", "translations/en.json"):
        metadata = json.loads((ROOT / filename).read_text())
        for name in ("tranquil_hold_control", "zseries_hold_control", "zseries_set_alarm", "zseries_sync_clock"):
            assert set(metadata["services"][name]["fields"]) == set(services[name]["fields"])
        for prefix in ("tranquil", "zseries"):
            for spec in (tranquil() if prefix == "tranquil" else zseries("z280")).controller_state_sensor_specs:
                assert spec.translation_key in metadata["entity"]["sensor"]


@pytest.mark.parametrize("bed_type", list(LABELS))
async def test_options_switch_from_generic_okin_profile_applies_fixed_defaults(hass, bed_type):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_CST,
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROTOCOL_VARIANT,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_MOTOR_COUNT: 4,
            CONF_PROTOCOL_VARIANT: "cst_support",
            CONF_MOTOR_PULSE_COUNT: 7,
            CONF_MOTOR_PULSE_DELAY_MS: 150,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    rebuilt = await flow._async_options_form({CONF_BED_TYPE: bed_type}, step_id="settings")
    markers = {marker.schema for marker in rebuilt["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers and CONF_MOTOR_PULSE_DELAY_MS not in markers
    saved = await flow._async_options_form({CONF_BED_TYPE: bed_type}, step_id="settings")
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == bed_type
    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert (entry.data[CONF_MOTOR_PULSE_COUNT], entry.data[CONF_MOTOR_PULSE_DELAY_MS]) == (10, 100)
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(("count", "error"), [("0", True), ("601", True), ("1", False), ("600", False)])
async def test_zseries_pulse_count_range_is_validated_in_setup_and_options(hass, count, error):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
        _invalid_pulse_count,
    )
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_MOTOR_PULSE_COUNT

    assert _invalid_pulse_count(BED_TYPE_ZSERIES_Z230, int(count)) is error
    assert not _invalid_pulse_count(BED_TYPE_TRANQUIL, int(count))  # Other profiles unchanged.

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = BED_TYPE_ZSERIES_Z230
    flow._disambiguated_bed_type = BED_TYPE_ZSERIES_Z230
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    if error:
        form = await flow.async_step_bluetooth_confirm(
            {CONF_BED_TYPE: BED_TYPE_ZSERIES_Z230, CONF_NAME: "Bed", CONF_MOTOR_PULSE_COUNT: count}
        )
        assert form["type"] == "form"
        assert form["errors"][CONF_MOTOR_PULSE_COUNT] == "invalid_pulse_count_range"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_ZSERIES_Z230},
    )
    entry.add_to_hass(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.hass = hass
    options.handler = entry.entry_id
    result = await options._async_options_form(
        {CONF_BED_TYPE: BED_TYPE_ZSERIES_Z230, CONF_MOTOR_PULSE_COUNT: count}, step_id="settings"
    )
    if error:
        assert result["errors"] == {CONF_MOTOR_PULSE_COUNT: "invalid_pulse_count_range"}
    else:
        assert result["type"] == "create_entry"
        assert entry.data[CONF_MOTOR_PULSE_COUNT] == int(count)


async def test_enabling_alarm_requires_time_and_clearing_does_not(hass):
    await async_register_services(hass)
    controller = zseries("z230")
    controller._alarm_available = True
    coordinator = _target(BED_TYPE_ZSERIES_Z230, controller)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, SIDE_BOTH)], []),
        ),
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.serenity.dt_util.now",
            return_value=datetime(2026, 10, 1, 13, 47, 59),
        ),
    ):
        with pytest.raises(ServiceValidationError) as raised:
            await hass.services.async_call(
                DOMAIN,
                "zseries_set_alarm",
                {"device_id": "bed", "enabled": True, "wake_mode": "massage"},
                blocking=True,
            )
        assert raised.value.translation_key == "zseries_alarm_time_required"
        assert written(controller) == []
        await hass.services.async_call(
            DOMAIN, "zseries_set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
        )
    assert written(controller) == ["07061a0a01040d2f3b", "070500000000000001", "00c0", "00c0"]
