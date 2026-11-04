"""Coordinator routing for controller-selected disconnected transports."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

from .conftest import make_controller_mock


async def test_local_role_operation_skips_the_central_connection_path(
    hass: HomeAssistant, mock_config_entry
) -> None:
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    controller = make_controller_mock(
        requires_disconnected_transport=True,
        disconnected_transport_ready=True,
    )
    coordinator._controller = controller
    called = False

    async def operation(selected_controller) -> None:
        nonlocal called
        assert selected_controller is controller
        called = True

    with (
        patch.object(
            coordinator,
            "async_ensure_connected",
            new=AsyncMock(side_effect=AssertionError("central connect was attempted")),
        ) as ensure_connected,
        patch.object(
            coordinator,
            "_async_refresh_controller_auth",
            new=AsyncMock(side_effect=AssertionError("central auth was attempted")),
        ) as refresh_auth,
        patch.object(coordinator, "_reset_disconnect_timer") as reset_timer,
    ):
        await coordinator.async_execute_controller_command(
            operation,
            read_positions_after_operation=False,
        )

    assert called
    ensure_connected.assert_not_awaited()
    refresh_auth.assert_not_awaited()
    reset_timer.assert_not_called()


async def test_unready_local_role_fails_before_the_operation(
    hass: HomeAssistant, mock_config_entry
) -> None:
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    controller = make_controller_mock(
        requires_disconnected_transport=True,
        disconnected_transport_ready=False,
    )
    coordinator._controller = controller
    called = False

    async def operation(_selected_controller) -> None:
        nonlocal called
        called = True

    with (
        patch.object(
            coordinator,
            "async_ensure_connected",
            new=AsyncMock(side_effect=AssertionError("central fallback was attempted")),
        ) as ensure_connected,
        pytest.raises(ConnectionError, match="disconnected transport is not ready"),
    ):
        await coordinator.async_execute_controller_command(
            operation,
            read_positions_after_operation=False,
        )

    assert not called
    ensure_connected.assert_not_awaited()


async def test_stop_uses_ready_local_role_without_central_reconnect(
    hass: HomeAssistant, mock_config_entry
) -> None:
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    controller = make_controller_mock(
        requires_disconnected_transport=True,
        disconnected_transport_ready=True,
    )
    controller.stop_all = AsyncMock()
    coordinator._controller = controller

    with (
        patch.object(
            coordinator,
            "async_ensure_connected",
            new=AsyncMock(side_effect=AssertionError("central reconnect was attempted")),
        ) as ensure_connected,
        patch.object(
            coordinator,
            "_async_refresh_controller_auth",
            new=AsyncMock(side_effect=AssertionError("central auth was attempted")),
        ) as refresh_auth,
        patch.object(coordinator, "_reset_disconnect_timer") as reset_timer,
        patch.object(coordinator, "_async_release_command_connection") as release,
    ):
        await coordinator._async_send_stop_command()

    controller.stop_all.assert_awaited_once()
    ensure_connected.assert_not_awaited()
    refresh_auth.assert_not_awaited()
    reset_timer.assert_not_called()
    release.assert_not_awaited()


async def test_central_prepare_connects_before_loading_the_controller(
    hass: HomeAssistant, mock_config_entry
) -> None:
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    live_controller = make_controller_mock()

    async def connect(*, reset_timer: bool) -> bool:
        assert reset_timer is False
        coordinator._controller = live_controller
        return True

    coordinator._controller = None
    with patch.object(coordinator, "async_ensure_connected", side_effect=connect) as ensure:
        selected = await coordinator._async_prepare_controller_operation("test")

    ensure.assert_awaited_once_with(reset_timer=False)
    assert selected is live_controller


async def test_stop_reconnects_then_stops_the_replacement_central_controller(
    hass: HomeAssistant, mock_config_entry
) -> None:
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    offline_controller = make_controller_mock()
    live_controller = make_controller_mock()
    live_controller.stop_all = AsyncMock()
    coordinator._controller = offline_controller

    async def connect(*, reset_timer: bool) -> bool:
        assert reset_timer is False
        coordinator._controller = live_controller
        return True

    with (
        patch.object(coordinator, "async_ensure_connected", side_effect=connect) as ensure,
        patch.object(coordinator, "_async_refresh_controller_auth", new=AsyncMock()),
    ):
        await coordinator._async_send_stop_command()

    ensure.assert_awaited_once_with(reset_timer=False)
    offline_controller.stop_all.assert_not_called()
    live_controller.stop_all.assert_awaited_once()
