"""Tests for Linak bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.linak import LinakCommands, LinakController
from custom_components.adjustable_bed.const import LINAK_CONTROL_CHAR_UUID
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestLinakCommands:
    """Test Linak command constants."""

    def test_preset_memory_commands(self):
        """Test preset memory commands are correct."""
        assert LinakCommands.PRESET_MEMORY_1 == bytes([0x0E, 0x00])
        assert LinakCommands.PRESET_MEMORY_2 == bytes([0x0F, 0x00])
        assert LinakCommands.PRESET_MEMORY_3 == bytes([0x0C, 0x00])
        assert LinakCommands.PRESET_MEMORY_4 == bytes([0x44, 0x00])

    def test_program_memory_commands(self):
        """Test program memory commands are correct."""
        assert LinakCommands.PROGRAM_MEMORY_1 == bytes([0x38, 0x00])
        assert LinakCommands.PROGRAM_MEMORY_2 == bytes([0x39, 0x00])
        assert LinakCommands.PROGRAM_MEMORY_3 == bytes([0x3A, 0x00])
        assert LinakCommands.PROGRAM_MEMORY_4 == bytes([0x45, 0x00])

    def test_movement_commands(self):
        """Test movement commands are correct."""
        assert LinakCommands.MOVE_STOP == bytes([0x00, 0x00])
        assert LinakCommands.MOVE_HEAD_UP == bytes([0x03, 0x00])
        assert LinakCommands.MOVE_HEAD_DOWN == bytes([0x02, 0x00])
        assert LinakCommands.MOVE_LEGS_UP == bytes([0x09, 0x00])
        assert LinakCommands.MOVE_LEGS_DOWN == bytes([0x08, 0x00])

    def test_light_commands(self):
        """Test light commands are correct."""
        assert LinakCommands.LIGHTS_ON == bytes([0x92, 0x00])
        assert LinakCommands.LIGHTS_OFF == bytes([0x93, 0x00])
        assert LinakCommands.LIGHTS_TOGGLE == bytes([0x94, 0x00])

    def test_massage_commands(self):
        """Test massage commands are correct."""
        assert LinakCommands.MASSAGE_ALL_OFF == bytes([0x80, 0x00])
        assert LinakCommands.MASSAGE_ALL_TOGGLE == bytes([0x91, 0x00])
        assert LinakCommands.MASSAGE_HEAD_TOGGLE == bytes([0xA6, 0x00])
        assert LinakCommands.MASSAGE_FOOT_TOGGLE == bytes([0xA7, 0x00])


class TestLinakController:
    """Test Linak controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == LINAK_CONTROL_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        command = LinakCommands.MOVE_STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, command, response=True
        )

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        command = LinakCommands.MOVE_HEAD_UP
        await coordinator.controller.write_command(command, repeat_count=3, repeat_delay_ms=50)

        assert mock_bleak_client.write_gatt_char.call_count == 3

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # Simulate disconnection
        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(LinakCommands.MOVE_STOP)

    async def test_write_command_bleak_error(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command handles BleakError."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.write_gatt_char.side_effect = BleakError("Write failed")

        with pytest.raises(BleakError):
            await coordinator.controller.write_command(LinakCommands.MOVE_STOP)


class TestLinakMovement:
    """Test Linak movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends repeated commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        # Should have sent multiple HEAD_UP commands plus STOP
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be stop
        last_command = calls[-1][0][1]
        assert last_command == LinakCommands.MOVE_STOP

    async def test_move_legs_down(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs down sends repeated commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        last_command = calls[-1][0][1]
        assert last_command == LinakCommands.MOVE_STOP

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.MOVE_STOP, response=True
        )


class TestLinakPresets:
    """Test Linak preset commands."""

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LinakCommands.PRESET_MEMORY_1),
            (2, LinakCommands.PRESET_MEMORY_2),
            (3, LinakCommands.PRESET_MEMORY_3),
            (4, LinakCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        # First call should be the preset command (with repeats)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_command

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LinakCommands.PROGRAM_MEMORY_1),
            (2, LinakCommands.PROGRAM_MEMORY_2),
            (3, LinakCommands.PROGRAM_MEMORY_3),
            (4, LinakCommands.PROGRAM_MEMORY_4),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, expected_command, response=True
        )


class TestLinakLights:
    """Test Linak light commands."""

    async def test_lights_on(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights on command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.LIGHTS_ON, response=True
        )

    async def test_lights_off(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.LIGHTS_OFF, response=True
        )

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.LIGHTS_TOGGLE, response=True
        )


class TestLinakMassage:
    """Test Linak massage commands."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.MASSAGE_ALL_OFF, response=True
        )

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.MASSAGE_ALL_TOGGLE, response=True
        )


class TestLinakPositionData:
    """Test Linak position data handling."""

    async def test_handle_position_data(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test position data handling."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Simulate position data: 410 out of 820 max = 50% = 34 degrees
        data = bytearray([0x9A, 0x01])  # 410 in little-endian

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_called_once_with("back", 34.0)

    async def test_handle_position_data_max(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test position data at maximum."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Max position
        data = bytearray([0x34, 0x03])  # 820 in little-endian

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_called_once_with("back", 68.0)

    async def test_handle_position_data_zero(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test position data at zero."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        data = bytearray([0x00, 0x00])

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_called_once_with("back", 0.0)

    async def test_handle_position_data_invalid(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test invalid position data is ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Too short data
        data = bytearray([0x00])

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_not_called()
