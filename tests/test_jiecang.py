"""Tests for Jiecang bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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

        command = bytes.fromhex("f1f10801010a7e")
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            JIECANG_CHAR_UUID, command, response=True
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

        command = bytes.fromhex("f1f10801010a7e")
        await coordinator.controller.write_command(command, repeat_count=3, repeat_delay_ms=100)

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
            await coordinator.controller.write_command(bytes.fromhex("f1f10801010a7e"))


class TestJiecangMotorMovement:
    """Test Jiecang motor movement commands (full Comfort Motion protocol)."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends HEAD_UP command followed by BUTTON_RELEASE."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        # Should send HEAD_UP commands followed by BUTTON_RELEASE
        assert mock_bleak_client.write_gatt_char.call_count >= 2
        # First call should be HEAD_UP
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f1010101037e")
        # Last call should be BUTTON_RELEASE
        last_call = mock_bleak_client.write_gatt_char.call_args_list[-1]
        assert last_call[0][1] == bytes.fromhex("f1f14e004e7e")

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends HEAD_DOWN command followed by BUTTON_RELEASE."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        # Should send HEAD_DOWN commands followed by BUTTON_RELEASE
        assert mock_bleak_client.write_gatt_char.call_count >= 2
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f1020101047e")
        last_call = mock_bleak_client.write_gatt_char.call_args_list[-1]
        assert last_call[0][1] == bytes.fromhex("f1f14e004e7e")

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends LEG_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        assert mock_bleak_client.write_gatt_char.call_count >= 2
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f1030101057e")

    async def test_move_legs_down(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs down sends LEG_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        assert mock_bleak_client.write_gatt_char.call_count >= 2
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f1040101067e")

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up sends LEG_UP command (alias)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        assert mock_bleak_client.write_gatt_char.call_count >= 2
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f1030101057e")

    async def test_move_back_up(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move back up sends HEAD_UP command (alias)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        assert mock_bleak_client.write_gatt_char.call_count >= 2
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f1010101037e")

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends BUTTON_RELEASE command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        # Should send BUTTON_RELEASE
        mock_bleak_client.write_gatt_char.assert_called()
        last_call = mock_bleak_client.write_gatt_char.call_args_list[-1]
        assert last_call[0][1] == bytes.fromhex("f1f14e004e7e")

    async def test_move_head_stop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head stop sends BUTTON_RELEASE command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_stop()

        mock_bleak_client.write_gatt_char.assert_called()
        last_call = mock_bleak_client.write_gatt_char.call_args_list[-1]
        assert last_call[0][1] == bytes.fromhex("f1f14e004e7e")


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
        assert first_call[0][1] == bytes.fromhex("f1f10801010a7e")

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
        assert first_call[0][1] == bytes.fromhex("f1f1070101097e")

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, bytes.fromhex("f1f10b01010d7e")),
            (2, bytes.fromhex("f1f10d01010f7e")),
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

    async def test_preset_memory_3(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory 3 (Jiecang supports 1-3)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(3)

        # Memory 3 should send MEMORY_3 command
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f11801011a7e")

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

        # Memory 4 is not supported on Jiecang (1-3 only)
        await coordinator.controller.preset_memory(4)

        assert "support memory presets 1-3 only" in caplog.text

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
    """Test Jiecang program memory (supported via BLE)."""

    async def test_program_memory_1(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test program memory 1 sends MEMORY_1_SET command."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        # Should send MEMORY_1_SET command
        mock_bleak_client.write_gatt_char.assert_called()
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == bytes.fromhex("f1f10a01010c7e")

    async def test_program_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory with invalid number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(4)

        assert "support memory presets 1-3 only" in caplog.text


class TestJiecangPositionNotifications:
    """Test Jiecang position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

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
