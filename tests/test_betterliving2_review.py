"""Source-prepared sole-review corrections; public HA paths, virtual BLE only."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
)
from custom_components.adjustable_bed.beds.keeson import betterliving2 as runtime
from custom_components.adjustable_bed.beds.keeson import betterliving2_services as actions
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.profiles import betterliving2 as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_betterliving2_runtime import bed, client_for, data, writes

NOW = datetime(2026, 7, 14, 12, 30, 45)
PACKETS = {"p2": "ed8003071ebe11", "p3": "a50c0000be05071e0001"}


@contextmanager
def ready(child):
    with (
        patch.object(child, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(child, "_async_refresh_controller_auth", AsyncMock()),
    ):
        yield


async def observed(event, public_task):
    """Fail on early public completion, with a virtual-only fixture bound."""
    waiter = asyncio.create_task(event.wait())
    try:
        async with asyncio.timeout(15):
            done, _ = await asyncio.wait((waiter, public_task), return_when=asyncio.FIRST_COMPLETED)
            if public_task in done:
                await public_task
                assert event.is_set(), "Public operation completed before expected protocol event"
            await waiter
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


async def hold(controller):
    assert isinstance(controller, runtime.BetterLiving2Controller)
    await controller.hold_control("back_up", 100)


@pytest.mark.parametrize("latency", (0.4, None), ids=("400ms", "stall"))
async def test_public_100ms_hold_bounds_first_write_and_drains_exact_release(hass, latency):
    child, controller, client, _ = await bed(hass)
    events, contexts = [], []

    async def admitted(controller):
        context = current_command_context()
        assert context is not None
        contexts.append(context.cancel_event)
        await hold(controller)

    try:
        with ready(child), virtual_clock() as clock:

            async def write(_char, frame, **_kwargs):
                events.append((round(clock.now, 6), bytes(frame)))
                if frame != app.command("P1", 0):
                    if latency is None:
                        await asyncio.sleep(30)
                    else:
                        await asyncio.sleep(latency)

            client.write_gatt_char.side_effect = write
            await child.async_execute_controller_command(admitted)
            assert events == [
                (0.0, app.command("P1", 1)),
                (0.1, app.command("P1", 0)),
                (0.2, app.command("P1", 0)),
            ]
            assert contexts and not contexts[0].is_set()
            assert not controller._operation_lock.locked() and not controller._wire_lock.locked()
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("latency", (0.4, None), ids=("400ms", "stall"))
async def test_public_hold_deadline_interrupts_repeated_write(hass, latency):
    child, controller, client, _ = await bed(hass)
    events = []

    async def repeated(controller):
        assert isinstance(controller, runtime.BetterLiving2Controller)
        await controller.hold_control("back_up", 250)

    try:
        with ready(child), virtual_clock() as clock:

            async def write(_char, frame, **_kwargs):
                events.append((round(clock.now, 6), bytes(frame)))
                if frame != app.command("P1", 0) and len(events) > 1:
                    if latency is None:
                        await asyncio.sleep(30)
                    else:
                        await asyncio.sleep(latency)

            client.write_gatt_char.side_effect = write
            await child.async_execute_controller_command(repeated)
            assert events == [
                (0.0, app.command("P1", 1)),
                (0.1, app.command("P1", 1)),
                (0.25, app.command("P1", 0)),
                (0.35, app.command("P1", 0)),
            ]
            assert not controller._operation_lock.locked() and not controller._wire_lock.locked()
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("action", ("alarm", "massage"))
async def test_native_parent_both_invalid_later_profile_has_no_mutation(hass, action):
    events = []
    with ExitStack() as stack, virtual_clock():
        parent, children, device, _ = await native_pair(
            hass,
            stack,
            action,
            "sequential",
            "right",
            events,
        )
        try:
            right = children["right"]
            right.entry.persist_data(
                {**right.entry.data, "protocol_variant": "auto"},
                keys={"protocol_variant"},
            )
            with pytest.raises(ServiceValidationError):
                await call_app(hass, device, action)
            assert events == []
        finally:
            await parent.async_shutdown()


@pytest.mark.parametrize("wire", ("p2", "p3"))
@pytest.mark.parametrize("ending", ("stop", "cancel", "stale"))
async def test_public_startup_reply_cleanup_preserves_external_stop_and_stale_fences(
    hass, wire, ending
):
    child, old, old_client, _ = await bed(hass, wire)
    old.on_disconnect()
    old_client.is_connected = False
    child._controller = child._client = None
    history, events, contexts, callbacks = [], [], [], []
    stop_entered, release_stop = asyncio.Event(), asyncio.Event()

    async def hook(_child, controller, client, frame):
        if frame == app.alarm_query(wire.upper(), app.Calendar.from_datetime(NOW)):
            context = current_command_context()
            assert context is not None
            contexts.append(context.cancel_event)
            sender, callback = client.start_notify.call_args.args
            callbacks.append((sender, callback))
            callback(sender, bytearray.fromhex(PACKETS[wire]))
            await asyncio.sleep(30)
        elif frame == app.command(wire.upper(), 0):
            stop_entered.set()
            async with asyncio.timeout(15):
                await release_stop.wait()

    async def connect(reset_timer=True):
        if not child.is_connected:
            await bind(child, wire, history, events, hook)
        return True

    async def user_action(controller):
        assert isinstance(controller, runtime.BetterLiving2Controller)
        await controller.lights_toggle()

    try:
        with (
            patch.object(child, "_async_connect_locked", AsyncMock(side_effect=connect)),
            patch.object(child, "_async_refresh_controller_auth", AsyncMock()),
            virtual_clock(),
            patch.object(runtime.dt_util, "now", return_value=NOW),
        ):
            user = asyncio.create_task(child.async_execute_controller_command(user_action))
            await observed(stop_entered, user)
            notification_controller, notification_client = history[-1][1:]
            other = replacement = None
            if ending == "stop":
                other = asyncio.create_task(child.async_stop_command())
                await asyncio.sleep(0)
            elif ending == "cancel":
                user.cancel()
                await asyncio.sleep(0)
                user.cancel()
            else:
                notification_controller.on_disconnect()
                notification_client.is_connected = False
                replacement = client_for(wire.upper())
                child._client = replacement
                child._controller = await create_controller(
                    child, "betterliving2", wire, replacement
                )
                await child._controller.async_discover_capabilities()
            release_stop.set()
            outcomes = await asyncio.gather(
                user, *([other] if other is not None else []), return_exceptions=True
            )
            assert app.command(wire.upper(), app.STEP_LIGHT) not in [
                frame for _, _, frame in events if isinstance(frame, bytes)
            ]
            stops = [frame for _, _, frame in events if frame == app.command(wire.upper(), 0)]
            assert len(stops) == (3 if ending == "stop" else 1)
            if ending == "stale":
                assert replacement is not None
                sender, callback = callbacks[0]
                callback(sender, bytearray.fromhex(PACKETS[wire]))
                assert child.controller_state.get(runtime.ALARM) is None
                assert not writes(replacement)
                assert any(isinstance(outcome, ConnectionError) for outcome in outcomes)
            else:
                assert contexts and contexts[0].is_set()
                assert notification_controller._active_cancel is None
    finally:
        release_stop.set()
        await child.async_shutdown()


@pytest.mark.parametrize("lock_name", ("_operation_lock", "_wire_lock"))
@pytest.mark.parametrize("wait", (0.08, 0.2))
async def test_public_hold_deadline_includes_locks_without_unowned_release(hass, lock_name, wait):
    child, controller, client, _ = await bed(hass)
    lock = getattr(controller, lock_name)
    events, ended = [], []
    await lock.acquire()
    try:
        with ready(child), virtual_clock() as clock:

            async def unblock():
                await asyncio.sleep(wait)
                lock.release()

            async def write(_char, frame, **_kwargs):
                events.append((round(clock.now, 6), bytes(frame)))

            async def command():
                await child.async_execute_controller_command(hold)
                ended.append(clock.now)

            client.write_gatt_char.side_effect = write
            await asyncio.gather(command(), unblock())
            if wait < 0.1:
                assert events == [
                    (0.08, app.command("P1", 1)),
                    (0.1, app.command("P1", 0)),
                    (0.2, app.command("P1", 0)),
                ]
            else:
                assert events == []
                assert ended[0] <= 0.100001
            assert not controller._operation_lock.locked() and not controller._wire_lock.locked()
    finally:
        if lock.locked():
            lock.release()
        await child.async_shutdown()


async def test_public_stop_and_repeated_caller_cancel_drain_only_owner_release(hass):
    child, controller, client, _ = await bed(hass)
    entered, cleanup = asyncio.Event(), asyncio.Event()
    try:
        with ready(child), virtual_clock():

            async def write(_char, frame, **_kwargs):
                if frame == app.command("P1", 1):
                    entered.set()
                    await asyncio.sleep(30)
                else:
                    cleanup.set()
                    await asyncio.sleep(0.04)

            client.write_gatt_char.side_effect = write
            moving = asyncio.create_task(child.async_execute_controller_command(hold))
            await observed(entered, moving)
            stopping = asyncio.create_task(child.async_stop_command())
            await observed(cleanup, stopping)
            moving.cancel()
            await asyncio.sleep(0)
            moving.cancel()
            await asyncio.gather(moving, stopping, return_exceptions=True)
            assert writes(client) == [app.command("P1", 1), *[app.command("P1", 0)] * 2]
            assert controller._active_cancel is None
            assert not controller._operation_lock.locked() and not controller._wire_lock.locked()
    finally:
        await child.async_shutdown()


async def test_public_hold_session_retirement_never_releases_on_new_client(hass):
    child, controller, client, _ = await bed(hass)
    entered = asyncio.Event()
    try:
        with ready(child), virtual_clock():

            async def write(*_args, **_kwargs):
                entered.set()
                await asyncio.sleep(30)

            client.write_gatt_char.side_effect = write
            moving = asyncio.create_task(child.async_execute_controller_command(hold))
            await observed(entered, moving)
            controller.on_disconnect()
            client.is_connected = False
            replacement = client_for()
            child._client = replacement
            child._controller = await create_controller(child, "betterliving2", "p1", replacement)
            await child._controller.async_discover_capabilities()
            with pytest.raises(ConnectionError):
                await moving
            assert writes(client) == [app.command("P1", 1)]
            assert not writes(replacement)
    finally:
        await child.async_shutdown()


async def bind(child, wire, history, events, write_hook=None, startup=True):
    client = client_for(wire.upper())
    client.address = child.address
    child._client = client
    controller = await create_controller(child, "betterliving2", wire, client)
    child._controller = controller
    history.append((child.address, controller, client))

    async def write(_char, frame, **_kwargs):
        events.append((child.address, client, bytes(frame)))
        if write_hook is not None:
            await write_hook(child, controller, client, bytes(frame))

    async def disconnect():
        events.append((child.address, client, "disconnect"))
        client.is_connected = False
        return True

    client.write_gatt_char.side_effect = write
    client.disconnect.side_effect = disconnect
    child._position_connection_generation += 1
    await controller.async_discover_capabilities()
    if startup:
        await controller.async_on_connect(
            SimpleNamespace(
                async_start_notify=controller.start_notify,
                store_device_info=lambda *_: None,
            )
        )
    else:
        await controller.start_notify()
    return controller, client


async def native_pair(hass, stack, action, mode, initial, events, hook=None):
    hass.config.components.add(DOMAIN)
    wires = ("p1", "p1" if action == "massage" else "p3")
    descriptors = [
        {"side": side, **data(wire, layout, address)}
        for side, wire, layout, address in (
            ("left", wires[0], "2", "AA:BB:CC:DD:08:31"),
            ("right", wires[1], "3", "AA:BB:CC:DD:08:32"),
        )
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BetterLiving2 review pair",
        version=5,
        data={
            "pair_id": "betterliving2-review",
            "pair_mode": "separate_address",
            "name": "Review pair",
            "bed_type": "betterliving2",
            "pair_children": descriptors,
            "pair_member_addresses": [row["address"] for row in descriptors],
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    children = _build_paired_children(hass, entry)
    # Match actual paired entry setup before any live connect/preflight.
    for child in children.values():
        await child.async_prime_offline_controller()
        assert child.capability_controller is not None
    parent = PairedBedCoordinator(hass, entry, children, connection_mode=mode)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = parent
    _async_ensure_paired_device_registry(hass, entry, parent)
    registry = dr.async_get(hass)
    parent_identifier = next(
        identifier for identifier in parent.device_info["identifiers"] if identifier[0] == DOMAIN
    )
    parent_device = registry.async_get_device_by_identifier(parent_identifier, entry.entry_id)
    assert parent_device is not None
    assert len(dr.async_child_entries_for_config_entry(registry, entry.entry_id)) == 2
    history = []
    for side, child in children.items():
        wire = child.entry.data["protocol_variant"]
        if initial == "both" or initial == side:
            await bind(child, wire, history, events, hook, startup=False)

        async def connect(reset_timer=True, child=child, wire=wire):
            if not child.is_connected:
                await bind(child, wire, history, events, hook)
            return True

        stack.enter_context(
            patch.object(child, "_async_connect_locked", AsyncMock(side_effect=connect))
        )
        stack.enter_context(patch.object(child, "_async_refresh_controller_auth", AsyncMock()))
    await async_register_services(hass)
    return parent, children, parent_device.id, history


async def call_app(hass, parent_id, action):
    if action == "alarm":
        name = "betterliving2_set_alarm"
        payload = {"enabled": True, "time": "07:30", "weekdays": [1], "action": "memory_1"}
    else:
        name = "betterliving2_massage"
        payload = {"head": 1, "feet": 2}
    await hass.services.async_call(
        DOMAIN,
        name,
        {"device_id": [parent_id], **payload},
        blocking=True,
    )


def action_frames(events, child, action):
    wire = child.entry.data["protocol_variant"].upper()
    prefix = alarm_prefix(wire)
    return [
        frame
        for address, _client, frame in events
        if address == child.address
        and isinstance(frame, bytes)
        and (
            frame == app.command("P1", app.P1_MASSAGE_BASES["head"] + 1)
            if action == "massage"
            else frame[:2] == prefix
        )
    ]


def alarm_prefix(wire):
    return app.alarm(
        wire,
        hour=7,
        minute=30,
        week=0x82,
        massage=0,
        kind=app.ALARM_KINDS[wire]["memory_1"],
        now=app.Calendar.from_datetime(NOW),
    )[:2]


async def test_public_expired_hold_does_not_cancel_prior_notification_cleanup(hass):
    child, controller, client, _ = await bed(hass, "p2")
    entered = asyncio.Event()
    ended = []
    try:
        with ready(child), virtual_clock() as clock:

            async def write(_char, frame, **_kwargs):
                assert frame == app.command("P2", 0)
                entered.set()
                await asyncio.sleep(0.4)

            client.write_gatt_char.side_effect = write
            sender, callback = client.start_notify.call_args.args
            callback(sender, bytearray.fromhex(PACKETS["p2"]))
            prior = controller._notify_stop
            assert prior is not None
            await observed(entered, prior)
            await child.async_execute_controller_command(hold)
            ended.append(clock.now)
            assert ended[0] <= 0.100001
            assert not prior.cancelled()
            await prior
            assert writes(client) == [app.command("P2", 0)]
            assert child.controller_state[runtime.ALARM] == "selected"
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("action", ("alarm", "massage"))
@pytest.mark.parametrize(
    "mode,initial",
    (
        ("sequential", "right"),
        ("sequential", "offline"),
        ("concurrent", "right"),
        ("concurrent", "both"),
        ("concurrent", "offline"),
    ),
)
async def test_native_parent_both_binds_only_owned_physical_switches(hass, action, mode, initial):
    events = []
    with (
        ExitStack() as stack,
        virtual_clock(),
        patch.object(runtime.dt_util, "now", return_value=NOW),
    ):
        parent, children, device, history = await native_pair(
            hass,
            stack,
            action,
            mode,
            initial,
            events,
        )
        try:
            old_right = children["right"].client
            await call_app(hass, device, action)
            assert action_frames(events, children["left"], action)
            assert action_frames(events, children["right"], action)
            clients = {id(client) for _, _, client in history}
            assert len(clients) == len(history)
            assert {address for address, _, _ in history} == {
                children["left"].address,
                children["right"].address,
            }
            if mode == "sequential" and initial == "right":
                drop = next(
                    i
                    for i, (_, client, frame) in enumerate(events)
                    if client is old_right and frame == "disconnect"
                )
                first_action = next(
                    i
                    for i, (address, _, frame) in enumerate(events)
                    if address == children["left"].address
                    and frame in action_frames(events, children["left"], action)
                )
                assert drop < first_action
                right_clients = [
                    client for address, _, client in history if address == children["right"].address
                ]
                assert len(right_clients) == 2 and right_clients[-1] is not old_right
                assert not old_right.is_connected
        finally:
            await parent.async_shutdown()


@pytest.mark.parametrize("action", ("alarm", "massage"))
@pytest.mark.parametrize("drift", ("layout", "owner", "roster", "stop", "reconnect"))
async def test_native_both_rejects_later_owner_drift_before_mutation(hass, action, drift):
    events = []
    with ExitStack() as stack, virtual_clock():
        parent, children, device, history = await native_pair(
            hass,
            stack,
            action,
            "sequential",
            "right",
            events,
        )
        # children is a copy; inject faults into the store the topology reads.
        live_roster = parent._children
        original_roster = dict(live_roster)
        original_clients = {side: child.client for side, child in original_roster.items()}
        original_controllers = {side: child._controller for side, child in original_roster.items()}
        original_history = tuple(history)
        roster_fault = drift in {"owner", "roster"}
        hook_calls = []
        replacements = {}
        original_import = actions.async_import_modules
        boundary = []

        if roster_fault:
            service_name = (
                "betterliving2_set_alarm" if action == "alarm" else "betterliving2_massage"
            )
            handler = actions.set_alarm if action == "alarm" else actions.massage
            assert (
                hass.services.async_services_for_domain(DOMAIN)[service_name].job.target is handler
            )
            assert parent.children == original_roster and parent.children is not live_roster
            assert not events

        async def change_then_import(*args):
            right = children["right"]
            if roster_fault:
                hook_calls.append(drift)
                selection = runtime.current_selection()
                assert isinstance(selection, actions.Selection)
                assert selection.batches[0].roster == tuple(original_roster.items())
                for side, child in original_roster.items():
                    owner = selection.owners[id(child)]
                    assert owner.child is child
                    assert owner.client is original_clients[side]
                    assert owner.controller is original_controllers[side]
                    assert owner.link is getattr(original_controllers[side], "_link", None)
            if drift == "layout":
                right.entry.persist_data(
                    {**right.entry.data, "product_type": "2"}, keys={"product_type"}
                )
            elif drift == "owner":
                replacements.update(_build_paired_children(hass, parent.entry))
                live_roster["right"] = replacements["right"]
                assert parent.child_for_side("right") is replacements["right"]
                assert replacements["right"] is not right
            elif drift == "roster":
                assert live_roster.pop("right") is right
                assert parent.child_for_side("right") is None
            elif drift == "stop":
                await parent.async_stop_command(side="right")
            else:
                await right.async_disconnect("intentional")
                with pytest.raises(ServiceValidationError):
                    await bind(right, right.entry.data["protocol_variant"], history, events)
            if roster_fault:
                assert [child for _, child in parent._targets_for("both")] == list(
                    live_roster.values()
                )
            boundary.append(len(events))
            await original_import(*args)

        try:
            with patch.object(actions, "async_import_modules", change_then_import):
                if drift == "stop":
                    await call_app(hass, device, action)
                else:
                    with pytest.raises(ServiceValidationError) as rejected:
                        await call_app(hass, device, action)
                    if roster_fault:
                        assert str(rejected.value) == "BetterLiving2 physical roster changed"
            if roster_fault:
                assert hook_calls == [drift]
                assert tuple(history) == original_history
                assert not events
                for side, child in original_roster.items():
                    assert child.client is original_clients[side]
                    assert child._controller is original_controllers[side]
                    if (client := original_clients[side]) is not None:
                        assert not writes(client)
                assert all(child.client is None for child in replacements.values())
            assert not action_frames(events, original_roster["left"], action)
            assert not action_frames(events, original_roster["right"], action)
            assert len(events) == boundary[0]
        finally:
            live_roster.clear()
            live_roster.update(original_roster)
            await parent.async_shutdown()
            for child in replacements.values():
                await child.async_shutdown()


@pytest.mark.parametrize("action", ("alarm", "massage"))
async def test_native_both_rechecks_later_profile_before_each_write(hass, action):
    events = []
    changed = False
    children = {}

    async def hook(child, _controller, _client, frame):
        nonlocal changed
        is_action = (
            frame == app.command("P1", app.P1_MASSAGE_BASES["head"] + 1)
            if action == "massage"
            else frame[:2] == alarm_prefix("P1")
        )
        if child is children["left"] and is_action and not changed:
            changed = True
            right = children["right"]
            right.entry.persist_data(
                {**right.entry.data, "product_type": "2"}, keys={"product_type"}
            )
            await asyncio.sleep(0)

    with ExitStack() as stack, virtual_clock():
        parent, children, device, _ = await native_pair(
            hass,
            stack,
            action,
            "sequential",
            "right",
            events,
            hook,
        )
        try:
            with pytest.raises(PairedSideError):
                await call_app(hass, device, action)
            assert len(action_frames(events, children["left"], action)) == 1
            assert not action_frames(events, children["right"], action)
        finally:
            await parent.async_shutdown()


@pytest.mark.parametrize("wire", ("p2", "p3"))
async def test_public_startup_alarm_reply_retires_query_not_user_action(hass, wire):
    child, old, old_client, _ = await bed(hass, wire)
    old.on_disconnect()
    old_client.is_connected = False
    child._controller = child._client = None
    history, events, contexts = [], [], []

    async def hook(_child, controller, client, frame):
        query = app.alarm_query(wire.upper(), app.Calendar.from_datetime(NOW))
        if frame == query:
            context = current_command_context()
            assert context is not None
            contexts.append(context.cancel_event)
            sender, callback = client.start_notify.call_args.args
            callback(sender, bytearray.fromhex(PACKETS[wire]))
            await asyncio.sleep(30)

    async def connect(reset_timer=True):
        if not child.is_connected:
            await bind(child, wire, history, events, hook)
        return True

    async def user_action(controller):
        assert isinstance(controller, runtime.BetterLiving2Controller)
        await controller.lights_toggle()

    try:
        with (
            patch.object(child, "_async_connect_locked", AsyncMock(side_effect=connect)),
            patch.object(child, "_async_refresh_controller_auth", AsyncMock()),
            virtual_clock(),
            patch.object(runtime.dt_util, "now", return_value=NOW),
        ):
            await child.async_execute_controller_command(user_action)
            frames = [frame for _, _, frame in events if isinstance(frame, bytes)]
            assert frames == [
                app.current_time(wire.upper(), app.Calendar.from_datetime(NOW)),
                app.alarm_query(wire.upper(), app.Calendar.from_datetime(NOW)),
                app.command(wire.upper(), 0),
                app.command(wire.upper(), app.STEP_LIGHT),
            ]
            assert contexts and all(not event.is_set() for event in contexts)
            assert child.controller_state[runtime.ALARM] == "selected"
            assert history[-1][1]._notify_stop is None
    finally:
        await child.async_shutdown()
