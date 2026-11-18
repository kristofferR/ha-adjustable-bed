"""Recovering a dropped link under "Stay connected for a while".

The idle window belongs to the last command. A link the bed or adapter drops
is recovered once inside that window, and recovery never opens a new one, so a
bed that drops idle links cannot be held connected forever.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONNECTION_MODE_ALWAYS,
    CONNECTION_MODE_IDLE,
    CONNECTION_MODE_RELEASE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

pytestmark = pytest.mark.usefixtures("mock_coordinator_connected")


def _coordinator(hass: HomeAssistant, mode: str) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:A1",
            CONF_NAME: "Idle recovery bed",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_CONNECTION_MODE: mode,
            CONF_IDLE_DISCONNECT_SECONDS: 40,
        },
        unique_id="AA:BB:CC:DD:EE:A1",
    )
    entry.add_to_hass(hass)
    return AdjustableBedCoordinator(hass, entry)


def _drop(coordinator: AdjustableBedCoordinator, client: MagicMock) -> None:
    """Have the bed drop the link and report whether recovery is scheduled."""
    client.is_connected = False
    coordinator._on_disconnect(client)


def _take_reconnect_timer(coordinator: AdjustableBedCoordinator) -> bool:
    timer = coordinator._reconnect_timer
    if timer is None:
        return False
    timer.cancel()
    coordinator._reconnect_timer = None
    return True


async def test_recovery_keeps_the_original_idle_deadline(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A recovered link disconnects when the last command's window ends."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    # 20 seconds of the 40-second window remain when the bed drops the link.
    deadline = hass.loop.time() + 20
    coordinator._idle_deadline = deadline

    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)

    mock_bleak_client.is_connected = True
    await coordinator._async_auto_reconnect()

    assert coordinator.is_connected
    assert coordinator._idle_deadline == deadline
    timer = coordinator._disconnect_timer
    assert timer is not None
    assert timer.when() == pytest.approx(deadline, abs=1.0)


async def test_no_recovery_after_the_idle_window(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A bed that keeps dropping the link is released once the window ends."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    # The reconnect delay would land after the window.
    coordinator._idle_deadline = hass.loop.time() + 3

    _drop(coordinator, mock_bleak_client)

    assert not _take_reconnect_timer(coordinator)


async def test_late_recovery_timer_does_not_reconnect(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A recovery whose window ended while it waited does not connect."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 20
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)
    coordinator._idle_deadline = hass.loop.time() - 1
    attempts = coordinator.connection_attempt_count

    await coordinator._async_auto_reconnect()

    assert coordinator.connection_attempt_count == attempts
    assert not coordinator.is_connected


async def test_recovery_while_a_command_needs_the_link(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A drop under a running command is still recovered after the window."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() - 1

    async with coordinator._command_lock:
        _drop(coordinator, mock_bleak_client)

    assert _take_reconnect_timer(coordinator)


async def test_command_after_recovery_opens_a_new_window(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A command on a recovered link gets the full idle window again."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 20
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)
    mock_bleak_client.is_connected = True
    await coordinator._async_auto_reconnect()

    async def _noop(controller: object) -> None:
        del controller

    await coordinator.async_execute_controller_command(_noop)

    deadline = coordinator._idle_deadline
    assert deadline is not None
    assert deadline == pytest.approx(hass.loop.time() + 40, abs=1.0)


@pytest.mark.parametrize("mode", [CONNECTION_MODE_RELEASE, CONNECTION_MODE_ALWAYS])
async def test_other_modes_reconnect_on_the_next_command(
    hass: HomeAssistant, mock_bleak_client: MagicMock, mode: str
) -> None:
    """Release and always-connected modes wait for the next command, as before."""
    coordinator = _coordinator(hass, mode)
    assert await coordinator.async_connect()

    _drop(coordinator, mock_bleak_client)

    assert not _take_reconnect_timer(coordinator)


async def test_recovery_keeps_the_deadline_when_startup_re_arms(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A connect retry that re-arms the timer cannot extend a recovered window."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    deadline = hass.loop.time() + 20
    coordinator._idle_deadline = deadline
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)
    mock_bleak_client.is_connected = True
    connect = coordinator._async_connect_locked

    async def _connect_with_late_drop(reset_timer: bool = True) -> bool:
        connected = await connect(reset_timer)
        # As if a late drop callback cleared the window and a retry re-armed it.
        coordinator._recovered_link_window = False
        coordinator._reset_disconnect_timer()
        return connected

    coordinator._async_connect_locked = _connect_with_late_drop
    await coordinator._async_auto_reconnect()

    assert coordinator._idle_deadline == deadline
    timer = coordinator._disconnect_timer
    assert timer is not None
    assert timer.when() == pytest.approx(deadline, abs=1.0)


async def test_recovered_link_skips_position_hydration(
    hass: HomeAssistant,
) -> None:
    """Hydration's retry window must not hold a recovered link past its window."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    coordinator._disable_angle_sensing = False
    coordinator._recovered_link_window = True
    with patch.object(
        coordinator, "_expected_initial_position_axes", return_value={"back"}
    ):
        coordinator._schedule_position_hydration()

    assert coordinator._position_hydration_task is None


@pytest.mark.parametrize("command_waiting", [False, True])
async def test_recovery_connect_cannot_outlast_the_window(
    hass: HomeAssistant, command_waiting: bool
) -> None:
    """A slow recovery connect is abandoned and its unready link released.

    The release happens before a command queued on the connection lock runs,
    so the command never sees the half-open link.
    """
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    # The window ends before the connect can finish.
    coordinator._idle_deadline = hass.loop.time()
    hang = asyncio.Event()
    half_open = MagicMock(is_connected=True)
    seen_by_command: list[object] = []

    async def _command() -> None:
        coordinator._command_link_generation += 1
        async with coordinator._lock:
            seen_by_command.append(coordinator._client)

    async def _slow_connect(reset_timer: bool = True) -> bool:
        del reset_timer
        coordinator._client = half_open
        coordinator._link_ready = False
        await hang.wait()
        return True

    async def _release(reason: str) -> bool:
        assert reason == "idle_timeout"
        coordinator._client = None
        return True

    coordinator._async_connect_locked = _slow_connect
    with (
        patch.object(coordinator, "_idle_window_allows_recovery", return_value=True),
        patch.object(coordinator, "_async_disconnect_locked", side_effect=_release) as release,
    ):
        recovery = hass.async_create_task(coordinator._async_auto_reconnect())
        await asyncio.sleep(0)
        command = hass.async_create_task(_command()) if command_waiting else None
        await recovery
        if command is not None:
            await command

    assert not coordinator._recovered_link_window
    release.assert_awaited_once()
    if command_waiting:
        assert seen_by_command == [None]


async def test_internal_retry_teardown_keeps_the_recovered_window(
    hass: HomeAssistant,
) -> None:
    """A teardown inside the recovery's own connect attempts keeps its window."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    coordinator._recovered_link_window = True

    async with coordinator._lock:
        await coordinator._async_disconnect_locked("authentication_failed")

    assert coordinator._recovered_link_window
    await coordinator.async_disconnect()
    assert not coordinator._recovered_link_window


async def test_drop_during_recovery_keeps_its_window(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A late drop while recovery connects must not let the retry open a full window."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() - 1
    coordinator._recovered_link_window = True
    in_flight = hass.loop.create_future()
    coordinator._reconnect_task = in_flight  # type: ignore[assignment]

    _drop(coordinator, mock_bleak_client)

    assert coordinator._recovered_link_window
    in_flight.cancel()
    coordinator._reconnect_task = None


async def test_drop_during_a_background_position_read_is_not_command_demand(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """The background read holds the command lock as a read, not a command."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() - 1

    async def _read_and_drop() -> None:
        _drop(coordinator, mock_bleak_client)

    with patch.object(coordinator, "_async_read_positions", _read_and_drop):
        await coordinator._async_read_positions_background(coordinator._cancel_counter)

    assert not _take_reconnect_timer(coordinator)


async def test_one_recovery_per_idle_window(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A recovered link that drops again inside the same window waits for a command.

    Receivers that drop idle links every few seconds (#369) would otherwise be
    reconnected repeatedly after every command.
    """
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 30
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)
    mock_bleak_client.is_connected = True
    await coordinator._async_auto_reconnect()
    assert coordinator.is_connected

    _drop(coordinator, mock_bleak_client)

    assert not _take_reconnect_timer(coordinator)


def _record_stop(coordinator: AdjustableBedCoordinator, sent_on: list[object]):
    """Patch the controller class so STOP records the client it went out on.

    Call while connected; the reconnect builds a new instance of that class.
    """
    controller = coordinator.controller
    assert controller is not None

    async def _stop_all(self: object) -> None:
        del self
        sent_on.append(coordinator._client)

    return patch.object(type(controller), "stop_all", _stop_all)


async def test_stop_after_the_window_reconnects_and_sends(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A bed still moving from a latched command gets its STOP after an idle drop.

    The window ended, so the drop is not recovered, but STOP is a command and
    connects on demand.
    """
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() - 1
    sent_on: list[object] = []
    record_stop = _record_stop(coordinator, sent_on)
    _drop(coordinator, mock_bleak_client)
    assert not _take_reconnect_timer(coordinator)
    attempts = coordinator.connection_attempt_count
    mock_bleak_client.is_connected = True

    with record_stop:
        await coordinator.async_stop_command()

    assert coordinator.connection_attempt_count == attempts + 1
    assert sent_on == [mock_bleak_client]


async def test_stop_during_a_recovery_uses_its_connect(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A STOP queued behind a recovery lifts the window and uses that connect.

    Without that, the window ending mid-connect would cancel the connect, tear
    the link down and make the STOP connect again from scratch.
    """
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 20
    sent_on: list[object] = []
    record_stop = _record_stop(coordinator, sent_on)
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)

    gate = asyncio.Event()
    connect = coordinator._async_connect_locked
    connects = 0

    async def _gated_connect(reset_timer: bool = True) -> bool:
        nonlocal connects
        connects += 1
        await gate.wait()
        mock_bleak_client.is_connected = True
        return await connect(reset_timer)

    coordinator._async_connect_locked = _gated_connect
    with record_stop:
        recovery = hass.async_create_task(coordinator._async_auto_reconnect())
        while connects == 0:
            await asyncio.sleep(0)
        stop = hass.async_create_task(coordinator.async_stop_command())
        # The STOP holds the command lock and waits on the connection lock.
        while not coordinator._command_lock.locked():
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        # Past the window's end: an unlifted window would cancel the connect now.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
        await asyncio.sleep(0)
        gate.set()
        await recovery
        await stop

    assert connects == 1
    assert sent_on == [mock_bleak_client]
    assert coordinator.is_connected
    # The link served the STOP, so its window may recover one drop.
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)


async def test_spent_window_is_not_recovered_after_the_command_left(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A recovery scheduled under a command does not reuse a spent window.

    The recovered link dropped during a command, so the drop scheduled
    recovery; by the time it fires the command has finished and the window
    already had its one recovery.
    """
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 30
    coordinator._link_from_recovery = True
    async with coordinator._command_lock:
        _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)
    attempts = coordinator.connection_attempt_count

    await coordinator._async_auto_reconnect()

    assert coordinator.connection_attempt_count == attempts
    assert not coordinator.is_connected


async def test_command_queued_behind_a_read_lifts_the_recovery_deadline(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A command still waiting for the command lock already owns the recovery."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 20
    sent_on: list[object] = []
    record_stop = _record_stop(coordinator, sent_on)
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)

    gate = asyncio.Event()
    read_done = asyncio.Event()
    connect = coordinator._async_connect_locked
    connects = 0

    async def _gated_connect(reset_timer: bool = True) -> bool:
        nonlocal connects
        connects += 1
        await gate.wait()
        mock_bleak_client.is_connected = True
        return await connect(reset_timer)

    async def _read() -> None:
        async with coordinator._command_lock, coordinator._link_read_scope(True):
            await read_done.wait()

    coordinator._async_connect_locked = _gated_connect
    with record_stop:
        read = hass.async_create_task(_read())
        recovery = hass.async_create_task(coordinator._async_auto_reconnect())
        while connects == 0:
            await asyncio.sleep(0)
        # STOP queues on the command lock behind the read.
        stop = hass.async_create_task(coordinator.async_stop_command())
        await asyncio.sleep(0)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
        await asyncio.sleep(0)
        gate.set()
        await recovery
        read_done.set()
        await read
        await stop

    assert connects == 1
    assert sent_on == [mock_bleak_client]


async def test_link_opened_for_a_service_check_gets_a_full_window(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A link a service opened to check, then released by STOP, idles normally."""
    from custom_components.adjustable_bed.services import _release_preflighted

    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    # The service check connects without arming the idle timer.
    assert await coordinator.async_ensure_connected(reset_timer=False)
    assert coordinator._disconnect_timer is None

    await _release_preflighted([(coordinator, coordinator)])

    assert coordinator._idle_deadline == pytest.approx(hass.loop.time() + 40, abs=1.0)
    assert coordinator._disconnect_timer is not None


async def _run_gated_recovery(
    hass: HomeAssistant,
    coordinator: AdjustableBedCoordinator,
    client: MagicMock,
    during,
) -> int:
    """Run one recovery whose connect waits until ``during`` has run and the window passed.

    Returns how many connects happened.
    """
    gate = asyncio.Event()
    connect = coordinator._async_connect_locked
    connects = 0

    async def _gated_connect(reset_timer: bool = True) -> bool:
        nonlocal connects
        connects += 1
        await gate.wait()
        client.is_connected = True
        return await connect(reset_timer)

    coordinator._async_connect_locked = _gated_connect
    recovery = hass.async_create_task(coordinator._async_auto_reconnect())
    while connects == 0 and not recovery.done():
        await asyncio.sleep(0)
    await during()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await asyncio.sleep(0)
    gate.set()
    await recovery
    return connects


async def _dropped_inside_window(
    hass: HomeAssistant, client: MagicMock
) -> AdjustableBedCoordinator:
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    coordinator._idle_deadline = hass.loop.time() + 20
    _drop(coordinator, client)
    assert _take_reconnect_timer(coordinator)
    return coordinator


async def test_stop_queued_before_recovery_starts_makes_it_unbounded(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A STOP already waiting behind a read is command demand for the recovery."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    assert await coordinator.async_connect()
    controller_cls = type(coordinator.controller)
    coordinator._idle_deadline = hass.loop.time() + 20
    _drop(coordinator, mock_bleak_client)
    assert _take_reconnect_timer(coordinator)
    sent_on: list[object] = []
    release_read = asyncio.Event()

    async def _read() -> None:
        async with coordinator._command_lock, coordinator._link_read_scope(True):
            await release_read.wait()

    read = hass.async_create_task(_read())
    await asyncio.sleep(0)

    async def _stop_all(self: object) -> None:
        del self
        sent_on.append(coordinator._client)

    with patch.object(controller_cls, "stop_all", _stop_all):
        stop = hass.async_create_task(coordinator.async_stop_command())
        await asyncio.sleep(0)
        assert coordinator._command_needs_link()

        async def _nothing() -> None:
            return None

        connects = await _run_gated_recovery(hass, coordinator, mock_bleak_client, _nothing)
        release_read.set()
        await read
        await stop

    assert connects == 1
    assert sent_on == [mock_bleak_client]


async def test_command_group_is_demand_before_its_first_operation(
    hass: HomeAssistant,
) -> None:
    """A group that checks the bed before its first write already needs the link."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    started = asyncio.Event()
    release = asyncio.Event()

    async def _live_check() -> None:
        started.set()
        await release.wait()

    group = hass.async_create_task(
        coordinator.async_execute_command_group([_live_check], resources=("*",))
    )
    await started.wait()

    assert coordinator._command_needs_link()
    release.set()
    await group
    assert not coordinator._command_demand


async def test_command_hold_lifts_an_inflight_recovery(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A linked action that starts holding the link mid-recovery uses its connect."""
    coordinator = await _dropped_inside_window(hass, mock_bleak_client)

    with contextlib.ExitStack() as held:

        async def _hold() -> None:
            held.enter_context(coordinator.hold_command_connection())

        connects = await _run_gated_recovery(hass, coordinator, mock_bleak_client, _hold)

    assert connects == 1
    assert coordinator.is_connected


async def test_startup_commands_on_a_recovered_link_do_not_earn_another_recovery(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """A controller's own connect-time command opens a window, not a recovery budget.

    Several controllers send a command of their own after connecting. On a
    recovered link that must not let the next drop be recovered again.
    """
    coordinator = await _dropped_inside_window(hass, mock_bleak_client)
    mock_bleak_client.is_connected = True
    await coordinator._async_auto_reconnect()
    assert coordinator.is_connected

    async def _startup_query(controller: object) -> None:
        del controller

    await coordinator.async_execute_controller_command(_startup_query, cancel_running=False)
    _drop(coordinator, mock_bleak_client)

    assert not _take_reconnect_timer(coordinator)


async def test_inline_group_is_demand(hass: HomeAssistant) -> None:
    """A group run inside an existing scheduler reservation also needs the link."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    reservation = MagicMock(
        scheduler_token=coordinator._command_scheduler.token, defer_disconnect=False
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def _live_check() -> None:
        started.set()
        await release.wait()

    with patch(
        "custom_components.adjustable_bed.coordinator.current_command_context",
        return_value=reservation,
    ):
        group = hass.async_create_task(
            coordinator.async_execute_command_group([_live_check], resources=("*",))
        )
        await started.wait()
        assert coordinator._command_needs_link()
        release.set()
        await group


async def test_recovery_leaves_a_link_another_connect_opened_alone(
    hass: HomeAssistant, mock_bleak_client: MagicMock
) -> None:
    """If an explicit connect wins the lock, the recovery does not claim its link."""
    coordinator = await _dropped_inside_window(hass, mock_bleak_client)
    deadline = coordinator._idle_deadline
    attempts = coordinator.connection_attempt_count

    async with coordinator._lock:
        recovery = hass.async_create_task(coordinator._async_auto_reconnect())
        await asyncio.sleep(0)
        # As if the Connect button opened the link meanwhile.
        mock_bleak_client.is_connected = True
        coordinator._client = mock_bleak_client
    await recovery

    assert coordinator.connection_attempt_count == attempts
    assert not coordinator._link_from_recovery
    assert not coordinator._recovered_link_window
    assert coordinator._idle_deadline == deadline
