"""A physical live client is not proof that its fresh02 handshake completed."""
import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteMemory,
    get_limoss_remote_session,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote import make_controller
from tests.test_limoss_remote_preflight_review import prepare_live
from tests.test_limoss_remote_review_lifecycle import CAPS


async def test_inflight_registered_startup_must_not_skip_later_fresh_preflight(hass):
    left = actual_coordinator(hass, **{
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    left_controller, left_client = await prepare_live(left)
    left_controller._sleep = LimossRemoteController._sleep.__get__(left_controller)
    right = actual_coordinator(hass, **{
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    right._client = right._controller = None
    await right.async_prime_offline_controller()
    right_client = make_controller().client
    right_client.is_connected = False
    right._post_connect_delay, right._max_retries = 0, 1
    entered, release, moved = asyncio.Event(), asyncio.Event(), asyncio.Event()
    trace = []
    for child in (left, right):
        get_limoss_remote_session(child.hass, child.address).memories.slots[8] = LimossRemoteMemory("Eight", ((0, -1),))
        child.save_app_state()

    def left_write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        trace.append(("left", opcode))
        if opcode == 0x11:
            moved.set()

    async def right_write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        trace.append(("right", opcode))
        if opcode == 2:
            entered.set()
            await release.wait()
        if opcode in {0, 1, 2}:
            reply = {2: "0208120007", 0: "0001020304", 1: "0101020304"}[opcode]
            right_client.start_notify.call_args.args[1](role, bytearray(format_command(bytes.fromhex(reply), 0)))

    async def disconnect():
        right_client.is_connected = False

    async def establish(*args, **kwargs):
        right_client.is_connected = True
        return right_client

    left_client.write_gatt_char.side_effect = left_write
    right_client.write_gatt_char.side_effect = right_write
    right_client.disconnect = AsyncMock(side_effect=disconnect)
    adapter = AdapterSelectionResult(BLEDevice(right.address, "App bed", {}), "local", -50, True, ["local"])
    module = "custom_components.adjustable_bed.coordinator."
    connect = operation = None
    try:
        with ExitStack() as stack:
            stack.enter_context(patch(module + "select_adapter", new=AsyncMock(return_value=adapter)))
            stack.enter_context(patch(module + "establish_connection", side_effect=establish))
            stack.enter_context(patch(module + "close_stale_connections_by_address", new=AsyncMock()))
            stack.enter_context(patch(module + "discover_services", new=AsyncMock(return_value=True)))
            stack.enter_context(patch(module + "client_source", return_value="local"))
            stack.enter_context(patch(module + "async_path_for_source", return_value=None))
            stack.enter_context(patch.object(hass.config_entries, "async_reload", new=AsyncMock()))
            await async_register_services(hass)
            connect = asyncio.create_task(right.async_connect())
            await asyncio.wait_for(entered.wait(), 2)
            assert right.is_connected and not connect.done()
            assert right.controller.capabilities.memory_count == 8
            with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
                       return_value=([(left, const.SIDE_BOTH), (right, const.SIDE_BOTH)], [])):
                operation = asyncio.create_task(hass.services.async_call(
                    const.DOMAIN, "limoss_remote_recall_memory",
                    {"device_id": ["left", "right"], "preset": 8, "duration": 0.1}, blocking=True,
                ))
                try:
                    await asyncio.wait_for(moved.wait(), 0.8)
                except TimeoutError:
                    pass
                movement_before_reply = moved.is_set()
                release.set()
                assert await asyncio.wait_for(connect, 3)
                error = None
                try:
                    await asyncio.wait_for(operation, 3)
                except HomeAssistantError as exc:
                    error = str(exc)
            assert error is not None, "Fresh capacity7 must reject requested slot8"
            assert not movement_before_reply, "First receiver moved while later fresh02 was still pending"
            assert not any(side == "left" and opcode == 0x11 for side, opcode in trace)
    finally:
        release.set()
        for task in (connect, operation):
            if task is not None:
                task.cancel()
        await asyncio.gather(*[task for task in (connect, operation) if task], return_exceptions=True)
        for child in (left, right):
            child._cancel_disconnect_timer()
            child._cancel_diagnostic_polling()
            child._cancel_controller_state_refresh_retry()
            await child._command_scheduler.async_shutdown()


async def pending_controller(hass):
    coordinator = actual_coordinator(hass, **{
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    controller = await create_controller(coordinator, const.BED_TYPE_LIMOSS_REMOTE, None, coordinator.client)
    assert isinstance(controller, LimossRemoteController)
    coordinator._controller = controller
    controller._sleep = AsyncMock()
    client = coordinator.client
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        requests.append(opcode)
        if opcode == 2:
            entered.set()
            await release.wait()
        payload = {2: "0208120008", 0: "0001020304", 1: "0101020304"}[opcode]
        client.start_notify.call_args.args[1](char, bytearray(format_command(bytes.fromhex(payload), 0)))

    client.write_gatt_char.side_effect = write
    return coordinator, controller, client, entered, release, requests


async def test_reentrant_startup_waits_and_cancelled_waiter_does_not_cancel_owner(hass):
    _, controller, client, entered, release, requests = await pending_controller(hass)
    startup = asyncio.create_task(controller.start_notify())
    waiter = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        waiter = asyncio.create_task(controller.start_notify())
        await asyncio.sleep(0)
        assert not waiter.done() and not startup.done()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert controller._notify_ready is not None and not controller._notify_ready.done()
        release.set()
        await asyncio.wait_for(startup, 2)
        await controller.start_notify()
        assert requests == [2, 0, 1]
        client.start_notify.assert_awaited_once()
    finally:
        release.set()
        for task in (startup, waiter):
            if task is not None:
                task.cancel()
        await asyncio.gather(*[task for task in (startup, waiter) if task], return_exceptions=True)


@pytest.mark.parametrize("failure", ["write_error", "owner_cancel", "stop", "disconnect"])
async def test_pending_startup_failure_wakes_waiters_without_cached_readiness(hass, failure):
    _, controller, client, entered, release, _ = await pending_controller(hass)
    original = client.write_gatt_char.side_effect
    write_error = ConnectionError("Capability write failed")

    async def write(char, packet, **kwargs):
        if failure == "write_error":
            entered.set()
            await release.wait()
            raise write_error
        await original(char, packet, **kwargs)

    client.write_gatt_char.side_effect = write
    startup = asyncio.create_task(controller.start_notify())
    waiter = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        waiter = asyncio.create_task(controller.start_notify())
        await asyncio.sleep(0)
        assert not waiter.done()
        if failure == "owner_cancel":
            startup.cancel()
        elif failure == "stop":
            await controller.stop_notify()
        elif failure == "disconnect":
            client.is_connected = False
            controller.on_disconnect()
        else:
            release.set()
        with pytest.raises((ConnectionError, asyncio.CancelledError)) as caught:
            await asyncio.wait_for(waiter, 2)
        if failure == "write_error":
            assert caught.value is write_error
        release.set()
        with pytest.raises((ConnectionError, asyncio.CancelledError)):
            await asyncio.wait_for(startup, 2)
        assert controller._notify_ready is None
    finally:
        release.set()
        for task in (startup, waiter):
            if task is not None:
                task.cancel()
        await asyncio.gather(*[task for task in (startup, waiter) if task], return_exceptions=True)


async def test_retired_startup_cannot_complete_or_unsubscribe_replacement_generation(hass):
    _, controller, client, entered, release, requests = await pending_controller(hass)
    startup = asyncio.create_task(controller.start_notify())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        old_ready = controller._notify_ready
        await controller.stop_notify()

        def replacement_write(char, packet, **kwargs):
            opcode = LimossController._tea_decrypt(packet[1:9])[1]
            requests.append(opcode)
            payload = {2: "0208120007", 0: "0001020304", 1: "0101020304"}[opcode]
            client.start_notify.call_args.args[1](char, bytearray(format_command(bytes.fromhex(payload), 0)))

        client.write_gatt_char.side_effect = replacement_write
        # The real ATT lane remains occupied by the retired generation until it
        # drains. The replacement is admitted, then both owners are released.
        replacement = asyncio.create_task(controller.start_notify())
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(startup, 2)
        await asyncio.wait_for(replacement, 2)
        assert old_ready is not controller._notify_ready
        assert controller._notify_ready is not None and controller._notify_ready.done()
        assert controller.memory_slot_count == 7
        client.stop_notify.assert_awaited_once()
        await controller.start_notify()
        assert client.start_notify.await_count == 2
    finally:
        release.set()
        startup.cancel()
        await asyncio.gather(startup, return_exceptions=True)
