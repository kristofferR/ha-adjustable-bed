"""ComfortFurniture 2.3 through the production factory and session, on virtual time."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.keeson.comfortfurniture import (
    LEVEL,
    TIMER,
    ComfortFurnitureController,
)
from custom_components.adjustable_bed.const import KEESON_VARIANT_COMFORTFURNITURE
from tests.hold_lease_wire import virtual_clock
from tests.test_comfortfurniture_vectors import COMMANDS
from tests.test_ore_comfort_bed import _controller, _written


async def make_bed(hass: HomeAssistant, client: MagicMock) -> ComfortFurnitureController:
    ctrl = await _controller(hass, client, KEESON_VARIANT_COMFORTFURNITURE, 4)
    assert isinstance(ctrl, ComfortFurnitureController)
    ctrl._coordinator._motor_pulse_count = 2
    return ctrl


@pytest.mark.parametrize("row", COMMANDS, ids=lambda r: r["id"])
async def test_every_command_uses_production_callers(
    hass, mock_coordinator_connected, mock_bleak_client, row
):
    c = await make_bed(hass, mock_bleak_client)
    action, expected = row["action"], [row["expected_bytes"]]
    with virtual_clock():
        if action in ("movement_release_stop", "preset_stop_same_button"):
            await (c.stop_all if action == "movement_release_stop" else c.stop_preset)()
        elif action == "bed_reset_label":
            await next(
                s for s in c.controller_button_specs if s.key == "comfortfurniture_reset"
            ).press_fn(c)
        elif action.startswith("preset_"):
            name, verb = action.removeprefix("preset_").rsplit("_", 1)
            name = {"zero_gravity": "zero_g", "as": "anti_snore"}.get(name, name)
            await (c.recall_named if verb == "recall" else c.save_named)(name)
        elif action in ("bed_light_on", "bed_light_off"):
            await (c.lights_on if action.endswith("on") else c.lights_off)()
        elif action == "massage_start_initial":
            await c.massage_start()
            expected += ["e5fe1610000022d4", "e5fe1610000012e4"]
        elif action == "massage_stop":
            await c.massage_off()
        elif action.startswith("massage_timer_"):
            await c.set_massage_timer_option(
                action.removeprefix("massage_timer_").removesuffix("min")
            )
        elif action.startswith(("massage_wave_bin", "massage_intensity_bin")):
            slider = action.split("_")[1]
            await c.set_massage_progress(slider, int(action[-1]) * 10)
        else:
            axis, direction = action.rsplit("_", 1)
            axis = {"foot": "feet", "back_foot": "both"}.get(axis, axis)
            spec = next(s for s in c.motor_control_specs if s.key == axis)
            await (spec.open_fn if direction == "up" else spec.close_fn)(c)
            expected = expected * 2 + ["e5fe160000000006"]
    assert _written(mock_bleak_client) == expected
    assert all(
        call.kwargs["response"] is False
        for call in mock_bleak_client.write_gatt_char.call_args_list
    )


async def test_presets_stop_on_second_tap_and_save_never_recalls(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)
    with virtual_clock():
        await c.preset_reading()
        await c.preset_reading()
        await c.program_flat()
        await c.preset_memory(1)
        await c.stop_all()
    assert _written(mock_bleak_client) == [
        "e5fe1621000004e1",
        "e5fe1621000000e5",
        "e5fe1621000012d3",
        "e5fe1621000006df",
        "e5fe1621000000e5",
    ]
    with pytest.raises(ValueError):
        await c.program_memory(2)


async def test_slider_persistence_start_sequence_and_timer_reset(
    hass, mock_coordinator_connected, mock_bleak_client, hass_storage
):
    c = await make_bed(hass, mock_bleak_client)
    with virtual_clock():
        await c.set_massage_progress("wave", 29)
        await c.set_massage_progress("intensity", 0)
        await c.massage_start()
        for option in ("10", "20", "30"):
            await c.set_massage_timer_option(option)
        await c.massage_off()
        assert c._coordinator.controller_state[TIMER] is None
    assert _written(mock_bleak_client)[2:5] == [
        "e5fe1610000011e5",
        "e5fe1610000023d3",
        "e5fe1610000011e5",
    ]
    assert _written(mock_bleak_client)[5:] == [
        "e5fe1610000030c6",
        "e5fe1610000031c5",
        "e5fe1610000032c4",
        "e5fe1610000010e6",
    ]
    assert c._coordinator.controller_state[LEVEL["wave"]] == 3
    assert c._coordinator.controller_state[LEVEL["intensity"]] == 1
    coord = c._coordinator
    await coord.async_shutdown()
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    restarted = AdjustableBedCoordinator(hass, coord.entry)
    await restarted.async_connect()
    assert restarted.controller.persisted_app_state == {"wave": 29, "intensity": 0}
    for bad in ({"wave": -1}, {"intensity": 30}, {"wave": True}, {"head": 1}):
        with pytest.raises(ValueError):
            c.restore_persisted_app_state(bad)


@pytest.mark.parametrize("mode", ["event", "task", "notify"])
async def test_held_cleanup_is_independent_of_cancellation(
    hass, mock_coordinator_connected, mock_bleak_client, mode
):
    c = await make_bed(hass, mock_bleak_client)
    received = mock_bleak_client.start_notify.call_args.args[1]

    async def write(*_args, **_kwargs):
        if len(_written(mock_bleak_client)) == 1:
            if mode == "task":
                raise asyncio.CancelledError
            if mode == "notify":
                received(None, bytearray.fromhex("000000000000000700"))
            else:
                c._coordinator.cancel_command.set()

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock():
        if mode == "task":
            with pytest.raises(asyncio.CancelledError):
                await c.move_back_up()
        else:
            await c.move_back_up()
    assert _written(mock_bleak_client) == ["e5fe160000000105", "e5fe160000000006"]
    c._coordinator.cancel_command.clear()


async def test_finite_holds_expire_by_elapsed_time_without_catchup(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)
    c._coordinator._motor_pulse_count = 3
    times: list[float] = []

    async def slow_write(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.24)

    mock_bleak_client.write_gatt_char.side_effect = slow_write
    with virtual_clock():
        await c.move_back_up()
    assert _written(mock_bleak_client) == ["e5fe160000000105", "e5fe160000000006"]
    assert times == pytest.approx([0, 0.4])


@pytest.mark.parametrize("replace", ["client", "controller", "generation"])
async def test_pending_sequence_and_cleanup_cannot_move_to_replacement_session(
    hass, mock_coordinator_connected, mock_bleak_client, replace
):
    c = await make_bed(hass, mock_bleak_client)
    coord = c._coordinator
    old_receiver = mock_bleak_client.start_notify.call_args.args[1]

    async def swap(*_args, **_kwargs):
        if replace == "client":
            coord._client = MagicMock(is_connected=True)
        elif replace == "controller":
            coord._controller = MagicMock()
        else:
            c.on_disconnect()

    mock_bleak_client.write_gatt_char.side_effect = swap
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.massage_start()
    assert _written(mock_bleak_client) == ["e5fe1610000011e5"]
    current_cancel = coord.cancel_command
    current_cancel.clear()
    old_receiver(None, bytearray.fromhex("000000000000000700"))
    assert not current_cancel.is_set()


async def test_admission_before_first_wait_and_no_stale_release(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)

    async def drop(*_args, **_kwargs):
        c.on_disconnect()

    mock_bleak_client.write_gatt_char.side_effect = drop
    with virtual_clock():
        await c.move_back_up()
    assert _written(mock_bleak_client) == ["e5fe160000000105"]
    c._coordinator.cancel_command.clear()
    # Missing roles are refused synchronously before the pre-send sleep.
    c._coordinator._client = None
    sleep = AsyncMock()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(asyncio, "sleep", sleep)
        with pytest.raises(ConnectionError):
            await c.lights_on()
    sleep.assert_not_awaited()


async def test_ble_lock_wait_cannot_extend_finite_movement(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)
    await c._ble_lock.acquire()
    with virtual_clock():
        moving = asyncio.create_task(c.move_back_up())
        await asyncio.sleep(0.4)
        c._ble_lock.release()
        await moving
    assert _written(mock_bleak_client) == ["e5fe160000000006"]


async def test_peripheral_timeout_is_not_a_successful_hold_expiry(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)
    mock_bleak_client.write_gatt_char.side_effect = [TimeoutError("BLE write"), None]
    with virtual_clock(), pytest.raises(TimeoutError, match="BLE write"):
        await c.move_back_up()
    assert _written(mock_bleak_client)[-1] == "e5fe160000000006"


@pytest.mark.parametrize("action", ["stop", "replace"])
async def test_stop_or_ownership_change_during_first_wait_cannot_transmit(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch, action
):
    c = await make_bed(hass, mock_bleak_client)

    async def before_send(_delay):
        if action == "stop":
            c._coordinator.cancel_command.set()
        else:
            c._coordinator._controller = MagicMock()

    monkeypatch.setattr(asyncio, "sleep", before_send)
    with pytest.raises(asyncio.CancelledError if action == "stop" else ConnectionError):
        await c.preset_flat()
    assert not _written(mock_bleak_client)
    if action == "stop":
        # STOP can arrive before the recall writes, so its intent is retained
        # before that first wait and uses the preset-specific stop word.
        await c.stop_all()
        assert _written(mock_bleak_client) == ["e5fe1621000000e5"]
        c._coordinator.cancel_command.clear()


async def test_entities_use_readable_names_without_duplicate_controls(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)
    names = {s.key: (s.translation_placeholders or {}).get("action", s.name) for s in c.controller_button_specs}
    assert names == {
        "comfortfurniture_save_zero_g": "Save zero-gravity position",
        "comfortfurniture_save_flat": "Save flat position",
        "comfortfurniture_save_anti_snore": "Save anti-snore position",
        "comfortfurniture_save_reading": "Save reading position",
        "comfortfurniture_preset_stop": "Stop preset",
        "comfortfurniture_reset": "Reset",
    }
    wave = next(s for s in c.controller_number_specs if s.key == "comfortfurniture_wave_level")
    assert (wave.native_min_value, wave.native_max_value) == (1, 3)
    with virtual_clock():
        await wave.set_fn(c, 2)
    assert _written(mock_bleak_client)[-1] == "e5fe1610000022d4"


async def test_rejected_recall_keeps_the_previous_selection(
    hass, mock_coordinator_connected, mock_bleak_client
):
    from bleak.exc import BleakError

    c = await make_bed(hass, mock_bleak_client)
    mock_bleak_client.write_gatt_char.side_effect = BleakError("rejected")
    with virtual_clock(), pytest.raises(BleakError):
        await c.recall_named("flat")
    # A retry recalls again instead of sending preset stop.
    assert c._selected_preset is None


async def test_massage_switch_starts_and_stops_with_unknown_state(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await make_bed(hass, mock_bleak_client)
    assert not c.supports_massage_off_control  # the switch replaces the generic off button
    (massage,) = c.controller_switch_specs
    with virtual_clock():
        await massage.set_fn(c, True)
        await massage.set_fn(c, False)
    assert _written(mock_bleak_client)[-4:] == [
        "e5fe1610000011e5", "e5fe1610000022d4", "e5fe1610000012e4", "e5fe1610000010e6",
    ]
    assert massage.state_key is not None
    assert c._coordinator.controller_state.get(massage.state_key) is None
