"""Registry retirement and current-owner polling across public command boundaries."""
import asyncio
from dataclasses import replace

import pytest
from bleak.exc import BleakError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed.controller import MotionBedController
from custom_components.adjustable_bed.beds.motion_bed.models import select_motion_bed
from custom_components.adjustable_bed.beds.motion_bed.protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.beds.solace.controller import SolaceController
from custom_components.adjustable_bed.const import DOMAIN
from tests.test_entity_sweep import async_setup_platforms_and_sweep
from tests.test_motion_bed_lifecycle import real_coordinator


@pytest.mark.parametrize("replacement", ["W2", "different_protocol"])
async def test_motion_layout_covers_retire_without_losing_active_customization(hass, replacement):
    coord = await real_coordinator(hass, "QMS-IQ")
    registry = er.async_get(hass)
    old_key = "motion_bed_hip"  # W1-only axis
    old = registry.async_get_or_create("cover", DOMAIN, coord.entity_unique_id(old_key), config_entry=coord.entry)
    if replacement == "W2":
        coord._controller = MotionBedController(coord, selection=select_motion_bed("QMS-IQ", movement_override="W2"))
    else:
        coord._controller = SolaceController(coord)
    active_key = coord.controller.motor_control_specs[0].key
    active = registry.async_get_or_create("cover", DOMAIN, coord.entity_unique_id(active_key), config_entry=coord.entry)
    active = registry.async_update_entity(active.entity_id, name="My motor", disabled_by=er.RegistryEntryDisabler.USER)
    other_entry = MockConfigEntry(domain=DOMAIN, data={})
    other_entry.add_to_hass(hass)
    unrelated = registry.async_get_or_create("cover", DOMAIN, "other_" + old.unique_id, config_entry=other_entry)
    other_platform = registry.async_get_or_create("cover", "unrelated", old.unique_id, config_entry=coord.entry)
    entities = await async_setup_platforms_and_sweep(hass, coord.entry, coord)
    assert old.unique_id not in {entity.unique_id for entity in entities}
    assert registry.async_get(old.entity_id) is None
    assert registry.async_get(active.entity_id) == active
    for row in (unrelated, other_platform):
        assert registry.async_get(row.entity_id) == row
    assert coord.client.write_gatt_char.await_count == 0
    coord._cancel_disconnect_timer()



@pytest.mark.parametrize("failure", ["ble", "connection", "timeout", "preemption"])
async def test_thermal_poll_retries_only_at_existing_cadence_after_query_interruption(hass, monkeypatch, failure):
    coord = await real_coordinator(hass, "TL-Q")
    controller = coord.controller
    controller._state = replace(controller._state, thermal_module_present=True)
    controller._active_module = "thermal"
    controller._started_modules.add("thermal")
    real_sleep = asyncio.sleep
    retry, second_spacing, retry_gate = asyncio.Event(), asyncio.Event(), asyncio.Event()
    delays = []

    async def sleep(delay):
        delays.append(delay)
        if delay == 5:
            if not retry.is_set():
                retry.set()
                await retry_gate.wait()
            else:
                second_spacing.set()
                await asyncio.Event().wait()
        else:
            await real_sleep(0)

    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    if failure == "preemption":
        await coord._command_lock.acquire()
    else:
        error = {"ble": BleakError("temporary status failure"), "connection": ConnectionError("temporary link failure"), "timeout": TimeoutError("temporary ATT timeout")}[failure]
        coord.client.write_gatt_char.side_effect = [error, None]
    poll = asyncio.create_task(controller._thermal_poll())
    controller._thermal_task = poll
    try:
        if failure == "preemption":
            for _ in range(20):
                await real_sleep(0)
            command_ran = asyncio.Event()
            async def command(current_controller):
                command_ran.set()
            movement = asyncio.create_task(coord.async_execute_controller_command(command, cancel_running=True))
            for _ in range(20):
                await real_sleep(0)
            coord._command_lock.release()
            await movement
            assert command_ran.is_set()
        await asyncio.wait_for(retry.wait(), 1)
        assert not poll.done()
        assert controller._thermal_task is poll and "thermal" in controller._started_modules
        assert coord._command_connection_holds == 1
        assert delays == [2, 5]
        retry_gate.set()
        await asyncio.wait_for(second_spacing.wait(), 1)
        assert coord.client.write_gatt_char.await_args.args[1] == SOURCE_COMMANDS["LengnuanFragment:58"]
        assert delays == [2, 5, 5]
        assert coord._command_connection_holds == 1
    finally:
        poll.cancel()
        await asyncio.gather(poll, return_exceptions=True)
        assert coord._command_connection_holds == 0
        coord._cancel_disconnect_timer()
        await coord._command_scheduler.async_shutdown()


@pytest.mark.parametrize("ending", ["cancel", "replacement"])
async def test_thermal_poll_terminal_owner_loss_does_not_retry(hass, monkeypatch, ending):
    coord = await real_coordinator(hass, "TL-Q")
    controller = coord.controller
    controller._state = replace(controller._state, thermal_module_present=True)
    controller._active_module = "thermal"
    real_sleep = asyncio.sleep
    delays = []
    async def sleep(delay):
        delays.append(delay)
        await real_sleep(0)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    await coord._command_lock.acquire()
    poll = asyncio.create_task(controller._thermal_poll())
    for _ in range(20):
        await real_sleep(0)
    assert coord._command_connection_holds == 1
    if ending == "cancel":
        poll.cancel()
    else:
        coord._controller = MotionBedController(coord, selection=select_motion_bed("QMS-IQ"))
    coord._command_lock.release()
    if ending == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await poll
    else:
        await poll
    assert coord._command_connection_holds == 0
    assert delays == [2]
    coord.client.write_gatt_char.assert_not_awaited()
    coord._cancel_disconnect_timer()
    await coord._command_scheduler.async_shutdown()


