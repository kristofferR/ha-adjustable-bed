"""Tests for Okin 7-byte bed controller."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_7byte import (
    Okin7ByteCommands,
    Okin7ByteController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_7BYTE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    NECTAR_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_okin_7byte_config_entry_data() -> dict:
    """Return mock config entry data for Okin 7-byte bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin 7-byte Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIN_7BYTE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_7byte_config_entry(
    hass: HomeAssistant, mock_okin_7byte_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin 7-byte bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin 7-byte Test Bed",
        data=mock_okin_7byte_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_7byte_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestOkin7ByteCommands:
    """Test Okin 7-byte command constants."""

    def test_all_commands_are_7_bytes(self):
        """All commands should be exactly 7 bytes."""
        commands = [
            Okin7ByteCommands.HEAD_UP,
            Okin7ByteCommands.HEAD_DOWN,
            Okin7ByteCommands.FOOT_UP,
            Okin7ByteCommands.FOOT_DOWN,
            Okin7ByteCommands.LUMBAR_UP,
            Okin7ByteCommands.LUMBAR_DOWN,
            Okin7ByteCommands.STOP,
            Okin7ByteCommands.FLAT,
            Okin7ByteCommands.LOUNGE,
            Okin7ByteCommands.ZERO_GRAVITY,
            Okin7ByteCommands.ANTI_SNORE,
            Okin7ByteCommands.MASSAGE_ON,
            Okin7ByteCommands.MASSAGE_WAVE,
            Okin7ByteCommands.MASSAGE_OFF,
            Okin7ByteCommands.LIGHT_ON,
            Okin7ByteCommands.LIGHT_OFF,
        ]
        for cmd in commands:
            assert len(cmd) == 7, f"Command {cmd.hex()} is not 7 bytes"

    def test_command_header_format(self):
        """Commands should start with 5A 01 03 10 30."""
        header = bytes.fromhex("5A01031030")
        commands = [
            Okin7ByteCommands.HEAD_UP,
            Okin7ByteCommands.STOP,
            Okin7ByteCommands.FLAT,
        ]
        for cmd in commands:
            assert cmd[0:5] == header, f"Command {cmd.hex()} has wrong header"

    def test_command_trailer(self):
        """Commands should end with A5."""
        commands = [
            Okin7ByteCommands.HEAD_UP,
            Okin7ByteCommands.STOP,
            Okin7ByteCommands.FLAT,
        ]
        for cmd in commands:
            assert cmd[6] == 0xA5, f"Command {cmd.hex()} doesn't end with A5"

    def test_motor_command_bytes(self):
        """Motor commands should have correct byte 5 values."""
        assert Okin7ByteCommands.HEAD_UP[5] == 0x00
        assert Okin7ByteCommands.HEAD_DOWN[5] == 0x01
        assert Okin7ByteCommands.FOOT_UP[5] == 0x02
        assert Okin7ByteCommands.FOOT_DOWN[5] == 0x03
        assert Okin7ByteCommands.LUMBAR_UP[5] == 0x04
        assert Okin7ByteCommands.LUMBAR_DOWN[5] == 0x07
        assert Okin7ByteCommands.STOP[5] == 0x0F

    def test_preset_command_bytes(self):
        """Preset commands should have correct byte 5 values."""
        assert Okin7ByteCommands.FLAT[5] == 0x10
        assert Okin7ByteCommands.LOUNGE[5] == 0x11
        assert Okin7ByteCommands.ZERO_GRAVITY[5] == 0x13
        assert Okin7ByteCommands.ANTI_SNORE[5] == 0x16

    def test_massage_command_bytes(self):
        """Massage commands should have correct byte 5 values."""
        assert Okin7ByteCommands.MASSAGE_ON[5] == 0x58
        assert Okin7ByteCommands.MASSAGE_WAVE[5] == 0x59
        assert Okin7ByteCommands.MASSAGE_OFF[5] == 0x5A

    def test_light_command_bytes(self):
        """Light commands should have correct byte 5 values."""
        assert Okin7ByteCommands.LIGHT_ON[5] == 0x73
        assert Okin7ByteCommands.LIGHT_OFF[5] == 0x74


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestOkin7ByteController:
    """Test Okin7ByteController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Nectar write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == NECTAR_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lounge preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_lounge is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lights."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_memory_presets_not_supported(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should NOT support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is False


class TestOkin7ByteMovement:
    """Test Okin 7-byte movement commands."""

    async def test_move_head_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 7
        assert first_call_data == Okin7ByteCommands.HEAD_UP

    async def test_move_lumbar_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should send LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == Okin7ByteCommands.LUMBAR_UP

    async def test_stop_all_sends_stop_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == Okin7ByteCommands.STOP

    async def test_movement_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP
        last_call_data = calls[-1][0][1]
        assert last_call_data == Okin7ByteCommands.STOP


class TestOkin7BytePresets:
    """Test Okin 7-byte preset commands."""

    async def test_preset_flat_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == Okin7ByteCommands.FLAT

    async def test_preset_zero_g_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send ZERO_GRAVITY command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == Okin7ByteCommands.ZERO_GRAVITY


class TestOkin7ByteLights:
    """Test Okin 7-byte light commands."""

    async def test_lights_on_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on should send LIGHT_ON command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == Okin7ByteCommands.LIGHT_ON

    async def test_lights_off_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should send LIGHT_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == Okin7ByteCommands.LIGHT_OFF
