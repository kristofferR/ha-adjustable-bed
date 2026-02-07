"""Tests for Rondure / 1500 Tilt Base bed controller (FurniBus protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.rondure import (
    RondureCommands,
    RondureController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_RONDURE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    RONDURE_VARIANT_BOTH,
    RONDURE_VARIANT_SIDE_A,
    RONDURE_VARIANT_SIDE_B,
    RONDURE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_rondure_config_entry_data() -> dict:
    """Return mock config entry data for Rondure bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Rondure Test Bed",
        CONF_BED_TYPE: BED_TYPE_RONDURE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: RONDURE_VARIANT_BOTH,
    }


@pytest.fixture
def mock_rondure_config_entry(
    hass: HomeAssistant, mock_rondure_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Rondure bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Rondure Test Bed",
        data=mock_rondure_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="rondure_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_rondure_side_a_config_entry_data() -> dict:
    """Return mock config entry data for Rondure bed (Side A only)."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Rondure Side A Test Bed",
        CONF_BED_TYPE: BED_TYPE_RONDURE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: RONDURE_VARIANT_SIDE_A,
    }


@pytest.fixture
def mock_rondure_side_a_config_entry(
    hass: HomeAssistant, mock_rondure_side_a_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Rondure bed (Side A)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Rondure Side A Test Bed",
        data=mock_rondure_side_a_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF-A",
        entry_id="rondure_side_a_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestRondureCommands:
    """Test Rondure command constants."""

    def test_motor_commands_are_single_bit_flags(self):
        """Motor commands should be single-bit flags."""
        assert RondureCommands.HEAD_UP == 0x00000001
        assert RondureCommands.HEAD_DOWN == 0x00000002
        assert RondureCommands.FOOT_UP == 0x00000004
        assert RondureCommands.FOOT_DOWN == 0x00000008
        assert RondureCommands.TILT_UP == 0x00000010
        assert RondureCommands.TILT_DOWN == 0x00000020
        assert RondureCommands.LUMBAR_UP == 0x00000040
        assert RondureCommands.LUMBAR_DOWN == 0x00000080

    def test_preset_commands(self):
        """Preset commands should be correct values."""
        assert RondureCommands.ZERO_G == 0x00001000
        assert RondureCommands.FLAT == 0x08000000
        assert RondureCommands.TV_ANTI_SNORE == 0x00008000
        assert RondureCommands.READ_PRESET == 0x00002000
        assert RondureCommands.MUSIC_MEMORY == 0x00004000

    def test_massage_commands(self):
        """Massage commands should be correct values."""
        assert RondureCommands.MASSAGE_FOOT == 0x00000400
        assert RondureCommands.MASSAGE_HEAD == 0x00000800
        assert RondureCommands.MASSAGE_LUMBAR == 0x00400000
        assert RondureCommands.MASSAGE_MODE_1 == 0x00100000
        assert RondureCommands.MASSAGE_MODE_2 == 0x00200000
        assert RondureCommands.MASSAGE_MODE_3 == 0x00080000

    def test_light_command(self):
        """Light command should be correct value."""
        assert RondureCommands.LIGHT == 0x00020000

    def test_stop_command(self):
        """STOP command should be zero."""
        assert RondureCommands.STOP == 0x00000000

    def test_timer_level_command(self):
        """Timer/Level toggle command should be correct."""
        assert RondureCommands.TIMER_LEVEL == 0x00000100


# -----------------------------------------------------------------------------
# Checksum Tests
# -----------------------------------------------------------------------------


class TestRondureChecksum:
    """Test Rondure checksum calculation."""

    def test_checksum_bitwise_not_of_sum(self):
        """Checksum should be bitwise NOT of sum of all bytes."""
        # Test with sample packet bytes
        data = bytes([0xE5, 0xFE, 0x16, 0x01, 0x00, 0x00, 0x00])
        expected_sum = 0xE5 + 0xFE + 0x16 + 0x01 + 0x00 + 0x00 + 0x00
        expected_checksum = (~expected_sum) & 0xFF

        # Create controller to access checksum method
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_BOTH)
        actual_checksum = controller._calculate_checksum(data)

        assert actual_checksum == expected_checksum

    def test_checksum_for_stop_command(self):
        """Test checksum calculation for STOP command packet."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_BOTH)

        # STOP is all zeros, so cmd bytes are [0, 0, 0, 0]
        # Header: [0xE5, 0xFE, 0x16]
        # Full packet before checksum: [0xE5, 0xFE, 0x16, 0, 0, 0, 0]
        data = bytes([0xE5, 0xFE, 0x16, 0, 0, 0, 0])
        checksum = controller._calculate_checksum(data)

        # Sum = 0xE5 + 0xFE + 0x16 = 0x1F9
        # ~0x1F9 & 0xFF = ~505 & 0xFF = -506 & 0xFF
        expected_sum = 0xE5 + 0xFE + 0x16
        expected = (~expected_sum) & 0xFF
        assert checksum == expected


# -----------------------------------------------------------------------------
# Packet Building Tests
# -----------------------------------------------------------------------------


class TestRondurePacketBuilding:
    """Test Rondure packet building."""

    def test_both_sides_packet_is_8_bytes(self):
        """Both-sides packet should be exactly 8 bytes."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_BOTH)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        assert len(packet) == 8

    def test_single_side_packet_is_9_bytes(self):
        """Single-side packet should be exactly 9 bytes."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_SIDE_A)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        assert len(packet) == 9

    def test_both_sides_packet_header(self):
        """Both-sides packet should start with [0xE5, 0xFE, 0x16]."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_BOTH)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        assert packet[0] == 0xE5
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_single_side_packet_header(self):
        """Single-side packet should start with [0xE6, 0xFE, 0x16]."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_SIDE_A)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        assert packet[0] == 0xE6
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_command_bytes_little_endian(self):
        """Command bytes should be in little-endian order."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_BOTH)

        # ZERO_G = 0x00001000
        packet = controller._build_packet(RondureCommands.ZERO_G)

        # Bytes 3-6 are command in little-endian: [0x00, 0x10, 0x00, 0x00]
        assert packet[3] == 0x00  # LSB
        assert packet[4] == 0x10
        assert packet[5] == 0x00
        assert packet[6] == 0x00  # MSB

    def test_side_a_packet_has_side_byte_0x01(self):
        """Side A packet should have side byte 0x01."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_SIDE_A)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        # Side byte is at index 7 (before checksum)
        assert packet[7] == 0x01

    def test_side_b_packet_has_side_byte_0x02(self):
        """Side B packet should have side byte 0x02."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_SIDE_B)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        # Side byte is at index 7 (before checksum)
        assert packet[7] == 0x02

    def test_packet_ends_with_valid_checksum(self):
        """Packet should end with valid checksum."""
        from unittest.mock import MagicMock
        controller = RondureController(MagicMock(), RONDURE_VARIANT_BOTH)
        packet = controller._build_packet(RondureCommands.HEAD_UP)

        # Verify checksum
        checksum_byte = packet[-1]
        data_before_checksum = packet[:-1]
        expected_checksum = controller._calculate_checksum(data_before_checksum)

        assert checksum_byte == expected_checksum


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestRondureController:
    """Test RondureController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Rondure write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == RONDURE_WRITE_CHAR_UUID

    async def test_supports_preset_flat(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support flat preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_flat is True

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_massage(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support massage."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_massage is True

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_has_tilt_support(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Rondure should support tilt motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_tilt_support is True


class TestRondureMovement:
    """Test Rondure movement commands."""

    async def test_move_head_up_sends_8_byte_packet(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 8-byte packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 8

    async def test_stop_all_sends_stop_packet(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # STOP command: all zeros in command bytes
        assert call_data[3] == 0x00
        assert call_data[4] == 0x00
        assert call_data[5] == 0x00
        assert call_data[6] == 0x00

    async def test_movement_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP
        last_call_data = calls[-1][0][1]
        # STOP has all zeros in command bytes
        assert last_call_data[3] == 0x00
        assert last_call_data[4] == 0x00
        assert last_call_data[5] == 0x00
        assert last_call_data[6] == 0x00


class TestRondurePresets:
    """Test Rondure preset commands."""

    async def test_preset_flat_sends_flat_command(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # FLAT = 0x08000000 in little-endian: [0x00, 0x00, 0x00, 0x08]
        assert call_data[3] == 0x00
        assert call_data[4] == 0x00
        assert call_data[5] == 0x00
        assert call_data[6] == 0x08

    async def test_preset_zero_g_sends_zero_g_command(
        self,
        hass: HomeAssistant,
        mock_rondure_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send ZERO_G command."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # ZERO_G = 0x00001000 in little-endian: [0x00, 0x10, 0x00, 0x00]
        assert call_data[3] == 0x00
        assert call_data[4] == 0x10
        assert call_data[5] == 0x00
        assert call_data[6] == 0x00


class TestRondureVariants:
    """Test Rondure protocol variants."""

    def test_variant_constants_defined(self):
        """Variant constants should be defined."""
        assert RONDURE_VARIANT_BOTH == "both"
        assert RONDURE_VARIANT_SIDE_A == "side_a"
        assert RONDURE_VARIANT_SIDE_B == "side_b"

    async def test_side_a_sends_9_byte_packet(
        self,
        hass: HomeAssistant,
        mock_rondure_side_a_config_entry,
        mock_coordinator_connected,
    ):
        """Side A variant should send 9-byte packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_rondure_side_a_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert len(call_data) == 9
        # Side byte should be 0x01 for side A
        assert call_data[7] == 0x01
