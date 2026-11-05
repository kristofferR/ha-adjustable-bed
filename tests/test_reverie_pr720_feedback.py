"""Registered peer and selected-axis regressions from the PR720 review."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
    dashboard_payload,
    decrypt_user_frame,
    state_query_payloads,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
    PairlinkMeshStatusEvent,
    PairlinkRuntimeNotReadyError,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE_NIGHTSTAND,
    DOMAIN,
    REVERIE_NIGHTSTAND_FOOT_POSITION_UUID,
    REVERIE_NIGHTSTAND_HEAD_POSITION_UUID,
    REVERIE_NIGHTSTAND_LUMBAR_UUID,
    REVERIE_STK_SIDE_DATA_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_reverie_pairlink import _controller, _join_central
from tests.test_reverie_pairlink_production import (
    _PEER_PATH,
    _device,
    _peer_path,
    _recv,
    _send_peer_write,
    _send_state_selector,
    _subscribe_peer,
)
from tests.test_reverie_pairlink_sdk_wiring import (
    _full_tlv,
    _local_canonical,
    _message,
    _read_available,
)


async def test_registered_backup_disconnect_preserves_primary_telemetry(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _socket, _entry):
        runtime = controller._runtime
        coordinator = controller._coordinator
        await controller.start_notify(coordinator._handle_position_update)
        for selector, value in ((1, 25), (5, 30), (12, 2)):
            await _send_state_selector(bus, _PEER_PATH, runtime, selector, value)
        primary = runtime.primary_mac
        exposed = dict(controller._state)
        backup = "22:33:44:55:66:77"
        path = _peer_path("hci3", backup)
        bus.managed_objects[path] = _device(backup)
        socket = await _subscribe_peer(bus, path)
        try:
            await _send_peer_write(bus, path, b"\x01\x00" + bytes(4))
            _recv(socket)
            for selector, value in ((1, 60), (5, 60), (12, 4)):
                await _send_state_selector(bus, path, runtime, selector, value, encrypted=False)
            assert (
                controller._peer_states[backup]["massage_head_intensity"]
                != exposed["massage_head_intensity"]
            )
            assert runtime.primary_mac == primary
            bus.managed_objects[path] = _device(backup, connected=False)
            assert bus.peer_disconnect_callback is not None
            bus.peer_disconnect_callback(path, False)
            assert backup not in controller._peer_states
            assert controller._state == exposed
            for key, value in exposed.items():
                assert coordinator.controller_state[key] == value
            assert coordinator.position_data["back"] == 25
        finally:
            socket.close()


async def test_stk_selected_head_controls_feedback_and_real_seek(hass, mock_coordinator_connected):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="STK selected head",
        unique_id="AA:BB:CC:DD:EE:FC",
        data={
            "address": "AA:BB:CC:DD:EE:FC",
            "bed_type": BED_TYPE_REVERIE_NIGHTSTAND,
            "motor_count": 2,
            "has_massage": True,
            "disable_angle_sensing": False,
            "protocol_variant": "STK",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    try:
        await coordinator.async_connect()
        controller = coordinator.controller
        handlers = {
            call.args[0]: call.args[1] for call in coordinator.client.start_notify.call_args_list
        }
        handlers[REVERIE_NIGHTSTAND_HEAD_POSITION_UUID](None, bytearray((25,)))
        handlers[REVERIE_NIGHTSTAND_LUMBAR_UUID](None, bytearray((54,)))
        assert coordinator.position_data["back"] == 25
        controller._set_stk_side("2")
        assert coordinator.position_data["back"] == 54
        assert coordinator.controller_state["reverie_back_position"] == 54
        values = {
            REVERIE_NIGHTSTAND_HEAD_POSITION_UUID: bytes((25,)),
            REVERIE_NIGHTSTAND_FOOT_POSITION_UUID: bytes((10,)),
            REVERIE_NIGHTSTAND_LUMBAR_UUID: bytes((54,)),
        }
        coordinator.client.read_gatt_char = AsyncMock(side_effect=lambda uuid: values[uuid])
        coordinator.client.write_gatt_char.reset_mock()
        await coordinator.async_seek_position(
            "back",
            25,
            lambda c: c.move_back_up(),
            lambda c: c.move_back_down(),
            lambda c: c.move_back_stop(),
        )
        assert any(
            call.args[:2] == (REVERIE_STK_SIDE_DATA_UUID, bytes((2, 0x51, 25)))
            for call in coordinator.client.write_gatt_char.call_args_list
        )
        controller._set_stk_side("3")
        assert "back" not in coordinator.position_data
        assert coordinator.controller_state["reverie_back_position"] is None
        handlers[REVERIE_NIGHTSTAND_LUMBAR_UUID](None, bytearray((25,)))
        assert coordinator.position_data["back"] == 25
        assert coordinator.controller_state["reverie_stk_head_position"] == 25
        assert coordinator.controller_state["reverie_stk_head2_position"] == 25
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("timing", ["write", "lock"])
@pytest.mark.parametrize("mutation", [None, "key", "epoch", "target", "stop"])
async def test_admitted_comfort_accepts_feedback_but_keeps_transport_and_stop_guards(
    monkeypatch, timing, mutation
):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    controller._state.update(
        back_position=20,
        legs_position=30,
        reverie_pairlink_head2_position=40,
        massage_head_intensity=3,
        massage_foot_intensity=4,
        reverie_massage_timer=5,
        reverie_massage_mode=1,
    )
    request = ReverieComfortRequest(
        head_position=35,
        foot_position=45,
        lumbar_position=55,
        head_massage=5,
        foot_massage=6,
        timer_byte=8,
        mode=2,
    )
    plan = controller.prepare_comfort(request)
    client.writes.clear()

    def feedback():
        controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, 1, 20)))
        if mutation == "key":
            runtime._peer_keys[runtime.target_mac] = bytes.fromhex("AABBCCDD")
        elif mutation == "epoch":
            runtime.epoch += 1
        elif mutation == "target":
            runtime.target_mac = "11:22:33:44:55:66"
        elif mutation == "stop":
            controller._coordinator.cancel_command.set()

    actual_write = client.write_gatt_char

    async def write(*args, **kwargs):
        await actual_write(*args, **kwargs)
        if len(client.writes) == 1 and timing == "write":
            feedback()

    monkeypatch.setattr(client, "write_gatt_char", write)
    actual_send = controller._async_send_profile_frame
    sends = 0

    async def send(*args, **kwargs):
        nonlocal sends
        sends += 1
        if sends != 2 or timing != "lock":
            return await actual_send(*args, **kwargs)
        await controller._ble_lock.acquire()
        pending = asyncio.create_task(actual_send(*args, **kwargs))
        try:
            await asyncio.sleep(0)
            assert not pending.done()
            feedback()
        finally:
            controller._ble_lock.release()
        await pending

    monkeypatch.setattr(controller, "_async_send_profile_frame", send)
    try:
        if mutation is None:
            await controller.async_set_comfort(request, prepared_plan=plan)
            assert len(client.writes) == len(plan.payloads)
        else:
            with pytest.raises(
                (PairlinkRuntimeNotReadyError, PermissionError, asyncio.CancelledError)
            ):
                await controller.async_set_comfort(request, prepared_plan=plan)
            assert len(client.writes) == 1
    finally:
        await controller.stop_notify()


@pytest.mark.parametrize("feedback", [None, "first", "every"])
@pytest.mark.parametrize("mutation", [None, "key", "epoch", "target", "stop", "sign"])
async def test_initial_dashboard_reads_accept_feedback_but_keep_session_guards(
    monkeypatch, feedback, mutation
):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    captured = runtime.prepare_send(mtu=client.mtu_size)
    effect = PairlinkMeshStatusEvent(runtime.epoch, runtime.target_mac, None, 8)
    client.writes.clear()
    original_write = client.write_gatt_char

    async def write(*args, **kwargs):
        await original_write(*args, **kwargs)
        if feedback == "every" or (feedback == "first" and len(client.writes) == 1):
            controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, 1, 20)))
        if len(client.writes) == 1:
            if mutation == "key":
                runtime._peer_keys[runtime.target_mac] = bytes.fromhex("AABBCCDD")
            elif mutation == "epoch":
                runtime.epoch += 1
            elif mutation == "target":
                runtime.target_mac = "11:22:33:44:55:66"
            elif mutation == "stop":
                controller._coordinator.cancel_command.set()
            elif mutation == "sign":
                runtime.sign_gate.sign_all = False

    monkeypatch.setattr(client, "write_gatt_char", write)
    try:
        if mutation == "stop":
            with pytest.raises(asyncio.CancelledError):
                await controller._async_run_initial_dashboard_queries(effect)
        else:
            await controller._async_run_initial_dashboard_queries(effect)
        expected = state_query_payloads() if mutation is None else state_query_payloads()[:1]
        assert captured.device_key is not None
        assert (
            tuple(
                decrypt_user_frame(
                    frame, event_key=captured.event_key, device_key=captured.device_key
                )[10:]
                for _uuid, frame, _response in client.writes
            )
            == expected
        )
    finally:
        await controller.stop_notify()


async def test_registered_local_initial_reads_keep_going_after_early_feedback(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, socket, _entry):
        runtime = controller._runtime
        backend = runtime.peripheral_backend
        assert backend is not None
        captured = runtime.prepare_send()
        _read_available(socket)
        original_send = backend.async_notify_to_peer
        sends = 0

        async def send(peer, value, **kwargs):
            nonlocal sends
            await original_send(peer, value, **kwargs)
            sends += 1
            if sends == 1:
                generation = runtime.prepare_send().peer_state_generation
                await _send_state_selector(bus, _PEER_PATH, runtime, 1, 20)
                for _ in range(20):
                    if runtime.prepare_send().peer_state_generation != generation:
                        break
                    await asyncio.sleep(0)
                assert runtime.prepare_send().peer_state_generation != generation

        monkeypatch.setattr(backend, "async_notify_to_peer", send)
        await _send_peer_write(bus, _PEER_PATH, _message(4, data=_full_tlv()))
        await hass.async_block_till_done()
        assert captured.device_key is not None
        assert (
            tuple(
                decrypt_user_frame(
                    frame, event_key=captured.event_key, device_key=captured.device_key
                )[10:]
                for frame in _read_available(socket)
            )
            == state_query_payloads()
        )


@pytest.mark.parametrize("feedback", [False, True])
@pytest.mark.parametrize("mutation", [None, "key", "stop"])
async def test_diagnostic_start_accepts_feedback_but_keeps_auth_and_stop_guards(
    monkeypatch, feedback, mutation
):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    captured = runtime.prepare_send(mtu=client.mtu_size)
    client.writes.clear()
    original_write = client.write_gatt_char

    async def write(*args, **kwargs):
        await original_write(*args, **kwargs)
        if len(client.writes) == 1:
            if feedback:
                controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, 1, 20)))
            if mutation == "key":
                runtime._peer_keys[runtime.target_mac] = bytes.fromhex("AABBCCDD")
            elif mutation == "stop":
                controller._coordinator.cancel_command.set()

    monkeypatch.setattr(client, "write_gatt_char", write)
    try:
        if mutation == "stop":
            with pytest.raises(asyncio.CancelledError):
                await controller.async_start_diagnostic()
        elif mutation == "key":
            with pytest.raises(ExceptionGroup):
                await controller.async_start_diagnostic()
        else:
            await controller.async_start_diagnostic()
        expected = (dashboard_payload(79, 20), dashboard_payload(92, 0))
        if mutation is not None:
            expected = expected[:1]
        assert captured.device_key is not None
        assert (
            tuple(
                decrypt_user_frame(
                    frame, event_key=captured.event_key, device_key=captured.device_key
                )[10:]
                for _uuid, frame, _response in client.writes
            )
            == expected
        )
        assert controller._diagnostic_timer is not None
        assert controller._diagnostic_timer.delay == 2
    finally:
        await controller.stop_notify()


async def test_registered_local_diagnostic_keeps_going_after_early_feedback(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, socket, _entry):
        runtime = controller._runtime
        backend = runtime.peripheral_backend
        assert backend is not None
        captured = runtime.prepare_send()
        _read_available(socket)
        original_send = backend.async_notify_to_peer
        sends = 0

        async def send(peer, value, **kwargs):
            nonlocal sends
            await original_send(peer, value, **kwargs)
            sends += 1
            if sends == 1:
                generation = runtime.prepare_send().peer_state_generation
                await _send_state_selector(bus, _PEER_PATH, runtime, 1, 20)
                for _ in range(20):
                    if runtime.prepare_send().peer_state_generation != generation:
                        break
                    await asyncio.sleep(0)
                assert runtime.prepare_send().peer_state_generation != generation

        monkeypatch.setattr(backend, "async_notify_to_peer", send)
        await controller.async_start_diagnostic()
        await hass.async_block_till_done()
        assert captured.device_key is not None
        assert tuple(
            decrypt_user_frame(frame, event_key=captured.event_key, device_key=captured.device_key)[
                10:
            ]
            for frame in _read_available(socket)
        ) == (dashboard_payload(79, 20), dashboard_payload(92, 0))


@pytest.mark.parametrize("feedback", [False, True])
@pytest.mark.parametrize("primary_drift", [False, True])
async def test_captured_release_accepts_queued_peer_feedback_without_retargeting(
    hass, monkeypatch, enable_custom_integrations, feedback, primary_drift
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, socket, _entry):
        runtime = controller._runtime
        captured = runtime.prepare_send()
        backend = runtime.peripheral_backend
        assert backend is not None
        backup_socket = None
        try:
            if primary_drift:
                address = "22:33:44:55:66:77"
                path = _peer_path("hci3", address)
                bus.managed_objects[path] = _device(address)
                backup_socket = await _subscribe_peer(bus, path)
                await _send_peer_write(bus, path, b"\x01\x00" + bytes(4))
                _recv(backup_socket)
                await _send_peer_write(bus, path, b"\x02\x31\x08")
                assert _recv(backup_socket) == b"\x01\x20"
                await hass.async_block_till_done()
                assert runtime.primary_mac == address
                _read_available(backup_socket)
            _read_available(socket)
            controller._coordinator.cancel_command.set()
            await backend._lock.acquire()
            pending = asyncio.create_task(
                controller._async_release_to_captured_target(dashboard_payload(3, 0), captured)
            )
            try:
                await asyncio.sleep(0)
                assert not pending.done()
                if feedback:
                    generation = runtime.peer_sessions[captured.target_mac].state_generation
                    await _send_state_selector(
                        bus, _PEER_PATH, runtime, 1, 20, device_key=captured.device_key
                    )
                    for _ in range(40):
                        if (
                            runtime.peer_sessions[captured.target_mac].state_generation
                            != generation
                        ):
                            break
                        await asyncio.sleep(0)
                    assert runtime.peer_sessions[captured.target_mac].state_generation != generation
            finally:
                backend._lock.release()
            await pending
            assert tuple(
                decrypt_user_frame(
                    frame, event_key=captured.event_key, device_key=captured.device_key
                )[10:]
                for frame in _read_available(socket)
            ) == (dashboard_payload(3, 0),)
            if backup_socket is not None:
                assert _read_available(backup_socket) == []
        finally:
            if backup_socket is not None:
                backup_socket.close()


@pytest.mark.parametrize(
    "mutation", ["key", "event_key", "epoch", "sign", "mtu", "peer_generation"]
)
async def test_captured_release_rejects_queued_auth_or_physical_changes(
    hass, monkeypatch, enable_custom_integrations, mutation
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, socket, _entry):
        runtime = controller._runtime
        captured = runtime.prepare_send()
        assert captured.peer is not None and captured.device_key is not None
        backend = runtime.peripheral_backend
        assert backend is not None
        _read_available(socket)
        await backend._lock.acquire()
        pending = asyncio.create_task(
            controller._async_release_to_captured_target(dashboard_payload(3, 0), captured)
        )
        try:
            await asyncio.sleep(0)
            assert not pending.done()
            generation = runtime.peer_sessions[captured.target_mac].state_generation
            await _send_state_selector(
                bus, _PEER_PATH, runtime, 1, 20, device_key=captured.device_key
            )
            for _ in range(40):
                if runtime.peer_sessions[captured.target_mac].state_generation != generation:
                    break
                await asyncio.sleep(0)
            assert runtime.peer_sessions[captured.target_mac].state_generation != generation
            if mutation == "key":
                runtime._peer_keys[captured.target_mac] = (
                    bytes((captured.device_key[0] ^ 1,)) + captured.device_key[1:]
                )
            elif mutation == "event_key":
                old = runtime.current_event_key
                runtime._current_event_key = bytes((old[0] ^ 1,)) + old[1:]
            elif mutation == "epoch":
                runtime.epoch += 1
            elif mutation == "sign":
                runtime.sign_gate.sign_all = False
            elif mutation == "mtu":
                runtime.peer_sessions[captured.target_mac].notify_mtu = captured.mtu + 1
            else:
                backend._peer_generations[captured.peer.device_path] += 1
        finally:
            backend._lock.release()
        with pytest.raises(
            Exception, match="authentication|session|signing|peer|generation|transport"
        ):
            await pending
        assert _read_available(socket) == []


@pytest.mark.parametrize("feedback", [False, True])
async def test_central_captured_release_accepts_queued_feedback_after_stop(monkeypatch, feedback):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    captured = runtime.prepare_send(mtu=client.mtu_size)
    client.writes.clear()
    controller._coordinator.cancel_command.set()
    await controller._ble_lock.acquire()
    pending = asyncio.create_task(
        controller._async_release_to_captured_target(dashboard_payload(3, 0), captured)
    )
    try:
        await asyncio.sleep(0)
        assert not pending.done()
        if feedback:
            controller.handle_mesh_event(32, bytes((0, 0, 0, 0, 2, 0xA7, 1, 20)))
    finally:
        controller._ble_lock.release()
    try:
        await pending
        assert captured.device_key is not None
        assert tuple(
            decrypt_user_frame(frame, event_key=captured.event_key, device_key=captured.device_key)[
                10:
            ]
            for _uuid, frame, _response in client.writes
        ) == (dashboard_payload(3, 0),)
    finally:
        await controller.stop_notify()
