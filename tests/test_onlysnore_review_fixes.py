"""S1-S3: physical alarm owners, elapsed demos and late native HA entities."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.onlysnore import services as app_services
from custom_components.adjustable_bed.beds.onlysnore import state_keys as keys
from custom_components.adjustable_bed.beds.onlysnore.controller import OnlySnoreController
from custom_components.adjustable_bed.codec import onlysnore as codec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import async_register_children
from custom_components.adjustable_bed.paired_topology import PairedSideError
from tests.hold_lease_wire import virtual_clock
from tests.test_onlysnore import controller as transport_template

THREE = bytes.fromhex("a50a08000000000003")
ONE = bytes.fromhex("a50a08000000000001")
ALARM_TWO = bytes.fromhex("a50d08007f05071e000101")


@dataclass
class Receiver:
    coordinator: AdjustableBedCoordinator
    entry: MockConfigEntry
    clients: list

    @property
    def mutations(self):
        return [
            call.args[1]
            for client in self.clients
            for call in client.write_gatt_char.call_args_list
            if call.args[1][:2] == b"\x07\x05"
        ]


async def connect(receiver: Receiver):
    coordinator = receiver.coordinator
    if coordinator.controller is not None and coordinator.is_connected:
        return True
    client = transport_template().client
    client.address = coordinator.address

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    receiver.clients.append(client)
    coordinator._client = client
    try:
        coordinator._controller = await create_controller(coordinator, "onlysnore", None, client)
        coordinator._position_connection_generation += 1
        coordinator._connection_creator_task = asyncio.current_task()
        await coordinator.controller.start_notify()
    except BaseException:
        await client.disconnect()
        if coordinator._client is client:
            coordinator._client = None
            coordinator._controller = None
            coordinator._connection_creator_task = None
        raise
    return True


@asynccontextmanager
async def receivers(
    hass, *, topology="standalone", online=(True, False), address_prefix="AA:BB:CC:DD:17"
):
    app_services.register_services(hass)
    items = []
    registry = dr.async_get(hass)
    devices = []
    for index, connected in enumerate(online, 1):
        address = f"{address_prefix}:{index:02X}"
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=5,
            title=f"OnlySnore {index}",
            data={
                "address": address,
                "bed_type": "onlysnore",
                "profile_id": "onlysnore",
                "product_type": "single",
                "disable_angle_sensing": True,
                "idle_disconnect_seconds": 0,
                "capabilities": {"onlysnore": {"alarm_count": 1}},
            },
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        coordinator = AdjustableBedCoordinator(hass, entry)
        item = Receiver(coordinator, entry, [])

        # Only radio connection establishment is replaced. Construction,
        # scheduler admission, route validation, writes and disconnect are real.
        async def ensure_connected(*, receiver=item, **_kwargs):
            return await connect(receiver)

        coordinator.async_ensure_connected = AsyncMock(side_effect=ensure_connected)
        coordinator.async_connect = AsyncMock(side_effect=ensure_connected)
        items.append(item)
        coordinator._offline_controller = await create_controller(
            coordinator, "onlysnore", None, None
        )
        if connected:
            await connect(item)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        devices.append(
            registry.async_get_or_create(config_entry_id=entry.entry_id, **coordinator.device_info)
        )
    pair = None
    if topology != "standalone":
        entry = MockConfigEntry(domain=DOMAIN, version=5, data={"pair_id": "onlysnore-review-pair"})
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        pair = PairedBedCoordinator(
            hass,
            entry,
            dict(zip(("left", "right"), (item.coordinator for item in items), strict=True)),
            connection_mode=topology,
        )
        hass.data[DOMAIN][entry.entry_id] = pair
        parent = registry.async_get_or_create(config_entry_id=entry.entry_id, **pair.device_info)
        async_register_children(hass, pair)
        assert len(dr.async_child_entries_for_config_entry(registry, entry.entry_id)) == 2
        assert (
            registry.async_get_device_by_identifier(
                next(iter(pair.device_info["identifiers"])), entry.entry_id
            )
            is not None
        )
        device_ids = [parent.id]
    else:
        device_ids = [device.id for device in devices]
    try:
        yield items, device_ids, pair
    finally:
        for item in items:
            await item.coordinator.async_shutdown()
            assert item.coordinator._connection_creator_task is None
        if pair is not None:
            assert pair._sequential._cycle is None


async def alarm(hass, ids, *, slot=1):
    await hass.services.async_call(
        DOMAIN,
        "onlysnore_set_alarm",
        {"device_id": ids, "time": "07:30", "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], "slot": slot},
        blocking=True,
    )


@asynccontextmanager
async def paused_factory(second, *, fail=False):
    entered, release, drained = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = create_controller

    async def construct(coordinator, *args, **kwargs):
        nonlocal fail
        if coordinator is second:
            entered.set()
            try:
                await release.wait()
                if fail:
                    fail = False
                    raise ConnectionError("peer factory failed")
            finally:
                drained.set()
        return await original(coordinator, *args, **kwargs)

    with patch(__name__ + ".create_controller", construct):
        try:
            yield entered, release, drained
        finally:
            release.set()


@pytest.mark.parametrize("topology", ["standalone", "concurrent", "sequential"])
async def test_mixed_live_and_valid_offline_physical_receivers(hass, topology):
    async with receivers(hass, topology=topology) as (items, ids, _pair):
        admitted = items[0].coordinator.controller
        assert items[1].coordinator.controller is None
        with virtual_clock():
            try:
                await alarm(hass, ids)
            except PairedSideError as error:
                pytest.fail(f"Mixed physical receiver failure: {error.side_errors!r}")
        assert items[0].mutations == items[1].mutations == [bytes.fromhex("07057f01071e000101")]
        assert items[1].clients
        # Concurrent and standalone retain the admitted live controller;
        # sequential topology may intentionally release its completed side.
        if topology != "sequential":
            assert items[0].coordinator.controller is admitted


@pytest.mark.parametrize("left_connected", [False, True])
async def test_sequential_alarm_switches_from_connected_right_to_both_receivers(
    hass, left_connected
):
    async with receivers(hass, topology="sequential", online=(left_connected, True)) as (
        items,
        ids,
        _pair,
    ):
        original_right = items[1].coordinator.controller
        with virtual_clock():
            await alarm(hass, ids)
        assert items[0].mutations == items[1].mutations == [bytes.fromhex("07057f01071e000101")]
        assert items[1].coordinator.last_disconnect_reason == "sequential_switch"
        assert original_right is not items[1].coordinator.controller
        assert len(items[0].clients) == 1 and len(items[1].clients) == 2
        assert not items[1].clients[0].write_gatt_char.call_args_list
        for item in items:
            item.coordinator.async_connect.assert_awaited_once()
        assert all(not client.is_connected for item in items for client in item.clients)


@pytest.mark.parametrize(
    "drift", ["disconnect", "reconnect", "replacement", "product", "address", "roster"]
)
async def test_sequential_alarm_rejects_external_session_or_selection_change(hass, drift):
    async with receivers(hass, topology="sequential", online=(False, True)) as (items, ids, pair):
        right = items[1].coordinator
        entered, release = asyncio.Event(), asyncio.Event()
        original = pair._topology._release_other_sides

        async def paused_switch(keep):
            entered.set()
            await release.wait()
            return await original(keep)

        with patch.object(pair._topology, "_release_other_sides", paused_switch), virtual_clock():
            task = asyncio.create_task(alarm(hass, ids))
            try:
                await entered.wait()
                if drift in ("disconnect", "reconnect"):
                    await right.async_disconnect()
                    if drift == "reconnect":
                        await connect(items[1])
                elif drift == "replacement":
                    right._controller = OnlySnoreController(right, "single")
                elif drift == "product":
                    hass.config_entries.async_update_entry(
                        right.entry, data={**right.entry.data, "product_type": "double"}
                    )
                elif drift == "address":
                    right._address = "AA:BB:CC:DD:17:99"
                else:
                    pair._children["right"] = items[0].coordinator
                release.set()
                with pytest.raises(PairedSideError) as error:
                    async with asyncio.timeout(1):
                        await task
                assert error.value.side_errors
                assert all(
                    isinstance(cause, ServiceValidationError)
                    for cause in error.value.side_errors.values()
                )
                assert all(not item.mutations for item in items)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_sequential_alarm_stop_before_planned_switch_writes_no_alarm(hass):
    async with receivers(hass, topology="sequential", online=(False, True)) as (items, ids, pair):
        entered, release = asyncio.Event(), asyncio.Event()
        original = pair._topology._release_other_sides

        async def paused_switch(keep):
            entered.set()
            await release.wait()
            return await original(keep)

        with patch.object(pair._topology, "_release_other_sides", paused_switch), virtual_clock():
            task = asyncio.create_task(alarm(hass, ids))
            try:
                await entered.wait()
                await pair.async_stop_command()
                release.set()
                async with asyncio.timeout(1):
                    await task
                assert all(not item.mutations for item in items)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_sequential_alarm_rejects_diagnostic_connect_after_planned_release(hass):
    async with receivers(hass, topology="sequential", online=(False, True)) as (items, ids, _pair):
        left, right = (item.coordinator for item in items)
        original = OnlySnoreController.set_alarm

        async def connect_peer(ctrl, **kwargs):
            await original(ctrl, **kwargs)
            if ctrl._coordinator is left:
                # The diagnostic Connect button uses this same public method
                # on its own task, outside the sequential operation.
                await asyncio.create_task(right.async_connect())

        with (
            patch.object(OnlySnoreController, "set_alarm", connect_peer),
            virtual_clock(),
            pytest.raises(PairedSideError) as error,
        ):
            await alarm(hass, ids)
        assert isinstance(error.value.side_errors["right"], ServiceValidationError)
        assert items[0].mutations == [bytes.fromhex("07057f01071e000101")]
        assert not items[1].mutations


async def test_standalone_then_sequential_pair_retains_each_planned_release(hass):
    async with (
        receivers(hass, topology="sequential", online=(False, True)) as (items, ids, _pair),
        receivers(hass, online=(True,), address_prefix="AA:BB:CC:DD:18") as (
            standalone,
            standalone_ids,
            _unused,
        ),
    ):
        with virtual_clock():
            await alarm(hass, standalone_ids + ids)
        assert all(
            item.mutations == [bytes.fromhex("07057f01071e000101")]
            for item in [*standalone, *items]
        )


async def test_right_only_stop_after_release_fences_left_before_alarm_write(hass):
    async with receivers(hass, topology="sequential", online=(False, True)) as (items, ids, pair):
        left, right = (item.coordinator for item in items)
        entered, release = asyncio.Event(), asyncio.Event()
        original = left.async_execute_controller_command

        async def paused_command(command, **kwargs):
            entered.set()
            await release.wait()
            await original(command, **kwargs)

        with (
            patch.object(left, "async_execute_controller_command", paused_command),
            virtual_clock(),
        ):
            task = asyncio.create_task(alarm(hass, ids))
            try:
                await entered.wait()
                assert not right.is_connected
                epochs = (left.stop_epoch, right.stop_epoch)
                await pair.async_stop_command(side="right")
                assert (left.stop_epoch, right.stop_epoch) == epochs
                release.set()
                with pytest.raises(PairedSideError) as error:
                    async with asyncio.timeout(1):
                        await task
                assert isinstance(error.value.side_errors["left"], ServiceValidationError)
                assert all(not item.mutations for item in items)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_concurrent_alarm_waits_for_offline_construction_before_any_mutation(hass):
    async with receivers(hass, topology="concurrent") as (items, ids, _pair):
        second = items[1].coordinator
        async with paused_factory(second) as (entered, release, drained):
            with virtual_clock():
                task = asyncio.create_task(alarm(hass, ids))
                try:
                    await entered.wait()
                    await asyncio.sleep(0)
                    assert second.client is not None and second.controller is None
                    assert not task.done()
                    assert all(not item.mutations for item in items)
                    release.set()
                    await task
                    assert drained.is_set()
                    assert (
                        items[0].mutations
                        == items[1].mutations
                        == [bytes.fromhex("07057f01071e000101")]
                    )
                finally:
                    release.set()
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)


async def test_concurrent_alarm_stop_drains_waiting_cohort_without_alarm_mutation(hass):
    async with receivers(hass, topology="concurrent") as (items, ids, pair):
        scheduler = items[0].coordinator._command_scheduler
        admitted = asyncio.Event()
        original_stop = scheduler.admit_stop
        stop_epoch = items[0].coordinator.stop_epoch

        def admit_stop(*args, **kwargs):
            result = original_stop(*args, **kwargs)
            admitted.set()
            return result

        async with paused_factory(items[1].coordinator) as (entered, release, drained):
            with patch.object(scheduler, "admit_stop", admit_stop), virtual_clock():
                task = asyncio.create_task(alarm(hass, ids))
                stop = None
                try:
                    await entered.wait()
                    await asyncio.sleep(0)
                    assert not task.done() and all(not item.mutations for item in items)
                    async with asyncio.timeout(1):
                        stop = asyncio.create_task(pair.async_stop_command())
                        await admitted.wait()
                        assert items[0].coordinator.stop_epoch > stop_epoch
                        release.set()
                        await stop
                        await task
                    assert task.done() and stop.done() and drained.is_set()
                    assert all(not item.mutations for item in items)
                finally:
                    release.set()
                    for pending in (task, stop):
                        if pending is not None and not pending.done():
                            pending.cancel()
                    await asyncio.gather(
                        *(pending for pending in (task, stop) if pending is not None),
                        return_exceptions=True,
                    )
    assert all(not client.is_connected for item in items for client in item.clients)
    assert all(
        item.coordinator._command_scheduler._worker is None
        or item.coordinator._command_scheduler._worker.done()
        for item in items
    )


async def test_concurrent_alarm_peer_factory_failure_drains_waiting_cohort(hass):
    async with (
        receivers(hass, topology="concurrent") as (items, ids, _pair),
        paused_factory(items[1].coordinator, fail=True) as (entered, release, drained),
    ):
        with virtual_clock():
            task = asyncio.create_task(alarm(hass, ids))
            try:
                await entered.wait()
                await asyncio.sleep(0)
                assert not task.done() and all(not item.mutations for item in items)
                release.set()
                with pytest.raises(PairedSideError) as error:
                    async with asyncio.timeout(1):
                        await task
                assert isinstance(error.value.side_errors["right"], ConnectionError)
                assert str(error.value.side_errors["right"]) == "peer factory failed"
                assert task.done() and drained.is_set()
                assert all(not item.mutations for item in items)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert all(not client.is_connected for item in items for client in item.clients)
    assert all(
        item.coordinator._command_scheduler._worker is None
        or item.coordinator._command_scheduler._worker.done()
        for item in items
    )


@pytest.mark.parametrize("topology", ["standalone", "concurrent", "sequential"])
async def test_later_invalid_slot_preflights_before_any_alarm_mutation(hass, topology):
    async with receivers(hass, topology=topology) as (items, ids, _pair):
        items[0].coordinator.controller._alarm_count = 3
        with pytest.raises(Exception, match="slot"), virtual_clock():
            await alarm(hass, ids, slot=2)
        assert all(not item.mutations for item in items)
        assert not items[1].clients


@pytest.mark.parametrize("drift", ["controller", "session", "route", "product", "foreign_receiver"])
async def test_all_target_barrier_rejects_drift_after_preflight_before_first_mutation(hass, drift):
    async with receivers(hass) as (items, ids, _pair):
        first, second = (item.coordinator for item in items)
        entered, release = asyncio.Event(), asyncio.Event()
        original = first.async_execute_controller_command

        async def wait_for_drift(command, **kwargs):
            entered.set()
            await release.wait()
            await original(command, **kwargs)

        first.async_execute_controller_command = wait_for_drift
        task = asyncio.create_task(alarm(hass, ids))
        try:
            await entered.wait()
            if drift == "controller":
                first._controller = OnlySnoreController(first, "single")
            elif drift == "session":
                first.controller._generation += 1
            elif drift in ("route", "product"):
                field, value = (
                    ("protocol_variant", "changed")
                    if drift == "route"
                    else ("product_type", "double")
                )
                hass.config_entries.async_update_entry(
                    second.entry, data={**second.entry.data, field: value}
                )
            else:
                await connect(items[1])
                second._controller = OnlySnoreController(first, "single")
            release.set()
            with pytest.raises(Exception, match="BED|receiver"), virtual_clock():
                await task
            assert all(not item.mutations for item in items)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_native_paired_roster_replacement_invalidates_the_whole_selection(hass):
    async with receivers(hass, topology="concurrent") as (items, ids, pair):
        first = items[0].coordinator
        original = first.async_execute_controller_command

        async def replace_roster(command, **kwargs):
            pair._children["right"] = first
            await original(command, **kwargs)

        first.async_execute_controller_command = replace_roster
        with pytest.raises(PairedSideError) as error, virtual_clock():
            await alarm(hass, ids)
        assert error.value.side_errors
        assert all(
            isinstance(cause, ServiceValidationError) and "roster" in str(cause)
            for cause in error.value.side_errors.values()
        )
        assert all(not item.mutations for item in items)


async def test_stop_during_lazy_import_cannot_start_any_mixed_receiver(hass):
    async with receivers(hass) as (items, ids, _pair):
        entered, release = asyncio.Event(), asyncio.Event()
        original = app_services.async_import_modules

        async def delayed_import(*args):
            entered.set()
            await release.wait()
            await original(*args)

        with patch.object(app_services, "async_import_modules", delayed_import):
            task = asyncio.create_task(alarm(hass, ids))
            try:
                await entered.wait()
                with virtual_clock():
                    await items[0].coordinator.async_stop_command()
                release.set()
                with pytest.raises(Exception, match="STOP|ownership"):
                    await task
                assert all(not item.mutations for item in items)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("completion_delay", [0.12, 0.4])
async def test_demo_elapsed_deadline_includes_initial_inflight_write(hass, completion_delay):
    async with receivers(hass, online=(True,)) as (items, _ids, _pair):
        receiver = items[0]
        ctrl = receiver.coordinator.controller
        client = ctrl.client
        original = client.write_gatt_char
        writes = []

        async def delayed_write(characteristic, frame, **kwargs):
            writes.append((asyncio.get_running_loop().time(), frame))
            await original(characteristic, frame, **kwargs)
            if frame == codec.intervention(2, 1):
                await asyncio.sleep(completion_delay)

        client.write_gatt_char = AsyncMock(side_effect=delayed_write)
        with virtual_clock():
            await ctrl.demo(duration_ms=200)
        assert [frame for _at, frame in writes] == [
            codec.intervention(2, 1),
            codec.INTERVENTION_STOP,
        ]
        assert writes[-1][0] - writes[0][0] == pytest.approx(0.2)


async def test_demo_deadline_cleanup_drains_repeated_cancellation(hass):
    async with receivers(hass, online=(True,)) as (items, _ids, _pair):
        ctrl = items[0].coordinator.controller
        client = ctrl.client
        transmitted, stopping, finish_stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        writes = []

        async def write(_characteristic, frame, **_kwargs):
            writes.append(frame)
            if frame == codec.INTERVENTION_STOP:
                stopping.set()
                await finish_stop.wait()
            else:
                transmitted.set()
                await asyncio.Event().wait()

        client.write_gatt_char = AsyncMock(side_effect=write)
        task = asyncio.create_task(ctrl.demo())
        try:
            await transmitted.wait()
            task.cancel()
            await stopping.wait()
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            finish_stop.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            finish_stop.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert writes == [codec.intervention(2, 1), codec.INTERVENTION_STOP]


async def test_real_forwarded_platforms_discover_late_alarm_slots_and_keep_disconnect_ids(
    hass, enable_custom_integrations
):
    async with receivers(hass, online=(True,)) as (items, _ids, _pair):
        receiver = items[0]
        coord, entry = receiver.coordinator, receiver.entry
        ctrl = coord.controller
        platforms = (Platform.SENSOR, Platform.BINARY_SENSOR)
        hass.config.components.add(DOMAIN)
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
        await hass.async_block_till_done()
        registry = er.async_get(hass)

        def entity_id(domain, key):
            return registry.async_get_entity_id(domain, DOMAIN, coord.entity_unique_id(str(key)))

        assert entity_id("sensor", keys.ALARM_TIME[1]) is None
        char, callback = ctrl.client.start_notify.call_args.args
        try:
            with patch.object(hass.config_entries, "async_schedule_reload") as reload:
                callback(char, bytearray(THREE))
                await hass.async_block_till_done()
                ids = {str(key): entity_id("sensor", key) for key in keys.ALARM_TIME}
                assert all(ids.values())
                callback(char, bytearray(ALARM_TWO))
                await hass.async_block_till_done()
                alarm = hass.states.get(ids[str(keys.ALARM_TIME[1])])
                assert alarm.state == "07:30"
                assert alarm.attributes[str(keys.ALARM_OPEN[1])] is True
                await coord.async_disconnect()
                await hass.async_block_till_done()
                assert ctrl._alarm_count == 3
                assert coord.controller_state.get(keys.ALARM_TIME[1]) is None
                for key in keys.ALARM_TIME:
                    assert entity_id("sensor", key) == ids[str(key)]
                reload.assert_not_called()
        finally:
            await hass.config_entries.async_unload_platforms(entry, platforms)


async def test_explicit_alarm_count_withdrawal_clears_state_and_revokes_slot_permission(hass):
    async with receivers(hass, online=(True,)) as (items, _ids, _pair):
        coord = items[0].coordinator
        ctrl = coord.controller
        char, callback = ctrl.client.start_notify.call_args.args
        callback(char, bytearray(THREE))
        callback(char, bytearray(ALARM_TWO))
        assert coord.controller_state.get(keys.ALARM_OPEN[1]) is True
        callback(char, bytearray(ONE))
        assert ctrl._alarm_count == 1 and 1 not in ctrl._alarms
        assert coord.controller_state.get(keys.ALARM_TIME[1]) is None
        assert coord.controller_state.get(keys.ALARM_OPEN[1]) is None
        with pytest.raises(ValueError, match="slot"):
            ctrl.alarm_frame(2, True, 7, 30, 127, 0, False)
