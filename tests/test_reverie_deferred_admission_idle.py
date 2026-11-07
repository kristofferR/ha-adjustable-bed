"""Deferred movement admission and background Pairlink idle ownership."""

import asyncio
from copy import copy
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_IDLE_DISCONNECT_SECONDS,
    DOMAIN,
    PAIRLINK_ROLE_CENTRAL,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_reverie_pairlink import _controller, _join_central
from tests.test_reverie_pairlink_production import _entry


@pytest.mark.parametrize("action", ["reverie_run_routine", "reverie_test"])
@pytest.mark.parametrize("stop", [False, True])
async def test_later_deferred_target_respects_stop_before_dispatch(
    hass,
    monkeypatch,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_establish_connection,
    action,
    stop,
):
    clients = [copy(mock_bleak_client) for _ in range(2)]
    for client in clients:
        client.write_gatt_char = AsyncMock()
        client.disconnect = AsyncMock()
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()
    mock_establish_connection.side_effect = clients
    coordinators = []
    for index in range(2):
        address = f"AA:BB:CC:DD:EE:{index + 1:02X}"
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=address,
            data={
                "address": address,
                "bed_type": "reverie",
                "motor_count": 2,
                "has_massage": True,
                "disable_angle_sensing": True,
            },
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        coordinators.append(coordinator)
    first, later = coordinators
    entered, release = asyncio.Event(), asyncio.Event()
    original_write = clients[0].write_gatt_char

    async def blocked_write(*args, **kwargs):
        entered.set()
        await release.wait()
        await original_write(*args, **kwargs)

    clients[0].write_gatt_char = blocked_write
    clients[1].write_gatt_char.reset_mock()

    def resolve(_hass, devices, _side):
        selected = {"first": first, "later": later}
        return ([(selected[device], "both") for device in devices], [])

    monkeypatch.setattr("custom_components.adjustable_bed.services._resolve_sided_targets", resolve)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.reverie.services._resolve_sided_targets", resolve
    )
    await async_register_services(hass)
    data = {}
    if action == "reverie_run_routine":
        data["steps"] = [
            {
                "comfort": {
                    "head_position": 25,
                    "foot_position": 40,
                    "head_massage": 0,
                    "foot_massage": 0,
                },
                "duration_minutes": 1,
            }
        ]
    call = asyncio.create_task(
        hass.services.async_call(
            DOMAIN, action, {"device_id": ["first", "later"], **data}, blocking=True
        )
    )
    try:
        async with asyncio.timeout(2):
            await entered.wait()
        if stop:
            await hass.services.async_call(
                DOMAIN, "stop_all", {"device_id": ["later"]}, blocking=True
            )
            clients[1].write_gatt_char.reset_mock()
        release.set()
        await call
        if stop:
            clients[1].write_gatt_char.assert_not_awaited()
            assert later.controller._routine_timer is None
            assert later.controller._diagnostic_timer is None
            await hass.services.async_call(
                DOMAIN, action, {"device_id": ["later"], **data}, blocking=True
            )
        assert clients[1].write_gatt_char.await_count > 0
    finally:
        release.set()
        if not call.done():
            call.cancel()
        await asyncio.gather(call, return_exceptions=True)
        for coordinator in coordinators:
            await coordinator.async_stop_command()
            coordinator.controller.on_disconnect()
            await coordinator.async_shutdown()


@pytest.mark.parametrize("idle_seconds", [0, 40])
@pytest.mark.parametrize("poll_kind", ["status", "clock"])
async def test_central_polls_preserve_idle_deadline_and_never_reconnect(
    hass,
    monkeypatch,
    idle_seconds,
    poll_kind,
):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    entry = _entry(address=controller._coordinator.address, role=PAIRLINK_ROLE_CENTRAL)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_IDLE_DISCONNECT_SECONDS: idle_seconds,
        },
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller
    coordinator._client = client
    coordinator._ready = True
    controller._coordinator = coordinator
    client.disconnect = AsyncMock(side_effect=lambda: setattr(client, "is_connected", False))
    connect = AsyncMock(side_effect=AssertionError("A background poll must not reconnect"))
    monkeypatch.setattr(coordinator, "_async_connect_locked", connect)
    scheduled = []
    monkeypatch.setattr(
        controller,
        "_schedule_status_sync",
        lambda _generation, *, delay_seconds: scheduled.append(delay_seconds),
    )
    clock_queries = []
    monkeypatch.setattr(
        controller,
        "_schedule_clock_query",
        lambda _generation, *, delay_seconds: clock_queries.append(delay_seconds),
    )
    controller._set_active_control_session(True)
    poll = (
        controller._async_run_status_sync
        if poll_kind == "status"
        else controller._async_run_clock_query
    )
    generation = (
        controller._status_sync_generation
        if poll_kind == "status"
        else controller._clock_sync_generation
    )
    coordinator._reset_disconnect_timer()
    timer = coordinator._disconnect_timer
    deadline = timer.when() if timer is not None else None
    try:
        assert (timer is None) is (idle_seconds == 0)
        client.writes.clear()
        for _ in range(3):
            await poll(generation)
            assert coordinator._disconnect_timer is timer
            if timer is not None:
                assert not timer.cancelled()
                assert timer.when() == deadline
            if poll_kind == "clock":
                assert client.writes[-1][1] == b"\x01\x1a"
                # The registered response rearms the clock; a query alone does not.
                previous_queries = len(clock_queries)
                assert client.notify_callback is not None
                client.notify_callback(None, bytearray.fromhex("021a78563412"))
                await hass.async_block_till_done()
                assert clock_queries[previous_queries:] == [5]
        assert len(client.writes) == (6 if poll_kind == "status" else 3)
        assert scheduled == ([0, 1, 1, 1] if poll_kind == "status" else [0])
        if timer is not None:
            # Model this exact handle reaching its deadline without a real wait.
            timer.cancel()
            coordinator._disconnect_timer = None
            await coordinator._async_idle_disconnect()
            client.disconnect.assert_awaited_once()
        else:
            client.disconnect.assert_not_awaited()
            await coordinator.async_disconnect()
        client.writes.clear()
        await poll(generation)
        assert client.writes == []
        connect.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("preemptor", ["command", "stop", "caller"])
@pytest.mark.parametrize("idle_seconds", [0, 40])
async def test_status_poll_rearms_after_internal_preemption_only(
    hass, monkeypatch, preemptor, idle_seconds
):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    entry = _entry(address=controller._coordinator.address, role=PAIRLINK_ROLE_CENTRAL)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_IDLE_DISCONNECT_SECONDS: idle_seconds,
        },
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller, coordinator._client, coordinator._ready = controller, client, True
    controller._coordinator = coordinator
    client.disconnect = AsyncMock(side_effect=lambda: setattr(client, "is_connected", False))
    scheduled = []
    monkeypatch.setattr(
        controller,
        "_schedule_status_sync",
        lambda _generation, *, delay_seconds: scheduled.append(delay_seconds),
    )
    controller._set_active_control_session(True)
    generation = controller._status_sync_generation
    coordinator._reset_disconnect_timer()
    original_timer = coordinator._disconnect_timer
    entered, never_release = asyncio.Event(), asyncio.Event()
    write = client.write_gatt_char
    first = True

    async def blocked_first_write(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            entered.set()
            await never_release.wait()
        await write(*args, **kwargs)

    monkeypatch.setattr(client, "write_gatt_char", blocked_first_write)
    client.writes.clear()
    poll = asyncio.create_task(controller._async_run_status_sync(generation))
    try:
        async with asyncio.timeout(2):
            await entered.wait()
            if preemptor == "command":
                await coordinator.async_execute_controller_command(
                    lambda current: current.preset_flat(), read_positions_after_operation=False
                )
            elif preemptor == "stop":
                await coordinator.async_stop_command()
            else:
                poll.cancel()
            result = (await asyncio.gather(poll, return_exceptions=True))[0]
        assert coordinator.is_connected
        assert controller._active_control_session
        assert controller._status_sync_generation == generation
        if preemptor == "caller":
            assert isinstance(result, asyncio.CancelledError)
            assert scheduled == [0]
            assert coordinator._disconnect_timer is original_timer
        else:
            assert result is None
            assert poll.cancelling() == 0
            assert scheduled == [0, 1]
            # The next poll preserves the new deadline created by user activity.
            timer = coordinator._disconnect_timer
            before = len(client.writes)
            await controller._async_run_status_sync(generation)
            assert len(client.writes) > before
            assert scheduled == [0, 1, 1]
            assert coordinator._disconnect_timer is timer
    finally:
        if not poll.done():
            poll.cancel()
        await asyncio.gather(poll, return_exceptions=True)
        await coordinator.async_shutdown()
