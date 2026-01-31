"""Tests for Scott Living bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.scott_living import (
    ScottLivingCommands,
    ScottLivingController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SCOTT_LIVING,
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
def mock_scott_living_config_entry_data() -> dict:
    """Return mock config entry data for Scott Living bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Scott Living Test Bed",
        CONF_BED_TYPE: BED_TYPE_SCOTT_LIVING,
        CONF_MOTOR_COUNT: 4,  # Head, foot, tilt, lumbar
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_scott_living_config_entry(
    hass: HomeAssistant, mock_scott_living_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Scott Living bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Scott Living Test Bed",
        data=mock_scott_living_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="scott_living_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestScottLivingCommands:
    """Test Scott Living command constants."""

    def test_motor_commands_cmd0(self):
        """Motor commands in cmd0 byte should be correct."""
        assert ScottLivingCommands.MOTOR_HEAD_UP == 1  # 0x01
        assert ScottLivingCommands.MOTOR_HEAD_DOWN == 2  # 0x02
        assert ScottLivingCommands.MOTOR_FEET_UP == 4  # 0x04
        assert ScottLivingCommands.MOTOR_FEET_DOWN == 8  # 0x08
        assert ScottLivingCommands.MOTOR_TILT_UP == 16  # 0x10
        assert ScottLivingCommands.MOTOR_TILT_DOWN == 32  # 0x20
        assert ScottLivingCommands.MOTOR_LUMBAR_UP == 64  # 0x40
        assert ScottLivingCommands.MOTOR_LUMBAR_DOWN == 128  # 0x80

    def test_cmd1_commands(self):
        """Commands in cmd1 byte should be correct."""
        assert ScottLivingCommands.MEMORY_1 == 256  # 0x100 -> cmd1=0x01
        assert ScottLivingCommands.LIGHT == 512  # 0x200 -> cmd1=0x02
        assert ScottLivingCommands.ZERO_G == 4096  # 0x1000 -> cmd1=0x10
        assert ScottLivingCommands.MEMORY_2 == 8192  # 0x2000 -> cmd1=0x20
        assert ScottLivingCommands.MEMORY_3 == 16384  # 0x4000 -> cmd1=0x40 (TV)
        assert ScottLivingCommands.ANTI_SNORE == 32768  # 0x8000 -> cmd1=0x80

    def test_preset_flat(self):
        """Flat preset command should be correct."""
        assert ScottLivingCommands.PRESET_FLAT == 134217728  # 0x8000000 -> cmd3=0x08


# -----------------------------------------------------------------------------
# Packet Building Tests
# -----------------------------------------------------------------------------


class TestScottLivingPacketBuilding:
    """Test Scott Living packet building."""

    def test_packet_is_9_bytes(self):
        """Packets should be exactly 9 bytes."""
        controller = ScottLivingController(MagicMock())
        packet = controller._build_command(ScottLivingCommands.MOTOR_HEAD_UP)

        assert len(packet) == 9

    def test_packet_header(self):
        """Packet should start with correct header [0xE6, 0xFE, 0x16]."""
        controller = ScottLivingController(MagicMock())
        packet = controller._build_command(0)

        assert packet[0] == 0xE6
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_command_bytes_little_endian(self):
        """Command value should be split into bytes in little-endian order."""
        controller = ScottLivingController(MagicMock())
        # Test with ZERO_G = 0x1000 -> cmd0=0x00, cmd1=0x10
        packet = controller._build_command(ScottLivingCommands.ZERO_G)

        assert packet[3] == 0x00  # cmd0
        assert packet[4] == 0x10  # cmd1
        assert packet[5] == 0x00  # cmd2
        assert packet[6] == 0x00  # cmd3

    def test_side_byte_is_always_1(self):
        """Side byte (position 7) should always be 0x01."""
        controller = ScottLivingController(MagicMock())
        packet = controller._build_command(ScottLivingCommands.MOTOR_HEAD_UP)

        assert packet[7] == 0x01

    def test_checksum_is_inverted_sum(self):
        """Checksum should be (~sum(bytes 0-7)) & 0xFF."""
        controller = ScottLivingController(MagicMock())
        packet = controller._build_command(0)  # Zero command

        # Calculate expected checksum
        header = [0xE6, 0xFE, 0x16]
        data = header + [0x00, 0x00, 0x00, 0x00, 0x01]  # cmd bytes + side
        expected_checksum = (~sum(data)) & 0xFF

        assert packet[8] == expected_checksum

    def test_motor_head_up_packet(self):
        """HEAD_UP command should produce correct packet bytes."""
        controller = ScottLivingController(MagicMock())
        packet = controller._build_command(ScottLivingCommands.MOTOR_HEAD_UP)

        # HEAD_UP = 1 -> cmd0=0x01
        assert packet[3] == 0x01  # cmd0
        assert packet[4] == 0x00  # cmd1
        assert packet[5] == 0x00  # cmd2
        assert packet[6] == 0x00  # cmd3
        assert packet[7] == 0x01  # side

    def test_preset_flat_packet(self):
        """PRESET_FLAT command should produce correct packet bytes."""
        controller = ScottLivingController(MagicMock())
        packet = controller._build_command(ScottLivingCommands.PRESET_FLAT)

        # PRESET_FLAT = 0x8000000 -> cmd3=0x08
        assert packet[3] == 0x00  # cmd0
        assert packet[4] == 0x00  # cmd1
        assert packet[5] == 0x00  # cmd2
        assert packet[6] == 0x08  # cmd3
        assert packet[7] == 0x01  # side


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestScottLivingController:
    """Test ScottLivingController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Keeson Base write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support TV preset (Memory 3)."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True
        assert coordinator.controller.memory_slot_count == 3

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_has_tilt_support(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support tilt motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_tilt_support is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """Scott Living should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True


# -----------------------------------------------------------------------------
# Movement Tests
# -----------------------------------------------------------------------------


class TestScottLivingMovement:
    """Test Scott Living movement commands."""

    async def test_move_head_up_sends_9_byte_packet(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 9-byte packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 9

    async def test_move_tilt_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """move_tilt_up should send MOTOR_TILT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_tilt_up()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MOTOR_TILT_UP = 0x10 in cmd0
        assert call_data[3] == 0x10

    async def test_move_lumbar_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should send MOTOR_LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MOTOR_LUMBAR_UP = 0x40 in cmd0
        assert call_data[3] == 0x40

    async def test_stop_all_sends_zero_command(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send zero command value."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # All command bytes should be zero
        assert call_data[3] == 0x00
        assert call_data[4] == 0x00
        assert call_data[5] == 0x00
        assert call_data[6] == 0x00


# -----------------------------------------------------------------------------
# Preset Tests
# -----------------------------------------------------------------------------


class TestScottLivingPresets:
    """Test Scott Living preset commands."""

    async def test_preset_flat_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send PRESET_FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # PRESET_FLAT = 0x8000000 -> cmd3=0x08
        assert call_data[6] == 0x08

    async def test_preset_zero_g_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send ZERO_G command."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # ZERO_G = 0x1000 -> cmd1=0x10
        assert call_data[4] == 0x10

    async def test_preset_memory_1_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_scott_living_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should send MEMORY_1 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_scott_living_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MEMORY_1 = 0x100 -> cmd1=0x01
        assert call_data[4] == 0x01
