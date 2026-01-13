"""Tests for MotoSleep bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motosleep import (
    MotoSleepCommands,
    MotoSleepController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTOSLEEP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    MOTOSLEEP_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestMotoSleepCommands:
    """Test MotoSleep command constants."""

    def test_preset_commands(self):
        """Test preset command values (ASCII characters)."""
        assert MotoSleepCommands.PRESET_HOME == ord('O')
        assert MotoSleepCommands.PRESET_MEMORY_1 == ord('U')
        assert MotoSleepCommands.PRESET_MEMORY_2 == ord('V')
        assert MotoSleepCommands.PRESET_ANTI_SNORE == ord('R')
        assert MotoSleepCommands.PRESET_TV == ord('S')
        assert MotoSleepCommands.PRESET_ZERO_G == ord('T')

    def test_program_commands(self):
        """Test program command values."""
        assert MotoSleepCommands.PROGRAM_MEMORY_1 == ord('Z')
        assert MotoSleepCommands.PROGRAM_MEMORY_2 == ord('a')
        assert MotoSleepCommands.PROGRAM_ANTI_SNORE == ord('W')
        assert MotoSleepCommands.PROGRAM_TV == ord('X')
        assert MotoSleepCommands.PROGRAM_ZERO_G == ord('Y')

    def test_motor_commands(self):
        """Test motor command values."""
        assert MotoSleepCommands.MOTOR_HEAD_UP == ord('K')
        assert MotoSleepCommands.MOTOR_HEAD_DOWN == ord('L')
        assert MotoSleepCommands.MOTOR_FEET_UP == ord('M')
        assert MotoSleepCommands.MOTOR_FEET_DOWN == ord('N')
        assert MotoSleepCommands.MOTOR_NECK_UP == ord('P')
        assert MotoSleepCommands.MOTOR_NECK_DOWN == ord('Q')

    def test_massage_commands(self):
        """Test massage command values."""
        assert MotoSleepCommands.MASSAGE_HEAD_STEP == ord('C')
        assert MotoSleepCommands.MASSAGE_FOOT_STEP == ord('B')
        assert MotoSleepCommands.MASSAGE_STOP == ord('D')
        assert MotoSleepCommands.MASSAGE_HEAD_UP == ord('G')
        assert MotoSleepCommands.MASSAGE_HEAD_DOWN == ord('H')
        assert MotoSleepCommands.MASSAGE_FOOT_UP == ord('E')
        assert MotoSleepCommands.MASSAGE_FOOT_DOWN == ord('F')

    def test_light_commands(self):
        """Test light command values."""
        assert MotoSleepCommands.LIGHTS_TOGGLE == ord('A')


@pytest.fixture
def mock_motosleep_config_entry_data() -> dict:
    """Return mock config entry data for MotoSleep bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "MotoSleep Test Bed",
        CONF_BED_TYPE: BED_TYPE_MOTOSLEEP,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_motosleep_config_entry(
    hass: HomeAssistant, mock_motosleep_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for MotoSleep bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MotoSleep Test Bed",
        data=mock_motosleep_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="motosleep_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestMotoSleepController:
    """Test MotoSleep controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == MOTOSLEEP_CHAR_UUID

    async def test_build_command(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building (2-byte format)."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(ord('K'))

        # MotoSleep: [0x24, char_code] - '$' followed by command char
        assert len(command) == 2
        assert command[0] == 0x24  # '$'
        assert command[1] == ord('K')

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(MotoSleepCommands.MASSAGE_STOP)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(MotoSleepCommands.MASSAGE_STOP)
            )


class TestMotoSleepMovement:
    """Test MotoSleep movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be HEAD_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MotoSleepCommands.MOTOR_HEAD_UP)
        assert first_command == expected

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends HEAD_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MotoSleepCommands.MOTOR_HEAD_DOWN)
        assert first_command == expected

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up sends FEET_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MotoSleepCommands.MOTOR_FEET_UP)
        assert first_command == expected

    async def test_move_head_stop_noop(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head stop does nothing (MotoSleep stops when button released)."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_stop()

        # Should not send any command
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends massage stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected = coordinator.controller._build_command(MotoSleepCommands.MASSAGE_STOP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )


class TestMotoSleepPresets:
    """Test MotoSleep preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat/home command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected = coordinator.controller._build_command(MotoSleepCommands.PRESET_HOME)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected = coordinator.controller._build_command(MotoSleepCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        expected = coordinator.controller._build_command(MotoSleepCommands.PRESET_TV)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        expected = coordinator.controller._build_command(MotoSleepCommands.PRESET_ANTI_SNORE)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    @pytest.mark.parametrize(
        "memory_num,expected_char",
        [
            (1, MotoSleepCommands.PRESET_MEMORY_1),
            (2, MotoSleepCommands.PRESET_MEMORY_2),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_char: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected = coordinator.controller._build_command(expected_char)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected

    @pytest.mark.parametrize(
        "memory_num,expected_char",
        [
            (1, MotoSleepCommands.PROGRAM_MEMORY_1),
            (2, MotoSleepCommands.PROGRAM_MEMORY_2),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_char: int,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        expected = coordinator.controller._build_command(expected_char)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )


class TestMotoSleepLights:
    """Test MotoSleep light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected = coordinator.controller._build_command(MotoSleepCommands.LIGHTS_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )


class TestMotoSleepMassage:
    """Test MotoSleep massage commands."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        expected = coordinator.controller._build_command(MotoSleepCommands.MASSAGE_STOP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_toggle(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_toggle()

        expected = coordinator.controller._build_command(MotoSleepCommands.MASSAGE_HEAD_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )

    async def test_massage_foot_toggle(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_toggle()

        expected = coordinator.controller._build_command(MotoSleepCommands.MASSAGE_FOOT_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected = coordinator.controller._build_command(MotoSleepCommands.MASSAGE_HEAD_UP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MOTOSLEEP_CHAR_UUID, expected, response=True
        )


class TestMotoSleepPositionNotifications:
    """Test MotoSleep position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_motosleep_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that MotoSleep doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_motosleep_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text
