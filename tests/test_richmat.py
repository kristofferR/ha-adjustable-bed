"""Tests for Richmat bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.richmat import (
    RichmatCommands,
    RichmatController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    RICHMAT_NORDIC_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestRichmatCommands:
    """Test Richmat command constants."""

    def test_preset_commands(self):
        """Test preset command values."""
        assert RichmatCommands.PRESET_FLAT == 0x31
        assert RichmatCommands.PRESET_ANTI_SNORE == 0x46
        assert RichmatCommands.PRESET_LOUNGE == 0x59
        assert RichmatCommands.PRESET_MEMORY_1 == 0x2E
        assert RichmatCommands.PRESET_MEMORY_2 == 0x2F
        assert RichmatCommands.PRESET_TV == 0x58
        assert RichmatCommands.PRESET_ZERO_G == 0x45

    def test_program_commands(self):
        """Test program command values."""
        assert RichmatCommands.PROGRAM_ANTI_SNORE == 0x69
        assert RichmatCommands.PROGRAM_LOUNGE == 0x65
        assert RichmatCommands.PROGRAM_MEMORY_1 == 0x2B
        assert RichmatCommands.PROGRAM_MEMORY_2 == 0x2C
        assert RichmatCommands.PROGRAM_TV == 0x64
        assert RichmatCommands.PROGRAM_ZERO_G == 0x66

    def test_motor_commands(self):
        """Test motor command values."""
        assert RichmatCommands.MOTOR_PILLOW_UP == 0x3F
        assert RichmatCommands.MOTOR_PILLOW_DOWN == 0x40
        assert RichmatCommands.MOTOR_HEAD_UP == 0x24
        assert RichmatCommands.MOTOR_HEAD_DOWN == 0x25
        assert RichmatCommands.MOTOR_FEET_UP == 0x26
        assert RichmatCommands.MOTOR_FEET_DOWN == 0x27
        assert RichmatCommands.MOTOR_LUMBAR_UP == 0x41
        assert RichmatCommands.MOTOR_LUMBAR_DOWN == 0x42
        assert RichmatCommands.END == 0x6E

    def test_massage_commands(self):
        """Test massage command values."""
        assert RichmatCommands.MASSAGE_HEAD_STEP == 0x4C
        assert RichmatCommands.MASSAGE_FOOT_STEP == 0x4E
        assert RichmatCommands.MASSAGE_PATTERN_STEP == 0x48
        assert RichmatCommands.MASSAGE_TOGGLE == 0x5D

    def test_light_commands(self):
        """Test light command values."""
        assert RichmatCommands.LIGHTS_TOGGLE == 0x3C


@pytest.fixture
def mock_richmat_config_entry_data() -> dict:
    """Return mock config entry data for Richmat bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Richmat Test Bed",
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_richmat_config_entry(
    hass: HomeAssistant, mock_richmat_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Richmat bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Richmat Test Bed",
        data=mock_richmat_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="richmat_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestRichmatController:
    """Test Richmat controller."""

    async def test_control_characteristic_uuid_nordic(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports Nordic characteristic UUID by default."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == RICHMAT_NORDIC_CHAR_UUID

    async def test_build_command_nordic(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Nordic variant builds single-byte commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Nordic variant: single byte
        command = coordinator.controller._build_command(RichmatCommands.PRESET_FLAT)
        assert command == bytes([0x31])

    async def test_build_command_wilinke(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test WiLinke variant builds 5-byte commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Create a WiLinke controller directly
        controller = RichmatController(coordinator, is_wilinke=True)

        # WiLinke: [110, 1, 0, cmd, cmd+111]
        command = controller._build_command(RichmatCommands.PRESET_FLAT)
        assert len(command) == 5
        assert command[0] == 110
        assert command[1] == 1
        assert command[2] == 0
        assert command[3] == RichmatCommands.PRESET_FLAT
        # checksum = (cmd + 111) & 0xFF
        expected_checksum = (RichmatCommands.PRESET_FLAT + 111) & 0xFF
        assert command[4] == expected_checksum

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(RichmatCommands.END)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(RichmatCommands.END)
            )


class TestRichmatMovement:
    """Test Richmat movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be END command
        last_command = calls[-1][0][1]
        expected_end = coordinator.controller._build_command(RichmatCommands.END)
        assert last_command == expected_end

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends FEET_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be FEET_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(RichmatCommands.MOTOR_FEET_UP)
        assert first_command == expected

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends END command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_end = coordinator.controller._build_command(RichmatCommands.END)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_end, response=True
        )


class TestRichmatPresets:
    """Test Richmat preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_TV)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_ANTI_SNORE)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, RichmatCommands.PRESET_MEMORY_1),
            (2, RichmatCommands.PRESET_MEMORY_2),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, RichmatCommands.PROGRAM_MEMORY_1),
            (2, RichmatCommands.PROGRAM_MEMORY_2),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )


class TestRichmatLights:
    """Test Richmat light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.LIGHTS_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )


class TestRichmatMassage:
    """Test Richmat massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_HEAD_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_FOOT_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage mode step command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_PATTERN_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )


class TestRichmatPositionNotifications:
    """Test Richmat position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Richmat doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
