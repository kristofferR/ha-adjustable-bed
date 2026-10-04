"""Actual scheduled OFF completion and fresh sequential receiver preflight."""

import asyncio
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.exceptions import HomeAssistantError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteMemory,
    get_limoss_remote_session,
)
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote_review_lifecycle import (
    CAPS,
    live_controller,
    pair_runtime,
    public_call,
)


async def prepare_live(coordinator):
    controller = await live_controller(coordinator)
    client = coordinator.client

    def startup(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        reply = {2: "0208120008", 0: "0001020304", 1: "0101020304"}[opcode]
        client.start_notify.call_args.args[1](char, bytearray(format_command(bytes.fromhex(reply), 0)))

    client.write_gatt_char.side_effect = startup
    await coordinator.async_start_notify()
    client.write_gatt_char.reset_mock()
    return controller, client


@pytest.mark.parametrize("interrupt", [None, "stop", "replace"])
async def test_options_off_must_finish_before_persist_even_after_scheduler_replacement(hass, interrupt):
    coordinator = actual_coordinator(hass, **{
        const.CONF_HAS_LIGHT: True,
        const.CONF_HAS_MASSAGE: True,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    controller, client = await prepare_live(coordinator)
    before = deepcopy(dict(coordinator.entry.data))
    entered, release = asyncio.Event(), asyncio.Event()
    opcodes = []

    async def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        opcodes.append(opcode)
        if interrupt and opcode == 0x71:
            entered.set()
            await release.wait()

    client.write_gatt_char.side_effect = write
    flow = AdjustableBedOptionsFlow(coordinator.entry)
    flow.hass, flow.handler = hass, coordinator.entry.entry_id
    save = None
    try:
        with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
            assert (await flow.async_step_settings({const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS}))["type"] == "form"
            save = asyncio.create_task(flow.async_step_settings({}))
            if interrupt:
                await asyncio.wait_for(entered.wait(), 2)
                # Real coordinator STOP invalidates the scheduler ticket, drains
                # the canceled ATT operation and sends its actual native STOP.
                if interrupt == "stop":
                    await asyncio.wait_for(coordinator.async_stop_command(), 2)
                else:
                    await coordinator.async_execute_controller_command(
                        AsyncMock(), cancel_running=True,
                    )
            result = await asyncio.wait_for(save, 2)
            if interrupt:
                assert coordinator.entry.data == before, "STOP ended OFF early, but options persisted a new profile"
                reload.assert_not_awaited()
            else:
                assert result["type"] == "create_entry"
                assert opcodes == [0x71] * 10 + [0x66] * 10
    finally:
        release.set()
        if save is not None:
            save.cancel()
            await asyncio.gather(save, return_exceptions=True)
        coordinator._cancel_disconnect_timer()
        coordinator._cancel_diagnostic_polling()
        await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize(("change", "route"), [
    ("none", "recall"), ("memory", "recall"), ("layout", "hold"),
    ("memory", "goto"), ("memory", "save"), ("failure", "recall"),
    ("cancel", "recall"),
])
async def test_registered_sequential_pair_rejects_fresh_second_profile_before_any_movement(hass, change, route):
    old_pair, children, cached = await pair_runtime(hass)
    entry = old_pair.entry
    hass.config_entries.async_update_entry(entry, data={
        **entry.data, const.CONF_PAIR_CONNECTION_MODE: const.PAIR_CONNECTION_MODE_SEQUENTIAL,
    })
    pair = PairedBedCoordinator(hass, entry, children)
    hass.data[const.DOMAIN][entry.entry_id] = pair
    clients = {side: child.client for side, child in children.items()}
    trace = []
    awaiting_capability = asyncio.Event()
    for side, child in children.items():
        get_limoss_remote_session(child.hass, child.address).memories.slots[8] = LimossRemoteMemory("Eight", ((0, -1),))
        child.save_app_state()
        child._client = child._controller = None
        child._post_connect_delay = 0
        child._max_retries = 1
        client = clients[side]
        client.is_connected = False

        async def disconnect(client=client, side=side):
            client.is_connected = False
            trace.append((side, "disconnect"))

        def write(role, packet, *, side=side, client=client, **kwargs):
            opcode = LimossController._tea_decrypt(packet[1:9])[1]
            trace.append((side, opcode))
            if opcode in {0, 1, 2}:
                if side == const.SIDE_RIGHT and change == "failure" and opcode == 2:
                    raise ConnectionError("Second capability query failed")
                if side == const.SIDE_RIGHT and change == "cancel" and opcode == 2:
                    awaiting_capability.set()
                    return
                caps = "0208120008"
                if side == const.SIDE_RIGHT and change == "memory":
                    caps = "0208120007"
                if side == const.SIDE_RIGHT and change == "layout":
                    caps = "0202120008"
                reply = {2: caps, 0: "0001020304", 1: "0101020304"}[opcode]
                client.start_notify.call_args.args[1](role, bytearray(format_command(bytes.fromhex(reply), 0)))

        client.disconnect = AsyncMock(side_effect=disconnect)
        client.write_gatt_char.side_effect = write
        assert child.capability_controller is cached[side]
        assert child.capability_controller.memory_slot_count == 8
        assert "motor_2_up" in child.capability_controller.held_control_options

    async def adapter(hass, address, *args, **kwargs):
        return AdapterSelectionResult(BLEDevice(address, "App bed", {}), "local", -50, True, ["local"])

    async def establish(cls, device, name, **kwargs):
        side = next(side for side, child in children.items() if child.address == device.address)
        assert not any(client.is_connected for client in clients.values()), "Sequential path opened two BLE links"
        clients[side].is_connected = True
        trace.append((side, "connect"))
        return clients[side]

    async def factory(*args, **kwargs):
        controller = await create_controller(*args, **kwargs)
        # Preserve real timer yielding; the held loop must be cancellable.
        return controller

    module = "custom_components.adjustable_bed.coordinator."
    try:
        with ExitStack() as stack:
            stack.enter_context(patch(module + "select_adapter", side_effect=adapter))
            stack.enter_context(patch(module + "establish_connection", side_effect=establish))
            stack.enter_context(patch(module + "close_stale_connections_by_address", new=AsyncMock()))
            stack.enter_context(patch(module + "discover_services", new=AsyncMock(return_value=True)))
            stack.enter_context(patch(module + "client_source", return_value="local"))
            stack.enter_context(patch(module + "async_path_for_source", return_value=None))
            stack.enter_context(patch(module + "create_controller", side_effect=factory))
            stack.enter_context(patch.object(hass.config_entries, "async_reload", new=AsyncMock()))
            data = {"duration": 0.1}
            service = {"recall": "goto_preset", "hold": "hold_control", "goto": "goto_preset", "save": "save_preset"}[route]
            if route in {"goto", "save"}:
                data = {}
            if change == "layout":
                service, data = "hold_control", {**data, "control": "motor_2_up"}
            else:
                data["preset"] = 8
            error = None
            operation = asyncio.create_task(public_call(hass, pair, service, data))
            try:
                if change == "cancel":
                    await asyncio.wait_for(awaiting_capability.wait(), 2)
                    operation.cancel()
                await asyncio.wait_for(operation, 5)
            except (HomeAssistantError, asyncio.CancelledError) as exc:
                error = str(exc)
            finally:
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
            movements = [(side, opcode) for side, opcode in trace if opcode in {0x11, 0x22}]
            if change == "none":
                assert error is None and {side for side, _ in movements} == {const.SIDE_LEFT, const.SIDE_RIGHT}
            else:
                assert error is not None, "Fresh second profile must reject the requested action"
                assert not movements, "First receiver moved before the later receiver's fresh capability rejection"
                assert not any(opcode in {0x10, 0x20, 0x30, 0x40} for _, opcode in trace)
    finally:
        for child in children.values():
            child._cancel_disconnect_timer()
            child._cancel_diagnostic_polling()
            child._cancel_controller_state_refresh_retry()
            await child._command_scheduler.async_shutdown()


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("interrupt", ["stop", "replace", "caller_cancel"])
async def test_feature_service_interrupted_off_never_commits_selected_flags(hass, paired, interrupt):
    if paired:
        target, children, _ = await pair_runtime(hass)
        coordinator = children[const.SIDE_LEFT]
        side = const.SIDE_LEFT
    else:
        coordinator = actual_coordinator(hass, **{
            const.CONF_HAS_LIGHT: True,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
        })
        target, side = coordinator, const.SIDE_BOTH
    controller, client = await prepare_live(coordinator)
    before = deepcopy(dict(target.entry.data))
    entered, release = asyncio.Event(), asyncio.Event()
    opcodes = []

    async def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        opcodes.append(opcode)
        if opcode == 0x71:
            entered.set()
            await release.wait()

    client.write_gatt_char.side_effect = write
    feature = asyncio.create_task(public_call(
        hass, target, "limoss_remote_features", {"underbed_light": False, "massage": False}, side,
    ))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if interrupt == "stop":
            await coordinator.async_stop_command()
        elif interrupt == "replace":
            await coordinator.async_execute_controller_command(AsyncMock(), cancel_running=True)
        else:
            feature.cancel()
        with pytest.raises((HomeAssistantError, asyncio.CancelledError)):
            await asyncio.wait_for(feature, 2)
        assert target.entry.data == before
        assert controller.underbed_light and controller.massage
        assert opcodes.count(0x71) == 1 and 0x66 not in opcodes
    finally:
        release.set()
        feature.cancel()
        await asyncio.gather(feature, return_exceptions=True)


async def test_queued_off_replaced_before_callback_does_not_save_options(hass):
    coordinator = actual_coordinator(hass, **{
        const.CONF_HAS_LIGHT: True,
        const.CONF_HAS_MASSAGE: True,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    })
    controller, client = await prepare_live(coordinator)
    before = deepcopy(dict(coordinator.entry.data))
    entered, finish, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def active():
        entered.set()
        await finish.wait()

    command = asyncio.create_task(coordinator.async_execute_command_group(
        [active], resources=("*",), cancel_running=False,
    ))
    await asyncio.wait_for(entered.wait(), 2)
    enqueue = coordinator._command_scheduler.enqueue

    async def observed_enqueue(intent, **kwargs):
        handle = await enqueue(intent, **kwargs)
        queued.set()
        return handle

    flow = AdjustableBedOptionsFlow(coordinator.entry)
    flow.hass, flow.handler = hass, coordinator.entry.entry_id
    save = replacement = None
    try:
        assert (await flow.async_step_settings({const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS}))["type"] == "form"
        with patch.object(coordinator._command_scheduler, "enqueue", side_effect=observed_enqueue):
            save = asyncio.create_task(flow.async_step_settings({}))
            await asyncio.wait_for(queued.wait(), 2)
            replacement = asyncio.create_task(coordinator.async_execute_controller_command(
                AsyncMock(), cancel_running=True,
            ))
            result = await asyncio.wait_for(save, 2)
        assert result.get("errors") == {"base": "limoss_remote_feature_update_failed"}
        assert coordinator.entry.data == before
        assert controller.underbed_light and controller.massage
        client.write_gatt_char.assert_not_awaited()
    finally:
        finish.set()
        await asyncio.gather(command, *[task for task in (save, replacement) if task], return_exceptions=True)
