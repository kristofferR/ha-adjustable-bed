"""Tests for Solace bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.solace import (
    SolaceCommands,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SOLACE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_solace_config_entry_data() -> dict:
    """Return mock config entry data for Solace bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Solace Test Bed",
        CONF_BED_TYPE: BED_TYPE_SOLACE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_solace_config_entry(
    hass: HomeAssistant, mock_solace_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Solace bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Solace Test Bed",
        data=mock_solace_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="solace_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestSolaceController:
    """Test Solace controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == SOLACE_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        command = SolaceCommands.MOTOR_STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(SolaceCommands.MOTOR_STOP)


class TestSolaceMovement:
    """Test Solace movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends BACK_UP followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # First call should be BACK_UP
        first_command = calls[0][0][1]
        assert first_command == SolaceCommands.MOTOR_BACK_UP

        # Last call should be stop
        last_command = calls[-1][0][1]
        assert last_command == SolaceCommands.MOTOR_STOP

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends BACK_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == SolaceCommands.MOTOR_BACK_DOWN

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends LEGS_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == SolaceCommands.MOTOR_LEGS_UP

    async def test_move_legs_down(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs down sends LEGS_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == SolaceCommands.MOTOR_LEGS_DOWN

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MOTOR_STOP, response=True
        )


class TestSolacePresets:
    """Test Solace preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SolaceCommands.PRESET_ALL_FLAT

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SolaceCommands.PRESET_ZERO_G

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SolaceCommands.PRESET_TV

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SolaceCommands.PRESET_ANTI_SNORE

    async def test_preset_yoga(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset yoga command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_yoga()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SolaceCommands.PRESET_YOGA

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, SolaceCommands.PRESET_MEMORY_1),
            (2, SolaceCommands.PRESET_MEMORY_2),
            (3, SolaceCommands.PRESET_MEMORY_3),
            (4, SolaceCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_command

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, SolaceCommands.PROGRAM_MEMORY_1),
            (2, SolaceCommands.PROGRAM_MEMORY_2),
            (3, SolaceCommands.PROGRAM_MEMORY_3),
            (4, SolaceCommands.PROGRAM_MEMORY_4),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, expected_command, response=True
        )


class TestSolacePositionNotifications:
    """Test Solace position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Solace doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()


class TestSolaceMassage:
    """Test Solace massage commands."""

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage head up command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_HEAD_UP, response=True
        )

    async def test_massage_head_down(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage head down command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_down()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_HEAD_DOWN, response=True
        )

    async def test_massage_foot_up(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage foot up command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_up()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_FOOT_UP, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage foot down command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_FOOT_DOWN, response=True
        )

    async def test_massage_intensity_up(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage frequency up command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_intensity_up()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_FREQUENCY_UP, response=True
        )

    async def test_massage_intensity_down(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage frequency down command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_intensity_down()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_FREQUENCY_DOWN, response=True
        )

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, SolaceCommands.MASSAGE_STOP, response=True
        )
