"""Jordan's Restful A20 frames through setup, controls and the owned BLE link."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.serenity.controller import RestfulController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import BED_TYPE_RESTFUL, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type
from custom_components.adjustable_bed.errors import BedCommandTimedOutError
from custom_components.adjustable_bed.services import async_register_services
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.okin_nframe_vectors import RESTFUL_FRAMES
from tests.test_okin_bedding_apps import STOP, _coordinator, written
from tests.test_okin_bedding_apps_integration import _target, configure_entity_runtime

FRAMES = {name: bytes.fromhex(literal).hex() for name, _, literal in RESTFUL_FRAMES}


@pytest.mark.parametrize(("vector", "action", "literal"), RESTFUL_FRAMES)
def test_restful_profile_matches_each_frozen_literal(vector, action, literal) -> None:
    from custom_components.adjustable_bed.codec import okin_nframe as codec
    from custom_components.adjustable_bed.profiles.okin_nframe import RESTFUL

    assert codec.frame(0 if action == "stop" else RESTFUL.keys[action], RESTFUL.width) == bytes.fromhex(
        literal
    ), vector
    assert set(RESTFUL.keys) == {action for _, action, _ in RESTFUL_FRAMES} - {"stop"}


@pytest.mark.parametrize("name", ["OKIN", "okin-restful", "Jordan's Restful", "UnNamed"])
def test_shared_okin_signals_do_not_choose_restful(name) -> None:
    info = MagicMock(
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=["62741523-52f9-8864-b1ab-3b3a8d65950b"],
        manufacturer_data={},
    )
    info.name = name
    assert detect_bed_type(info) != BED_TYPE_RESTFUL


async def test_restful_entities_keep_recalls_and_confirmed_saves_separate(hass) -> None:
    coordinator = _coordinator()
    coordinator.hass = hass
    controller = await create_controller(coordinator, BED_TYPE_RESTFUL, None, coordinator.client)
    assert isinstance(controller, RestfulController)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_RESTFUL)
    entities = _button_entities_for(hass, runtime)
    saves = {
        button.unique_id: button.extra_state_attributes
        for button in entities
        if button.unique_id
        and any(
            key in button.unique_id
            for key in ("program_memory_", "restful_save_zero_g", "restful_save_tv")
        )
    }
    assert saves.keys() == {
        "bed_program_memory_1_left",
        "bed_program_memory_2_left",
        "bed_restful_save_zero_g_left",
        "bed_restful_save_tv_left",
    }
    assert all(attrs["requires_confirmation"] and "held_control" not in attrs for attrs in saves.values())
    assert {spec.key for spec in controller.motor_control_specs} == {"head", "feet", "lumbar"}
    assert controller.supports_preset_tv and controller.supports_preset_lounge
    assert not controller.supports_preset_incline
    assert not controller.supports_head_massage_intensity_step_control
    assert not controller.supports_foot_massage_intensity_step_control
    assert not controller.supports_clock_alarm
    assert not controller.supports_clock_sync


@pytest.mark.parametrize(
    ("method", "args", "vector", "press_ms"),
    [
        ("move_lumbar_up", (), "tilt-up", 200),
        ("move_lumbar_down", (), "lumbar-down", 200),
        ("preset_flat", (), "flat", 1500),
        ("preset_lounge", (), "leisure", 500),
        ("preset_tv", (), "tv", 500),
        ("preset_memory", (1,), "memory-1", 500),
        ("preset_memory", (2,), "memory-2", 500),
        ("program_memory", (1,), "save-m1", 5000),
        ("program_memory", (2,), "save-m2", 5000),
        ("execute_app_control", ("save_tv",), "save-tv", 5000),
        ("execute_app_control", ("save_zero_g",), "save-zero-gravity", 5000),
        ("lights_on", (), "light-on", 500),
        ("massage_intensity_up", (), "massage-increase", 500),
        ("stop_all", (), "release", 0),
    ],
)
async def test_restful_normal_controls_end_with_two_neutrals(method, args, vector, press_ms) -> None:
    coordinator = _coordinator()
    controller = RestfulController(coordinator)
    times = []

    async def record(*_args, **_kwargs) -> None:
        times.append(round(asyncio.get_running_loop().time() * 1000))

    coordinator.client.write_gatt_char.side_effect = record
    with virtual_clock():
        await getattr(controller, method)(*args)
    assert written(controller) == [FRAMES[vector]] * (press_ms // 100) + [STOP, STOP]
    assert times == [*range(0, press_ms, 100), press_ms + 100, press_ms + 200]
    assert "save_pending_code" not in controller.protocol_diagnostics


@pytest.mark.parametrize(
    ("properties", "response"),
    [(("write",), True), (("write-without-response",), False), (("write", "write-without-response"), True)],
)
async def test_restful_writes_to_the_selected_service_handle(properties, response) -> None:
    coordinator = _coordinator()
    controller = RestfulController(coordinator)
    command = coordinator.client.services[0].characteristics[0]
    command.properties = properties
    duplicate = MagicMock(uuid=command.uuid, properties=("write",), handle=23)
    coordinator.client.services.insert(0, MagicMock(uuid="deadbeef", characteristics=[duplicate]))
    with virtual_clock():
        await controller.stop_all()
    assert len(coordinator.client.write_gatt_char.await_args_list) == 2
    for call in coordinator.client.write_gatt_char.await_args_list:
        assert call.args[0] is command
        assert call.kwargs["response"] is response


@pytest.mark.parametrize("reuse_client", [False, True])
async def test_restful_held_press_never_releases_on_a_replacement_link(reuse_client) -> None:
    coordinator = _coordinator()
    controller = RestfulController(coordinator)
    first = coordinator.client
    replacement = first if reuse_client else _coordinator().client

    async def reconnect(*_args, **_kwargs) -> None:
        controller.on_disconnect()
        coordinator.client = replacement
        coordinator.cancel_command.set()

    first.write_gatt_char.side_effect = reconnect
    with virtual_clock(), pytest.raises(ConnectionError, match="previous BLE connection"):
        await controller.move_head_up()
    assert first.write_gatt_char.await_count == 1
    if not reuse_client:
        replacement.write_gatt_char.assert_not_awaited()


async def test_restful_stop_after_cancel_does_not_repeat_the_cleanup() -> None:
    coordinator = _coordinator()
    coordinator.cancel_counter = 1
    controller = RestfulController(coordinator)

    async def cancel(*_args, **_kwargs) -> None:
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = cancel
    with virtual_clock():
        await controller.move_head_up()
        await controller.stop_all()
    assert written(controller) == [FRAMES["head-up"], STOP, STOP]


async def test_restful_stop_still_attempts_its_second_neutral_after_a_timeout() -> None:
    coordinator = _coordinator()
    controller = RestfulController(coordinator)
    times = []

    async def write(*_args, **_kwargs) -> None:
        times.append(round(asyncio.get_running_loop().time() * 1000))
        if len(times) == 1:
            await asyncio.sleep(10)

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(TimeoutError):
        await controller.stop_all()
    assert written(controller) == [STOP, STOP]
    assert times == [100, 1100]


async def test_restful_subscribes_to_exact_role_and_discards_old_callbacks() -> None:
    coordinator = _coordinator(manufacturer=b"CST13")
    controller = RestfulController(coordinator)
    first = coordinator.client
    notify = first.services[0].characteristics[1]
    manufacturer = first.services[1].characteristics[0]
    first.stop_notify = AsyncMock()
    timer_20 = bytearray.fromhex("00 00 00 00 00 00 00 00 00 00 02")
    timer_10 = bytearray.fromhex("00 00 00 00 00 00 00 00 00 00 01")
    signed = bytearray.fromhex("00 00 00 00 00 00 00 00 00 00 ff")
    alarm = bytearray.fromhex("00 0c 00 00 20 02 06 1e 00 01 00")

    with virtual_clock():
        await controller.start_notify()
    subscribed, receive = first.start_notify.await_args.args
    assert subscribed is notify
    first.read_gatt_char.assert_awaited_once_with(manufacturer)
    receive(MagicMock(handle=22), timer_20)
    receive(notify, timer_20[:-1])
    assert "restful_massage_timer_minutes" not in controller.protocol_diagnostics
    receive(notify, timer_20)
    assert controller.protocol_diagnostics["restful_massage_timer_minutes"] == 20
    coordinator.handle_controller_state_updates.reset_mock()
    receive(notify, timer_20)
    receive(notify, alarm)
    coordinator.handle_controller_state_updates.assert_not_called()

    await controller.stop_notify()
    first.stop_notify.assert_awaited_once_with(notify)
    controller.on_disconnect()
    assert any(
        update.key == "restful_massage_timer_minutes" and update.value is None
        for update in coordinator.handle_controller_state_updates.call_args.args
    )
    with virtual_clock():
        await controller.start_notify()
    receive(notify, timer_10)
    assert "restful_massage_timer_minutes" not in controller.protocol_diagnostics
    _, current_receive = first.start_notify.await_args.args
    current_receive(notify, timer_20)
    assert controller.protocol_diagnostics["restful_massage_timer_minutes"] == 20
    current_receive(notify, signed)
    assert controller.protocol_diagnostics["restful_status_code"] == -1
    assert controller.protocol_diagnostics["restful_massage_timer_minutes"] is None
    assert not any("alarm" in spec.key for spec in controller.controller_state_sensor_specs)

    async def save_status(*_args, **_kwargs) -> None:
        current_receive(notify, timer_10)

    first.write_gatt_char.side_effect = save_status
    with virtual_clock():
        await controller.program_memory(1)
    assert controller.protocol_diagnostics["restful_massage_timer_minutes"] is None
    assert "restful_save_event_code" not in controller.protocol_diagnostics
    current_receive(notify, timer_10)
    assert controller.protocol_diagnostics["restful_massage_timer_minutes"] == 10


async def test_restful_hold_service_rejects_saves_and_uses_the_physical_axis(hass, monkeypatch) -> None:
    await async_register_services(hass)
    controller = RestfulController(_coordinator())
    coordinator = _target(BED_TYPE_RESTFUL, controller)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(coordinator, SIDE_BOTH)], []),
    )
    data = {"device_id": "bed", "duration": 0.25}
    with virtual_clock():
        with raises_key("held_control_not_supported", ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "hold_control", {**data, "control": "save_tv"}, blocking=True
            )
        assert written(controller) == []
        await hass.services.async_call(
            DOMAIN, "hold_control", {**data, "control": "lumbar_up"}, blocking=True
        )
    assert written(controller) == [FRAMES["tilt-up"]] * 3 + [STOP, STOP]


@pytest.mark.parametrize("replace_link", [False, True])
async def test_restful_timed_move_releases_only_its_press(hass, monkeypatch, replace_link) -> None:
    await async_register_services(hass)
    physical = _coordinator()
    controller = RestfulController(physical)
    coordinator = _target(BED_TYPE_RESTFUL, controller)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(coordinator, SIDE_BOTH)], []),
    )
    first = physical.client
    replacement = _coordinator().client

    async def swap(*_args, **_kwargs) -> None:
        controller.on_disconnect()
        physical.client = replacement

    if replace_link:
        first.write_gatt_char.side_effect = swap
    with virtual_clock():
        call = hass.services.async_call(
            DOMAIN, "timed_move",
            {"device_id": "bed", "motor": "lumbar", "direction": "up", "duration_ms": 250},
            blocking=True,
        )
        if replace_link:
            with pytest.raises(ConnectionError, match="previous BLE connection"):
                await call
        else:
            await call
    if replace_link:
        assert first.write_gatt_char.await_count == 1
        replacement.write_gatt_char.assert_not_awaited()
    else:
        assert written(controller) == [FRAMES["tilt-up"]] * 3 + [STOP, STOP]


@pytest.mark.parametrize(
    ("wait_for_lock", "neutral_fails"), [(True, False), (False, False), (False, True)]
)
async def test_restful_short_hold_requires_a_completed_press(wait_for_lock, neutral_fails) -> None:
    physical = _coordinator()
    controller = RestfulController(physical)
    neutrals = 0
    cleanup_error = BleakError("neutral write failed")

    async def write(_char, data, **_kwargs) -> None:
        nonlocal neutrals
        if data.hex() != STOP:
            await asyncio.sleep(0.125)
            return
        neutrals += 1
        if neutral_fails and neutrals == 1:
            raise cleanup_error

    async def unlock() -> None:
        await asyncio.sleep(0.125)
        controller._ble_lock.release()

    physical.client.write_gatt_char.side_effect = write
    with virtual_clock():
        release = None
        if wait_for_lock:
            await controller._ble_lock.acquire()
            release = asyncio.create_task(unlock())
        with pytest.raises(BedCommandTimedOutError) as timeout:
            await controller.hold_control("lumbar_up", 100)
        if release is not None:
            await release
    assert neutrals == 2
    assert timeout.value.__cause__ is (cleanup_error if neutral_fails else None)


@pytest.mark.parametrize("has_status", [False, True])
async def test_restful_first_setup_verifies_the_status_role(hass, monkeypatch, has_status) -> None:
    from homeassistant.const import CONF_ADDRESS

    from custom_components.adjustable_bed import config_flow
    from custom_components.adjustable_bed.const import CONF_BED_TYPE
    from tests.test_config_flow import _fresh_gate

    client = _coordinator().client
    if not has_status:
        client.services[0].characteristics.pop()
    client.disconnect = AsyncMock()
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    flow._pending_entry = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_BED_TYPE: BED_TYPE_RESTFUL,
    }
    freshness, device = _fresh_gate("hci0", -55)
    monkeypatch.setattr(
        config_flow, "async_wait_for_advertisement", AsyncMock(return_value=(freshness, device))
    )
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    monkeypatch.setattr(config_flow, "read_ble_device_info", AsyncMock(return_value=(None, None)))
    result = await flow._async_probe_worker()
    assert result.succeeded is has_status
    if not has_status:
        assert result.detail is not None and "requires its notification characteristic" in result.detail
    client.write_gatt_char.assert_not_awaited()
    client.disconnect.assert_awaited_once()
