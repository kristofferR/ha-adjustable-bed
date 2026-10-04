"""Registered service waiter must recheck subscription ownership after awaiting."""
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
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteMemory,
    get_limoss_remote_session,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote import make_controller
from tests.test_limoss_remote_preflight_review import prepare_live
from tests.test_limoss_remote_review_lifecycle import CAPS


@pytest.mark.parametrize("retire", [False, True])
async def test_retirement_after_ready_before_waiter_resumes_prevents_first_movement(hass, retire):
    left = actual_coordinator(hass, **{
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01", const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    left_controller, left_client = await prepare_live(left)
    left_controller._sleep = LimossRemoteController._sleep.__get__(left_controller)
    right = actual_coordinator(hass, **{
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02", const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    right._post_connect_delay, right._max_retries = 0, 1
    old_controller, old_client = await prepare_live(right)
    old_controller._sleep = LimossRemoteController._sleep.__get__(old_controller)
    # Production caches a completed controller for offline capabilities. Restart
    # its public notification channel so the new generation has a real waiter.
    await old_controller.stop_notify()
    assert right.capability_controller is old_controller
    new_client = make_controller().client
    new_client.is_connected = False
    entered, release, waiter_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    trace = []
    for child in (left, right):
        get_limoss_remote_session(child.hass, child.address).memories.slots[8] = LimossRemoteMemory("Eight", ((0, -1),))
        child.save_app_state()

    def left_write(role, packet, **kwargs):
        trace.append(("left", LimossController._tea_decrypt(packet[1:9])[1]))

    async def old_write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        trace.append(("old_right", opcode))
        if opcode == 2:
            entered.set()
            await release.wait()
        if opcode in {0, 1, 2}:
            reply = {2: "0208120008", 0: "0001020304", 1: "0101020304"}[opcode]
            old_client.start_notify.call_args.args[1](role, bytearray(format_command(bytes.fromhex(reply), 0)))

    def new_write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        trace.append(("new_right", opcode))
        reply = {2: "0208120007", 0: "0001020304", 1: "0101020304"}[opcode]
        new_client.start_notify.call_args.args[1](role, bytearray(format_command(bytes.fromhex(reply), 0)))

    async def establish(*args, **kwargs):
        new_client.is_connected = True
        return new_client

    async def disconnect():
        new_client.is_connected = False

    left_client.write_gatt_char.side_effect = left_write
    old_client.write_gatt_char.side_effect = old_write
    new_client.write_gatt_char.side_effect = new_write
    new_client.disconnect = AsyncMock(side_effect=disconnect)
    adapter = AdapterSelectionResult(BLEDevice(right.address, "App bed", {}), "local", -50, True, ["local"])
    module = "custom_components.adjustable_bed.coordinator."
    owner = operation = None
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
            owner = asyncio.create_task(right.async_start_notify())
            await asyncio.wait_for(entered.wait(), 2)
            ready = old_controller._notify_ready
            assert ready is not None and not ready.done()

            def physical_retirement(_future):
                # Simulate an actual backend disconnection at this event-loop
                # boundary; use the coordinator's production callback admission.
                trace.append(("old_right", "backend_disconnect"))
                old_client.is_connected = False
                right._on_disconnect(old_client)

            if retire:
                ready.add_done_callback(physical_retirement)
            original_start = old_controller.start_notify

            async def observed_start(*args, **kwargs):
                waiter_entered.set()
                return await original_start(*args, **kwargs)

            stack.enter_context(patch.object(old_controller, "start_notify", side_effect=observed_start))
            with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
                       return_value=([(left, const.SIDE_BOTH), (right, const.SIDE_BOTH)], [])):
                operation = asyncio.create_task(hass.services.async_call(
                    const.DOMAIN, "goto_preset",
                    {"device_id": ["left", "right"], "preset": 8, "duration": 0.1}, blocking=True,
                ))
                await asyncio.wait_for(waiter_entered.wait(), 2)
                release.set()
                await asyncio.wait_for(owner, 3)
                error = None
                try:
                    await asyncio.wait_for(operation, 4)
                except (HomeAssistantError, ConnectionError) as exc:
                    error = str(exc)
            if retire:
                assert error == "App startup notification owner changed"
                assert not any(side == "left" and opcode == 0x11 for side, opcode in trace)
            else:
                assert error is None
                assert {side for side, opcode in trace if opcode == 0x11} == {"left", "old_right"}
    finally:
        release.set()
        for task in (owner, operation):
            if task is not None:
                task.cancel()
        await asyncio.gather(*[task for task in (owner, operation) if task], return_exceptions=True)
        for child in (left, right):
            child._cancel_disconnect_timer()
            child._cancel_diagnostic_polling()
            child._cancel_controller_state_refresh_retry()
            await child._command_scheduler.async_shutdown()


@pytest.mark.parametrize("change", ["client", "role", "cancel"])
async def test_waiter_checks_live_owner_role_and_cancel_after_readiness_wakeup(hass, change):
    from tests.test_limoss_remote_session_readiness import pending_controller

    coordinator, controller, client, entered, release, _ = await pending_controller(hass)
    owner = asyncio.create_task(controller.start_notify())
    waiter = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        ready = controller._notify_ready
        assert ready is not None

        def retire(_future):
            if change == "client":
                coordinator._client = make_controller().client
            elif change == "role":
                client.services = make_controller().client.services
            else:
                coordinator.cancel_command.set()

        ready.add_done_callback(retire)
        waiter = asyncio.create_task(controller.start_notify())
        await asyncio.sleep(0)
        assert not waiter.done()
        release.set()
        await asyncio.wait_for(owner, 2)
        expected = asyncio.CancelledError if change == "cancel" else ConnectionError
        with pytest.raises(expected):
            await asyncio.wait_for(waiter, 2)
    finally:
        release.set()
        for task in (owner, waiter):
            if task is not None:
                task.cancel()
        await asyncio.gather(*[task for task in (owner, waiter) if task], return_exceptions=True)
