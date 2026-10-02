"""Public and callback boundaries for superseded Motion Bed operations."""
import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed import STOP, MotionBedController
from custom_components.adjustable_bed.button import (
    ControllerActionButton,
    _async_follow_motion_bed_module_actions,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_MOTION_BED_NAME,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from custom_components.adjustable_bed.motion_bed_protocol import SOURCE_COMMANDS, build_thermal_gear
from custom_components.adjustable_bed.motion_bed_requests import MotionBedWrite
from custom_components.adjustable_bed.motion_bed_services import build_motion_bed_request
from custom_components.adjustable_bed.services import async_register_services
from tests.test_motion_bed_controller import rig_for
from tests.test_motion_bed_lifecycle import real_coordinator


async def test_module_startup_failure_can_retry_same_connected_module(monkeypatch):
    rig = rig_for("TL-Q")
    await rig.controller.async_discover_capabilities()
    rig.controller._state = replace(rig.controller._state, motor_module_present=True)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", AsyncMock())
    rig.client.write_gatt_char.side_effect = [ConnectionError("one failed write"), None, None]
    with pytest.raises(ConnectionError):
        await rig.controller._start_present_modules()
    await rig.controller._start_present_modules()
    assert len(rig.writes) == 3
    assert rig.writes[:2] == [SOURCE_COMMANDS["DiandongFragment:319"]] * 2


async def test_new_report_replaces_receiver_context_before_notification():
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    await rig.controller.async_execute_motion_bed_write(MotionBedWrite("sleep_report", (STOP,), "month_report"))
    await rig.controller.async_execute_motion_bed_write(MotionBedWrite("sleep_report", (STOP,), "day_report", historical_day=True))
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF02000414010A1403010203040506"))
    assert rig.controller.protocol_diagnostics["month_days"] is None
    assert rig.controller.protocol_diagnostics["day_total"] == 3
    await rig.controller.async_execute_motion_bed_write(MotionBedWrite("sleep_report", (STOP,), "month_report"))
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF02000414010A1403010203040506"))
    assert rig.controller.protocol_diagnostics["day_total"] is None


@pytest.mark.parametrize("module,expected", [("motor", STOP), ("air", SOURCE_COMMANDS["QinangFragment:302"]), ("thermal", build_thermal_gear(4))])
async def test_hub_stop_routes_current_selected_module(hass, module, expected):
    coord = await real_coordinator(hass, "TL-Q")
    controller = coord.controller
    controller._state = replace(controller._state, motor_module_present=True, air_module_present=True, thermal_module_present=True)
    controller._active_module = module
    await coord.async_stop_command()
    assert [call.args[1] for call in coord.client.write_gatt_char.await_args_list] == [expected]


async def test_public_module_delete_reply_refreshes_remaining_inventory(monkeypatch):
    rig = rig_for("TL-Q")
    await rig.controller.start_notify()
    queued = []
    rig.controller._spawn = queued.append
    rig.controller._state = replace(rig.controller._state, motor_module_present=True, air_module_present=True)
    await rig.controller.async_execute_motion_bed_write(build_motion_bed_request("motion_bed_module", {"operation": "delete", "module_type": 11, "confirmed": True}))
    rig.callback(rig.last, bytearray.fromhex("FFFFFFFF0100281400"))
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", AsyncMock())
    for operation in queued:
        await operation()
    assert rig.writes[-1] == SOURCE_COMMANDS["MainMcuActivity:182"]


async def test_registered_existing_buttons_publish_audio_availability(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_MOTION_BED_NAME: "QMS-IQ"})
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    controller = MotionBedController(coord, selection=select_motion_bed("QMS-IQ"))
    coord._controller = controller
    initial = [ControllerActionButton(coord, spec) for spec in controller.controller_button_specs]
    for index, entity in enumerate(initial):
        entity.hass = hass
        entity.entity_id = f"button.motion_action_{index}"
        entity.async_write_ha_state = MagicMock()
    _async_follow_motion_bed_module_actions(hass, entry, coord, MagicMock(), initial)
    controller._state = replace(controller._state, audio_available=True)
    controller._publish()
    assert initial and all(entity.async_write_ha_state.called for entity in initial)
    await entry._async_process_on_unload(hass)


async def test_switch_away_back_retires_old_thermal_poll(monkeypatch):
    rig = rig_for("TL-Q")
    await rig.controller.async_discover_capabilities()
    rig.controller._state = replace(rig.controller._state, motor_module_present=True, thermal_module_present=True)
    rig.controller._active_module = "thermal"
    real_sleep = asyncio.sleep
    pending = []
    async def sleep(delay):
        if delay in (2, 5):
            event = asyncio.Event()
            pending.append(event)
            await event.wait()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    await rig.controller._module_startup("thermal")
    await real_sleep(0)
    old_poll, = rig.controller._tasks
    # Selection is public; freeze new startup scheduling to inspect old ownership.
    rig.controller._spawn = MagicMock()
    await rig.controller.set_motion_bed_surface("motor")
    await rig.controller.set_motion_bed_surface("thermal")
    pending[0].set()
    await real_sleep(0)
    try:
        assert old_poll.done()
        assert SOURCE_COMMANDS["LengnuanFragment:58"] not in rig.writes
    finally:
        old_poll.cancel()
        await asyncio.gather(old_poll, return_exceptions=True)


async def test_repeat_provisioning_retires_old_poll_and_deadline(monkeypatch):
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    real_sleep = asyncio.sleep
    pending = []
    async def sleep(delay):
        event = asyncio.Event()
        pending.append(event)
        await event.wait()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    request = MotionBedWrite("provision_wifi", (STOP,), "network", confirmed=True, persistent=True, network_poll=True)
    await rig.controller.async_execute_motion_bed_write(request)
    await real_sleep(0)
    old_poll, = rig.controller._tasks
    await rig.controller.async_execute_motion_bed_write(request)
    await real_sleep(0)
    try:
        assert old_poll.done()
        assert rig.controller._network_poll_active
        assert rig.controller.protocol_diagnostics["provisioning_status"] == "waiting"
        assert len([t for t in rig.controller._tasks if not t.done()]) == 1
    finally:
        tasks = tuple(rig.controller._tasks)
        await rig.controller.stop_notify()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_registered_report_service_keeps_new_receiver_on_actual_scheduler(hass):
    coord = await real_coordinator(hass, "QMS-IQ")
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(coord, SIDE_BOTH)], [])):
        for kind in ("month", "day"):
            await hass.services.async_call(DOMAIN, "motion_bed_sleep_report", {"device_id": "bed", "kind": kind}, blocking=True)
    coord.controller._handle_notification(bytes.fromhex("FFFFFFFF02000414010A1403010203040506"))
    assert coord.controller.protocol_diagnostics["month_days"] is None
    assert coord.controller.protocol_diagnostics["day_total"] == 3
    assert len(coord.client.write_gatt_char.await_args_list) == 2


@pytest.mark.parametrize("family", ["thermal", "network"])
async def test_superseded_query_is_rejected_after_real_scheduler_lock(hass, monkeypatch, family):
    coord = await real_coordinator(hass, "TL-Q" if family == "thermal" else "QMS-IQ")
    controller = coord.controller
    real_sleep = asyncio.sleep
    async def sleep(delay):
        await real_sleep(0)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    controller._spawn = MagicMock()
    if family == "thermal":
        controller._state = replace(controller._state, thermal_module_present=True, motor_module_present=True)
        controller._active_module = "thermal"
        operation = controller._thermal_poll
    else:
        controller._state = replace(controller._state, provisioning_status="waiting")
        operation = controller._network_poll
    await coord._command_lock.acquire()
    old = asyncio.create_task(operation())
    try:
        for _ in range(5):
            await real_sleep(0)
        assert not old.done() and not coord.client.write_gatt_char.await_args_list
        if family == "thermal":
            await controller.set_motion_bed_surface("motor")
            await controller.set_motion_bed_surface("thermal")
        else:
            request = build_motion_bed_request("motion_bed_provision_wifi", {"ssid": "ssid", "password": "password", "longitude": 0, "latitude": 0, "confirmed": True})
            # Keep its seven proven frames; avoid real inter-frame timer waits.
            await controller.async_execute_motion_bed_write(replace(request, spacing_ms=0))
        writes = list(coord.client.write_gatt_char.await_args_list)
        coord._command_lock.release()
        await old
        assert coord.client.write_gatt_char.await_args_list == writes
        if family == "network":
            assert controller._network_poll_active
            assert controller.protocol_diagnostics["provisioning_status"] == "waiting"
    finally:
        if coord._command_lock.locked():
            coord._command_lock.release()
        old.cancel()
        await asyncio.gather(old, return_exceptions=True)


async def test_inventory_churn_during_final_clock_cannot_start_replacement_poll(hass, monkeypatch):
    coord = await real_coordinator(hass, "TL-Q")
    controller = coord.controller
    original_client = coord.client
    async def disconnect():
        original_client.is_connected = False
        coord._on_disconnect(original_client)
    original_client.disconnect = AsyncMock(side_effect=disconnect)
    await controller.start_notify()
    char, receive = coord.client.start_notify.await_args.args
    clock_started, release_clock, poll_tick = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_sleep = asyncio.sleep
    async def sleep(delay):
        if delay in (2, 5):
            await poll_tick.wait()
            poll_tick.clear()
        else:
            await real_sleep(0)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    attempts = []
    async def write(selected, frame, **kwargs):
        attempts.append(bytes(frame))
        if len(attempts) == 2:
            clock_started.set()
            await release_clock.wait()
        elif len(attempts) == 3:
            raise ConnectionError("replacement initialization fails")
    coord.client.write_gatt_char.side_effect = write
    controller._state = replace(controller._state, thermal_module_present=True)
    first = asyncio.create_task(controller._start_present_modules())
    try:
        async with asyncio.timeout(1):
            await clock_started.wait()
            original_generation = controller._module_generation
            receive(char, bytearray.fromhex("FFFFFFFF010027140000000000000000"))
            for _ in range(5):
                await real_sleep(0)
            assert controller._active_module is None
            receive(char, bytearray.fromhex("FFFFFFFF01002714000000000000000C"))
            for _ in range(5):
                await real_sleep(0)
            assert controller._active_module == "thermal"
            assert controller._module_generation > original_generation
            pending = tuple(controller._tasks)
            release_clock.set()
            await first
            await asyncio.gather(*pending, return_exceptions=True)
            for _ in range(5):
                await real_sleep(0)
            assert len(attempts) == 3 and "thermal" not in controller._started_modules
            poll_tick.set()
            for _ in range(12):
                await real_sleep(0)
            assert SOURCE_COMMANDS["LengnuanFragment:58"] not in attempts[3:]
    finally:
        release_clock.set()
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        tasks = tuple(controller._tasks)
        await controller.stop_notify()
        await asyncio.gather(*tasks, return_exceptions=True)
        await coord.async_shutdown()


@pytest.mark.parametrize("service,data", [
    ("motion_bed_clock", {"timestamp": "2026-10-01T07:45:00"}),
    ("motion_bed_air_setting", {"mode": 3, "gear": 8, "timer": 2, "confirmed": True}),
    ("motion_bed_thermal_schedule", {"hour": 21, "minute": 30, "mode": 1, "gear": 4, "confirmed": True}),
])
async def test_idle_hub_inventory_preflight_and_replacement_dispatch(hass, monkeypatch, service, data):
    from tests.test_motion_bed_controller import characteristic, client_for
    coord = await real_coordinator(hass, "TL-Q")
    old = coord.controller
    old._spawn = MagicMock()
    frame = bytearray.fromhex("FFFFFFFF010027140000000000000000")
    frame[9], frame[12], frame[15] = 10, 11, 12
    old._handle_notification(bytes(frame))
    coord.cache_capability_controller()
    coord.client.is_connected = False
    coord._on_disconnect(coord.client)
    assert coord.controller is None and coord.capability_controller is old
    assert old.protocol_diagnostics["motor_module_present"] is None
    replacement = None
    async def reconnect(**kwargs):
        nonlocal replacement
        client = client_for(characteristic(79))
        coord._client = client
        replacement = MotionBedController(coord, selection=select_motion_bed("TL-Q"))
        coord._controller = replacement
        replacement._spawn = MagicMock()
        await replacement.start_notify()
        return True
    coord.async_ensure_connected = AsyncMock(side_effect=reconnect)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", AsyncMock())
    await async_register_services(hass)
    try:
        with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(coord, SIDE_BOTH)], [])):
            await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)
        assert replacement is coord.controller and replacement is not old
        assert coord.client.write_gatt_char.await_args_list[-1].args[1] == build_motion_bed_request(service, data).frames[-1]
        # A definite new inventory overrides the retained capability on this target.
        replacement._handle_notification(bytes.fromhex("FFFFFFFF010027140000000000000000"))
        with pytest.raises(ValueError):
            replacement.validate_motion_bed_write(build_motion_bed_request(service, data))
    finally:
        coord._cancel_disconnect_timer()
        current = coord.capability_controller
        if current is not None:
            await current.stop_notify()
        await coord._command_scheduler.async_shutdown()


async def test_provisioning_public_service_holds_quick_disconnect_until_final_result(hass, monkeypatch):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller = coord.controller
    coord._disconnect_after_command = True
    real_sleep, real_wait_for = asyncio.sleep, asyncio.wait_for
    tick = asyncio.Event()
    entered = asyncio.Event()
    async def sleep(delay):
        if delay == 6:
            entered.set()
            await tick.wait()
        else:
            await real_sleep(0)
    async def wait_for(awaitable, timeout):
        if timeout == 0.3:
            awaitable.close()
            raise TimeoutError
        return await real_wait_for(awaitable, timeout)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.wait_for", wait_for)
    await async_register_services(hass)
    try:
        with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(coord, SIDE_BOTH)], [])):
            await hass.services.async_call(DOMAIN, "motion_bed_provision_wifi", {"device_id": "bed", "ssid": "BED", "password": "password", "longitude": 0, "latitude": 0, "confirmed": True}, blocking=True)
        await entered.wait()
        assert coord._command_connection_holds == 1 and coord._disconnect_timer is None
        await coord._async_idle_disconnect()
        assert coord.is_connected
        tick.set()
        task = controller._network_task
        assert task is not None
        await task
        assert controller._network_queries == 10
        assert len(coord.client.write_gatt_char.await_args_list) == 17
        assert controller.protocol_diagnostics["provisioning_status"] == "timed_out"
        assert coord._command_connection_holds == 0 and coord._disconnect_timer is not None
    finally:
        tasks = tuple(controller._tasks)
        await controller.stop_notify()
        await asyncio.gather(*tasks, return_exceptions=True)
        coord._cancel_disconnect_timer()
        await coord._command_scheduler.async_shutdown()


async def test_calibration_editor_metadata_accepts_the_registered_integer(enable_custom_integrations, hass):
    import voluptuous as vol
    from homeassistant.helpers.selector import NumberSelector
    from homeassistant.helpers.service import async_get_all_descriptions
    await async_register_services(hass)
    descriptions = await async_get_all_descriptions(hass)
    selector = descriptions[DOMAIN]["motion_bed_calibration"]["fields"]["flat"]["selector"]
    assert "number" in selector and "object" not in selector
    selected = vol.Schema(NumberSelector(selector["number"]))(10)
    assert selected == 10
    coord = await real_coordinator(hass, "QMS4")
    try:
        with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(coord, SIDE_BOTH)], [])):
            await hass.services.async_call(DOMAIN, "motion_bed_calibration", {"device_id": "bed", "flat": int(selected), "side_position": 140, "confirmed": True}, blocking=True)
        assert coord.client.write_gatt_char.await_args.args[1] == build_motion_bed_request("motion_bed_calibration", {"flat": 10, "side_position": 140, "confirmed": True}).frames[0]
    finally:
        coord._cancel_disconnect_timer()
        await coord.controller.stop_notify()
        await coord._command_scheduler.async_shutdown()


@pytest.mark.parametrize("ending", ["success", "failed", "cancel", "disconnect", "replacement", "write_failure", "query_failure"])
async def test_provisioning_connection_hold_cleanup_boundaries(hass, monkeypatch, ending):
    from tests.test_motion_bed_controller import characteristic, client_for
    coord = await real_coordinator(hass, "QMS-IQ")
    controller = coord.controller
    coord._disconnect_after_command = True
    real_sleep = asyncio.sleep
    tick, entered = asyncio.Event(), asyncio.Event()
    async def sleep(delay):
        if delay == 6:
            entered.set()
            await tick.wait()
        else:
            await real_sleep(0)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    request = MotionBedWrite("provision_wifi", (STOP,), "network", persistent=True, confirmed=True, network_poll=True)
    try:
        if ending == "write_failure":
            coord.client.write_gatt_char.side_effect = ConnectionError("write failed")
            with pytest.raises(ConnectionError):
                await controller.async_execute_motion_bed_write(request)
            assert controller._network_task is None
        else:
            await controller.async_execute_motion_bed_write(request)
            await entered.wait()
            task = controller._network_task
            assert task is not None and coord._command_connection_holds == 1
            if ending in ("success", "failed"):
                controller._spawn = MagicMock()
                controller._handle_notification(bytes.fromhex("FFFFFFFF02001913000F" if ending == "success" else "FFFFFFFF020019130000"))
                tick.set()
            elif ending == "cancel":
                task.cancel()
            elif ending == "disconnect":
                coord.client.is_connected = False
                coord._on_disconnect(coord.client)
            elif ending == "replacement":
                coord._client = client_for(characteristic(89))
                await controller.async_discover_capabilities()
            else:
                coord.client.write_gatt_char.side_effect = ConnectionError("query failed")
                tick.set()
            result, = await asyncio.gather(task, return_exceptions=True)
            if ending == "query_failure":
                assert result is None
                assert controller._network_queries == 10
                assert controller.protocol_diagnostics["provisioning_status"] == "timed_out"
            assert not controller._network_poll_active
        assert coord._command_connection_holds == 0
        assert controller._network_connection_hold is None
    finally:
        tasks = tuple(controller._tasks)
        await controller.stop_notify()
        await asyncio.gather(*tasks, return_exceptions=True)
        coord._cancel_disconnect_timer()
        await coord._command_scheduler.async_shutdown()


async def test_hub_snapshot_never_admits_unknown_absent_deleted_or_other_target(hass):
    from tests.test_motion_bed_services import invoke, make_target
    target = make_target(hass, "TL-Q")
    target.controller._state = replace(target.controller._state, motor_module_present=None, air_module_present=None, thermal_module_present=None)
    data = {"mode": 3, "gear": 8, "timer": 2, "confirmed": True}
    request = build_motion_bed_request("motion_bed_air_setting", data)
    with pytest.raises(ValueError):
        target.controller.validate_motion_bed_write(request)
    frame = bytearray.fromhex("FFFFFFFF010027140000000000000000")
    frame[12] = 11
    target.controller._spawn = MagicMock()
    target.controller._handle_notification(bytes(frame))
    target.controller.on_disconnect()
    target.controller.validate_motion_bed_write(request)
    target.coordinator.address = "AA:BB:CC:DD:EE:99"
    with pytest.raises(ValueError):
        target.controller.validate_motion_bed_write(request)
    target.coordinator.address = target.controller._target_address
    target.controller._activate("module_change")
    target.controller._handle_notification(bytes.fromhex("FFFFFFFF0100281400"))
    with pytest.raises(ValueError):
        target.controller.validate_motion_bed_write(request)
    # A definitely absent later target prevents the earlier admitted target's write.
    earlier = make_target(hass, "TL-Q", address="AA:BB:CC:DD:EE:01")
    from homeassistant.exceptions import ServiceValidationError
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [earlier, target], "motion_bed_air_setting", data)
    earlier.client.write_gatt_char.assert_not_awaited()
    target.client.write_gatt_char.assert_not_awaited()
