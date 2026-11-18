"""Recovering a dropped link under "Stay connected for a while".

The idle window belongs to the last command. A link the bed or adapter drops
is recovered only inside that window, and recovery never opens a new one, so a
bed that drops idle links cannot be held connected forever.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

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
    connect = coordinator.async_connect

    async def _connect_with_late_drop() -> bool:
        connected = await connect()
        # As if a late drop callback cleared the window and a retry re-armed it.
        coordinator._recovered_link_window = False
        coordinator._reset_disconnect_timer()
        return connected

    coordinator.async_connect = _connect_with_late_drop
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
    """A slow recovery connect is abandoned and its unready link released."""
    coordinator = _coordinator(hass, CONNECTION_MODE_IDLE)
    # The window ends before the connect can finish.
    coordinator._idle_deadline = hass.loop.time()
    hang = asyncio.Event()

    async def _slow_connect() -> bool:
        if command_waiting:
            # A command queued behind the startup that never became ready.
            coordinator._command_link_generation += 1
        await hang.wait()
        return True

    coordinator.async_connect = _slow_connect
    with (
        patch.object(coordinator, "_idle_window_allows_recovery", return_value=True),
        patch.object(coordinator, "async_disconnect", AsyncMock()) as disconnect,
    ):
        await coordinator._async_auto_reconnect()

    assert not coordinator._recovered_link_window
    # Releases a link a cancelled startup may have left half open.
    disconnect.assert_awaited_once_with(reason="idle_timeout")


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
