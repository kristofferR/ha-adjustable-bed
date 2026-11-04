"""Deferred local routines retain their original registered physical peer."""

import asyncio

import pytest

from custom_components.adjustable_bed.const import DOMAIN
from tests.test_reverie_local_send_guard import VALUES
from tests.test_reverie_pairlink_production import (
    _PEER_PATH,
    _device,
    _device_for_address,
    _login_packet,
    _peer_path,
    _recv,
    _send_peer_write,
    _send_state_selector,
    _subscribe_peer,
)
from tests.test_reverie_pairlink_sdk_wiring import _local_canonical


def _received(peer_socket):
    frames = []
    if peer_socket.fileno() < 0:
        return frames
    while True:
        try:
            frame = _recv(peer_socket)
        except BlockingIOError:
            return frames
        if not frame:
            return frames
        frames.append(frame)


@pytest.mark.parametrize(
    "change", ["replace", "disconnect_replace", "rejoin", "backup_disconnect", "resubscribe"]
)
async def test_registered_routine_cannot_follow_a_replacement_peer(
    hass, monkeypatch, enable_custom_integrations, change
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, original_socket, _entry):
        runtime = controller._runtime
        coordinator = controller._coordinator
        controller._cancel_backup_check()
        original = runtime.prepare_send()
        device = _device_for_address(hass, coordinator.address)
        assert device is not None
        await hass.services.async_call(
            DOMAIN,
            "reverie_run_routine",
            {
                "device_id": device.id,
                "steps": [
                    {"duration_minutes": 1, "comfort": {**VALUES, "head_position": 25}},
                    {"duration_minutes": 1, "comfort": {**VALUES, "head_position": 45}},
                ],
            },
            blocking=True,
        )
        timer = controller._routine_timer
        generation = controller._routine_generation
        assert timer is not None and coordinator._command_connection_holds > 0
        assert _received(original_socket)

        replacement_socket = None
        try:
            if change in ("disconnect_replace", "rejoin"):
                bus.managed_objects[_PEER_PATH] = _device(connected=False)
                assert bus.peer_disconnect_callback is not None
                bus.peer_disconnect_callback(_PEER_PATH, False)

            if change == "resubscribe":
                original_socket.close()
                for _ in range(3):
                    await asyncio.sleep(0)
                assert not runtime.peer_sessions[original.target_mac].subscribed
                replacement_socket = await _subscribe_peer(bus, _PEER_PATH)
                assert runtime.prepare_send().peer == original.peer
            elif change == "rejoin":
                path = _PEER_PATH
                bus.managed_objects[path] = _device()
                replacement_socket = await _subscribe_peer(bus, path)
                await _send_peer_write(bus, path, _login_packet())
                _recv(replacement_socket)
                await _send_peer_write(bus, path, b"\x02\x31\x08")
                assert _recv(replacement_socket) == b"\x01\x20"
                assert runtime.prepare_send().peer != original.peer
            else:
                address = "22:33:44:55:66:77"
                path = _peer_path("hci3", address)
                bus.managed_objects[path] = _device(address)
                replacement_socket = await _subscribe_peer(bus, path)
                await _send_peer_write(
                    bus,
                    path,
                    _login_packet() if change == "disconnect_replace" else b"\x01\x00" + bytes(4),
                )
                _recv(replacement_socket)
                if change == "backup_disconnect":
                    await _send_state_selector(bus, _PEER_PATH, runtime, 1, 30)
                    bus.managed_objects[path] = _device(address, connected=False)
                    assert bus.peer_disconnect_callback is not None
                    bus.peer_disconnect_callback(path, False)
                else:
                    await _send_peer_write(bus, path, b"\x02\x31\x08")
                    assert _recv(replacement_socket) == b"\x01\x20"
                    assert runtime.primary_mac == address
            controller._cancel_backup_check()
            await hass.async_block_till_done()
            _received(original_socket)
            _received(replacement_socket)

            # Fire the retained callback without waiting on a protocol timer.
            timer.cancel()
            controller._enqueue_routine_step(generation)
            await hass.async_block_till_done()
            if change in ("backup_disconnect", "resubscribe"):
                assert _received(replacement_socket if change == "resubscribe" else original_socket)
                assert runtime.prepare_send().peer == original.peer
            else:
                assert _received(replacement_socket) == []
                assert _received(original_socket) == []
                assert controller._routine_generation > generation
            assert controller._routine_timer is None
            assert coordinator._command_connection_holds == 0

            if change not in ("backup_disconnect", "resubscribe"):
                await hass.services.async_call(
                    DOMAIN,
                    "reverie_run_routine",
                    {
                        "device_id": device.id,
                        "steps": [
                            {"duration_minutes": 1, "comfort": {**VALUES, "head_position": 15}},
                            {"duration_minutes": 1, "comfort": {**VALUES, "head_position": 55}},
                        ],
                    },
                    blocking=True,
                )
                assert _received(replacement_socket)
                fresh_timer = controller._routine_timer
                assert fresh_timer is not None
                controller._enqueue_routine_step(generation)
                await hass.async_block_till_done()
                assert _received(replacement_socket) == []
                assert controller._routine_timer is fresh_timer
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": device.id}, blocking=True
                )
                assert fresh_timer.cancelled()
                assert coordinator._command_connection_holds == 0
        finally:
            if replacement_socket is not None:
                replacement_socket.close()
