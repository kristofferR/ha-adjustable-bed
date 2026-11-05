"""Tests for Okin ORE bed controller."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_ore import (
    OkinOreCommands,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_ORE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OKIN_ORE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_okin_ore_config_entry_data() -> dict:
    """Return mock config entry data for Okin ORE bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin ORE Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIN_ORE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_MOTOR_PULSE_COUNT: 3,
        CONF_MOTOR_PULSE_DELAY_MS: 0,
    }


@pytest.fixture
def mock_okin_ore_config_entry(
    hass: HomeAssistant, mock_okin_ore_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin ORE bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin ORE Test Bed",
        data=mock_okin_ore_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_ore_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestOkinOreController:
    """Test Okin ORE controller behavior."""

    def test_command_constants_use_cmd_prefix(self) -> None:
        """Command constants keep their values with CMD_* naming."""
        assert OkinOreCommands.CMD_STOP == 0x2000
        assert OkinOreCommands.CMD_HEAD_UP == 0x2001
        assert OkinOreCommands.CMD_FOOT_UP == 0x2003
        assert OkinOreCommands.CMD_ALL_DOWN == 0x200C
        assert OkinOreCommands.CMD_HEAD_MASSAGE_UP == 0x2020
        assert OkinOreCommands.CMD_LIGHT_TOGGLE == 0x2080

    async def test_write_command_skips_when_cancel_event_pre_set(
        self,
        hass: HomeAssistant,
        mock_okin_ore_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """write_command should no-op when cancellation is already set."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_ore_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        cancel_event = asyncio.Event()
        cancel_event.set()
        await coordinator.controller.write_command(
            coordinator.controller._build_command(OkinOreCommands.CMD_STOP),
            cancel_event=cancel_event,
        )

        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_preset_flat_sends_repeated_command_then_stop(
        self,
        hass: HomeAssistant,
        mock_okin_ore_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """preset_flat should use pulse repeat settings and always send STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_ore_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.preset_flat()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        expected_preset = coordinator.controller._build_command(OkinOreCommands.CMD_FLAT)
        expected_stop = coordinator.controller._build_command(OkinOreCommands.CMD_STOP)
        assert len(calls) == coordinator.motor_pulse_count + 1
        assert [call[0][0] for call in calls] == [OKIN_ORE_WRITE_CHAR_UUID] * len(calls)
        assert [call[0][1] for call in calls[:-1]] == [expected_preset] * coordinator.motor_pulse_count
        assert calls[-1][0][1] == expected_stop

    @pytest.mark.parametrize(
        ("memory_num", "expected_command"),
        [
            (1, OkinOreCommands.CMD_MEMORY_1),
            (2, OkinOreCommands.CMD_MEMORY_2),
        ],
    )
    async def test_preset_memory_uses_stop_cleanup(
        self,
        hass: HomeAssistant,
        mock_okin_ore_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: int,
    ):
        """preset_memory should use repeated preset writes and STOP cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_ore_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.preset_memory(memory_num)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        expected_preset = coordinator.controller._build_command(expected_command)
        expected_stop = coordinator.controller._build_command(OkinOreCommands.CMD_STOP)
        assert len(calls) == coordinator.motor_pulse_count + 1
        assert [call[0][1] for call in calls[:-1]] == [expected_preset] * coordinator.motor_pulse_count
        assert calls[-1][0][1] == expected_stop

    @pytest.mark.parametrize(
        ("state_attr", "toggle_method", "down_command"),
        [
            ("_head_massage", "massage_head_toggle", OkinOreCommands.CMD_HEAD_MASSAGE_DOWN),
            ("_foot_massage", "massage_foot_toggle", OkinOreCommands.CMD_FOOT_MASSAGE_DOWN),
        ],
    )
    async def test_massage_toggle_steps_all_the_way_down(
        self,
        hass: HomeAssistant,
        mock_okin_ore_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        state_attr: str,
        toggle_method: str,
        down_command: int,
    ):
        """Toggle from active state should step down until the tracked level reaches 0."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_ore_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        setattr(coordinator.controller, state_attr, 3)
        await getattr(coordinator.controller, toggle_method)()

        assert getattr(coordinator.controller, state_attr) == 0
        expected_down = coordinator.controller._build_command(down_command)
        assert [call[0][1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            expected_down,
            expected_down,
            expected_down,
        ]
