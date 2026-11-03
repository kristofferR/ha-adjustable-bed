"""Reverie entity actions follow implemented controls and receiver feedback."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.adjustable_bed.beds.reverie import ReverieController
from custom_components.adjustable_bed.beds.reverie_nightstand import ReverieNightstandController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    REVERIE_NIGHTSTAND_HEAD_WAVE_UUID,
    REVERIE_STK_SIDE_DATA_UUID,
)
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
from tests.test_reverie_review_lifecycle import _pairlink_central
from tests.test_reverie_session_lane import _central


@pytest.mark.parametrize(
    ("controller_type", "model", "scope"),
    [(ReverieController, "9T", "side"), (ReverieNightstandController, "R510L", "motor")],
)
async def test_cover_publishes_the_controller_stop_scope(
    hass, mock_coordinator_connected, controller_type, model, scope
):
    coordinator = await _central(hass)
    try:
        controller = controller_type(coordinator, model=model)
        coordinator._controller = controller
        cover = AdjustableBedCover(
            coordinator, _build_cover_description(controller.motor_control_specs[0])
        )
        assert cover.extra_state_attributes["held_stop_scope"] == scope
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("controller_type", "model", "has_mode_step"),
    [(ReverieController, "9T", True), (ReverieNightstandController, "R510L", False),
     (ReverieNightstandController, "STK", False)],
)
async def test_massage_buttons_only_expose_implemented_actions(
    hass, mock_coordinator_connected, controller_type, model, has_mode_step,
):
    coordinator = await _central(hass)
    controller = controller_type(coordinator, model=model)
    coordinator._controller = controller
    keys = {entity.entity_description.key for entity in _button_entities_for(hass, coordinator)}
    assert "massage_all_toggle" not in keys
    assert ("massage_mode_step" in keys) is has_mode_step
    assert {"massage_all_off", "massage_head_up", "massage_head_down"} <= keys
    await coordinator.async_shutdown()


@pytest.mark.parametrize("side", ["1", "2", "3"])
async def test_stk_head_massage_steps_use_selected_side(hass, mock_coordinator_connected, side):
    coordinator = await _central(hass)
    controller = ReverieNightstandController(coordinator, model="STK")
    coordinator._controller = controller
    controller._set_stk_side(side)
    controller._massage_head_level = 4
    coordinator.client.write_gatt_char.reset_mock()

    await coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.massage_head_up(), read_positions_after_operation=False,
    )
    assert coordinator.controller_state["massage_head_intensity"] == 5
    await coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.massage_head_down(), read_positions_after_operation=False,
    )

    assert [call.args[:2] for call in coordinator.client.write_gatt_char.await_args_list] == (
        [(REVERIE_NIGHTSTAND_HEAD_WAVE_UUID, bytes((level * 4,))) for level in (5, 4)]
        if side == "1" else
        [(REVERIE_STK_SIDE_DATA_UUID, bytes((int(side), 0x53, level * 4))) for level in (5, 4)]
    )
    assert coordinator.controller_state["massage_head_intensity"] == 4
    await coordinator.async_shutdown()


async def test_pairlink_rgb_feedback_drives_light_and_later_turn_on(hass, monkeypatch):
    coordinator, controller = await _pairlink_central(hass)
    light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
    monkeypatch.setattr(light, "async_write_ha_state", Mock())
    unsubscribe = coordinator.register_controller_state_callback(light._handle_light_state)
    set_color = AsyncMock()
    monkeypatch.setattr(controller, "set_light_color", set_color)

    def report(selector, value):
        controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, selector, value)))

    report(8, 20)
    report(9, 40)
    assert "under_bed_lights_rgb" not in coordinator.controller_state
    report(10, 60)
    assert coordinator.controller_state["under_bed_lights_rgb"] == light.rgb_color == (20, 40, 60)
    report(9, 80)
    assert light.rgb_color == (20, 80, 60)

    await light.async_turn_on()

    set_color.assert_awaited_once_with((20, 80, 60))
    controller.on_disconnect()
    assert coordinator.controller_state["under_bed_lights_rgb"] is None
    report(8, 99)
    assert coordinator.controller_state["under_bed_lights_rgb"] is None
    unsubscribe()
    await coordinator.async_shutdown()
