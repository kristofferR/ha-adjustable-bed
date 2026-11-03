"""Reverie reconnect, progression and paired persistence review cases."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie import ReverieController
from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie_nightstand import ReverieNightstandController
from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    CONF_BED_TYPE,
    CONF_SIDE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
from tests.test_reverie_routines import _pairlink_runtime
from tests.test_reverie_session_lane import _central


async def test_stk_local_selection_uses_reconnected_controller_without_ble(hass, mock_coordinator_connected):
    coordinator = await _central(hass)
    old = ReverieNightstandController(coordinator, model="STK")
    coordinator._controller = old
    entity = AdjustableBedControllerSelect(coordinator, old.controller_select_specs[0])
    fresh = ReverieNightstandController(coordinator, model="STK")
    coordinator._controller = fresh
    coordinator.client.write_gatt_char.reset_mock()

    await entity.async_select_option("2")

    assert old._stk_selected_side == "1"
    assert fresh._stk_selected_side == entity.current_option == "2"
    coordinator.client.write_gatt_char.assert_not_awaited()
    await coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.preset_memory(1), read_positions_after_operation=False,
    )
    assert coordinator.client.write_gatt_char.call_args.args[1] == bytes((2, 17))
    coordinator._controller = ReverieNightstandController(coordinator, model="R510L")
    with pytest.raises(ServiceValidationError, match="no longer supports"):
        await entity.async_select_option("3")
    await coordinator.async_shutdown()


@pytest.mark.parametrize("exit_kind", ["complete", "equal", "cancel", "replace", "disconnect", "failure"])
async def test_comfort_connection_hold_survives_handoff_and_releases(
    hass, mock_coordinator_connected, monkeypatch, exit_kind,
):
    coordinator = await _central(hass)
    coordinator._disconnect_after_command = True
    controller = coordinator.controller
    now = [0.0]
    monkeypatch.setattr(controller, "_comfort_now", lambda: now[0])
    request = ReverieComfortRequest(head_position=25, foot_position=40)
    await coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.async_set_comfort(request), read_positions_after_operation=False,
    )
    assert coordinator._command_connection_holds == 1
    assert coordinator._disconnect_timer is None

    if exit_kind in ("complete", "equal", "failure"):
        sample = bytearray((0, 0, 25 if exit_kind == "equal" else 0, 40 if exit_kind == "equal" else 0, 0, 0, 0, 0, 0))
        controller._parse_position_data(sample)
        now[0] = 0.001
        if exit_kind == "failure":
            controller._comfort_sample_stable = True
            controller._comfort_pending_sample = bytes(sample)
            monkeypatch.setattr(controller, "write_command", AsyncMock(side_effect=ConnectionError("write failed")))
            with pytest.raises(ConnectionError, match="write failed"):
                await controller._run_comfort_write(controller._comfort_sequence, bytes(sample))
        else:
            controller._parse_position_data(sample)
            await hass.async_block_till_done()
        if exit_kind == "complete":
            assert len(controller._comfort_writes) == 1
            assert coordinator._command_connection_holds == 1
            assert coordinator._disconnect_timer is None
            now[0] = 2.002
            controller._parse_position_data(sample)
            await hass.async_block_till_done()
    elif exit_kind == "cancel":
        await coordinator.async_stop_command()
    elif exit_kind == "replace":
        await coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.async_set_comfort(ReverieComfortRequest(head_position=50)),
            read_positions_after_operation=False,
        )
        assert coordinator._command_connection_holds == 1
        controller._cancel_comfort_progression()
    else:
        await coordinator.async_disconnect(reason="test teardown")

    assert not controller._comfort_writes
    assert coordinator._command_connection_holds == 0
    await coordinator.async_shutdown()


@pytest.mark.parametrize("controller_type", [ReverieController, ReverieNightstandController])
@pytest.mark.parametrize("model", ["3EMT", "O300T"])
async def test_routine_only_models_validate_and_dispatch_without_exposing_comfort(
    hass, mock_coordinator_connected, controller_type, model,
):
    coordinator = await _central(hass)
    controller = controller_type(coordinator, model=model)
    coordinator._controller = controller
    request = ReverieComfortRequest(25, 40, None if controller_type is ReverieController else 0, 0, 0)
    with pytest.raises(ValueError, match="no comfort settings"):
        await controller.async_set_comfort(request)
    invalid = ReverieComfortRequest(25, 40, None if controller_type is ReverieController else 0, 0, 0, force=True)
    with pytest.raises(ValueError, match="forced"):
        controller.validate_routine([(invalid, 1)])
    coordinator.client.write_gatt_char.reset_mock()
    await coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.async_start_routine([(request, 1)]), read_positions_after_operation=False,
    )
    assert controller._routine_timer is not None
    coordinator.client.write_gatt_char.assert_awaited()
    if controller_type is ReverieController:
        assert controller._comfort_request == request
    else:
        assert coordinator.client.write_gatt_char.call_args.args[1] == bytes.fromhex("00192800000000000000")
    await coordinator.async_shutdown()
    assert coordinator._command_connection_holds == 0


async def test_pairlink_children_keep_independent_catalogs_after_interleaved_saves(hass):
    parent = MockConfigEntry(domain=DOMAIN, data={})
    parent.add_to_hass(hass)

    def create(side):
        address = "AA:BB:CC:DD:EE:01" if side == "left" else "AA:BB:CC:DD:EE:02"
        child = ChildEntryView(parent, {CONF_ADDRESS: address, CONF_SIDE: side, CONF_BED_TYPE: BED_TYPE_REVERIE}, lambda _data: None)
        coordinator = AdjustableBedCoordinator(hass, child)
        return ReveriePairlinkController(coordinator, model="R510L", runtime=_pairlink_runtime())._sdk_io

    left, right = create("left"), create("right")
    # Both cached dictionaries start empty before either receiver persists data.
    await left._load()
    await right._load()
    await left._write("pl_finger_print", "home-left", "left fingerprint")
    await right._write("pl_finger_print", "home-right", "right fingerprint")
    await left._write("attributesManagement", "list", "left catalog")
    await right._write("attributesManagement", "list", "right catalog")
    assert await create("left")._load() == {
        "pl_finger_print": {"home-left": "left fingerprint"},
        "attributesManagement": {"list": "left catalog"},
    }
    assert await create("right")._load() == {
        "pl_finger_print": {"home-right": "right fingerprint"},
        "attributesManagement": {"list": "right catalog"},
    }
    assert await Store(hass, 1, f"adjustable_bed.pairlink_sdk.{parent.entry_id}").async_load() is None
