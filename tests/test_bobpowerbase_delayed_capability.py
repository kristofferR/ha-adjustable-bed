"""Hosted R1: an original registered action awaits its later BLE capability reply."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.goodvibe.controller import GoodVibeController, Link
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.profiles.bobpowerbase import CATALOG
from scripts.wire_snapshot import FakeClock, virtual_time
from tests.test_bobpowerbase import REAL_SLEEP
from tests.test_bobpowerbase_review import LIGHT_REPLY, pair_for, register, runtime
from tests.test_bobpowerbase_review import disconnected_service as disconnected_service
from tests.test_bobpowerbase_review import domain_bootstrap as domain_bootstrap
from tests.test_bobpowerbase_review import fake_time as fake_time


@pytest.mark.parametrize("outcome", ("delayed_reply", "timeout", "stop", "stale_reply", "caller_cancel", "second_target_missing"))
async def test_registered_light_action_waits_for_post_startup_reply_with_bounded_admission(
    hass, disconnected_service, mock_establish_connection, outcome,
):
    coordinator, device, client, _synchronous_reply = disconnected_service
    startup_finished = asyncio.Event()
    original_start = GoodVibeController.start_notify
    delivery_tasks = []
    delivered = []
    second = None
    devices = [device]
    if outcome == "second_target_missing":
        second = runtime(hass, address="AA:BB:CC:DD:EE:97")
        second.async_ensure_connected = AsyncMock(return_value=True)
        second._async_refresh_controller_auth = AsyncMock()
        devices.append(register(hass, second))

    async def started(controller, callback=None):
        await original_start(controller, callback)
        startup_finished.set()

    async def deliver():
        await startup_finished.wait()
        # Virtual BLE latency after start_notify AND its final startup write
        # have completed. A synchronous write callback cannot satisfy this test.
        await asyncio.sleep(0.1)
        if outcome == "timeout":
            return
        if outcome == "stop":
            await coordinator.async_stop_command()
        elif outcome == "caller_cancel":
            call.cancel()
        elif outcome == "stale_reply":
            old_callback = client.start_notify.await_args.args[1]
            client.is_connected = False
            mock_establish_connection.call_args.kwargs["disconnected_callback"](client)
            old_callback(None, bytearray(LIGHT_REPLY))
        else:
            assert startup_finished.is_set()
            frames = [item.args[1] for item in client.write_gatt_char.await_args_list]
            assert len(frames) == 4 and frames[-1][3:6] == bytes((8, 3, 1))
            delivered.append(len(frames))
            client.start_notify.await_args.args[1](None, bytearray(LIGHT_REPLY))

    async def write(_characteristic, packet, **_kwargs):
        if len(packet) > 5 and packet[3:6] == bytes((8, 3, 1)):
            delivery_tasks.append(asyncio.create_task(deliver()))

    client.write_gatt_char.side_effect = write
    try:
        # Reuse only the existing virtual clock; no wire scenarios or capture run.
        # Restore real yielding before installing it because the shared fixture
        # replaces asyncio.sleep to avoid unrelated protocol timer waits.
        with patch.object(asyncio, "sleep", REAL_SLEEP), virtual_time(FakeClock()) as _clock, patch.object(GoodVibeController, "start_notify", started):
            call = asyncio.create_task(hass.services.async_call(DOMAIN, "bobpowerbase", {
                "device_id": devices, "operation": "light_color", "rgb_color": [1, 2, 3],
            }, blocking=True))
            if outcome == "delayed_reply":
                await call
            elif outcome in ("caller_cancel", "stop"):
                with pytest.raises(asyncio.CancelledError):
                    await call
            elif outcome == "stale_reply":
                with pytest.raises((ConnectionError, ServiceValidationError)):
                    await call
            else:
                with pytest.raises(ServiceValidationError):
                    await call
            await asyncio.gather(*delivery_tasks)
        colors = [item.args[1] for item in client.write_gatt_char.await_args_list if item.args[1] == codec.rgb(1, 2, 3)]
        assert colors == ([codec.rgb(1, 2, 3)] if outcome == "delayed_reply" else [])
        if outcome == "delayed_reply":
            assert delivered == [4]
        if outcome == "stop":
            assert codec.function(0x6E) in [item.args[1] for item in client.write_gatt_char.await_args_list]
        if second is not None:
            second.client.write_gatt_char.assert_not_awaited()
    finally:
        for task in delivery_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*delivery_tasks, return_exceptions=True)
        if second is not None:
            await second.async_shutdown()


async def test_sequential_original_light_action_awaits_fresh_capability_on_each_reconnect(hass, fake_time):
    del fake_time
    from custom_components.adjustable_bed.beds.goodvibe.services import (
        async_register_goodvibe_services,
    )

    pair, physical = pair_for(hass, "sequential")
    device = register(hass, pair)
    connections = {child.address: 0 for child in physical}
    replies, writes, deliveries = [], [], []

    def drop(child):
        if child.controller is not None:
            child.controller.on_disconnect()
        if child.client is not None:
            child.client.is_connected = False
        child._controller = child._client = None
        child._position_connection_generation += 1

    for child in physical:
        drop(child)

        async def connect(*_args, owner=child, **_kwargs):
            if owner.controller is None:
                connections[owner.address] += 1
                owner._position_connection_generation += 1
                owner._client = MagicMock(is_connected=True)
                owner._client.stop_notify = AsyncMock()
                owner._client.write_gatt_char = AsyncMock(side_effect=lambda _char, packet, address=owner.address, **_kw: writes.append((address, packet, tuple(replies))))
                owner._controller = GoodVibeController(owner, profile="ultra_sh", catalog=CATALOG)
                controller = owner.controller
                link = Link(owner.client, MagicMock(uuid="tx", properties=["write"], handle=1), MagicMock(uuid="rx"), False)
                controller._link = link

                async def reply():
                    await asyncio.sleep(0.1)
                    replies.append(owner.address)
                    controller._notification(link, link.rx, bytearray(LIGHT_REPLY))

                deliveries.append(asyncio.create_task(reply()))
            return True

        async def disconnect(*_args, owner=child, **_kwargs):
            drop(owner)
            return True

        child.async_connect = AsyncMock(side_effect=connect)
        child.async_ensure_connected = AsyncMock(side_effect=connect)
        child.async_disconnect = AsyncMock(side_effect=disconnect)
        child._async_refresh_controller_auth = AsyncMock()
    async_register_goodvibe_services(hass)
    try:
        with patch.object(asyncio, "sleep", REAL_SLEEP), virtual_time(FakeClock()):
            await hass.services.async_call(DOMAIN, "bobpowerbase", {
                "device_id": device, "operation": "light_color", "rgb_color": [1, 2, 3],
            }, blocking=True)
            await asyncio.gather(*deliveries)
        assert set(connections.values()) == {2}
        assert len(writes) == 2
        assert all(packet == codec.rgb(1, 2, 3) and set(connections) <= set(admitted) for _address, packet, admitted in writes)
    finally:
        for task in deliveries:
            if not task.done():
                task.cancel()
        await asyncio.gather(*deliveries, return_exceptions=True)
        await pair.async_shutdown()
        await pair.entry._async_process_on_unload(hass)
