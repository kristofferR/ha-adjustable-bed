"""Tests for the separate DewertOkin ELEVATE StarCode controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.star_elevate import (
    StarElevateCommands,
    StarElevateController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_STAR_ELEVATE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_star_elevate_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an ELEVATE config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ELEVATE Test",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:46",
            CONF_NAME: "ELEVATE Test",
            CONF_BED_TYPE: BED_TYPE_STAR_ELEVATE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:46",
        entry_id="star_elevate_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestStarElevateController:
    """Test exact ELEVATE discovery-independent controller behavior."""

    async def test_factory_creates_separate_controller_and_motor_surface(
        self,
        hass: HomeAssistant,
        mock_star_elevate_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, StarElevateController)
        assert coordinator.controller.control_characteristic_uuid == NORDIC_UART_WRITE_CHAR_UUID
        assert [spec.key for spec in coordinator.controller.motor_control_specs] == [
            "elevate_actuator_1",
            "elevate_actuator_2",
            "elevate_both",
        ]

    async def test_movement_methods_use_dedicated_elevate_key_range(
        self,
        hass: HomeAssistant,
        mock_star_elevate_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        cases = (
            (controller.move_head_up, StarElevateCommands.ACTUATOR_1_UP),
            (controller.move_head_down, StarElevateCommands.ACTUATOR_1_DOWN),
            (controller.move_feet_up, StarElevateCommands.ACTUATOR_2_UP),
            (controller.move_feet_down, StarElevateCommands.ACTUATOR_2_DOWN),
            (controller.move_both_up, StarElevateCommands.BOTH_UP),
            (controller.move_both_down, StarElevateCommands.BOTH_DOWN),
        )
        for method, expected in cases:
            with patch.object(controller, "_move_with_stop", AsyncMock()) as mock_move:
                await method()
            mock_move.assert_awaited_once_with(expected)

    async def test_lazy_session_wake_and_commands_use_write_without_response(
        self,
        hass: HomeAssistant,
        mock_star_elevate_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        # Connection setup has already enabled RX and sent wake. Reset the flag
        # to exercise the same lazy fallback used after a missed initialization.
        controller._initialized = False

        with patch.object(controller, "_write_gatt_with_retry", AsyncMock()) as mock_write:
            await controller.write_command(StarElevateCommands.BOTH_UP)

        assert [call.args[1] for call in mock_write.await_args_list] == [
            StarElevateCommands.WAKE,
            StarElevateCommands.BOTH_UP,
        ]
        assert [call.kwargs["response"] for call in mock_write.await_args_list] == [False, False]

    async def test_flat_is_one_shot_and_stop_is_shared(
        self,
        hass: HomeAssistant,
        mock_star_elevate_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "write_command", AsyncMock()) as mock_write:
            await controller.preset_flat()
            await controller.stop_all()

        assert mock_write.await_args_list[0].args == (StarElevateCommands.FLAT,)
        assert mock_write.await_args_list[1].args[0] == StarElevateCommands.STOP
