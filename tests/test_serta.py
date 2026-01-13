"""Tests for Serta Motion Perfect III bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.serta import (
    SertaCommands,
    SertaController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SERTA,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SERTA_WRITE_HANDLE,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestSertaCommands:
    """Test Serta command constants."""

    def test_preset_commands(self):
        """Test preset commands are correct."""
        assert SertaCommands.FLAT == bytes.fromhex("e5fe1600000008fe")
        assert SertaCommands.ZERO_G == bytes.fromhex("e5fe1600100000f6")
        assert SertaCommands.TV == bytes.fromhex("e5fe1600400000c6")
        assert SertaCommands.HEAD_UP_PRESET == bytes.fromhex("e5fe160080000086")
        assert SertaCommands.LOUNGE == bytes.fromhex("e5fe1600200000e6")

    def test_motor_commands(self):
        """Test motor movement commands are correct."""
        assert SertaCommands.HEAD_UP == bytes.fromhex("e5fe160100000005")
        assert SertaCommands.HEAD_DOWN == bytes.fromhex("e5fe160200000004")
        assert SertaCommands.FOOT_UP == bytes.fromhex("e5fe160400000002")
        assert SertaCommands.FOOT_DOWN == bytes.fromhex("e5fe1608000000fe")
        assert SertaCommands.STOP == bytes.fromhex("e5fe160000000006")

    def test_massage_commands(self):
        """Test massage commands are correct."""
        assert SertaCommands.MASSAGE_HEAD_ADD == bytes.fromhex("e5fe1600080000fe")
        assert SertaCommands.MASSAGE_HEAD_MIN == bytes.fromhex("e5fe160000800086")
        assert SertaCommands.MASSAGE_FOOT_ADD == bytes.fromhex("e5fe160004000002")
        assert SertaCommands.MASSAGE_FOOT_MIN == bytes.fromhex("e5fe160000000105")
        assert SertaCommands.MASSAGE_HEAD_FOOT_ON == bytes.fromhex("e5fe160001000005")
        assert SertaCommands.MASSAGE_TIMER == bytes.fromhex("e5fe160002000004")

    def test_command_lengths(self):
        """Test all commands are 8 bytes."""
        commands = [
            SertaCommands.FLAT,
            SertaCommands.ZERO_G,
            SertaCommands.TV,
            SertaCommands.HEAD_UP_PRESET,
            SertaCommands.LOUNGE,
            SertaCommands.HEAD_UP,
            SertaCommands.HEAD_DOWN,
            SertaCommands.FOOT_UP,
            SertaCommands.FOOT_DOWN,
            SertaCommands.MASSAGE_HEAD_ADD,
            SertaCommands.MASSAGE_HEAD_MIN,
            SertaCommands.MASSAGE_FOOT_ADD,
            SertaCommands.MASSAGE_FOOT_MIN,
            SertaCommands.MASSAGE_HEAD_FOOT_ON,
            SertaCommands.MASSAGE_TIMER,
            SertaCommands.STOP,
        ]
        for cmd in commands:
            assert len(cmd) == 8, f"Command {cmd.hex()} should be 8 bytes"

    def test_command_prefix(self):
        """Test all commands have e5fe16 prefix."""
        commands = [
            SertaCommands.FLAT,
            SertaCommands.ZERO_G,
            SertaCommands.TV,
            SertaCommands.HEAD_UP,
            SertaCommands.HEAD_DOWN,
            SertaCommands.STOP,
        ]
        for cmd in commands:
            assert cmd[:3] == bytes.fromhex("e5fe16"), f"Command {cmd.hex()} should have e5fe16 prefix"


@pytest.fixture
def mock_serta_config_entry_data() -> dict:
    """Return mock config entry data for Serta bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Serta Test Bed",
        CONF_BED_TYPE: BED_TYPE_SERTA,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_serta_config_entry(
    hass: HomeAssistant, mock_serta_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Serta bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serta Test Bed",
        data=mock_serta_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="serta_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestSertaController:
    """Test Serta controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct handle-based identifier."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        # Serta uses handle-based writes
        expected = f"handle-0x{SERTA_WRITE_HANDLE:04x}"
        assert coordinator.controller.control_characteristic_uuid == expected

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        command = SertaCommands.STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, command, response=True
        )

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        command = SertaCommands.HEAD_UP
        await coordinator.controller.write_command(
            command, repeat_count=3, repeat_delay_ms=50
        )

        assert mock_bleak_client.write_gatt_char.call_count == 3

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(SertaCommands.STOP)

    async def test_write_command_bleak_error(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command handles BleakError."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.write_gatt_char.side_effect = BleakError("Write failed")

        with pytest.raises(BleakError):
            await coordinator.controller.write_command(SertaCommands.STOP)


class TestSertaMovement:
    """Test Serta movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # First call should be HEAD_UP
        first_command = calls[0][0][1]
        assert first_command == SertaCommands.HEAD_UP

        # Last call should be stop
        last_command = calls[-1][0][1]
        assert last_command == SertaCommands.STOP

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        first_command = calls[0][0][1]
        assert first_command == SertaCommands.HEAD_DOWN

        last_command = calls[-1][0][1]
        assert last_command == SertaCommands.STOP

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends FOOT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == SertaCommands.FOOT_UP

    async def test_move_feet_down(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet down sends FOOT_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == SertaCommands.FOOT_DOWN

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.STOP, response=True
        )

    async def test_move_back_up_delegates_to_head(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move back up delegates to move head up."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        assert first_command == SertaCommands.HEAD_UP


class TestSertaPresets:
    """Test Serta preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SertaCommands.FLAT

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SertaCommands.ZERO_G

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SertaCommands.TV

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore/lounge command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == SertaCommands.LOUNGE

    async def test_preset_memory_not_supported(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test preset memory logs warning (not supported on Serta)."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        assert "don't support memory presets" in caplog.text


class TestSertaProgramMemory:
    """Test Serta program memory (not supported)."""

    async def test_program_memory_warns(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning about not being supported."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text
        mock_bleak_client.write_gatt_char.assert_not_called()


class TestSertaMassage:
    """Test Serta massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.MASSAGE_HEAD_FOOT_ON, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test increase head massage intensity."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.MASSAGE_HEAD_ADD, response=True
        )

    async def test_massage_head_down(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test decrease head massage intensity."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_down()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.MASSAGE_HEAD_MIN, response=True
        )

    async def test_massage_foot_up(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test increase foot massage intensity."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_up()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.MASSAGE_FOOT_ADD, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test decrease foot massage intensity."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.MASSAGE_FOOT_MIN, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage timer step command."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        mock_bleak_client.write_gatt_char.assert_called_with(
            SERTA_WRITE_HANDLE, SertaCommands.MASSAGE_TIMER, response=True
        )


class TestSertaPositionNotifications:
    """Test Serta position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Serta doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()

    async def test_stop_notify_noop(
        self,
        hass: HomeAssistant,
        mock_serta_config_entry,
        mock_coordinator_connected,
    ):
        """Test stop_notify completes without error."""
        coordinator = AdjustableBedCoordinator(hass, mock_serta_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.stop_notify()
