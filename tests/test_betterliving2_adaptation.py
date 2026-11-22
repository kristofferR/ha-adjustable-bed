"""Admitted alarm cohorts and reused scheduler workers keep their app ownership."""

import asyncio
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
)
from custom_components.adjustable_bed import (
    coordinator_connection as connection,
)
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.beds.keeson import betterliving2 as runtime
from custom_components.adjustable_bed.beds.keeson import (
    betterliving2_selection as selection_runtime,
)
from custom_components.adjustable_bed.beds.keeson.betterliving2_selection import Selection
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.command_scheduler import CommandKind, current_command_context
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.errors import invalid
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.profiles import betterliving2 as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_betterliving2_holds_and_sides import (
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


@pytest.mark.parametrize(
    "stopped_side,outcome",
    (
        ("left", "stop"),
        ("right", "stop"),
        ("left", "profile"),
        ("right", "profile"),
        ("left", "stop_window"),
    ),
)
async def test_dispatched_alarm_scopes_stop_and_completes_peer_state(hass, stopped_side, outcome):
    entered = {side: asyncio.Event() for side in ("left", "right")}
    release = {side: asyncio.Event() for side in ("left", "right")}
    peer_side = "right" if stopped_side == "left" else "left"
    events, selections = [], []
    original_sync = runtime.BetterLiving2Controller.sync_clock

    async def sync(controller):
        side = next(side for side, child in children.items() if child is controller._coordinator)
        if side == peer_side or outcome == "stop_window":
            selected = runtime.current_selection()
            assert isinstance(selected, Selection)
            selections.append(selected)
            entered[side].set()
            await release[side].wait()
        await original_sync(controller)

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", "both", events
        )
        stack.enter_context(patch.object(runtime.BetterLiving2Controller, "sync_clock", sync))
        if outcome == "stop_window":
            original_stop = parent._stop_children

            async def stop_before_cancel(targets):
                for event in release.values():
                    event.set()
                await asyncio.sleep(0)
                return await original_stop(targets)

            stack.enter_context(patch.object(parent, "_stop_children", stop_before_cancel))
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered[peer_side], task)
            if outcome == "stop_window":
                await observed(entered[stopped_side], task)
            peer, target = children[peer_side], children[stopped_side]
            controller = peer._controller
            assert isinstance(controller, runtime.BetterLiving2Controller)
            assert len(action_frames(events, peer, "alarm")) == 2
            expected = controller.prepare_alarm(
                enabled=True, hour=7, minute=30, weekdays=frozenset({1}), action="memory_1"
            ).selected
            before = len(events)
            if outcome == "profile":
                target.entry.persist_data(
                    {**target.entry.data, "product_type": "3" if stopped_side == "left" else "2"},
                    keys={"product_type"},
                )
                release[peer_side].set()
                with pytest.raises(PairedSideError):
                    await task
                assert controller._saved != expected
                assert peer.stop_epoch > 0
            else:
                async with asyncio.timeout(15):
                    await hass.services.async_call(
                        DOMAIN,
                        "stop_all",
                        {"device_id": [device], "side": stopped_side},
                        blocking=True,
                    )
                    release[peer_side].set()
                    await task
                calendar = app.Calendar.from_datetime(NOW)
                tail = [
                    frame
                    for address, _client, frame in events[before:]
                    if address == peer.address and isinstance(frame, bytes)
                ]
                assert tail == [
                    app.current_time(controller.wire, calendar),
                    app.alarm_query(controller.wire, calendar),
                ]
                assert controller._saved == controller._view == expected
                assert peer.controller_state[runtime.HOUR] == 7
                assert peer.controller_state[runtime.MINUTE] == 30
                assert peer.stop_epoch == 0
                assert not any(
                    address == peer.address and frame == app.command(controller.wire, 0)
                    for address, _client, frame in events
                )
                target_wire = target.entry.data["protocol_variant"].upper()
                assert (
                    sum(
                        address == target.address and frame == app.command(target_wire, 0)
                        for address, _client, frame in events
                    )
                    == 2
                )
                assert all(not selection.invalid for selection in selections)
        finally:
            for event in release.values():
                event.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("stopped_side", ("left", "right"))
async def test_pre_dispatch_generation_yield_is_quiet_before_child_cancel(hass, stopped_side):
    entered, release = asyncio.Event(), asyncio.Event()
    peer_side = "right" if stopped_side == "left" else "left"
    events, windows = [], []
    original_query = runtime.BetterLiving2Controller.query_alarm
    original_check = Selection.check

    async def query(controller):
        if controller._coordinator is children[peer_side] and not release.is_set():
            entered.set()
            await release.wait()
        await original_query(controller)

    def check(selection, controller=None):
        if controller is not None and controller._coordinator is children[peer_side]:
            owner = selection.owners[id(children[stopped_side])]
            baseline = owner.batch.admission.expected_pair_generations[stopped_side][0] + 1
            generation = parent.pair_cancel_generation(
                stopped_side, owner.batch.admission.resources
            )[0]
            if (
                generation > baseline
                and owner.context is not None
                and not owner.context.cancel_event.is_set()
            ):
                windows.append(generation)
        return original_check(selection, controller)

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", stopped_side, events
        )
        target = children[stopped_side]
        original_stop = target.async_stop_command

        async def stop_child():
            release.set()
            await asyncio.sleep(0)
            return await original_stop()

        stack.enter_context(patch.object(target, "async_stop_command", stop_child))
        stack.enter_context(patch.object(runtime.BetterLiving2Controller, "query_alarm", query))
        stack.enter_context(patch.object(Selection, "check", check))
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered, task)
            async with asyncio.timeout(15):
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": stopped_side}, blocking=True
                )
                await task
            assert windows, (
                "The real guard must run after the pair bump but before child cancellation"
            )
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            peer = children[peer_side]
            assert peer.stop_epoch == 0
            assert not any(
                address == peer.address
                and frame == app.command(peer.entry.data["protocol_variant"].upper(), 0)
                for address, _client, frame in events
            )
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("profile_drift", (False, True))
async def test_sequential_native_cold_start_retires_offline_peer_stop(hass, profile_drift):
    entered, release = asyncio.Event(), asyncio.Event()
    events, clients, selections, guard_errors = [], [], [], []
    original_query = runtime.BetterLiving2Controller.query_alarm
    source = "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")

    async def query(controller):
        if controller._coordinator is children["left"] and not release.is_set():
            assert current_command_context() is None
            selected = runtime.current_selection()
            assert isinstance(selected, Selection)
            selections.append(selected)
            entered.set()
            await release.wait()
        try:
            await original_query(controller)
        except ServiceValidationError as err:
            guard_errors.append((err.translation_key, err.translation_placeholders))
            raise

    async def select(_hass, address, *_args, **_kwargs):
        return AdapterSelectionResult(BLEDevice(address, "Bed", {}), source, -50, True, [source])

    async def establish(_class, device, *_args, **_kwargs):
        child = next(child for child in children.values() if child.address == device.address)
        client = client_for(child.entry.data["protocol_variant"].upper())
        client.address = child.address
        clients.append(client)

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
            hass, stack, "alarm", "sequential", "offline", events
        )
        for child in children.values():
            child._max_retries = 2
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
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(entered, task)
            assert children["left"].is_connected and not children["right"].is_connected
            await hass.services.async_call(
                DOMAIN, "stop_all", {"device_id": [device], "side": "right"}, blocking=True
            )
            if profile_drift:
                peer = children["right"]
                peer.entry.persist_data(
                    {**peer.entry.data, "product_type": "2"}, keys={"product_type"}
                )
            release.set()
            async with asyncio.timeout(15):
                if profile_drift:
                    with pytest.raises(PairedSideError):
                        await task
                else:
                    await task
            if not profile_drift:
                assert len(clients) == 1, (
                    "Expected cancellation must not retry the native connection"
                )
                clients[0].stop_notify.assert_awaited_once()
            assert guard_errors == (
                [
                    (
                        "betterliving2_selection_changed",
                        {"reason": "BetterLiving2 entry/roster changed"},
                    )
                ]
                if profile_drift
                else []
            )
            assert all(not client.is_connected for client in clients)
            for client in clients:
                client.disconnect.assert_awaited_once()
            assert all(child.client is None for child in children.values())
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            assert [frame for _address, _client, frame in events if isinstance(frame, bytes)] == [
                app.current_time("P1", app.Calendar.from_datetime(NOW))
            ]
            assert not selections[0].active
            if not profile_drift:
                assert not selections[0].invalid
            assert not parent._topology.command_lock.locked()
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@contextmanager
def native_startup_transport(
    stack, children, events, *, established=None, notifying=None, stopping_notify=None, closing=None
):
    """Fake only BLE boundaries, retaining actual native connect and cleanup."""
    clients = []
    source = "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")

    async def select(_hass, address, *_args, **_kwargs):
        return AdapterSelectionResult(BLEDevice(address, "Bed", {}), source, -50, True, [source])

    async def establish(_class, device, *_args, **_kwargs):
        child = next(child for child in children.values() if child.address == device.address)
        client = client_for(child.entry.data["protocol_variant"].upper())
        client.address = child.address
        clients.append((child, client))

        async def write(_char, frame, **_kwargs):
            events.append((child.address, client, bytes(frame)))

        async def close():
            if closing is not None:
                await closing(child, client)
            events.append((child.address, client, "disconnect"))
            client.is_connected = False
            return True

        async def notify(*_args, **_kwargs):
            if notifying is not None:
                await notifying(child, client)

        client.write_gatt_char.side_effect = write
        client.disconnect.side_effect = close
        client.start_notify.side_effect = notify
        if stopping_notify is not None:

            async def stop_notify(*_args, **_kwargs):
                assert stopping_notify is not None
                await stopping_notify(child, client)

            client.stop_notify.side_effect = stop_notify
        if established is not None:
            await established(child, client)
        return client

    for child in children.values():
        child._max_retries = 2
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
    yield clients


@pytest.mark.parametrize("startup_side", ("left", "right"), ids=("first", "later"))
async def test_sequential_cancelled_startup_does_not_poison_next_connection(hass, startup_side):
    entered, release = asyncio.Event(), asyncio.Event()
    events = []
    original_query = runtime.BetterLiving2Controller.query_alarm

    async def query(controller):
        if controller._coordinator is children[startup_side] and not release.is_set():
            assert current_command_context() is None
            entered.set()
            await release.wait()
        await original_query(controller)

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )
        with native_startup_transport(stack, children, events) as clients:
            stack.enter_context(patch.object(runtime.BetterLiving2Controller, "query_alarm", query))
            task = asyncio.create_task(call_app(hass, device, "alarm"))
            try:
                await observed(entered, task)
                stopped = "right" if startup_side == "left" else "left"
                assert not children[stopped].is_connected
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": stopped}, blocking=True
                )
                release.set()
                async with asyncio.timeout(15):
                    await task
                child = children[startup_side]
                assert not child.cancel_command.is_set(), (
                    "A retired startup must not cancel a later connection"
                )
                assert len(clients) == (1 if startup_side == "left" else 2)
                assert not action_frames(events, child, "alarm")
                assert not any(
                    frame == app.command(children[side].entry.data["protocol_variant"].upper(), 0)
                    for side in children
                    for address, _client, frame in events
                    if address == children[side].address and isinstance(frame, bytes)
                )
                before = len(events)
                assert await child.async_connect()
                wire = child.entry.data["protocol_variant"].upper()
                assert [
                    frame
                    for address, _client, frame in events[before:]
                    if address == child.address and isinstance(frame, bytes)
                ] == [
                    app.current_time(wire, app.Calendar.from_datetime(NOW)),
                    app.alarm_query(wire, app.Calendar.from_datetime(NOW)),
                ]
                assert len(action_frames(events[:before], children["left"], "alarm")) == (
                    0 if startup_side == "left" else 2
                )
                await child.async_disconnect()
                for _owner, client in clients:
                    assert not client.is_connected
                    client.disconnect.assert_awaited_once()
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await parent.async_shutdown()


async def test_sequential_stop_between_outer_and_inner_write_guard_has_no_query(hass):
    events, stop_tasks = [], []
    original_query = runtime.BetterLiving2Controller.query_alarm
    original_check = Selection.check
    original_create_task = asyncio.create_task
    armed = False
    guards = 0

    def create_task(coro, **kwargs):
        if (
            armed
            and stop_tasks
            and getattr(getattr(coro, "cr_code", None), "co_qualname", "")
            == "BetterLiving2Controller._send.<locals>.write"
        ):

            async def after_stop():
                try:
                    await stop_tasks[0]
                    return await coro
                finally:
                    coro.close()

            return original_create_task(after_stop(), **kwargs)
        return original_create_task(coro, **kwargs)

    async def query(controller):
        nonlocal armed
        if controller._coordinator is children["left"]:
            armed = True
        await original_query(controller)

    def check(selection, controller=None):
        nonlocal guards
        if armed and controller is not None and controller._coordinator is children["left"]:
            guards += 1
            if guards == 1:
                original_check(selection, controller)
                stop_tasks.append(
                    asyncio.create_task(
                        hass.services.async_call(
                            DOMAIN,
                            "stop_all",
                            {"device_id": [device], "side": "right"},
                            blocking=True,
                        )
                    )
                )
                return
            if guards == 2:
                assert selection._cohort_cancelled(selection.owners[id(children["left"])].batch)
                assert (
                    not controller._active_cancel.is_set()
                    and not children["left"].cancel_command.is_set()
                )
        original_check(selection, controller)

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )
        with native_startup_transport(stack, children, events):
            stack.enter_context(patch.object(runtime.BetterLiving2Controller, "query_alarm", query))
            stack.enter_context(patch.object(Selection, "check", check))
            stack.enter_context(patch.object(asyncio, "create_task", create_task))
            try:
                async with asyncio.timeout(15):
                    await call_app(hass, device, "alarm")
                    await asyncio.gather(*stop_tasks)
                assert guards >= 2
                assert [
                    frame for _address, _client, frame in events if isinstance(frame, bytes)
                ] == [app.current_time("P1", app.Calendar.from_datetime(NOW))]
                assert all(child.client is None for child in children.values())
            finally:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
                await parent.async_shutdown()


@pytest.mark.parametrize("drift", ("profile", "session"))
async def test_cancelled_startup_revalidates_drift_during_notification_setup(hass, drift):
    connecting, bind = asyncio.Event(), asyncio.Event()
    notifying, release = asyncio.Event(), asyncio.Event()
    events = []

    async def established(child, _client):
        if child is children["left"] and not bind.is_set():
            connecting.set()
            await bind.wait()

    async def notify(child, _client):
        if child is children["left"] and not release.is_set():
            notifying.set()
            await release.wait()

    with ExitStack() as stack, virtual_clock():
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )
        with native_startup_transport(
            stack, children, events, established=established, notifying=notify
        ) as clients:
            task = asyncio.create_task(call_app(hass, device, "alarm"))
            try:
                await observed(connecting, task)
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": "right"}, blocking=True
                )
                bind.set()
                await observed(notifying, task)
                peer = children["right"]
                if drift == "profile":
                    peer.entry.persist_data(
                        {**peer.entry.data, "product_type": "2"}, keys={"product_type"}
                    )
                else:
                    peer._controller = runtime.BetterLiving2Controller(
                        peer, variant="p3", layout="3"
                    )
                release.set()
                async with asyncio.timeout(15):
                    with pytest.raises(PairedSideError):
                        await task
                failed = children["left"]._connection_attempt_details[0]
                assert failed["error_type"] == "ServiceValidationError"
                assert failed["error"] == str(
                    invalid(
                        "betterliving2_selection_changed",
                        reason="BetterLiving2 entry/roster changed"
                        if drift == "profile"
                        else "BetterLiving2 captured session changed",
                    )
                )
                assert not any(isinstance(frame, bytes) for _address, _client, frame in events)
                assert all(not client.is_connected for _owner, client in clients)
            finally:
                bind.set()
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                peer = children["right"]
                if drift == "session":
                    peer._controller = None
                await parent.async_shutdown()


@pytest.mark.parametrize("drift", ("profile", "session"))
async def test_cancelled_startup_cleanup_surfaces_late_drift(hass, drift):
    connecting, bind = asyncio.Event(), asyncio.Event()
    prepared, release = asyncio.Event(), asyncio.Event()
    events, errors, selections = [], [], []
    original_after = runtime.BetterLiving2Controller.async_after_connect
    original_check = Selection._check

    async def established(child, _client):
        if child is children["left"] and not bind.is_set():
            connecting.set()
            await bind.wait()

    async def after(controller, session):
        await original_after(controller, session)
        if controller._coordinator is children["left"] and not release.is_set():
            selection = runtime.current_selection()
            assert isinstance(selection, Selection)
            selections.append(selection)
            prepared.set()
            await release.wait()

    def check(selection, *args, **kwargs):
        try:
            return original_check(selection, *args, **kwargs)
        except ServiceValidationError as err:
            if kwargs.get("releasing"):
                errors.append((err.translation_key, err.translation_placeholders))
            raise

    with ExitStack() as stack, virtual_clock():
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )
        with native_startup_transport(stack, children, events, established=established) as clients:
            stack.enter_context(
                patch.object(runtime.BetterLiving2Controller, "async_after_connect", after)
            )
            stack.enter_context(patch.object(Selection, "_check", check))
            task = asyncio.create_task(call_app(hass, device, "alarm"))
            try:
                await observed(connecting, task)
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": "right"}, blocking=True
                )
                bind.set()
                await observed(prepared, task)
                peer = children["right"]
                if drift == "profile":
                    peer.entry.persist_data(
                        {**peer.entry.data, "product_type": "2"}, keys={"product_type"}
                    )
                else:
                    peer._controller = runtime.BetterLiving2Controller(
                        peer, variant="p3", layout="3"
                    )
                release.set()
                async with asyncio.timeout(15):
                    with pytest.raises(ServiceValidationError, match="selection was retired"):
                        await task
                assert errors == [
                    (
                        "betterliving2_selection_changed",
                        {
                            "reason": "BetterLiving2 entry/roster changed"
                            if drift == "profile"
                            else "BetterLiving2 captured session changed"
                        },
                    )
                ]
                assert selections[0].invalid and not selections[0].active
                assert not any(isinstance(frame, bytes) for _address, _client, frame in events)
                for _owner, client in clients:
                    assert not client.is_connected
                    client.disconnect.assert_awaited_once()
                assert all(child.client is None for child in children.values())
            finally:
                bind.set()
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                if drift == "session":
                    children["right"]._controller = None
                await parent.async_shutdown()


async def test_sequential_peer_stop_before_later_worker_dispatch_is_quiet(hass):
    events, stops, released_marks = [], [], []
    with ExitStack() as stack, virtual_clock():
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )
        original_commit = children["right"].commit_prepared_command

        def commit(handle):
            assert not children["left"].is_connected
            released_marks.append((children["left"].stop_epoch, parent.stop_count("left")))
            stops.append(
                asyncio.create_task(
                    hass.services.async_call(
                        DOMAIN, "stop_all", {"device_id": [device], "side": "left"}, blocking=True
                    )
                )
            )
            original_commit(handle)

        with native_startup_transport(stack, children, events):
            stack.enter_context(patch.object(children["right"], "commit_prepared_command", commit))
            try:
                async with asyncio.timeout(15):
                    await call_app(hass, device, "alarm")
                    await asyncio.gather(*stops)
                assert stops
                assert len(released_marks) == 1
                epoch, count = released_marks[0]
                assert children["left"].stop_epoch == epoch
                assert parent.stop_count("left") == count + 1
                assert len(action_frames(events, children["left"], "alarm")) == 2
                assert not action_frames(events, children["right"], "alarm")
                assert not any(
                    frame == app.command("P3", 0)
                    for address, _client, frame in events
                    if address == children["right"].address
                )
            finally:
                await asyncio.gather(*stops, return_exceptions=True)
                await parent.async_shutdown()


@pytest.mark.parametrize("stopped_side", ("left", "right"))
async def test_concurrent_split_barrier_preserves_untouched_dispatch(hass, stopped_side):
    peer_side = "right" if stopped_side == "left" else "left"
    peer_waiting, left_writing, release_peer = asyncio.Event(), asyncio.Event(), asyncio.Event()
    events = []
    original_wait = selection_runtime._first_set

    async def wait(*signals):
        await original_wait(*signals)
        context = current_command_context()
        if (
            context is not None
            and context.scheduler_token is children[peer_side]._command_scheduler.token
        ):
            peer_waiting.set()
            await release_peer.wait()

    async def hook(child, controller, _client, frame):
        if (
            child is children[stopped_side]
            and frame.startswith(alarm_prefix(controller.wire))
            and not left_writing.is_set()
        ):
            left_writing.set()
            await asyncio.Event().wait()

    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "concurrent", "both", events, hook
        )
        stack.enter_context(patch.object(selection_runtime, "_first_set", wait))
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        try:
            await observed(peer_waiting, task)
            await observed(left_writing, task)
            peer = children[peer_side]
            controller = peer._controller
            assert isinstance(controller, runtime.BetterLiving2Controller)
            selection = peer._command_scheduler._active.context
            assert selection.scheduler_token is peer._command_scheduler.token
            # Both are ready, but the untouched worker has not left its gate.
            assert not action_frames(events, peer, "alarm")
            expected = controller.prepare_alarm(
                enabled=True, hour=7, minute=30, weekdays=frozenset({1}), action="memory_1"
            ).selected
            async with asyncio.timeout(15):
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": stopped_side}, blocking=True
                )
                release_peer.set()
                await task
            assert len(action_frames(events, peer, "alarm")) == 2
            frames = [
                frame
                for address, _client, frame in events
                if address == peer.address and isinstance(frame, bytes)
            ]
            assert frames[-2:] == [
                app.current_time(controller.wire, app.Calendar.from_datetime(NOW)),
                app.alarm_query(controller.wire, app.Calendar.from_datetime(NOW)),
            ]
            assert controller._saved == controller._view == expected
            assert peer.stop_epoch == 0
            assert app.command(controller.wire, 0) not in frames
        finally:
            release_peer.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await parent.async_shutdown()


@pytest.mark.parametrize("point", ("notify", "disconnect"))
@pytest.mark.parametrize("drift", ("profile", "session"))
async def test_completed_native_cleanup_rechecks_late_owner_drift(hass, point, drift):
    connecting, bind, cleaning, release = (asyncio.Event() for _ in range(4))
    events, selections = [], []

    async def established(child, _client):
        if child is children["left"] and not bind.is_set():
            connecting.set()
            await bind.wait()

    async def cleanup(child, client):
        if child is children["left"] and not release.is_set():
            selected = runtime.current_selection()
            assert isinstance(selected, Selection)
            assert selected.owners[id(child)].retiring == (child._controller, client)
            selections.append(selected)
            cleaning.set()
            await release.wait()

    with ExitStack() as stack, virtual_clock():
        parent, children, device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )
        with native_startup_transport(
            stack,
            children,
            events,
            established=established,
            stopping_notify=cleanup if point == "notify" else None,
            closing=cleanup if point == "disconnect" else None,
        ) as clients:
            task = asyncio.create_task(call_app(hass, device, "alarm"))
            try:
                await observed(connecting, task)
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [device], "side": "right"}, blocking=True
                )
                bind.set()
                await observed(cleaning, task)
                peer = children["right"]
                if drift == "profile":
                    peer.entry.persist_data(
                        {**peer.entry.data, "product_type": "2"}, keys={"product_type"}
                    )
                else:
                    peer._controller = runtime.BetterLiving2Controller(
                        peer, variant="p3", layout="3"
                    )
                release.set()
                async with asyncio.timeout(15):
                    with pytest.raises(
                        ServiceValidationError,
                        match="entry/roster changed"
                        if drift == "profile"
                        else "captured session changed",
                    ):
                        await task
                assert all(child.client is None for child in children.values())
                assert not any(isinstance(frame, bytes) for _address, _client, frame in events)
                for _owner, client in clients:
                    assert not client.is_connected
                    client.disconnect.assert_awaited_once()
                assert not selections[0].active
            finally:
                bind.set()
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                if drift == "session":
                    children["right"]._controller = None
                await parent.async_shutdown()


@pytest.mark.parametrize("drift", (None, "profile", "session"))
async def test_completed_pair_leaves_later_pair_stop_to_native_admission(hass, drift):
    cleaning, release = asyncio.Event(), asyncio.Event()
    events = []

    async def closing(child, _client):
        if child is first_children["right"] and not release.is_set():
            cleaning.set()
            await release.wait()

    with ExitStack() as stack, virtual_clock():
        first, first_children, first_device, _ = await native_pair(
            hass, stack, "alarm", "sequential", "offline", events
        )

        async def another_pair(name, address_segment):
            descriptors = [
                {**row, "address": row["address"].replace(":08:", address_segment)}
                for row in first.entry.data["pair_children"]
            ]
            entry = MockConfigEntry(
                domain=DOMAIN,
                title=name,
                version=5,
                data={
                    **first.entry.data,
                    "pair_id": name,
                    "pair_children": descriptors,
                    "pair_member_addresses": [row["address"] for row in descriptors],
                },
            )
            entry.add_to_hass(hass)
            entry.mock_state(hass, ConfigEntryState.LOADED)
            members = _build_paired_children(hass, entry)
            for child in members.values():
                await child.async_prime_offline_controller()
            parent = PairedBedCoordinator(hass, entry, members, connection_mode="sequential")
            hass.data[DOMAIN][entry.entry_id] = parent
            _async_ensure_paired_device_registry(hass, entry, parent)
            identifier = next(iter(parent.device_info["identifiers"]))
            device = dr.async_get(hass).async_get_device_by_identifier(identifier, entry.entry_id)
            assert device is not None
            return parent, members, device.id

        second, second_children, second_device = await another_pair("Second pair", ":09:")
        third, third_children, third_device = await another_pair("Third pair", ":0A:")
        children = {
            **first_children,
            **{f"second_{side}": child for side, child in second_children.items()},
            **{f"third_{side}": child for side, child in third_children.items()},
        }
        with native_startup_transport(stack, children, events, closing=closing) as clients:
            task = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "set_alarm",
                    {
                        "device_id": [first_device, second_device, third_device],
                        "enabled": True,
                        "time": "07:30",
                        "weekdays": ["monday"],
                        "wake_action": "memory_1",
                    },
                    blocking=True,
                )
            )
            try:
                await observed(cleaning, task)
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [second_device]}, blocking=True
                )
                peer = second_children["right"]
                if drift == "profile":
                    peer.entry.persist_data(
                        {**peer.entry.data, "product_type": "2"}, keys={"product_type"}
                    )
                elif drift == "session":
                    peer._controller = runtime.BetterLiving2Controller(
                        peer, variant="p3", layout="3"
                    )
                assert all(child.stop_epoch == 0 for child in second_children.values())
                release.set()
                async with asyncio.timeout(15):
                    if drift is None:
                        await task
                    else:
                        with pytest.raises(
                            ServiceValidationError,
                            match="entry/roster changed"
                            if drift == "profile"
                            else "captured session changed",
                        ):
                            await task
                assert all(
                    len(action_frames(events, child, "alarm")) == 2
                    for child in first_children.values()
                )
                assert all(child not in second_children.values() for child, _client in clients)
                assert all(
                    len(action_frames(events, child, "alarm")) == (2 if drift is None else 0)
                    for child in third_children.values()
                )
                if drift is not None:
                    assert all(child not in third_children.values() for child, _client in clients)
                assert all(child.client is None for child in children.values())
                for _child, client in clients:
                    client.disconnect.assert_awaited_once()
                    assert not client.is_connected
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                if drift == "session":
                    second_children["right"]._controller = None
                await first.async_shutdown()
                await second.async_shutdown()
                await third.async_shutdown()


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


@pytest.mark.parametrize("outcome", ("stop", "validation_error", "stop_generation_window"))
async def test_native_cancelled_connect_cleanup_precedes_peer_binding(hass, outcome):
    left_entered, right_entered = asyncio.Event(), asyncio.Event()
    left_release, right_release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    events, clients, cleanup = [], {}, []
    original_query = runtime.BetterLiving2Controller.query_alarm
    original_disconnect = AdjustableBedCoordinator._async_disconnect_locked
    left_paused = False
    source = "AA:BB:CC:DD:EE:FF"
    is_stop = outcome.startswith("stop")
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
        if outcome == "stop_generation_window":
            original_stop = parent._stop_children

            async def stop_before_child_cancel(targets):
                right_release.set()
                await observed(cleaned, task)
                context = children["left"]._command_scheduler._active.context
                assert not context.cancel_event.is_set()
                return await original_stop(targets)

            stack.enter_context(patch.object(parent, "_stop_children", stop_before_child_cancel))
        task = asyncio.create_task(call_app(hass, device, "alarm"))
        stopping = None
        try:
            await observed(left_entered, task)
            await observed(right_entered, task)
            left, right = children["left"], children["right"]
            selected = right._command_scheduler._active.context
            assert selected.scheduler_token is right._command_scheduler.token
            if is_stop:
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
                if is_stop:
                    await task
                    assert stopping is not None
                    await stopping
                else:
                    with pytest.raises(PairedSideError):
                        await task
            assert not any(action_frames(events, child, "alarm") for child in children.values())
            if is_stop:
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
