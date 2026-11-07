"""Reverie reconnect, progression and paired persistence review cases."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie import ReverieController
from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie_nightstand import ReverieNightstandController
from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_PAIRLINK,
    CONF_BED_TYPE,
    CONF_SIDE,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
from tests.test_reverie_routines import _pairlink_runtime
from tests.test_reverie_session_lane import _central


async def _pairlink_central(hass):
    from tests.test_reverie_pairlink import _GattClient, _login_packet
    from tests.test_reverie_pairlink_production import _entry

    entry = _entry(role="central")
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._disconnect_after_command = True
    client = _GattClient()
    client.disconnect = AsyncMock()
    coordinator._client = client
    controller = await create_controller(coordinator, BED_TYPE_REVERIE_PAIRLINK, "R510L", client)
    coordinator._controller = controller
    await controller.start_notify()
    notify = client.notify_callback
    assert notify is not None
    notify(None, bytearray(_login_packet()))
    await hass.async_block_till_done()
    notify(None, bytearray(b"\x02\x31\x08"))
    await hass.async_block_till_done()
    return coordinator, controller


@pytest.mark.parametrize("finish", ["timer", "stop_failure", "dispatch_failure", "disconnect", "replace", "start_failure"])
async def test_pairlink_diagnostic_owns_connection_through_cleanup(hass, monkeypatch, finish):
    coordinator, controller = await _pairlink_central(hass)
    writes = AsyncMock(side_effect=ConnectionError("start failed") if finish == "start_failure" else None)
    monkeypatch.setattr(controller, "async_send_payload", writes)

    async def start():
        await coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.async_start_diagnostic(), read_positions_after_operation=False,
        )

    if finish == "start_failure":
        with pytest.raises(ExceptionGroup, match="start writes failed"):
            await start()
        writes.side_effect = None
    else:
        await start()
    assert coordinator._command_connection_holds == 1
    assert coordinator._disconnect_timer is None
    timer = controller._diagnostic_timer
    assert timer is not None
    captured, generation = controller._diagnostic_snapshot, controller._diagnostic_generation
    writes.reset_mock()

    if finish == "disconnect":
        controller.on_disconnect()
        writes.assert_not_awaited()
    else:
        if finish == "replace":
            await start()
            replacement_timer = controller._diagnostic_timer
            writes.reset_mock()
            controller._enqueue_diagnostic_stop(captured, generation)
            await controller._stop_diagnostic(captured, generation)
            assert controller._diagnostic_timer is replacement_timer
            assert coordinator._command_connection_holds == 1
            writes.assert_not_awaited()
            captured, generation = controller._diagnostic_snapshot, controller._diagnostic_generation
        if finish == "stop_failure":
            writes.side_effect = ConnectionError("stop failed")
            with pytest.raises(ExceptionGroup, match="stop writes failed"):
                await controller._stop_diagnostic(captured, generation)
            assert writes.await_count == 2
        elif finish == "dispatch_failure":
            monkeypatch.setattr(coordinator, "async_execute_controller_command", AsyncMock(side_effect=ConnectionError("dispatch failed")))
            with pytest.raises(ConnectionError, match="dispatch failed"):
                await controller._stop_diagnostic(captured, generation)
        else:
            async def send_stop(*_args, **_kwargs):
                assert coordinator._command_connection_holds == 1
                assert coordinator._disconnect_timer is None

            writes.side_effect = send_stop
            controller._diagnostic_timer.cancel()
            controller._enqueue_diagnostic_stop(captured, generation)
            await hass.async_block_till_done()
            assert [call.args[0] for call in writes.await_args_list] == [
                bytes.fromhex("01480000"), bytes.fromhex("015D0000"),
            ]
    assert timer.cancelled()
    assert coordinator._command_connection_holds == 0
    assert controller._diagnostic_timer is None
    assert controller._diagnostic_snapshot is None
    assert coordinator._disconnect_timer is not None
    await coordinator.async_shutdown()


@pytest.mark.parametrize(("mode", "rhythm"), [(0, False), (3, True)])
async def test_pairlink_feedback_populates_selects_and_preserves_numeric_mode(hass, monkeypatch, mode, rhythm):
    coordinator, controller = await _pairlink_central(hass)
    mode_select, rhythm_select = [
        AdjustableBedControllerSelect(coordinator, spec) for spec in controller.controller_select_specs
    ]
    assert mode_select.current_option is None
    assert rhythm_select.current_option is None
    controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, 12, mode)))
    controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, 13, int(rhythm))))
    assert mode_select.current_option == str(mode)
    assert rhythm_select.current_option == ("on" if rhythm else "off")
    assert type(coordinator.controller_state["reverie_massage_mode"]) is int
    assert controller._state["reverie_massage_mode"] == mode
    assert coordinator.controller_state["reverie_massage_rhythm"] is rhythm
    set_mode = AsyncMock()
    monkeypatch.setattr(controller, "set_massage_mode", set_mode)
    await controller.massage_mode_step()
    set_mode.assert_awaited_once_with((mode + 1) % 5)
    controller.on_disconnect()
    assert mode_select.current_option is None
    assert rhythm_select.current_option is None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("controller_type", [ReverieController, ReverieNightstandController, ReveriePairlinkController])
@pytest.mark.parametrize("stop_failure", [False, True])
async def test_public_stop_cancels_routine_and_invalidates_future_steps(
    hass, mock_coordinator_connected, monkeypatch, controller_type, stop_failure,
):
    if controller_type is ReveriePairlinkController:
        coordinator, controller = await _pairlink_central(hass)
        write_method = "async_send_payload"
    else:
        coordinator = await _central(hass)
        controller = controller_type(coordinator, model="9T" if controller_type is ReverieController else "R510L")
        coordinator._controller = controller
        write_method = "write_command" if controller_type is ReverieController else "_write_to_char"
    writes = AsyncMock()
    monkeypatch.setattr(controller, write_method, writes)
    request = ReverieComfortRequest(
        head_position=25,
        foot_position=40,
        lumbar_position=None if controller_type is ReverieController else 0,
        head_massage=0,
        foot_massage=0,
        timer_byte=0 if controller_type is ReveriePairlinkController else None,
        mode=0 if controller_type is ReveriePairlinkController else None,
    )
    await coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.async_start_routine([(request, 1), (request, 1)]),
        read_positions_after_operation=False,
    )
    timer = controller._routine_timer
    generation = controller._routine_generation
    assert timer is not None
    assert coordinator._command_connection_holds > 0
    writes.reset_mock()
    if stop_failure:
        writes.side_effect = ConnectionError("STOP failed")
        with pytest.raises((ConnectionError, ExceptionGroup)):
            await coordinator.async_stop_command()
    else:
        await coordinator.async_stop_command()
    assert writes.await_count > 0
    assert timer.cancelled()
    assert controller._routine_timer is None
    assert controller._routine_generation > generation
    assert coordinator._command_connection_holds == 0
    writes.reset_mock()
    controller._enqueue_routine_step(generation)
    await hass.async_block_till_done()
    writes.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("side", ["left", "both"])
async def test_sequential_pair_stop_cancels_ready_local_routine_without_central_reconnect(
    hass, monkeypatch, enable_custom_integrations, side,
):
    from custom_components.adjustable_bed.const import CONF_PAIR_ID
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_reverie_review_regressions import _ready_local

    async with _ready_local(hass, monkeypatch, "R510L") as (_, left, _sock):
        entry = MockConfigEntry(domain=DOMAIN, data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FE", CONF_BED_TYPE: BED_TYPE_REVERIE,
        })
        right = AdjustableBedCoordinator(hass, entry)
        right._controller = ReverieController(right, model="9T")
        central_connect = AsyncMock(side_effect=AssertionError("must not reconnect central side"))
        monkeypatch.setattr(right, "async_ensure_connected", central_connect)
        pair = PairedBedCoordinator(
            hass, MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "local-routine-stop"}),
            {"left": left, "right": right}, connection_mode="sequential",
        )
        controller = left.controller
        comfort = AsyncMock()
        monkeypatch.setattr(controller, "async_set_comfort", comfort)
        request = ReverieComfortRequest(head_position=25)
        await pair.async_execute_controller_command(
            lambda ctrl: ctrl.async_start_routine([(request, 1), (request, 1)]),
            side="left", resource="reverie:routine",
        )
        timer, generation = controller._routine_timer, controller._routine_generation
        assert timer is not None
        assert controller.disconnected_transport_ready
        assert not left.is_connected and not right.is_connected
        comfort.assert_awaited_once()

        await pair.async_stop_command(side=side)

        assert timer.cancelled()
        assert controller._routine_timer is None
        assert controller._routine_generation > generation
        assert controller._routine_settings == []
        assert controller._routine_connection_release is None
        assert left._command_connection_holds == 0
        controller._enqueue_routine_step(generation)
        await hass.async_block_till_done()
        comfort.assert_awaited_once()
        central_connect.assert_not_awaited()
        await pair.async_shutdown()


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
