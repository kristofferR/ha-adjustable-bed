"""Tests for DewertOkin bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.dewertokin import (
    DewertOkinCommands,
    DewertOkinController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_DEWERTOKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DEWERTOKIN_WRITE_HANDLE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestDewertOkinCommands:
    """Test DewertOkin command constants."""

    def test_preset_commands(self):
        """Test preset commands are correct."""
        assert DewertOkinCommands.FLAT == bytes.fromhex("040210000000")
        assert DewertOkinCommands.ZERO_G == bytes.fromhex("040200004000")
        assert DewertOkinCommands.TV == bytes.fromhex("040200003000")
        assert DewertOkinCommands.QUIET_SLEEP == bytes.fromhex("040200008000")
        assert DewertOkinCommands.MEMORY_1 == bytes.fromhex("040200001000")
        assert DewertOkinCommands.MEMORY_2 == bytes.fromhex("040200002000")

    def test_motor_commands(self):
        """Test motor movement commands are correct."""
        assert DewertOkinCommands.HEAD_UP == bytes.fromhex("040200000001")
        assert DewertOkinCommands.HEAD_DOWN == bytes.fromhex("040200000002")
        assert DewertOkinCommands.FOOT_UP == bytes.fromhex("040200000004")
        assert DewertOkinCommands.FOOT_DOWN == bytes.fromhex("040200000008")
        assert DewertOkinCommands.STOP == bytes.fromhex("040200000000")

    def test_massage_commands(self):
        """Test massage commands are correct."""
        assert DewertOkinCommands.WAVE_MASSAGE == bytes.fromhex("040280000000")
        assert DewertOkinCommands.HEAD_MASSAGE == bytes.fromhex("040200000800")
        assert DewertOkinCommands.FOOT_MASSAGE == bytes.fromhex("040200400000")
        assert DewertOkinCommands.MASSAGE_OFF == bytes.fromhex("040202000000")

    def test_light_commands(self):
        """Test light commands are correct."""
        assert DewertOkinCommands.UNDERLIGHT == bytes.fromhex("040200020000")

    def test_command_lengths(self):
        """Test all commands are 6 bytes."""
        commands = [
            DewertOkinCommands.FLAT,
            DewertOkinCommands.ZERO_G,
            DewertOkinCommands.TV,
            DewertOkinCommands.QUIET_SLEEP,
            DewertOkinCommands.MEMORY_1,
            DewertOkinCommands.MEMORY_2,
            DewertOkinCommands.HEAD_UP,
            DewertOkinCommands.HEAD_DOWN,
            DewertOkinCommands.FOOT_UP,
            DewertOkinCommands.FOOT_DOWN,
            DewertOkinCommands.WAVE_MASSAGE,
            DewertOkinCommands.HEAD_MASSAGE,
            DewertOkinCommands.FOOT_MASSAGE,
            DewertOkinCommands.MASSAGE_OFF,
            DewertOkinCommands.UNDERLIGHT,
            DewertOkinCommands.STOP,
        ]
        for cmd in commands:
            assert len(cmd) == 6, f"Command {cmd.hex()} should be 6 bytes"


@pytest.fixture
def mock_dewertokin_config_entry_data() -> dict:
    """Return mock config entry data for DewertOkin bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "DewertOkin Test Bed",
        CONF_BED_TYPE: BED_TYPE_DEWERTOKIN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_dewertokin_config_entry(
    hass: HomeAssistant, mock_dewertokin_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for DewertOkin bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="DewertOkin Test Bed",
        data=mock_dewertokin_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="dewertokin_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestDewertOkinController:
    """Test DewertOkin controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct handle-based identifier."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        # DewertOkin uses handle-based writes, so UUID is a handle placeholder
        expected = f"handle-0x{DEWERTOKIN_WRITE_HANDLE:04x}"
        assert coordinator.controller.control_characteristic_uuid == expected

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        command = DewertOkinCommands.STOP
        await coordinator.controller.write_command(command)

        # DewertOkin uses handle-based writes (integer handle)
        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, command, response=False
        )

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        command = DewertOkinCommands.HEAD_UP
        await coordinator.controller.write_command(
            command, repeat_count=3, repeat_delay_ms=50
        )

        assert mock_bleak_client.write_gatt_char.call_count == 3

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(DewertOkinCommands.STOP)

    async def test_write_command_bleak_error(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command handles BleakError."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.write_gatt_char.side_effect = BleakError("Write failed")

        with pytest.raises(BleakError):
            await coordinator.controller.write_command(DewertOkinCommands.STOP)


class TestDewertOkinMovement:
    """Test DewertOkin movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be stop
        last_command = calls[-1][0][1]
        assert last_command == DewertOkinCommands.STOP

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1
        last_command = calls[-1][0][1]
        assert last_command == DewertOkinCommands.STOP

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends FOOT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be FOOT_UP
        first_command = calls[0][0][1]
        assert first_command == DewertOkinCommands.FOOT_UP

    async def test_move_feet_down(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet down sends FOOT_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == DewertOkinCommands.FOOT_DOWN

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.STOP, response=False
        )


class TestDewertOkinPresets:
    """Test DewertOkin preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == DewertOkinCommands.FLAT

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == DewertOkinCommands.ZERO_G

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == DewertOkinCommands.TV

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore/quiet sleep command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == DewertOkinCommands.QUIET_SLEEP

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, DewertOkinCommands.MEMORY_1),
            (2, DewertOkinCommands.MEMORY_2),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_command

    async def test_preset_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test preset memory with invalid number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        # Memory 3 is not supported on DewertOkin
        await coordinator.controller.preset_memory(3)

        assert "only support memory presets 1 and 2" in caplog.text


class TestDewertOkinLights:
    """Test DewertOkin light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.UNDERLIGHT, response=False
        )

    async def test_lights_on(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights on uses toggle (since DewertOkin only has toggle)."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.UNDERLIGHT, response=False
        )


class TestDewertOkinMassage:
    """Test DewertOkin massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.WAVE_MASSAGE, response=False
        )

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.MASSAGE_OFF, response=False
        )

    async def test_massage_head_toggle(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.HEAD_MASSAGE, response=False
        )

    async def test_massage_foot_toggle(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            DEWERTOKIN_WRITE_HANDLE, DewertOkinCommands.FOOT_MASSAGE, response=False
        )


class TestDewertOkinPositionNotifications:
    """Test DewertOkin position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test that DewertOkin doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        # Should log that notifications aren't supported
        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_dewertokin_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_dewertokin_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
