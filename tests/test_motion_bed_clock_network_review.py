"""HA-local startup clocks and one bounded provisioning polling owner."""
import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from custom_components.adjustable_bed.motion_bed_protocol import (
    SOURCE_COMMANDS,
    build_clock,
    build_thermal_clock,
)
from custom_components.adjustable_bed.motion_bed_services import build_motion_bed_request
from custom_components.adjustable_bed.services import async_register_services
from tests.test_motion_bed_lifecycle import real_coordinator


async def _cleanup(coord, controller):
    tasks = tuple(controller._tasks)
    await controller.stop_notify()
    await asyncio.gather(*tasks, return_exceptions=True)
    coord._cancel_disconnect_timer()
    await coord._command_scheduler.async_shutdown()


async def _provision(hass, coord):
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(coord, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "motion_bed_provision_wifi", {"device_id": "bed", "ssid": "BED", "password": "password", "longitude": 0, "latitude": 0, "confirmed": True}, blocking=True)


@pytest.mark.parametrize("name", ["QMS-IQ", "TL-B", "TL-W"])
@pytest.mark.parametrize("zone", ["Pacific/Auckland", "America/Los_Angeles"])
async def test_registered_startup_uses_configured_zone_with_utc_host(hass, monkeypatch, freezer, name, zone):
    instant = datetime(2026, 10, 2, 23, 45, 56, tzinfo=UTC)
    freezer.move_to(instant)
    await hass.config.async_set_time_zone(zone)
    local = instant.astimezone(ZoneInfo(zone))
    coord = await real_coordinator(hass, name)
    controller = coord.controller
    controller._startup = MotionBedController._startup.__get__(controller)
    # The clock assertion runs actual builders/startup; its delays and later poll
    # are covered separately and cannot race this isolated startup check.
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", AsyncMock())
    controller._spawn = MagicMock()
    try:
        with monkeypatch.context() as host:
            host.setenv("TZ", "UTC")
            time.tzset()
            await coord.async_execute_controller_command(lambda c: c.start_notify())
        want = build_thermal_clock(local) if name == "TL-W" else build_clock(local)
        host_frame = build_thermal_clock(instant) if name == "TL-W" else build_clock(instant)
        frames = [call.args[1] for call in coord.client.write_gatt_char.await_args_list]
        assert want != host_frame and want in frames and host_frame not in frames
    finally:
        time.tzset()
        await _cleanup(coord, controller)


@pytest.mark.parametrize("ack_frame,success_at_deadline", [(0, False), (3, True), (6, False)])
async def test_early_pending_ack_has_one_query_at_each_native_interval(hass, monkeypatch, ack_frame, success_at_deadline):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller = coord.controller
    await controller.start_notify()
    request = build_motion_bed_request("motion_bed_provision_wifi", {"ssid": "BED", "password": "password", "longitude": 0, "latitude": 0, "confirmed": True})
    callback = coord.client.start_notify.call_args.args[1]
    char = coord.client.start_notify.call_args.args[0]
    real_sleep, real_wait = asyncio.sleep, asyncio.wait_for
    now, waiters, query_times = 0, [], []

    async def sleep(delay):
        if delay == 6:
            future = asyncio.get_running_loop().create_future()
            waiters.append((now + delay, future))
            await future
        else:
            await real_sleep(0)

    async def wait_for(awaitable, timeout):
        if timeout == 0.3:
            awaitable.close()
            raise TimeoutError
        return await real_wait(awaitable, timeout)

    async def write(characteristic, frame, **kwargs):
        if frame == request.frames[ack_frame]:
            callback(char, bytearray.fromhex("FFFFFFFF020019130001"))
        elif frame == SOURCE_COMMANDS["NetworkActivity:333"]:
            query_times.append(now)
            if now == 60 and success_at_deadline:
                callback(char, bytearray.fromhex("FFFFFFFF02001913000F"))

    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.wait_for", wait_for)
    coord.client.write_gatt_char.side_effect = write
    try:
        await _provision(hass, coord)
        for _ in range(20):
            await real_sleep(0)
        assert len(waiters) == 1
        task = controller._network_task
        assert task is not None
        for tick in range(1, 11):
            now = tick * 6
            for deadline, future in list(waiters):
                if deadline <= now and not future.done():
                    future.set_result(None)
            for _ in range(30):
                await real_sleep(0)
        await task
        assert query_times == list(range(6, 61, 6))
        assert controller._network_queries == 10
        assert controller.protocol_diagnostics["provisioning_status"] == ("success" if success_at_deadline else "timed_out")
        assert not controller._network_poll_active and coord._command_connection_holds == 0
        assert controller._network_connection_hold is None
    finally:
        await _cleanup(coord, controller)


@pytest.mark.parametrize("kind", ["ble", "connection", "timeout"])
@pytest.mark.parametrize("all_queries_fail", [False, True])
async def test_transient_provision_query_errors_reach_existing_bounded_deadline(hass, monkeypatch, kind, all_queries_fail):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller = coord.controller
    await controller.start_notify()
    real_sleep, real_wait = asyncio.sleep, asyncio.wait_for
    queries, intervals = 0, []

    async def sleep(delay):
        if delay == 6:
            intervals.append(delay)
            assert coord._command_connection_holds == 1
        await real_sleep(0)

    async def wait_for(awaitable, timeout):
        if timeout == 0.3:
            awaitable.close()
            raise TimeoutError
        return await real_wait(awaitable, timeout)

    async def write(characteristic, frame, **kwargs):
        nonlocal queries
        if frame == SOURCE_COMMANDS["NetworkActivity:333"]:
            queries += 1
            if all_queries_fail or queries == 1:
                raise {"ble": BleakError("transient"), "connection": ConnectionError("transient"), "timeout": TimeoutError("transient")}[kind]

    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.wait_for", wait_for)
    coord.client.write_gatt_char.side_effect = write
    try:
        await _provision(hass, coord)
        task = controller._network_task
        assert task is not None
        await task
        assert queries == controller._network_queries == 10
        assert intervals == [6] * 10
        assert controller.protocol_diagnostics["provisioning_status"] == "timed_out"
        assert not controller._network_poll_active and coord._command_connection_holds == 0
        assert controller._network_connection_hold is None and coord.client.is_connected
    finally:
        await _cleanup(coord, controller)


@pytest.mark.parametrize("ending", ["cancel", "replacement"])
async def test_provision_query_task_cancel_and_owner_loss_exit_without_retry(hass, monkeypatch, ending):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller = coord.controller
    await controller.start_notify()
    real_sleep, real_wait = asyncio.sleep, asyncio.wait_for
    entered, tick = asyncio.Event(), asyncio.Event()
    intervals = []

    async def sleep(delay):
        if delay == 6:
            intervals.append(delay)
            entered.set()
            await tick.wait()
        else:
            await real_sleep(0)

    async def wait_for(awaitable, timeout):
        if timeout == 0.3:
            awaitable.close()
            raise TimeoutError
        return await real_wait(awaitable, timeout)

    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.wait_for", wait_for)
    try:
        await _provision(hass, coord)
        await entered.wait()
        task = controller._network_task
        assert task is not None
        await coord._command_lock.acquire()
        tick.set()
        for _ in range(20):
            await real_sleep(0)
        if ending == "cancel":
            task.cancel()
        else:
            coord._controller = MotionBedController(coord, selection=select_motion_bed("QMS-IQ"))
        coord._command_lock.release()
        if ending == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        assert intervals == [6]
        assert coord._command_connection_holds == 0 and controller._network_connection_hold is None
        assert SOURCE_COMMANDS["NetworkActivity:333"] not in [call.args[1] for call in coord.client.write_gatt_char.await_args_list]
    finally:
        await _cleanup(coord, controller)


async def test_command_preemption_keeps_current_network_poll_with_bounded_windows(hass, monkeypatch):
    coord = await real_coordinator(hass, "QMS-IQ")
    controller = coord.controller
    await controller.start_notify()
    real_sleep, real_wait = asyncio.sleep, asyncio.wait_for
    entered, tick = asyncio.Event(), asyncio.Event()
    intervals = []
    async def sleep(delay):
        if delay == 6:
            intervals.append(delay)
            if len(intervals) == 1:
                entered.set()
                await tick.wait()
        await real_sleep(0)
    async def wait_for(awaitable, timeout):
        if timeout == 0.3:
            awaitable.close()
            raise TimeoutError
        return await real_wait(awaitable, timeout)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", sleep)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.wait_for", wait_for)
    try:
        await _provision(hass, coord)
        await entered.wait()
        task = controller._network_task
        assert task is not None
        await coord._command_lock.acquire()
        tick.set()
        for _ in range(20):
            await real_sleep(0)
        ran = asyncio.Event()
        async def command(current_controller):
            ran.set()
        movement = asyncio.create_task(coord.async_execute_controller_command(command, cancel_running=True))
        for _ in range(20):
            await real_sleep(0)
        coord._command_lock.release()
        await movement
        assert ran.is_set()
        await task
        assert intervals == [6] * 10
        assert controller._network_queries == 9
        assert controller.protocol_diagnostics["provisioning_status"] == "timed_out"
        assert not controller._network_poll_active and coord._command_connection_holds == 0
    finally:
        await _cleanup(coord, controller)
