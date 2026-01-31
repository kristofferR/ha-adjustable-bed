"""Tests for SBI/Q-Plus bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sbi import (
    HEAD_PULSE_TABLE,
    FOOT_PULSE_TABLE,
    SBICommands,
    SBIController,
    pulse_to_angle,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SBI,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_WRITE_CHAR_UUID,
    SBI_VARIANT_BOTH,
    SBI_VARIANT_SIDE_A,
    SBI_VARIANT_SIDE_B,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_sbi_config_entry_data() -> dict:
    """Return mock config entry data for SBI bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "SBI Test Bed",
        CONF_BED_TYPE: BED_TYPE_SBI,
        CONF_MOTOR_COUNT: 4,  # Head, foot, tilt, lumbar
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,  # SBI has position feedback
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: SBI_VARIANT_BOTH,
    }


@pytest.fixture
def mock_sbi_config_entry(
    hass: HomeAssistant, mock_sbi_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for SBI bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SBI Test Bed",
        data=mock_sbi_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="sbi_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_sbi_side_a_config_entry_data() -> dict:
    """Return mock config entry data for SBI bed (Side A)."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "SBI Side A Bed",
        CONF_BED_TYPE: BED_TYPE_SBI,
        CONF_MOTOR_COUNT: 4,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: SBI_VARIANT_SIDE_A,
    }


@pytest.fixture
def mock_sbi_side_a_config_entry(
    hass: HomeAssistant, mock_sbi_side_a_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for SBI bed (Side A)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SBI Side A Bed",
        data=mock_sbi_side_a_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:F1",
        entry_id="sbi_side_a_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestSBICommands:
    """Test SBI command constants."""

    def test_motor_commands(self):
        """Motor commands should be correct 32-bit little-endian values."""
        assert SBICommands.MOTOR_HEAD_UP == 0x00000001
        assert SBICommands.MOTOR_HEAD_DOWN == 0x00000002
        assert SBICommands.MOTOR_FEET_UP == 0x00000004
        assert SBICommands.MOTOR_FEET_DOWN == 0x00000008
        assert SBICommands.MOTOR_TILT_UP == 0x00000010
        assert SBICommands.MOTOR_TILT_DOWN == 0x00000020
        assert SBICommands.MOTOR_LUMBAR_UP == 0x00000040
        assert SBICommands.MOTOR_LUMBAR_DOWN == 0x00000080

    def test_preset_commands(self):
        """Preset commands should be correct values."""
        assert SBICommands.PRESET_FLAT == 0x08000000  # cmd3=0x08
        assert SBICommands.PRESET_ZERO_G == 0x00001000  # cmd1=0x10
        assert SBICommands.PRESET_MEMORY_1 == 0x00002000  # cmd1=0x20
        assert SBICommands.PRESET_MEMORY_2 == 0x00004000  # cmd1=0x40
        assert SBICommands.PRESET_TV == 0x00008000  # cmd1=0x80

    def test_light_command(self):
        """Light toggle command should be correct value."""
        assert SBICommands.TOGGLE_LIGHT == 0x00020000  # cmd2=0x02

    def test_massage_commands(self):
        """Massage commands should be correct values."""
        assert SBICommands.MASSAGE_LEVEL == 0x00000100  # cmd1=0x01
        assert SBICommands.MASSAGE_FOOT == 0x00000400  # cmd1=0x04
        assert SBICommands.MASSAGE_HEAD == 0x00000800  # cmd1=0x08
        assert SBICommands.MASSAGE_MODE_1 == 0x00100000  # cmd2=0x10
        assert SBICommands.MASSAGE_MODE_2 == 0x00200000  # cmd2=0x20
        assert SBICommands.MASSAGE_MODE_3 == 0x00080000  # cmd2=0x08
        assert SBICommands.MASSAGE_LUMBAR == 0x00400000  # cmd2=0x40

    def test_stop_command(self):
        """Stop command should be zero."""
        assert SBICommands.STOP == 0x00000000


# -----------------------------------------------------------------------------
# Pulse to Angle Tests
# -----------------------------------------------------------------------------


class TestPulseToAngle:
    """Test pulse-to-angle conversion functions."""

    def test_head_pulse_table_length(self):
        """Head pulse table should have 61 entries (0-60 degrees)."""
        assert len(HEAD_PULSE_TABLE) == 61

    def test_foot_pulse_table_length(self):
        """Foot pulse table should have 33 entries (0-32 degrees)."""
        assert len(FOOT_PULSE_TABLE) == 33

    def test_head_pulse_zero_gives_zero_degrees(self):
        """Pulse value 0 should give 0 degrees."""
        assert pulse_to_angle(0, HEAD_PULSE_TABLE) == 0

    def test_head_pulse_max_gives_60_degrees(self):
        """High pulse value should give 60 degrees."""
        assert pulse_to_angle(25000, HEAD_PULSE_TABLE) == 60

    def test_foot_pulse_zero_gives_zero_degrees(self):
        """Pulse value 0 should give 0 degrees."""
        assert pulse_to_angle(0, FOOT_PULSE_TABLE) == 0

    def test_foot_pulse_max_gives_32_degrees(self):
        """High pulse value should give 32 degrees."""
        assert pulse_to_angle(10000, FOOT_PULSE_TABLE) == 32

    def test_inverted_pulse_handling(self):
        """Pulse values >= 32768 should be inverted."""
        # 65535 - 65535 = 0, which maps to 0 degrees
        assert pulse_to_angle(65535, HEAD_PULSE_TABLE) == 0

    def test_mid_range_pulse(self):
        """Mid-range pulse should give reasonable angle."""
        # Pulse 10000 is between 10029 (index 27) and 10404 (index 28)
        angle = pulse_to_angle(10000, HEAD_PULSE_TABLE)
        assert 25 <= angle <= 30


# -----------------------------------------------------------------------------
# Packet Building Tests
# -----------------------------------------------------------------------------


class TestSBIPacketBuilding:
    """Test SBI packet building."""

    def test_both_mode_packet_is_8_bytes(self):
        """Both mode packets should be exactly 8 bytes."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_BOTH)
        packet = controller._build_command(SBICommands.MOTOR_HEAD_UP)

        assert len(packet) == 8

    def test_side_a_packet_is_9_bytes(self):
        """Side A mode packets should be exactly 9 bytes."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_SIDE_A)
        packet = controller._build_command(SBICommands.MOTOR_HEAD_UP)

        assert len(packet) == 9

    def test_side_b_packet_is_9_bytes(self):
        """Side B mode packets should be exactly 9 bytes."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_SIDE_B)
        packet = controller._build_command(SBICommands.MOTOR_HEAD_UP)

        assert len(packet) == 9

    def test_both_mode_header(self):
        """Both mode should use 0xE5 header."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_BOTH)
        packet = controller._build_command(0)

        assert packet[0] == 0xE5
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_side_a_header(self):
        """Side A mode should use 0xE6 header."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_SIDE_A)
        packet = controller._build_command(0)

        assert packet[0] == 0xE6
        assert packet[1] == 0xFE
        assert packet[2] == 0x16

    def test_side_a_has_side_byte_1(self):
        """Side A mode should have side byte = 0x01."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_SIDE_A)
        packet = controller._build_command(0)

        assert packet[7] == 0x01  # Side byte

    def test_side_b_has_side_byte_2(self):
        """Side B mode should have side byte = 0x02."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_SIDE_B)
        packet = controller._build_command(0)

        assert packet[7] == 0x02  # Side byte

    def test_command_bytes_little_endian(self):
        """Command value should be split into bytes in little-endian order."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_BOTH)
        # Test with PRESET_FLAT = 0x08000000
        packet = controller._build_command(SBICommands.PRESET_FLAT)

        assert packet[3] == 0x00  # cmd0 (bits 0-7)
        assert packet[4] == 0x00  # cmd1 (bits 8-15)
        assert packet[5] == 0x00  # cmd2 (bits 16-23)
        assert packet[6] == 0x08  # cmd3 (bits 24-31)

    def test_checksum_is_inverted_sum(self):
        """Checksum should be (~sum) & 0xFF."""
        controller = SBIController(MagicMock(), variant=SBI_VARIANT_BOTH)
        packet = controller._build_command(0)  # Zero command

        # Calculate expected checksum
        data = [0xE5, 0xFE, 0x16, 0x00, 0x00, 0x00, 0x00]
        expected_checksum = (~sum(data)) & 0xFF

        assert packet[7] == expected_checksum


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestSBIController:
    """Test SBIController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Keeson Base write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support 2 memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True
        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_has_tilt_support(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support tilt motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_tilt_support is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_position_feedback(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """SBI should support position feedback."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_position_feedback is True


# -----------------------------------------------------------------------------
# Movement Tests
# -----------------------------------------------------------------------------


class TestSBIMovement:
    """Test SBI movement commands."""

    async def test_move_head_up_sends_8_byte_packet_in_both_mode(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 8-byte packet in Both mode."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 8

    async def test_move_tilt_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """move_tilt_up should send MOTOR_TILT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_tilt_up()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MOTOR_TILT_UP = 0x10 in cmd0
        assert call_data[3] == 0x10

    async def test_stop_all_sends_zero_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send all-zero command bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
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


class TestSBIPresets:
    """Test SBI preset commands."""

    async def test_preset_flat_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send PRESET_FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # PRESET_FLAT = 0x08000000 -> cmd3=0x08
        assert call_data[6] == 0x08

    async def test_preset_zero_g_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send PRESET_ZERO_G command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # PRESET_ZERO_G = 0x00001000 -> cmd1=0x10
        assert call_data[4] == 0x10

    async def test_preset_memory_1_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should send PRESET_MEMORY_1 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # PRESET_MEMORY_1 = 0x00002000 -> cmd1=0x20
        assert call_data[4] == 0x20


# -----------------------------------------------------------------------------
# Massage Tests
# -----------------------------------------------------------------------------


class TestSBIMassage:
    """Test SBI massage commands."""

    async def test_massage_toggle_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """massage_toggle should send MASSAGE_LEVEL command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.massage_toggle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MASSAGE_LEVEL = 0x00000100 -> cmd1=0x01
        assert call_data[4] == 0x01

    async def test_massage_mode_1_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sbi_config_entry,
        mock_coordinator_connected,
    ):
        """massage_mode_1 should send MASSAGE_MODE_1 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sbi_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.massage_mode_1()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MASSAGE_MODE_1 = 0x00100000 -> cmd2=0x10
        assert call_data[5] == 0x10
