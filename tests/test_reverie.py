"""Tests for Reverie bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie import (
    ReverieCommands,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    REVERIE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestReverieCommands:
    """Test Reverie command constants."""

    def test_preset_commands(self):
        """Test preset command values."""
        assert ReverieCommands.PRESET_ZERO_G == [0x15]
        assert ReverieCommands.PRESET_ANTI_SNORE == [0x16]
        assert ReverieCommands.PRESET_FLAT == [0x05]
        assert ReverieCommands.PRESET_MEMORY_1 == [0x11]
        assert ReverieCommands.PRESET_MEMORY_2 == [0x12]
        assert ReverieCommands.PRESET_MEMORY_3 == [0x13]
        assert ReverieCommands.PRESET_MEMORY_4 == [0x14]

    def test_program_commands(self):
        """Test program command values."""
        assert ReverieCommands.PROGRAM_MEMORY_1 == [0x21]
        assert ReverieCommands.PROGRAM_MEMORY_2 == [0x22]
        assert ReverieCommands.PROGRAM_MEMORY_3 == [0x23]
        assert ReverieCommands.PROGRAM_MEMORY_4 == [0x24]

    def test_other_commands(self):
        """Test other command values."""
        assert ReverieCommands.LIGHTS_TOGGLE == [0x5B, 0x00]
        assert ReverieCommands.MOTOR_STOP == [0xFF]

    def test_massage_head(self):
        """Test head massage command factory."""
        cmd = ReverieCommands.massage_head(5)
        assert cmd == [0x53, 5]

    def test_massage_foot(self):
        """Test foot massage command factory."""
        cmd = ReverieCommands.massage_foot(7)
        assert cmd == [0x54, 7]

    def test_massage_wave(self):
        """Test wave massage command factory."""
        cmd = ReverieCommands.massage_wave(3)
        assert cmd == [0x43]  # 0x40 + 3

    def test_motor_head(self):
        """Test head motor position command factory."""
        cmd = ReverieCommands.motor_head(50)
        assert cmd == [0x51, 50]

    def test_motor_feet(self):
        """Test feet motor position command factory."""
        cmd = ReverieCommands.motor_feet(75)
        assert cmd == [0x52, 75]


@pytest.fixture
def mock_reverie_config_entry_data() -> dict:
    """Return mock config entry data for Reverie bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Reverie Test Bed",
        CONF_BED_TYPE: BED_TYPE_REVERIE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_reverie_config_entry(
    hass: HomeAssistant, mock_reverie_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Reverie bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reverie Test Bed",
        data=mock_reverie_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="reverie_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestReverieController:
    """Test Reverie controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == REVERIE_CHAR_UUID

    async def test_build_command_checksum(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building with XOR checksum."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command([0x05])

        # Format: [0x55, ...bytes, checksum]
        # checksum = 0x55 XOR all bytes
        assert command[0] == 0x55
        assert command[1] == 0x05
        expected_checksum = 0x55 ^ 0x05
        assert command[2] == expected_checksum

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(ReverieCommands.MOTOR_STOP)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(ReverieCommands.MOTOR_STOP)
            )


class TestReverieMovement:
    """Test Reverie movement commands (position-based)."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up moves to 100%."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        # Should send motor_head(100) command
        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(ReverieCommands.motor_head(100))
        assert first_command == expected

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down moves to 0%."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(ReverieCommands.motor_head(0))
        assert first_command == expected

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up moves feet to 100%."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(ReverieCommands.motor_feet(100))
        assert first_command == expected

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends MOTOR_STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected = coordinator.controller._build_command(ReverieCommands.MOTOR_STOP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )


class TestReveriePresets:
    """Test Reverie preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected = coordinator.controller._build_command(ReverieCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected = coordinator.controller._build_command(ReverieCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        expected = coordinator.controller._build_command(ReverieCommands.PRESET_ANTI_SNORE)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, ReverieCommands.PRESET_MEMORY_1),
            (2, ReverieCommands.PRESET_MEMORY_2),
            (3, ReverieCommands.PRESET_MEMORY_3),
            (4, ReverieCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: list,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected = coordinator.controller._build_command(expected_command)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, ReverieCommands.PROGRAM_MEMORY_1),
            (2, ReverieCommands.PROGRAM_MEMORY_2),
            (3, ReverieCommands.PROGRAM_MEMORY_3),
            (4, ReverieCommands.PROGRAM_MEMORY_4),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: list,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        expected = coordinator.controller._build_command(expected_command)
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )


class TestReverieLights:
    """Test Reverie light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected = coordinator.controller._build_command(ReverieCommands.LIGHTS_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )


class TestReverieMassage:
    """Test Reverie massage commands."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # Should send head(0) and foot(0) commands
        assert len(calls) >= 2

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        # Level should increment from 0 to 1
        expected = coordinator.controller._build_command(ReverieCommands.massage_head(1))
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_down(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity down (stays at 0)."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_down()

        # Level should stay at 0 (can't go negative)
        expected = coordinator.controller._build_command(ReverieCommands.massage_head(0))
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage wave mode step."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        # Wave level should increment from 0 to 1
        expected = coordinator.controller._build_command(ReverieCommands.massage_wave(1))
        mock_bleak_client.write_gatt_char.assert_called_with(
            REVERIE_CHAR_UUID, expected, response=True
        )


class TestReveriePositionNotifications:
    """Test Reverie position notification handling."""

    async def test_start_notify(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test starting position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        # Reverie uses same char for notify
        mock_bleak_client.start_notify.assert_called_once()

    async def test_parse_position_data(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
    ):
        """Test parsing position notification data."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # Create mock position data: [0x55, 0x51, position, checksum]
        data = bytearray([0x55, 0x51, 50, 0x55 ^ 0x51 ^ 50])
        coordinator.controller._parse_position_data(data)

        # Callback should be called with back position (0x51 maps to "back" in the implementation)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "back"

    async def test_parse_position_data_invalid_header(
        self,
        hass: HomeAssistant,
        mock_reverie_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test parsing position data with invalid header."""
        coordinator = AdjustableBedCoordinator(hass, mock_reverie_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # Invalid header (not 0x55)
        data = bytearray([0x00, 0x51, 50, 0x00])
        coordinator.controller._parse_position_data(data)

        # Callback should not be called
        callback.assert_not_called()
        assert "Invalid Reverie notification header" in caplog.text
