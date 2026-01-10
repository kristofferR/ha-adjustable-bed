"""Tests for Jiecang bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jiecang import (
    JiecangCommands,
    JiecangController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    JIECANG_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestJiecangCommands:
    """Test Jiecang command constants."""

    def test_preset_commands(self):
        """Test preset commands are correct."""
        assert JiecangCommands.MEMORY_1 == bytes.fromhex("f1f10b01010d7e")
        assert JiecangCommands.MEMORY_2 == bytes.fromhex("f1f10d01010f7e")
        assert JiecangCommands.FLAT == bytes.fromhex("f1f10801010a7e")
        assert JiecangCommands.ZERO_G == bytes.fromhex("f1f1070101097e")

    def test_command_lengths(self):
        """Test all commands are 7 bytes."""
        commands = [
            JiecangCommands.MEMORY_1,
            JiecangCommands.MEMORY_2,
            JiecangCommands.FLAT,
            JiecangCommands.ZERO_G,
        ]
        for cmd in commands:
            assert len(cmd) == 7, f"Command {cmd.hex()} should be 7 bytes"

    def test_command_prefix(self):
        """Test all commands start with 0xf1f1."""
        commands = [
            JiecangCommands.MEMORY_1,
            JiecangCommands.MEMORY_2,
            JiecangCommands.FLAT,
            JiecangCommands.ZERO_G,
        ]
        for cmd in commands:
            assert cmd[:2] == bytes([0xF1, 0xF1]), f"Command {cmd.hex()} should start with f1f1"

    def test_command_suffix(self):
        """Test all commands end with 0x7e."""
        commands = [
            JiecangCommands.MEMORY_1,
            JiecangCommands.MEMORY_2,
            JiecangCommands.FLAT,
            JiecangCommands.ZERO_G,
        ]
        for cmd in commands:
            assert cmd[-1] == 0x7E, f"Command {cmd.hex()} should end with 7e"


@pytest.fixture
def mock_jiecang_config_entry_data() -> dict:
    """Return mock config entry data for Jiecang bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Jiecang Test Bed",
        CONF_BED_TYPE: BED_TYPE_JIECANG,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_jiecang_config_entry(
    hass: HomeAssistant, mock_jiecang_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Jiecang bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jiecang Test Bed",
        data=mock_jiecang_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="jiecang_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestJiecangController:
    """Test Jiecang controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == JIECANG_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        command = JiecangCommands.FLAT
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            JIECANG_CHAR_UUID, command, response=False
        )

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        command = JiecangCommands.FLAT
        await coordinator.controller.write_command(
            command, repeat_count=3, repeat_delay_ms=100
        )

        assert mock_bleak_client.write_gatt_char.call_count == 3

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(JiecangCommands.FLAT)


class TestJiecangMotorMovement:
    """Test Jiecang motor movement commands (preset-only limitation)."""

    async def test_move_head_up_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move head up logs warning about preset-only limitation."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        assert "only support preset positions" in caplog.text
        # Should not send any command
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_move_head_down_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move head down logs warning about preset-only limitation."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        assert "only support preset positions" in caplog.text
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_move_legs_up_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move legs up logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        assert "only support preset positions" in caplog.text

    async def test_move_legs_down_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move legs down logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        assert "only support preset positions" in caplog.text

    async def test_move_feet_up_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move feet up logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        assert "only support preset positions" in caplog.text

    async def test_move_back_up_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move back up logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        assert "only support preset positions" in caplog.text

    async def test_stop_all_noop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all does nothing (motor control not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        # Should not send any command
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_move_head_stop_noop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head stop does nothing."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_stop()

        mock_bleak_client.write_gatt_char.assert_not_called()


class TestJiecangPresets:
    """Test Jiecang preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        # Check first call was FLAT command
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == JiecangCommands.FLAT

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == JiecangCommands.ZERO_G

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, JiecangCommands.MEMORY_1),
            (2, JiecangCommands.MEMORY_2),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_command

    async def test_preset_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test preset memory with invalid number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        # Memory 3 is not supported on Jiecang
        await coordinator.controller.preset_memory(3)

        assert "only support memory presets 1 and 2" in caplog.text

    async def test_preset_commands_repeat(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset commands are sent with repeat (3 times per code)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        # Jiecang presets use repeat_count=3
        assert mock_bleak_client.write_gatt_char.call_count == 3


class TestJiecangProgramMemory:
    """Test Jiecang program memory (not supported)."""

    async def test_program_memory_warns(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning about not being supported."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text
        mock_bleak_client.write_gatt_char.assert_not_called()


class TestJiecangPositionNotifications:
    """Test Jiecang position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Jiecang doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()

    async def test_stop_notify_noop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test stop_notify completes without error."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.stop_notify()
