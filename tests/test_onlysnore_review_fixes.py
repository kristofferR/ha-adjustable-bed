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
    coordinator._controller = await create_controller(coordinator, "onlysnore", None, client)
    coordinator._position_connection_generation += 1
    await coordinator.controller.start_notify()
    return True


@asynccontextmanager
async def receivers(hass, *, topology="standalone", online=(True, False)):
    app_services.register_services(hass)
    items = []
    registry = dr.async_get(hass)
    devices = []
    for index, connected in enumerate(online, 1):
        address = f"AA:BB:CC:DD:17:{index:02X}"
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


async def alarm(hass, ids, *, slot=1):
    await hass.services.async_call(
        DOMAIN,
        "onlysnore_set_alarm",
        {"device_id": ids, "time": "07:30", "week_mask": 127, "slot": slot},
        blocking=True,
    )


@pytest.mark.parametrize("topology", ["standalone", "concurrent", "sequential"])
async def test_mixed_live_and_valid_offline_physical_receivers(hass, topology):
    async with receivers(hass, topology=topology) as (items, ids, _pair):
        admitted = items[0].coordinator.controller
        assert items[1].coordinator.controller is None
        with virtual_clock():
            await alarm(hass, ids)
        assert items[0].mutations == items[1].mutations == [bytes.fromhex("07057f01071e000101")]
        assert items[1].clients
        # Concurrent and standalone retain the admitted live controller;
        # sequential topology may intentionally release its completed side.
        if topology != "sequential":
            assert items[0].coordinator.controller is admitted


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
                ids = {
                    str(key): entity_id(domain, key)
                    for domain, group in (
                        ("sensor", keys.ALARM_TIME),
                        ("binary_sensor", keys.ALARM_OPEN),
                    )
                    for key in group
                }
                assert all(ids.values())
                callback(char, bytearray(ALARM_TWO))
                await hass.async_block_till_done()
                assert hass.states.get(ids[str(keys.ALARM_TIME[1])]).state == "07:30"
                assert hass.states.get(ids[str(keys.ALARM_OPEN[1])]).state == "on"
                await coord.async_disconnect()
                await hass.async_block_till_done()
                assert ctrl._alarm_count == 3
                assert coord.controller_state.get(keys.ALARM_TIME[1]) is None
                for domain, group in (
                    ("sensor", keys.ALARM_TIME),
                    ("binary_sensor", keys.ALARM_OPEN),
                ):
                    for key in group:
                        assert entity_id(domain, key) == ids[str(key)]
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
