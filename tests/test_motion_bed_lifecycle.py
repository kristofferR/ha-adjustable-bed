"""Real disconnect admission and original-target release for Motion Bed work."""
import asyncio
from contextlib import suppress
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed import STOP, MotionBedController
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_MOTION_BED_NAME,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from custom_components.adjustable_bed.motion_bed_state import MotionBedFollowup
from tests.test_motion_bed_controller import characteristic, client_for, rig_for


async def real_coordinator(hass, name):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_MOTION_BED_NAME: name})
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    coord._client = client_for(characteristic(29))
    coord._controller = MotionBedController(coord, selection=select_motion_bed(name))
    coord._controller._startup = AsyncMock()
    coord._auto_reconnect_enabled = lambda: False
    await coord.controller.async_discover_capabilities()
    return coord


@pytest.mark.parametrize("intentional", [False, True])
@pytest.mark.parametrize("family", ["followup", "thermal", "network", "module"])
async def test_actual_disconnect_invalidates_each_owned_family_before_reference_clear(hass, intentional, family):
    coord = await real_coordinator(hass, "TL-Q" if family == "module" else "TL-W" if family == "thermal" else "QMS-IQ")
    controller = coord.controller
    old_client = coord.client
    entered = asyncio.Event()
    async def pending_query(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    coord.async_execute_controller_query = AsyncMock(side_effect=pending_query)
    if family == "followup":
        async def operation():
            await controller._followup(MotionBedFollowup("position_query", 25))
    elif family == "thermal":
        operation = controller._thermal_poll
    elif family == "network":
        controller._state = replace(controller._state, provisioning_status="waiting")
        operation = controller._network_poll
    else:
        controller._state = replace(controller._state, thermal_module_present=True)
        operation = controller._start_present_modules
    controller._spawn(operation)
    tasks = tuple(controller._tasks)
    await asyncio.sleep(0)
    generation = controller._generation
    coord._intentional_disconnect = intentional
    old_client.is_connected = False
    coord._on_disconnect(old_client)
    assert controller._generation > generation
    assert coord.controller is None and coord.client is None
    assert not controller._tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    assert all(task.cancelled() for task in tasks)
    old_client.write_gatt_char.assert_not_awaited()
    assert controller._session_client is None


async def test_stale_client_disconnect_does_not_invalidate_current_motion_bed(hass):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller, client = coord.controller, coord.client
    generation = controller._generation
    coord._on_disconnect(client_for(characteristic(90)))
    assert controller._generation == generation
    assert coord.controller is controller and coord.client is client


async def test_query_queued_before_actual_disconnect_is_rejected_before_reconnect(hass):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller, client = coord.controller, coord.client
    coord._async_prepare_controller_operation = AsyncMock()
    coord._async_finish_controller_operation = AsyncMock()
    await coord._command_lock.acquire()
    task = asyncio.create_task(controller._followup(MotionBedFollowup("position_query")))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    client.is_connected = False
    coord._on_disconnect(client)
    coord._command_lock.release()
    await task
    coord._async_prepare_controller_operation.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("family", ["followup", "thermal", "network", "module"])
async def test_every_owned_query_has_admission_gate_and_rejects_replacement_callback(monkeypatch, family):
    old = rig_for("TL-Q" if family == "module" else "TL-W" if family == "thermal" else "QMS-IQ")
    replacement = rig_for()
    await old.controller.async_discover_capabilities()
    await replacement.controller.async_discover_capabilities()
    async def sleep(delay):
        pass
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    calls = []
    async def query(callback, **kwargs):
        assert callable(kwargs["run_if"]) and kwargs["run_if"]()
        calls.append(callback)
        await callback(replacement.controller)
        if family == "thermal":
            old.controller._generation += 1
    old.coordinator.async_execute_controller_query = AsyncMock(side_effect=query)
    if family == "followup":
        await old.controller._followup(MotionBedFollowup("position_query"))
    elif family == "thermal":
        await old.controller._thermal_poll()
    elif family == "network":
        old.controller._state = replace(old.controller._state, provisioning_status="waiting")
        await old.controller._network_poll()
    else:
        old.controller._state = replace(old.controller._state, thermal_module_present=True)
        await old.controller._start_present_modules()
    assert calls
    assert not old.writes and not replacement.writes


@pytest.mark.parametrize("sleep_adjust", [False, True])
@pytest.mark.parametrize("old_connected", [False, True])
@pytest.mark.parametrize("characteristic_only", [False, True])
async def test_held_cleanup_releases_exact_original_binding_once_without_replacement_query(sleep_adjust, old_connected, characteristic_only):
    old = rig_for()
    await old.controller.async_discover_capabilities()
    holding, release = asyncio.Event(), asyncio.Event()
    async def hold(*args, **kwargs):
        holding.set()
        await release.wait()
    old.controller._hold = hold
    key = "sleep_adjust_activity_adjust_back_up" if sleep_adjust else "weitiao_w1fragment_back_up"
    task = asyncio.create_task(old.controller.async_execute_motion_bed_action(key))
    await holding.wait()
    old.client.is_connected = old_connected
    if characteristic_only:
        new_char = characteristic(90)
        old.client.services = [type("Service", (), {"characteristics": [new_char]})()]
        if old_connected:
            await old.controller.async_discover_capabilities()
        else:
            old.controller.on_disconnect()
        replacement = old.client
    else:
        replacement = client_for(characteristic(90))
        old.coordinator.address = "AA:BB:CC:DD:EE:02"
        old.coordinator.client = replacement
        await old.controller.async_discover_capabilities()
    release.set()
    with suppress(ConnectionError):
        await task
    old_calls = old.client.write_gatt_char.await_args_list
    assert len(old_calls) == (2 if old_connected else 1)
    if old_connected:
        assert old_calls[-1].args[:2] == (old.last, STOP)
    if replacement is not old.client:
        replacement.write_gatt_char.assert_not_awaited()
    else:
        assert all(call.args[0] is old.last for call in old_calls)


async def test_connecting_disconnect_invalidates_owned_work_before_retry_reference_retention(hass):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller, client = coord.controller, coord.client
    controller._spawn(lambda: controller._followup(MotionBedFollowup("position_query", 25)))
    tasks = tuple(controller._tasks)
    await asyncio.sleep(0)
    generation = controller._generation
    coord._connecting = True
    client.is_connected = False
    coord._on_disconnect(client)
    assert controller._generation == generation + 1
    assert coord.controller is controller and coord.client is client
    assert not controller._tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    assert all(task.cancelled() for task in tasks)
    client.write_gatt_char.assert_not_awaited()
