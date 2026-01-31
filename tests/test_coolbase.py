"""Tests for Cool Base bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.coolbase import (
    CoolBaseCommands,
    CoolBaseController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_coolbase_config_entry_data() -> dict:
    """Return mock config entry data for Cool Base bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Cool Base Test Bed",
        CONF_BED_TYPE: BED_TYPE_COOLBASE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_coolbase_config_entry(
    hass: HomeAssistant, mock_coolbase_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Cool Base bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cool Base Test Bed",
        data=mock_coolbase_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="coolbase_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestCoolBaseCommands:
    """Test Cool Base command constants."""

    def test_motor_commands(self):
        """Motor commands should be correct values."""
        assert CoolBaseCommands.MOTOR_HEAD_UP == 0x01
        assert CoolBaseCommands.MOTOR_HEAD_DOWN == 0x02
        assert CoolBaseCommands.MOTOR_FEET_UP == 0x04
        assert CoolBaseCommands.MOTOR_FEET_DOWN == 0x08

    def test_preset_commands(self):
        """Preset commands should be correct values."""
        assert CoolBaseCommands.PRESET_FLAT == 0x08000000
        assert CoolBaseCommands.PRESET_ZERO_G == 0x00001000
        assert CoolBaseCommands.PRESET_TV == 0x00004000
        assert CoolBaseCommands.PRESET_ANTI_SNORE == 0x00008000
        assert CoolBaseCommands.PRESET_MEMORY_1 == 0x00010000

    def test_light_command(self):
        """Light toggle command should be correct value."""
        assert CoolBaseCommands.TOGGLE_LIGHT == 0x00020000

    def test_massage_commands(self):
        """Massage commands should be correct values."""
        assert CoolBaseCommands.MASSAGE_HEAD == 0x00000800
        assert CoolBaseCommands.MASSAGE_FOOT == 0x00000400
        assert CoolBaseCommands.MASSAGE_LEVEL == 0x04000000

    def test_fan_commands(self):
        """Fan commands should be correct values (unique to Cool Base)."""
        assert CoolBaseCommands.FAN_LEFT == 0x00400000
        assert CoolBaseCommands.FAN_RIGHT == 0x40000000
        assert CoolBaseCommands.FAN_SYNC == 0x00040000


# -----------------------------------------------------------------------------
# Packet Building Tests
# -----------------------------------------------------------------------------


class TestCoolBasePacketBuilding:
    """Test Cool Base packet building."""

    def test_packet_is_8_bytes(self):
        """Packets should be exactly 8 bytes."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command(cmd0=0x01)

        assert len(packet) == 8

    def test_packet_header(self):
        """Packet should start with correct header [0xE5, 0xFE, 0x16]."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command()

        assert packet[0] == 0xE5
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_command_bytes_position(self):
        """Command bytes should be in positions 3-6."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command(cmd0=0x11, cmd1=0x22, cmd2=0x33, cmd3=0x44)

        assert packet[3] == 0x11  # cmd0
        assert packet[4] == 0x22  # cmd1
        assert packet[5] == 0x33  # cmd2
        assert packet[6] == 0x44  # cmd3

    def test_checksum_calculation(self):
        """Checksum should be XOR-based: (sum ^ 0xFF) & 0xFF."""
        controller = CoolBaseController(MagicMock())
        packet = controller._build_command()  # All zeros for command bytes

        # Header sum: 0xE5 + 0xFE + 0x16 = 0x1F9
        # With all zero commands: sum = 0x1F9
        # checksum = 0x1F9 ^ 0xFF = 0x106, & 0xFF = 0x06
        expected_checksum = (0xE5 + 0xFE + 0x16) ^ 0xFF & 0xFF
        assert packet[7] == expected_checksum

    def test_build_from_value_splits_correctly(self):
        """_build_command_from_value should split 32-bit value into bytes."""
        controller = CoolBaseController(MagicMock())
        # PRESET_FLAT = 0x08000000
        packet = controller._build_command_from_value(CoolBaseCommands.PRESET_FLAT)

        assert packet[3] == 0x00  # cmd0 (bits 0-7)
        assert packet[4] == 0x00  # cmd1 (bits 8-15)
        assert packet[5] == 0x00  # cmd2 (bits 16-23)
        assert packet[6] == 0x08  # cmd3 (bits 24-31)


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestCoolBaseController:
    """Test CoolBaseController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Keeson Base write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_fan_control(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should support fan control (unique feature)."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_fan_control is True

    async def test_fan_level_max(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """Cool Base should have max fan level of 3."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.fan_level_max == 3


# -----------------------------------------------------------------------------
# Movement Tests
# -----------------------------------------------------------------------------


class TestCoolBaseMovement:
    """Test Cool Base movement commands."""

    async def test_move_head_up_sends_8_byte_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 8-byte packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 8

    async def test_stop_all_sends_zero_command(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send all-zero command bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # Command bytes should all be zero
        assert call_data[3] == 0x00
        assert call_data[4] == 0x00
        assert call_data[5] == 0x00
        assert call_data[6] == 0x00


# -----------------------------------------------------------------------------
# Fan Control Tests
# -----------------------------------------------------------------------------


class TestCoolBaseFanControl:
    """Test Cool Base fan control commands."""

    async def test_fan_left_cycle_sends_correct_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """fan_left_cycle should send FAN_LEFT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.fan_left_cycle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FAN_LEFT = 0x00400000 -> cmd2=0x40
        assert call_data[5] == 0x40

    async def test_fan_right_cycle_sends_correct_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """fan_right_cycle should send FAN_RIGHT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.fan_right_cycle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FAN_RIGHT = 0x40000000 -> cmd3=0x40
        assert call_data[6] == 0x40

    async def test_fan_sync_cycle_sends_correct_packet(
        self,
        hass: HomeAssistant,
        mock_coolbase_config_entry,
        mock_coordinator_connected,
    ):
        """fan_sync_cycle should send FAN_SYNC command."""
        coordinator = AdjustableBedCoordinator(hass, mock_coolbase_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.fan_sync_cycle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FAN_SYNC = 0x00040000 -> cmd2=0x04
        assert call_data[5] == 0x04
