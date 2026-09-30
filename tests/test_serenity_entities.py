"""Serenity profile reloads preserve other sides and retire obsolete app entities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_SERENITY,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from tests.conftest import make_controller_mock
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_serenity import make_controller, written


@pytest.mark.parametrize("retain", [True, False])
async def test_status_sensor_reload_reconciles_only_the_current_side(hass, retain):
    controller = (
        make_controller()
        if retain
        else make_controller_mock(
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            position_number_specs=(),
        )
    )
    runtime = configure_entity_runtime(
        hass, controller, BED_TYPE_SERENITY if retain else BED_TYPE_DIAGNOSTIC
    )
    keys = {
        "serenity_manufacturer",
        "serenity_status_code",
        "serenity_massage_timer_code",
        "serenity_massage_timer_minutes",
        "serenity_save_event_code",
        "serenity_alarm_type",
    }
    registry = er.async_get(hass)
    old = [
        registry.async_get_or_create(
            "sensor", DOMAIN, f"bed_{key}_left", config_entry=runtime.entry
        )
        for key in keys
    ]
    other = registry.async_get_or_create(
        "sensor", DOMAIN, "bed_serenity_status_code_right", config_entry=runtime.entry
    )
    unrelated = registry.async_get_or_create(
        "sensor", DOMAIN, "bed_unrelated_left", config_entry=runtime.entry
    )
    entities = _sensor_entities_for(hass, runtime)
    assert all((registry.async_get(row.entity_id) is not None) is retain for row in old)
    assert registry.async_get(other.entity_id) is not None
    assert registry.async_get(unrelated.entity_id) is not None
    assert {entity.unique_id for entity in entities if "serenity_" in entity.unique_id} == (
        {f"bed_{key}_left" for key in keys} if retain else set()
    )


@pytest.mark.parametrize("retain", [True, False])
async def test_literal_app_buttons_reload_reconciles_only_current_side(hass, retain):
    controller = make_controller() if retain else make_controller_mock(controller_button_specs=())
    runtime = configure_entity_runtime(
        hass, controller, BED_TYPE_SERENITY if retain else BED_TYPE_DIAGNOSTIC
    )
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "button", DOMAIN, "bed_serenity_selector_4_up_left", config_entry=runtime.entry
    )
    other = registry.async_get_or_create(
        "button", DOMAIN, "bed_serenity_selector_4_up_right", config_entry=runtime.entry
    )
    unrelated = registry.async_get_or_create(
        "button", DOMAIN, "bed_other_action_left", config_entry=runtime.entry
    )
    entities = _button_entities_for(hass, runtime)
    assert (registry.async_get(old.entity_id) is not None) is retain
    assert registry.async_get(other.entity_id) is not None
    assert registry.async_get(unrelated.entity_id) is not None
    assert any(entity.unique_id == old.unique_id for entity in entities) is retain


async def test_profile_retires_old_lumbar_cover_without_guessing_auxiliary_axes(hass):
    controller = make_controller()
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_SERENITY)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "cover", DOMAIN, "bed_lumbar_left", config_entry=runtime.entry
    )
    other = registry.async_get_or_create(
        "cover", DOMAIN, "bed_lumbar_right", config_entry=runtime.entry
    )
    covers = _cover_entities_for(hass, runtime)
    assert {cover.entity_description.key for cover in covers} == {"head", "feet"}
    assert registry.async_get(old.entity_id) is None
    assert registry.async_get(other.entity_id) is not None
    actions = {button.unique_id for button in _button_entities_for(hass, runtime)}
    assert {
        f"bed_serenity_selector_{selector}_{direction}_left"
        for selector in (4, 5)
        for direction in ("up", "down")
    } <= actions


async def test_native_light_toggle_keeps_unknown_physical_state(hass):
    controller = make_controller()
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_SERENITY)

    async def dispatch(command, **kwargs):
        await command(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    button = next(
        button
        for button in _button_entities_for(hass, runtime)
        if button.unique_id == "bed_serenity_light_toggle_left"
    )
    await button.async_press()
    assert "0c02000200000000000000000000" in written(controller)
    assert not controller.get_light_state()
    assert not any(
        getattr(light, "supports_color", False) for light in _light_entities_for(hass, runtime)
    )


async def test_other_axis_stop_preempts_a_running_cover_through_production_scheduler(hass):
    controller = make_controller()
    client = controller.client
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_SERENITY,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = client
    coordinator._controller = controller
    coordinator._motor_pulse_count = 100
    controller._coordinator = coordinator
    started = asyncio.Event()
    frames = []

    async def write(_characteristic, payload, **kwargs):
        frames.append(payload.hex())
        if payload.hex() == "0c02000000010000000000000000":
            started.set()

    client.write_gatt_char.side_effect = write
    covers = {
        cover.entity_description.key: cover for cover in _cover_entities_for(hass, coordinator)
    }
    assert all(cover._motor_resource == "*" for cover in covers.values())
    with (
        patch.object(
            coordinator, "_async_prepare_controller_operation", AsyncMock(return_value=controller)
        ),
        patch.object(coordinator, "_async_finish_controller_operation", AsyncMock()),
        patch.object(covers["head"], "async_write_ha_state", MagicMock()),
        patch.object(covers["feet"], "async_write_ha_state", MagicMock()),
    ):
        movement = asyncio.create_task(covers["head"].async_open_cover())
        await started.wait()
        async with asyncio.timeout(2):
            await covers["feet"].async_stop_cover()
            await movement
    assert frames[0] == "0c02000000010000000000000000"
    assert all(frame == "0c02000000000000000000000000" for frame in frames[1:])
    assert len(frames) >= 3


async def test_discrete_light_switch_tracks_only_commanded_intent(hass):
    from custom_components.adjustable_bed.switch import _switch_entities_for

    controller = make_controller()
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_SERENITY)
    runtime.bed_type = BED_TYPE_SERENITY

    async def dispatch(command, **kwargs):
        await command(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    switches = _switch_entities_for(hass, runtime)
    light = next(
        switch for switch in switches if switch.entity_description.key == "under_bed_lights"
    )
    assert light.is_on is None
    assert light.assumed_state is True
    assert _light_entities_for(hass, runtime) == []
    with patch.object(light, "async_write_ha_state", MagicMock()):
        await light.async_turn_on()
        assert light.is_on is True
        await light.async_turn_off()
        assert light.is_on is False
    frames = written(controller)
    assert "0c02000000000000004000000000" in frames
    assert "0c02000000000000008000000000" in frames
    assert controller.get_light_state() == {}


async def test_parser_publishes_native_diagnostic_values_and_signed_alarm_attributes(hass):
    from tests.test_serenity import status

    controller = make_controller()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_SERENITY,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = controller.client
    coordinator._controller = controller
    controller._coordinator = coordinator
    sensors = {
        sensor._spec.key: sensor
        for sensor in _sensor_entities_for(hass, coordinator)
        if hasattr(sensor, "_spec") and sensor._spec.key.startswith("serenity_")
    }
    await controller.refresh_manufacturer()
    assert sensors["serenity_manufacturer"].native_value == "CST13"
    controller._handle_notification(None, status(2))
    assert sensors["serenity_status_code"].native_value == 2
    assert sensors["serenity_massage_timer_minutes"].native_value == 20
    await controller.hold_control("save_memory_1", 100)
    controller._handle_notification(None, status(3))
    assert sensors["serenity_save_event_code"].native_value == 4
    assert sensors["serenity_massage_timer_code"].native_value == 2
    assert sensors["serenity_massage_timer_minutes"].native_value == 20
    payload = status(128, alarm=True)
    payload[4:8] = bytes([128, 6, 129, 255])
    payload[9] = 1
    controller._handle_notification(None, payload)
    assert sensors["serenity_alarm_type"].native_value == 19
    assert sensors["serenity_alarm_type"].extra_state_attributes == {
        "serenity_alarm_repeat": -128,
        "serenity_alarm_hour": -127,
        "serenity_alarm_minute": -1,
        "serenity_alarm_on": True,
    }
    controller._handle_notification(None, status(128))
    assert sensors["serenity_status_code"].native_value == -128
    assert sensors["serenity_massage_timer_minutes"].native_value is None
