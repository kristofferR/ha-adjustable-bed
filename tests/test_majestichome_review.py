"""S1/S2: actual registered actions through reconnecting physical pair targets."""

import asyncio
from contextlib import AsyncExitStack
from copy import copy
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
    const,
)
from custom_components.adjustable_bed.beds.majestichome import controller as bed
from custom_components.adjustable_bed.beds.majestichome import services
from custom_components.adjustable_bed.beds.majestichome.protocol import Alarm
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.profile_id import with_profile_ids
from custom_components.adjustable_bed.services import (
    _resolve_sided_targets as resolve_native_targets,
)
from custom_components.adjustable_bed.services import (
    async_register_services,
)
from tests.pair_mode import CONF_PAIR_CONNECTION_MODE
from tests.test_majestichome import GATT, notify, written
from tests.test_majestichome import clock as clock
from tests.test_majestichome_runtime import runtime as runtime
from tests.test_majestichome_runtime import settings
from tests.test_paired_setup import _paired_entry_data


def alarm_reply(alarm):
    frame = bytes(
        (
            0x6E,
            0x20,
            13,
            5,
            1,
            2,
            alarm.number,
            alarm.reserved,
            alarm.hour,
            alarm.minute,
            alarm.preset,
            alarm.repeat,
        )
    )
    return frame + bytes((sum(frame) & 255,))


@pytest.fixture
async def live_pair(hass, mock_coordinator_connected, clock):
    async def build(mode, *, delayed_clock=False):
        data = _paired_entry_data()
        data[const.CONF_BED_TYPE] = "majestichome"
        data[CONF_PAIR_CONNECTION_MODE] = mode
        for row, product in zip(data[const.CONF_PAIR_CHILDREN], ("FARM", "JLRM"), strict=True):
            row.update(
                {
                    const.CONF_BED_TYPE: "majestichome",
                    const.CONF_PROTOCOL_VARIANT: product,
                    const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
                }
            )
            row.pop("capabilities", None)
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            title="Majestic review pair",
            data=with_profile_ids(data),
            version=5,
            state=ConfigEntryState.LOADED,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        pair = PairedBedCoordinator(hass, entry, children)
        hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
        _async_ensure_paired_device_registry(hass, entry, pair)
        events, connections = [], dict.fromkeys(children, 0)
        records = {side: Alarm(1, 0, 7, 30, 0x2E, 249) for side in children}
        hooks = {}
        for side, child in children.items():
            await child.async_prime_offline_controller()

            async def connect(*, reset_timer=True, side=side, child=child):
                connections[side] += 1
                state = {"ready": False}
                client = MagicMock(is_connected=True)
                row = GATT[1]
                tx = SimpleNamespace(uuid=row["write"].lower(), properties=["write"], handle=1)
                rx = SimpleNamespace(
                    uuid=row["declared_notify"].lower(), properties=["notify"], handle=2
                )
                client.services = [
                    SimpleNamespace(uuid=row["service"].lower(), characteristics=[tx, rx])
                ]
                client.start_notify = AsyncMock()
                client.stop_notify = AsyncMock()

                async def disconnect():
                    client.is_connected = False

                client.disconnect = AsyncMock(side_effect=disconnect)

                async def write(_char, packet, **kwargs):
                    if state["ready"]:
                        events.append((side, bytes(packet)))
                    if packet.hex() == "6e08010178":
                        if not delayed_clock or state["ready"]:
                            hass.loop.call_soon(
                                child.controller._notification,
                                child.controller._link,
                                rx,
                                bytearray.fromhex("6e09010078"),
                            )
                    elif packet == bed.LIST_ALARMS:
                        if hook := hooks.get("query"):
                            if hook(side, child, connections[side]):
                                return
                        child.controller._notification(
                            child.controller._link, rx, bytearray(alarm_reply(records[side]))
                        )

                client.write_gatt_char = AsyncMock(side_effect=write)
                child._client = client
                child._controller = await create_controller(
                    child, "majestichome", child.entry.data[const.CONF_PROTOCOL_VARIANT], client
                )
                await child.controller.start_notify()
                state["ready"] = True
                return True

            child._async_connect_locked = connect
        await async_register_services(hass)
        registry = dr.async_get(hass)
        parent = registry.async_get_device_by_identifier(
            next(iter(pair.device_info["identifiers"])), entry.entry_id
        )
        native = dr.async_entries_for_parent_device(registry, parent.id)
        left = next(device for device in native if "Left" in device.name)
        pairs.append(pair)
        return SimpleNamespace(
            pair=pair,
            children=children,
            parent=parent.id,
            left=left.id,
            events=events,
            connections=connections,
            records=records,
            hooks=hooks,
        )

    pairs = []
    yield build
    for pair in pairs:
        await pair.async_shutdown()


def mutations(events):
    return [
        (side, packet.hex())
        for side, packet in events
        if len(packet) > 6 and packet[3] == 5 and packet[5] == 1
    ]


@pytest.fixture
async def protocol_time(clock, monkeypatch):
    """Run real startup, FIFO pacing and reply bounds on one virtual loop clock."""
    from tests.hold_lease_wire import virtual_clock

    with virtual_clock() as fake:
        monkeypatch.setattr(bed, "monotonic", fake.time)
        monkeypatch.setattr(bed, "FIRST_WRITE_MS", 100)
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.goodvibe.controller.QUEUE_MS", 100
        )
        monkeypatch.setattr(bed.MajesticHomeController, "_delay", bed.GoodVibeController._delay)
        yield fake


def standalone_replies(target, client, *, records=True, hook=None):
    timers = []
    submissions = []

    async def write(_char, packet, **kwargs):
        ctrl = target.controller
        link = ctrl._link
        rx = client.start_notify.call_args.args[0]
        loop = asyncio.get_running_loop()
        if packet.hex() == "6e08010178":
            timers.append(
                loop.call_later(0.01, ctrl._notification, link, rx, bytearray.fromhex("6e09010078"))
            )
        if packet == bed.LIST_ALARMS:
            submissions.append(loop.time())
            if hook:
                hook(ctrl, link, rx)
            if records:
                for delay, alarm in (
                    (0.2, Alarm(1, 99, 22, 45, 250, 131)),
                    (0.7, Alarm(2, 0, 6, 0, 46, 129)),
                ):
                    timers.append(
                        loop.call_later(
                            delay, ctrl._notification, link, rx, bytearray(alarm_reply(alarm))
                        )
                    )

    client.write_gatt_char.side_effect = write
    return timers, submissions


@pytest.mark.parametrize(
    "route",
    ("standalone", "concurrent-parent", "concurrent-left", "sequential-parent", "sequential-left"),
)
async def test_toggle_reads_record_after_reconnect(hass, runtime, live_pair, protocol_time, route):
    if route == "standalone":
        target, client, _ = runtime
        timers, _ = standalone_replies(target, client)
        # Exercise an actual closed old session, not an injected cache on a live link.
        assert await target.async_connect()
        await target.async_disconnect("idle_timeout")
        try:
            await settings(hass, "toggle", alarm_id=1, enabled=False)
        finally:
            for timer in timers:
                timer.cancel()
        assert written(target)[-1] == "6e0d200501010163162dfa82c5"
        assert bed.LIST_ALARMS.hex() in written(target)
    else:
        runtime[2].side_effect = resolve_native_targets
        mode, destination = route.split("-")
        live = await live_pair(mode)
        for side in live.records:
            live.records[side] = Alarm(1, 99, 22, 45, 250, 131)
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {
                "device_id": getattr(live, destination),
                "operation": "toggle",
                "alarm_id": 1,
                "enabled": False,
            },
            blocking=True,
        )
        sides = {"left", "right"} if destination == "parent" else {"left"}
        assert sorted(mutations(live.events)) == sorted(
            (side, "6e0d200501010163162dfa82c5") for side in sides
        )
        assert {side for side, packet in live.events if packet == bed.LIST_ALARMS} == sides


@pytest.mark.parametrize(
    "route,records,slow",
    (
        ("standalone", True, False),
        ("concurrent-parent", True, False),
        ("sequential-left", True, False),
        ("sequential-left", False, False),
        ("standalone", True, True),
    ),
)
async def test_list_holds_link_for_bounded_observations(
    hass, runtime, live_pair, protocol_time, route, records, slow
):
    timers, submitted, targets, observed_controllers = [], [], [], []
    generations = {}
    if route == "standalone":
        target, client, _ = runtime
        timers, submitted = standalone_replies(target, client, records=records)
        base_write = client.write_gatt_char.side_effect

        async def write(*args, **kwargs):
            if args[1] == bed.LIST_ALARMS:
                generations[target] = target._command_link_generation
                assert not target.controller.requests_connection_recovery
                assert not target.controller.requires_persistent_connection
            await base_write(*args, **kwargs)
            if slow and args[1] == bed.LIST_ALARMS:
                await asyncio.sleep(1)

        client.write_gatt_char.side_effect = write
        device = "bed"
        targets = [target]
    else:
        runtime[2].side_effect = resolve_native_targets
        mode, destination = route.split("-")
        live = await live_pair(mode)
        device = getattr(live, destination)
        targets = (
            list(live.children.values()) if destination == "parent" else [live.children["left"]]
        )

        def delayed(side, child, generation):
            ctrl, link = child.controller, child.controller._link
            generations[child] = child._command_link_generation
            assert not ctrl.requests_connection_recovery
            assert not ctrl.requires_persistent_connection
            observed_controllers.append(ctrl)
            rx = link.rx
            loop = asyncio.get_running_loop()
            submitted.append(loop.time())
            if records:
                for delay, alarm in ((0.2, live.records[side]), (0.7, Alarm(2, 0, 6, 0, 46, 129))):

                    def reply(alarm=alarm):
                        assert child.is_connected
                        ctrl._notification(link, rx, bytearray(alarm_reply(alarm)))

                    timers.append(loop.call_later(delay, reply))
            return True

        live.hooks["query"] = delayed
    try:
        response = await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {
                "device_id": device,
                "operation": "list",
            },
            blocking=True,
            return_response=True,
        )
        assert len(response["targets"]) == len(targets)
        for item in response["targets"]:
            assert item["complete"] is False
            assert [row["number"] for row in item["alarms"]] == ([1, 2] if records else [])
        assert protocol_time.time() >= max(submitted) + 5
        # Slow GATT completion and later records do not restart the five-second window.
        assert protocol_time.time() < max(submitted) + 5.01
        assert all(child._command_connection_holds == 0 for child in targets)
        assert all(child._command_demand == 0 for child in targets)
        assert all(child._command_link_generation == generations[child] for child in targets)
        if route.startswith("sequential"):
            assert not targets[0].is_connected and targets[0].controller is None
            assert observed_controllers and all(not ctrl.alarms for ctrl in observed_controllers)
        else:
            for child in targets:
                child.controller.alarms.clear()
        assert all(len(item["alarms"]) == (2 if records else 0) for item in response["targets"])
        assert {item["side"] for item in response["targets"]} == (
            {"left", "right"}
            if route == "concurrent-parent"
            else {"left"}
            if route == "sequential-left"
            else {"both"}
        )
    finally:
        for timer in timers:
            timer.cancel()


@pytest.mark.parametrize("race", ("stop", "session", "owner", "route"))
async def test_alarm_read_abort_never_mutates(hass, runtime, protocol_time, race):
    target, client, _ = runtime
    pending = []
    invalidated = asyncio.Event()

    def hook(ctrl, link, rx):
        async def invalidate():
            await asyncio.sleep(0.2)
            if race == "stop":
                invalidated.set()
                await target.async_stop_command()
            elif race == "session":
                ctrl.on_disconnect()
                ctrl._link = None
            elif race == "owner":
                ctrl._physical_owner = copy(target)
            else:
                hass.config_entries.async_update_entry(
                    target.entry, data={**target.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"}
                )
            invalidated.set()

        pending.append(asyncio.create_task(invalidate()))

    timers, submitted = standalone_replies(target, client, records=False, hook=hook)
    try:
        try:
            await settings(hass, "list")
        except HomeAssistantError, ConnectionError, asyncio.CancelledError:
            pass
        assert invalidated.is_set()
        assert submitted and protocol_time.time() < submitted[0] + 1
        assert target._command_connection_holds == 0
        assert not any(
            len(bytes.fromhex(p)) > 6 and bytes.fromhex(p)[3:6] == bytes((5, 1, 1))
            for p in written(target)
        )
    finally:
        await asyncio.gather(*pending)
        for timer in timers:
            timer.cancel()


@pytest.mark.parametrize("failure", ("missing", "changed"))
async def test_toggle_all_target_read_barrier(hass, live_pair, protocol_time, failure):
    live = await live_pair("concurrent" if failure == "missing" else "sequential")

    def query(side, child, generation):
        if side == "right" and failure == "missing":
            return True
        if side == "left" and generation == 2 and failure == "changed":
            live.records[side] = Alarm(1, 99, 22, 45, 250, 131)
        return False

    live.hooks["query"] = query
    with pytest.raises((HomeAssistantError, TimeoutError)):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {
                "device_id": live.parent,
                "operation": "toggle",
                "alarm_id": 1,
            },
            blocking=True,
        )
    assert not mutations(live.events)
    assert all(child._command_connection_holds == 0 for child in live.children.values())


@pytest.mark.parametrize("service", ("timed_move", "hold_control"))
async def test_finite_public_rejects_short_duration(hass, runtime, protocol_time, service):
    target, client, _ = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    data = (
        {"motor": "back", "direction": "up", "duration_ms": 100}
        if service == "timed_move"
        else {"control": "head_up", "duration": 0.1}
    )
    with pytest.raises(ServiceValidationError, match="200"):
        await hass.services.async_call(
            const.DOMAIN, service, {"device_id": "bed", **data}, blocking=True
        )
    assert not written(target)


@pytest.mark.parametrize("route", ("timed_move", "hold_control", "implicit"))
async def test_public_minimum_after_real_startup(hass, runtime, protocol_time, monkeypatch, route):
    target, client, _ = runtime
    trace = []

    async def write(_char, packet, **kwargs):
        trace.append((protocol_time.time(), packet.hex()))
        await asyncio.sleep(0.002)  # Positive radio completion overhead, including startup.

    client.write_gatt_char.side_effect = write
    real_delay = bed.GoodVibeController._delay

    async def waking(ctrl, ms):
        result = await real_delay(ctrl, ms)
        await asyncio.sleep(0.002)  # A wake happens after, not exactly at, its due time.
        return result

    monkeypatch.setattr(bed.MajesticHomeController, "_delay", waking)
    assert await target.async_connect()
    assert trace[0][0] >= 0.1 and target.controller._next_write_at > 0
    assert trace[0][1] == "6e02010071" and trace[-1][1] == "6e08010178"
    trace.clear()
    started = protocol_time.time()
    if route == "implicit":
        target._motor_pulse_count = 1  # The persisted value read by the real coordinator.
        await target.async_execute_controller_command(lambda ctrl: ctrl.move_head_up())
    else:
        data = (
            {"motor": "back", "direction": "up", "duration_ms": 200}
            if route == "timed_move"
            else {"control": "head_up", "duration": 0.2}
        )
        await hass.services.async_call(
            const.DOMAIN, route, {"device_id": "bed", **data}, blocking=True
        )
    assert [p for _, p in trace] == ["6e01002493", "6e01006edd"]
    assert 0.1 <= trace[0][0] - started < 0.2
    assert trace[1][0] >= trace[0][0] + 0.1


async def test_finite_public_expiry_is_not_success(hass, runtime, protocol_time, monkeypatch):
    target, client, _ = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()

    async def late(ctrl, ms):
        await asyncio.sleep(0.3)
        return True

    monkeypatch.setattr(bed.MajesticHomeController, "_delay", late)
    with pytest.raises((HomeAssistantError, ValueError, TimeoutError)):
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": "bed",
                "motor": "back",
                "direction": "up",
                "duration_ms": 200,
            },
            blocking=True,
        )
    assert not written(target)


@pytest.mark.parametrize("renew", (False, True))
async def test_native_expiry_gate_after_pacing(hass, runtime, protocol_time, monkeypatch, renew):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    target, client, _ = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    observed = []
    movement_times = []

    async def write(_char, packet, **kwargs):
        if packet.hex() == "6e01002493":
            movement_times.append(protocol_time.time())

    client.write_gatt_char.side_effect = write
    original = bed.MajesticHomeController._pace

    async def paced(ctrl, cleanup):
        context = current_command_context()
        if not cleanup and not observed:
            observed.append(context)
            assert context is not None and context.hold_deadline is not None
            # Preserve a live admitted context but hold back its timer signal: the
            # actual-submit guard must honor the absolute clock independently.
            record = next(iter(target._command_scheduler._leases.values()))
            record.timer.cancel()
            original_deadline = context.hold_deadline
            if renew:
                await asyncio.sleep(0.2)
                await hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {
                        "device_id": "bed",
                        "motor": "back",
                        "direction": "up",
                        "duration_ms": 500,
                        "hold_owner": "safety",
                        "hold_generation": 1,
                    },
                    blocking=True,
                )
                record.timer.cancel()
                assert context.hold_deadline > original_deadline
                await asyncio.sleep(original_deadline - protocol_time.time() + 0.01)
                assert protocol_time.time() < context.hold_deadline
            else:
                await asyncio.sleep(original_deadline - protocol_time.time())
            assert not context.cancel_event.is_set()
        return await original(ctrl, cleanup)

    monkeypatch.setattr(bed.MajesticHomeController, "_pace", paced)
    async with asyncio.timeout(2):
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": "bed",
                "motor": "back",
                "direction": "up",
                "duration_ms": 500,
                "hold_owner": "safety",
                "hold_generation": 1,
            },
            blocking=True,
        )
    assert observed
    assert all(at < observed[0].hold_deadline for at in movement_times)
    packets = written(target)
    if renew:
        assert packets and packets[-1] == "6e01006edd"
        assert set(packets[:-1]) == {"6e01002493"}
    else:
        assert not packets


@pytest.mark.parametrize("operation", ("list", "new", "set", "delete"))
async def test_standalone_waits_for_late_clock_reply(hass, runtime, protocol_time, operation):
    target, client, _ = runtime
    queries = 0

    async def write(_char, packet, **kwargs):
        nonlocal queries
        if packet.hex() == "6e08010178":
            queries += 1
            if queries > 1:
                hass.loop.call_soon(notify, target, "6e09010078")

    client.write_gatt_char.side_effect = write
    await settings(hass, operation, alarm_id=1)
    assert queries == 2
    assert target.controller.observations["clock_available"]


async def test_concurrent_pair_waits_for_late_clock_replies(hass, live_pair):
    live = await live_pair("concurrent", delayed_clock=True)
    await hass.services.async_call(
        const.DOMAIN,
        "majestichome",
        {"device_id": live.parent, "operation": "set", "alarm_id": 1},
        blocking=True,
    )
    assert {side for side, _packet in mutations(live.events)} == {"left", "right"}
    assert live.connections == {"left": 1, "right": 1}


@pytest.mark.parametrize("fail", (False, True))
@pytest.mark.parametrize("paired", (False, True))
async def test_preflight_retains_links_until_all_targets_finish(
    hass, live_pair, monkeypatch, fail, paired
):
    live = await live_pair("concurrent")
    original = bed.MajesticHomeController.prepare_live
    targets = live.children
    async with AsyncExitStack() as cleanup:
        if not paired:
            targets = {}
            for side, child in live.children.items():
                entry = MockConfigEntry(domain=const.DOMAIN, data=dict(child.entry.data), version=5)
                entry.add_to_hass(hass)
                standalone = AdjustableBedCoordinator(hass, entry)
                await standalone.async_prime_offline_controller()
                monkeypatch.setitem(hass.data[const.DOMAIN], entry.entry_id, standalone)
                monkeypatch.setattr(
                    standalone,
                    "_async_connect_locked",
                    partial(child._async_connect_locked, child=standalone),
                )
                cleanup.push_async_callback(standalone.async_shutdown)
                targets[side] = standalone
            monkeypatch.setattr(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                lambda *args: ([(child, "both") for child in targets.values()], []),
            )
        for child in targets.values():
            child._disconnect_after_command = True
            # Make the handoff expire as soon as the next target yields.
            monkeypatch.setattr(child, "_idle_disconnect_delay", lambda: 0)

        async def prepare(controller, request, **kwargs):
            if controller.layout.key == "JLRM":
                for _ in range(5):
                    await asyncio.sleep(0)
                assert targets["left"].is_connected
                if fail:
                    raise ValueError("Right preflight failed")
            return await original(controller, request, **kwargs)

        with patch.object(bed.MajesticHomeController, "prepare_live", prepare):
            call = hass.services.async_call(
                const.DOMAIN,
                "majestichome",
                {"device_id": live.parent, "operation": "delete", "alarm_id": 1},
                blocking=True,
            )
            if fail:
                with pytest.raises(ServiceValidationError, match="Right preflight failed"):
                    await call
            else:
                await call
                for side in targets:
                    assert [packet for owner, packet in live.events if owner == side][-1] == (
                        bytes.fromhex("6e0820050201019f")
                    )
        assert live.connections == {"left": 1, "right": 1}
        for child in targets.values():
            assert child._command_connection_holds == 0
            assert not child.is_connected or child._disconnect_timer is not None


@pytest.mark.parametrize("mode", ("concurrent", "sequential"))
@pytest.mark.parametrize("target", ("parent", "left"))
@pytest.mark.parametrize("operation", ("list", "new", "set", "toggle", "delete"))
async def test_registered_actions_rebuild_on_actual_pair_links(
    hass, live_pair, protocol_time, mode, target, operation
):
    live = await live_pair(mode)
    fields = {
        "device_id": getattr(live, target),
        "operation": operation,
        "alarm_id": 1,
        "enabled": False,
    }
    if mode == "concurrent" and operation == "toggle":
        for side, child in live.children.items():
            if target == "left" and side != "left":
                continue
            await child.async_connect()
            child.controller.alarms[1] = live.records[side]
    await hass.services.async_call(const.DOMAIN, "majestichome", fields, blocking=True)
    sides = {"left", "right"} if target == "parent" else {"left"}
    expected = {
        "new": "6e0d200501010100071e2e00f6",
        "set": "6e0d200501010100071e2e00f6",
        "toggle": "6e0d200501010100071e2ef8ee",
        "delete": "6e0820050201019f",
    }
    if operation in expected:
        assert sorted(mutations(live.events)) == sorted(
            (side, expected[operation]) for side in sides
        )
    elif operation == "list":
        assert sorted((side, packet.hex()) for side, packet in live.events) == sorted(
            (side, "6e0820050100009c") for side in sides
        )
    else:
        for side in sides:
            assert [packet[3:6] for owner, packet in live.events if owner == side] == [
                bytes((8, 2, 1)),
                bytes((8, 3, 1)),
            ]
    assert all(live.connections[side] == (2 if mode == "sequential" else 1) for side in sides)
    assert all(live.connections[side] == 0 for side in live.children.keys() - sides)
    assert not mutations([(side, packet) for side, packet in live.events if side not in sides])
    if mode == "sequential":
        assert not any(child.is_connected for child in live.children.values())


@pytest.mark.parametrize("race", ("stop", "changed", "session", "owner", "target", "product"))
async def test_sequential_races_never_write_a_stale_mutation(hass, live_pair, race):
    live = await live_pair("sequential")
    real = services._execute_preflighted

    async def before_execution(*args, **kwargs):
        if race == "stop":
            await live.pair.async_stop_command()
        elif race == "changed":
            live.records["left"] = Alarm(1, 99, 22, 45, 250, 131)
        elif race == "target":
            await live.pair.async_remove_child("right")
        elif race == "product":
            child = live.children["left"]
            child.entry.persist_data({**child.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"})
        else:

            def invalidate(side, child, generation):
                if generation == 2:
                    if race == "session":
                        child.controller.on_disconnect()
                    else:
                        child.controller._physical_owner = copy(child)

            live.hooks["query"] = invalidate
        await real(*args, **kwargs)

    with patch.object(services, "_execute_preflighted", before_execution):
        if race == "stop":
            await hass.services.async_call(
                const.DOMAIN,
                "majestichome",
                {"device_id": live.parent, "operation": "toggle", "alarm_id": 1},
                blocking=True,
            )
        else:
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call(
                    const.DOMAIN,
                    "majestichome",
                    {"device_id": live.parent, "operation": "toggle", "alarm_id": 1},
                    blocking=True,
                )
    assert mutations(live.events) == []
    assert not any(child.is_connected for child in live.children.values())


async def test_all_entry_routes_are_rechecked_after_queued_group_lock(hass, live_pair):
    live = await live_pair("sequential")
    original = services._execute_preflighted

    async def queue_then_change(*args, **kwargs):
        async with live.pair._topology.command_lock:
            task = asyncio.create_task(original(*args, **kwargs))
            await asyncio.sleep(0)
            right = live.children["right"]
            right.entry.persist_data({**right.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"})
        await task

    with (
        patch.object(services, "_execute_preflighted", queue_then_change),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
        )
    assert mutations(live.events) == []


async def test_all_entry_routes_are_rechecked_at_submission_after_pacing(hass, live_pair):
    live = await live_pair("concurrent")
    original = services._execute_preflighted
    pace = bed.MajesticHomeController._pace
    armed = False

    async def execute(*args, **kwargs):
        nonlocal armed
        armed = True
        await original(*args, **kwargs)

    async def change_during_pace(controller, cleanup):
        nonlocal armed
        result = await pace(controller, cleanup)
        if armed:
            armed = False
            right = live.children["right"]
            right.entry.persist_data({**right.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"})
        return result

    with (
        patch.object(services, "_execute_preflighted", execute),
        patch.object(bed.MajesticHomeController, "_pace", change_during_pace),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
        )
    assert mutations(live.events) == []


async def test_sequential_all_target_live_preflight_before_first_mutation(hass, live_pair):
    live = await live_pair("sequential")
    original = bed.MajesticHomeController.prepare_live

    async def reject_right(controller, request, **kwargs):
        result = await original(controller, request, **kwargs)
        if controller.layout.key == "JLRM":
            raise ValueError("Right current settings unavailable")
        return result

    with (
        patch.object(bed.MajesticHomeController, "prepare_live", reject_right),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
        )
    assert mutations(live.events) == []


@pytest.mark.parametrize("partial", (False, True))
async def test_new_requires_explicit_id_before_import_even_with_partial_records(
    hass, runtime, partial
):
    target, client, _ = runtime
    assert await target.async_connect()
    notify(target, "6e09010078")
    if partial:
        notify(target, "6e200d0501020100071e2ef9f0")
    client.write_gatt_char.reset_mock()
    with (
        patch.object(services, "async_import_modules", AsyncMock()) as importing,
        pytest.raises(ServiceValidationError, match="explicit alarm ID"),
    ):
        await settings(hass, "new")
    importing.assert_not_awaited()
    assert written(target) == []
    await settings(hass, "new", alarm_id=2)
    assert written(target) == ["6e0d200501010200071e2e01f8"]


@pytest.mark.parametrize("mode", ("concurrent", "sequential"))
@pytest.mark.parametrize("operation", ("list", "toggle"))
async def test_fresh_settings_after_native_cover_stop(
    hass, live_pair, protocol_time, mode, operation
):
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.paired_coordinator import PairedSideProxy

    live = await live_pair(mode)
    left = live.children["left"]
    assert await left.async_connect()
    cover = AdjustableBedCover(
        PairedSideProxy(live.pair, left, "left"),
        _build_cover_description(left.controller.motor_control_specs[0]),
    )
    assert cover.entity_description.hold is not None
    assert cover.entity_description.stop_scope is None
    assert cover.extra_state_attributes["held_stop_scope"] == "side"
    before_stops = {side: live.pair.stop_count(side) for side in live.children}
    cover.async_write_ha_state = MagicMock()
    await cover.async_stop_cover()
    assert live.pair.stop_count("left") == before_stops["left"] + 1
    assert live.pair.stop_count("right") == before_stops["right"]
    assert live.pair._pair_cancel_generation("left", ("*",)) != (0,)
    assert ("left", bytes.fromhex("6e01006edd")) in live.events
    live.events.clear()
    response = await hass.services.async_call(
        const.DOMAIN,
        "majestichome",
        {
            "device_id": live.left,
            "operation": operation,
            "alarm_id": 1,
            "enabled": False,
        },
        blocking=True,
        return_response=True,
    )
    assert {side for side, _ in live.events} == {"left"}
    assert any(packet == bed.LIST_ALARMS for _, packet in live.events)
    if operation == "list":
        assert response["targets"][0]["side"] == "left"
        assert response["targets"][0]["alarms"][0]["number"] == 1
    else:
        assert response == {}
        assert mutations(live.events) == [("left", "6e0d200501010100071e2ef8ee")]


@pytest.mark.parametrize("race", ("session", "records"))
async def test_all_pending_live_plans_rechecked_at_submission(hass, live_pair, protocol_time, race):
    live = await live_pair("concurrent")
    original_execute, original_pace = (
        services._execute_preflighted,
        bed.MajesticHomeController._pace,
    )
    armed = False
    invalidated = []

    async def execute(*args, **kwargs):
        nonlocal armed
        armed = True
        await original_execute(*args, **kwargs)

    async def pace(ctrl, cleanup):
        nonlocal armed
        result = await original_pace(ctrl, cleanup)
        if armed and not cleanup:
            armed = False
            peer = next(child for child in live.children.values() if child.controller is not ctrl)
            invalidated.append(peer)
            if race == "session":
                peer.controller.on_disconnect()
            else:
                peer.controller.alarms[1] = Alarm(1, 99, 22, 45, 250, 131)
        return result

    with (
        patch.object(services, "_execute_preflighted", execute),
        patch.object(bed.MajesticHomeController, "_pace", pace),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {
                "device_id": live.parent,
                "operation": "set",
                "alarm_id": 1,
            },
            blocking=True,
        )
    assert invalidated and not mutations(live.events)


@pytest.mark.parametrize("mode", ("sequential", "concurrent"))
@pytest.mark.parametrize("target", ("parent", "left"))
@pytest.mark.parametrize("drift", ("removed", "replaced"))
async def test_pair_registration_rechecked_at_submission(
    hass, live_pair, protocol_time, mode, target, drift
):
    live = await live_pair(mode)
    original_execute, original_pace = (
        services._execute_preflighted,
        bed.MajesticHomeController._pace,
    )
    armed, changed, replacements = False, [], []

    async def execute(*args, **kwargs):
        nonlocal armed
        armed = True
        await original_execute(*args, **kwargs)

    async def pace(ctrl, cleanup):
        nonlocal armed
        result = await original_pace(ctrl, cleanup)
        if armed and not cleanup:
            armed = False
            entry = live.pair.entry
            assert ctrl._current_link().client.is_connected
            old = hass.data[const.DOMAIN].pop(entry.entry_id)
            assert old is live.pair
            changed.append(old)
            if drift == "replaced":
                replacement = PairedBedCoordinator(hass, entry, _build_paired_children(hass, entry))
                replacements.append(replacement)
                hass.data[const.DOMAIN][entry.entry_id] = replacement
        return result

    try:
        with (
            patch.object(services, "_execute_preflighted", execute),
            patch.object(bed.MajesticHomeController, "_pace", pace),
            pytest.raises(ServiceValidationError) as raised,
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "majestichome",
                {"device_id": getattr(live, target), "operation": "set", "alarm_id": 1},
                blocking=True,
            )
        assert raised.value.translation_key == "bed_changed"
        assert changed and not mutations(live.events)
        assert all(child._command_connection_holds == 0 for child in live.children.values())
    finally:
        hass.data[const.DOMAIN][live.pair.entry.entry_id] = live.pair
        for replacement in replacements:
            await replacement.async_shutdown()


@pytest.mark.parametrize("mode", ("concurrent", "sequential"))
async def test_registration_error_preserves_real_cleanup_failures(
    hass, live_pair, protocol_time, mode
):
    live = await live_pair(mode)
    original_execute, original_pace = (
        services._execute_preflighted,
        bed.MajesticHomeController._pace,
    )
    disconnect = live.children["left"].async_disconnect
    stop = live.children["right"].async_stop_command
    armed, fault = False, False

    async def execute(*args, **kwargs):
        nonlocal armed
        armed = True
        await original_execute(*args, **kwargs)

    async def pace(ctrl, cleanup):
        nonlocal armed, fault
        result = await original_pace(ctrl, cleanup)
        if armed and not cleanup:
            armed, fault = False, True
            assert hass.data[const.DOMAIN].pop(live.pair.entry.entry_id) is live.pair
        return result

    async def fail_disconnect(*args, **kwargs):
        if fault and mode == "sequential":
            raise ConnectionError("disconnect failed")
        return await disconnect(*args, **kwargs)

    async def fail_stop(*args, **kwargs):
        if fault and mode == "concurrent":
            raise ConnectionError("stop failed")
        return await stop(*args, **kwargs)

    try:
        with (
            patch.object(services, "_execute_preflighted", execute),
            patch.object(bed.MajesticHomeController, "_pace", pace),
            patch.object(live.children["left"], "async_disconnect", fail_disconnect),
            patch.object(live.children["right"], "async_stop_command", fail_stop),
            pytest.raises(PairedSideError) as raised,
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "majestichome",
                {"device_id": live.parent, "operation": "set", "alarm_id": 1},
                blocking=True,
            )
        assert fault and not mutations(live.events)
        if mode == "concurrent":
            assert str(raised.value.side_errors["right (stop)"]) == "stop failed"
        else:
            reason = raised.value.side_errors["left"]
            assert "release also failed" in str(reason)
            assert isinstance(reason.__cause__, ServiceValidationError)
            assert reason.__cause__.translation_key == "bed_changed"
        assert all(child._command_connection_holds == 0 for child in live.children.values())
    finally:
        hass.data[const.DOMAIN][live.pair.entry.entry_id] = live.pair


async def test_disconnected_sequential_side_stop_quietly_drops_the_whole_call(
    hass, live_pair, protocol_time
):
    live = await live_pair("sequential")
    original_execute = services._execute_preflighted
    stopped = []

    async def execute(*args, **kwargs):
        assert not any(child.is_connected for child in live.children.values())
        child = live.children["right"]
        before_epoch, before_count = child.stop_epoch, live.pair.stop_count("right")
        await live.pair.async_stop_command(side="right")
        assert child.stop_epoch == before_epoch
        assert live.pair.stop_count("right") == before_count + 1
        stopped.append("right")
        await original_execute(*args, **kwargs)

    with patch.object(services, "_execute_preflighted", execute):
        response = await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
            return_response=True,
        )
    assert response == {} and stopped == ["right"]
    assert not mutations(live.events)
    assert not any(packet == bytes.fromhex("6e01006edd") for _side, packet in live.events)
    assert not any(child.is_connected for child in live.children.values())


@pytest.mark.parametrize("phase", ("before-first", "between-windows"))
async def test_interrupted_list_refuses_incomplete_response(hass, live_pair, protocol_time, phase):
    live = await live_pair("sequential")
    original_execute = services._execute_preflighted
    original_observe = bed.MajesticHomeController.execute_prepared
    interrupted = []

    async def execute(*args, **kwargs):
        if phase == "before-first":
            await live.pair.async_stop_command()
            interrupted.append("before-first")
        await original_execute(*args, **kwargs)

    async def observe(ctrl, plan, **kwargs):
        observed = await original_observe(ctrl, plan, **kwargs)
        if phase == "between-windows" and ctrl is live.children["left"].controller:
            await live.pair.async_stop_command(side="right")
            interrupted.append("between-windows")
        return observed

    with (
        patch.object(services, "_execute_preflighted", execute),
        patch.object(bed.MajesticHomeController, "execute_prepared", observe),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {
                "device_id": live.parent,
                "operation": "list",
            },
            blocking=True,
            return_response=True,
        )
    assert interrupted == [phase]
    assert not mutations(live.events)
    lists = [(side, packet) for side, packet in live.events if packet == bed.LIST_ALARMS]
    assert [side for side, _ in lists] == ([] if phase == "before-first" else ["left"])
    assert all(child._command_connection_holds == 0 for child in live.children.values())


@pytest.mark.parametrize("operation", ("new", "set", "toggle", "delete"))
async def test_non_list_optional_response_is_an_empty_mapping(
    hass, runtime, protocol_time, operation
):
    target, client, _ = runtime
    timers, _ = standalone_replies(target, client)
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    try:
        response = await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {
                "device_id": "bed",
                "operation": operation,
                "alarm_id": 1,
                "enabled": False,
            },
            blocking=True,
            return_response=True,
        )
        assert response == {}
        expected = {
            "new": "6e0d200501010100071e2e00f6",
            "set": "6e0d200501010100071e2e00f6",
            "toggle": "6e0d200501010163162dfa82c5",
            "delete": "6e0820050201019f",
        }
        assert written(target)[-1] == expected[operation]
    finally:
        for timer in timers:
            timer.cancel()
