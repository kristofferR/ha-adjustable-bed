"""Admitted alarm cohorts and reused scheduler workers keep their app ownership."""

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import coordinator_connection as connection
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.beds.keeson import betterliving2 as runtime
from custom_components.adjustable_bed.beds.keeson.betterliving2_selection import Selection
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.command_scheduler import CommandKind, current_command_context
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.profiles import betterliving2 as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_betterliving2_review import (
    NOW,
    action_frames,
    alarm_prefix,
    bind,
    call_app,
    native_pair,
    observed,
    ready,
)
from tests.test_betterliving2_runtime import bed, client_for, writes


async def prior_worker(child):
    entered, retiring, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation():
        assert runtime.current_selection() is None
        context = current_command_context()
        assert context is not None
        entered.set()
        await context.cancel_event.wait()
        retiring.set()
        await release.wait()

    handle = await child.async_prepare_command_operation(
        operation, kind=CommandKind.COMMAND, cancel_running=False, group_id="previous-operation"
    )
    await child.async_wait_prepared_command(handle)
    child.commit_prepared_command(handle)
    await observed(entered, handle.future)
    return handle, retiring, release


@pytest.mark.parametrize("initial", ("right", "offline"))
@pytest.mark.parametrize("outcome", ("complete", "stop", "startup_failure"))
async def test_concurrent_alarm_waits_for_every_owned_startup(hass, initial, outcome):
    entered, release = asyncio.Event(), asyncio.Event()
    events = []
    children = {}
    blocked = False

    async def hook(child, _controller, _client, frame):
        nonlocal blocked
        if child is children.get("left") and not blocked:
            blocked = True
            entered.set()
            await release.wait()
            if outcome == "startup_failure":
                raise BleakError("owned startup failed")

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", initial, events, hook
        )
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered, task)
            # Let the other receiver complete this app's startup on virtual time.
            await asyncio.sleep(app.SETUP_QUERY_DELAY_MS / 1000 + 0.1)
            assert not task.done()
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            if outcome == "stop":
                await parent.async_stop_command()
            release.set()
            if outcome == "startup_failure":
                with pytest.raises(PairedSideError):
                    await task
            else:
                await task
            for child in children.values():
                frames = action_frames(events, child, "alarm")
                assert len(frames) == (app.ALARM_REPEAT_COUNT if outcome == "complete" else 0)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("wire,action", (("p1", "massage"), ("p2", "diagnostic"), ("p3", "alarm")))
@pytest.mark.parametrize("cold", (False, True))
async def test_replacement_service_binds_inside_reused_worker_before_connect(
    hass, wire, action, cold
):
    child, old, old_client, device = await bed(hass, wire)
    events, history, selections = [], [], []
    if cold:
        old.on_disconnect()
        old_client.is_connected = False
        child._controller = child._client = None
        await child.async_prime_offline_controller()
        assert child.capability_controller is not None

    async def hook(_child, _controller, _client, _frame):
        selected = runtime.current_selection()
        assert isinstance(selected, Selection) and selected.active
        selected.check(_controller)
        selections.append(selected)

    async def connect(reset_timer=True):
        if not child.is_connected:
            await bind(child, wire, history, events, hook)
        return True

    if not cold:

        async def write(_char, frame, **_kwargs):
            await hook(child, old, old_client, frame)

        old_client.write_gatt_char.side_effect = write

    await async_register_services(hass)
    with (
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
        patch.object(child, "_async_connect_locked", AsyncMock(side_effect=connect)),
        patch.object(child, "_async_refresh_controller_auth", AsyncMock()),
    ):
        prior, retiring, release = await prior_worker(child)
        if action == "alarm":
            task = asyncio.create_task(call_app(hass, device.id, "alarm"))
        elif action == "massage":
            task = asyncio.create_task(call_app(hass, device.id, "massage"))
        else:
            task = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "betterliving2_diagnostic_action",
                    {"device_id": [device.id], "action": "refresh_massage"},
                    blocking=True,
                )
            )
        try:
            await observed(retiring, task)
            release.set()
            await task
            await prior.future
            assert selections and all(selected is selections[0] for selected in selections)
            assert not selections[0].active
            assert runtime.current_selection() is None
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await child.async_shutdown()


async def test_reused_native_both_workers_recheck_peer_at_each_actual_write(hass):
    events, children, changed = [], {}, []

    async def hook(child, controller, _client, frame):
        selected = runtime.current_selection()
        assert isinstance(selected, Selection)
        if frame[:2] != alarm_prefix(controller.wire):
            return
        if changed:
            pytest.fail("An alarm write passed a changed physical cohort")
        peer = next(other for other in children.values() if other is not child)
        changed.append(child)
        peer.entry.persist_data(
            {
                **peer.entry.data,
                "product_type": "3" if peer.entry.data["product_type"] == "2" else "2",
            },
            keys={"product_type"},
        )

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", "both", events, hook
        )
        priors = [await prior_worker(child) for child in children.values()]
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            for _, retiring, _ in priors:
                await observed(retiring, task)
            for _, _, release in priors:
                release.set()
            with pytest.raises(PairedSideError):
                await task
            assert len(changed) == 1
            assert (
                sum(len(action_frames(events, child, "alarm")) for child in children.values()) == 1
            )
        finally:
            for _, _, release in priors:
                release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("paired", (False, True))
async def test_p3_cancel_requires_explicit_time_before_any_target_mutates(hass, paired):
    events = []
    with ExitStack() as stack:
        if paired:
            parent, children, device, _ = await native_pair(
                hass, stack, "alarm", "concurrent", "both", events
            )
            shutdown = parent.async_shutdown
            clients = [child.client for child in children.values()]
        else:
            child, _, client, entry = await bed(hass, "p3")
            device, clients = entry.id, [client]
            shutdown = child.async_shutdown
        await async_register_services(hass)
        try:
            with pytest.raises(ServiceValidationError) as error:
                await hass.services.async_call(
                    DOMAIN, "set_alarm", {"device_id": [device], "enabled": False}, blocking=True
                )
            assert error.value.translation_key == "alarm_time_required"
            assert all(not writes(client) for client in clients)
            assert not events
        finally:
            await shutdown()


async def test_p3_cancel_keeps_explicit_midnight_and_selected_fields(hass):
    child, controller, client, device = await bed(hass, "p3")
    await async_register_services(hass)
    try:
        with ready(child), virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
            expected = controller.prepare_alarm(
                enabled=False, hour=0, minute=0, weekdays=frozenset({0}), action="memory_2"
            ).frame
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": [device.id],
                    "enabled": False,
                    "time": "00:00",
                    "weekdays": ["sunday"],
                    "wake_action": "memory_2",
                },
                blocking=True,
            )
        assert writes(client)[:2] == [expected] * app.ALARM_REPEAT_COUNT
    finally:
        await child.async_shutdown()


async def test_retired_selection_cannot_be_reused_by_another_admitted_operation(hass):
    child, controller, client, device = await bed(hass, "p2")
    selections = []

    async def record(_char, _frame, **_kwargs):
        selections.append(runtime.current_selection())

    client.write_gatt_char.side_effect = record
    await async_register_services(hass)
    try:
        with ready(child), virtual_clock():
            await hass.services.async_call(
                DOMAIN,
                "betterliving2_diagnostic_action",
                {"device_id": [device.id], "action": "refresh_massage"},
                blocking=True,
            )
            selected = selections[0]
            assert isinstance(selected, Selection) and not selected.active
            before = list(writes(client))

            async def stale(_controller):
                with selected.bind_operation():
                    selected.start(_controller)
                    await _controller.query_massage()

            with pytest.raises(ServiceValidationError, match="retired"):
                await child.async_execute_controller_command(stale)
            assert writes(client) == before
            assert runtime.current_selection() is None
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("skip_callback", (False, True))
@pytest.mark.parametrize("initial", ("right", "offline"))
async def test_side_stop_retires_concurrent_gate_even_without_peer_callback(
    hass, initial, skip_callback
):
    entered, release = asyncio.Event(), asyncio.Event()
    events, children, began = [], {}, []
    blocked = False

    async def hook(child, _controller, _client, _frame):
        nonlocal blocked
        if not skip_callback and child is children.get("left") and not blocked:
            blocked = True
            entered.set()
            await release.wait()

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", initial, events, hook
        )
        left = children["left"]
        if skip_callback:
            original_prepare = left.async_prepare_command_operation

            async def prepare_without_callback(operation, **kwargs):
                async def cancelled_before_callback():
                    context = current_command_context()
                    assert context is not None
                    entered.set()
                    await context.cancel_event.wait()

                return await original_prepare(cancelled_before_callback, **kwargs)

            stack.enter_context(
                patch.object(left, "async_prepare_command_operation", prepare_without_callback)
            )
        original_begin = Selection.begin

        def track_begin(selection, child):
            began.append(child)
            original_begin(selection, child)

        stack.enter_context(patch.object(Selection, "begin", track_begin))
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered, task)
            await asyncio.sleep(app.SETUP_QUERY_DELAY_MS / 1000 + 0.1)
            assert not task.done()
            if skip_callback:
                assert left not in began
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            async with asyncio.timeout(15):
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": "left"}, blocking=True
                )
                release.set()
                await task
            assert not any(action_frames(events, child, "alarm") for child in children.values())
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("initial", ("both", "offline"))
async def test_late_prepared_peer_does_not_expand_side_stop(hass, initial):
    entered, release = asyncio.Event(), asyncio.Event()
    events = []

    async def delayed_auth():
        entered.set()
        await release.wait()

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", initial, events
        )
        right = children["right"]
        stack.enter_context(patch.object(right, "_async_refresh_controller_auth", delayed_auth))
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered, task)
            await asyncio.sleep(app.SETUP_QUERY_DELAY_MS / 1000 + 0.1)
            assert not task.done()
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            async with asyncio.timeout(15):
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": "left"}, blocking=True
                )
                release.set()
                await task
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            assert not any(
                address == right.address and frame == app.command("P3", 0)
                for address, _client, frame in events
            )
            assert (
                sum(
                    address == children["left"].address and frame == app.command("P1", 0)
                    for address, _client, frame in events
                )
                == 2
            )
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("initial", ("left", "offline"))
@pytest.mark.parametrize("startup_error", (False, True))
async def test_side_stop_during_peer_startup_query_keeps_failure_scope(
    hass, initial, startup_error
):
    entered, release = asyncio.Event(), asyncio.Event()
    events, controllers = [], []
    original_query = runtime.BetterLiving2Controller.query_alarm

    async def delayed_query(controller):
        if controller._coordinator is children["right"]:
            controllers.append(controller)
            entered.set()
            await release.wait()
            if startup_error:
                raise BleakError("independent startup query failure")
        await original_query(controller)

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", initial, events
        )
        stack.enter_context(
            patch.object(runtime.BetterLiving2Controller, "query_alarm", delayed_query)
        )
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered, task)
            assert not task.done()
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            async with asyncio.timeout(15):
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": "left"}, blocking=True
                )
                release.set()
                if startup_error:
                    with pytest.raises(PairedSideError) as error:
                        await task
                    assert isinstance(error.value.side_errors["right"], BleakError)
                else:
                    await task
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            right_stop = app.command("P3", 0)
            assert sum(
                address == children["right"].address and frame == right_stop
                for address, _client, frame in events
            ) == (2 if startup_error else 0)
            assert len(controllers) == 1
            controller = controllers[0]
            assert not controller._operation_lock.locked()
            assert not controller._wire_lock.locked()
            assert controller._active_cancel is None
            assert runtime.current_selection() is None
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("outcome", ("stop", "validation_error"))
async def test_native_cancelled_connect_cleanup_precedes_peer_binding(hass, outcome):
    left_entered, right_entered = asyncio.Event(), asyncio.Event()
    left_release, right_release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    events, clients, cleanup = [], {}, []
    original_query = runtime.BetterLiving2Controller.query_alarm
    original_disconnect = AdjustableBedCoordinator._async_disconnect_locked
    left_paused = False
    source = "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")

    async def query(controller):
        if controller._coordinator is children["right"] and not right_release.is_set():
            right_entered.set()
            await right_release.wait()
            if outcome == "validation_error":
                right = children["right"]
                right.entry.persist_data(
                    {**right.entry.data, "product_type": "2"}, keys={"product_type"}
                )
                await right._async_disconnect_locked("independent_profile_change")
        await original_query(controller)

    async def disconnect(child, reason="intentional"):
        selected = runtime.current_selection()
        result = await original_disconnect(child, reason)
        if child is children["right"] and not cleaned.is_set():
            assert isinstance(selected, Selection)
            cleanup.append((reason, selected.invalid, child.client, child._controller))
            cleaned.set()
        return result

    async def select(_hass, address, *_args, **_kwargs):
        return AdapterSelectionResult(BLEDevice(address, "Bed", {}), source, -50, True, [source])

    async def establish(_class, device, *_args, **_kwargs):
        nonlocal left_paused
        child = next(child for child in children.values() if child.address == device.address)
        if child is children["left"] and not left_paused:
            left_paused = True
            left_entered.set()
            await left_release.wait()
        client = client_for(child.entry.data["protocol_variant"].upper())
        client.address = child.address
        clients.setdefault(child.address, []).append(client)

        async def write(_char, frame, **_kwargs):
            events.append((child.address, client, bytes(frame)))

        async def close():
            events.append((child.address, client, "disconnect"))
            client.is_connected = False
            return True

        client.write_gatt_char.side_effect = write
        client.disconnect.side_effect = close
        return client

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", "offline", events
        )
        for child in children.values():
            child._max_retries = 1
            stack.enter_context(
                patch.object(
                    child,
                    "_async_connect_locked",
                    AdjustableBedCoordinator._async_connect_locked.__get__(child),
                )
            )
        for name, value in (
            ("select_adapter", AsyncMock(side_effect=select)),
            ("establish_connection", AsyncMock(side_effect=establish)),
            ("async_connection_paths", lambda *_: ()),
            ("client_source", lambda *_: source),
            ("async_path_for_source", lambda *_, **_kwargs: path),
            ("close_stale_connections_by_address", AsyncMock()),
            ("discover_services", AsyncMock(return_value=True)),
            ("read_ble_device_info", AsyncMock(return_value=(None, None))),
            ("connection_reachability", lambda *_: None),
        ):
            stack.enter_context(patch.object(connection, name, value))
        stack.enter_context(
            patch.object(connection.bluetooth, "async_last_service_info", return_value=None)
        )
        stack.enter_context(patch.object(runtime.BetterLiving2Controller, "query_alarm", query))
        stack.enter_context(
            patch.object(AdjustableBedCoordinator, "_async_disconnect_locked", disconnect)
        )
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        stopping = None
        try:
            await observed(left_entered, task)
            await observed(right_entered, task)
            left, right = children["left"], children["right"]
            selected = right._command_scheduler._active.context
            assert selected.scheduler_token is right._command_scheduler.token
            if outcome == "stop":
                context = left._command_scheduler._active.context
                stopping = asyncio.create_task(
                    hass.services.async_call(
                        DOMAIN, "stop_all", {"device_id": [device], "side": "left"}, blocking=True
                    )
                )
                await observed(context.cancel_event, stopping)
                assert not stopping.done() and left._command_lock.locked()
            right_release.set()
            await observed(cleaned, task)
            assert not left_release.is_set()
            assert cleanup[0][2:] == (None, None)
            assert not clients[right.address][0].is_connected
            clients[right.address][0].stop_notify.assert_awaited_once()
            left_release.set()
            async with asyncio.timeout(15):
                if outcome == "stop":
                    await task
                    assert stopping is not None
                    await stopping
                else:
                    with pytest.raises(PairedSideError):
                        await task
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            if outcome == "stop":
                assert cleanup[0][:2] == ("connect_cancelled", False)
                assert right.stop_epoch == 0
                assert not any(
                    address == right.address and frame == app.command("P3", 0)
                    for address, _client, frame in events
                )
                assert (
                    sum(
                        address == left.address and frame == app.command("P1", 0)
                        for address, _client, frame in events
                    )
                    == 2
                )
            else:
                assert cleanup[0][:2] == ("independent_profile_change", True)
                assert left.stop_epoch > 0 and right.stop_epoch > 0
        finally:
            left_release.set()
            right_release.set()
            for pending in (task, stopping):
                if pending is not None and not pending.done():
                    pending.cancel()
            await asyncio.gather(
                *(pending for pending in (task, stopping) if pending is not None),
                return_exceptions=True,
            )
            await parent.async_shutdown()
