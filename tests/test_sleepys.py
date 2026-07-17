"""Tests for Sleepy's Elite bed controllers.

Tests both BOX15 (9-byte with checksum) and BOX24 (7-byte) protocol variants.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sleepys import (
    SleepysBox15Commands,
    SleepysBox24Commands,
    _calculate_box15_checksum,
)
from custom_components.adjustable_bed.beds.sleepys_box25 import (
    Box25Commands,
    SleepysBox25Controller,
    SleepysBox25LegacyController,
    _translate_star_to_legacy,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_WRITE_CHAR_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    SLEEPYS_BOX24_WRITE_CHAR_UUID,
    SLEEPYS_BOX25_VARIANT_LEGACY,
    SLEEPYS_BOX25_VARIANT_STAR,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.validators import get_variants_for_bed_type

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_sleepys_box15_config_entry_data() -> dict:
    """Return mock config entry data for Sleepy's BOX15 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Sleepy's BOX15 Test",
        CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX15,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_sleepys_box15_config_entry(
    hass: HomeAssistant, mock_sleepys_box15_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Sleepy's BOX15 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's BOX15 Test",
        data=mock_sleepys_box15_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="sleepys_box15_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_sleepys_box24_config_entry_data() -> dict:
    """Return mock config entry data for Sleepy's BOX24 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Sleepy's BOX24 Test",
        CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX24,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_sleepys_box24_config_entry(
    hass: HomeAssistant, mock_sleepys_box24_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Sleepy's BOX24 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's BOX24 Test",
        data=mock_sleepys_box24_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="sleepys_box24_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_sleepys_box25_config_entry_data() -> dict:
    """Return mock config entry data for Sleepy's BOX25 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:25",
        CONF_NAME: "Sleepy's BOX25 Test",
        CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
        CONF_MOTOR_COUNT: 4,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: SLEEPYS_BOX25_VARIANT_STAR,
    }


@pytest.fixture
def mock_sleepys_box25_config_entry(
    hass: HomeAssistant, mock_sleepys_box25_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Sleepy's BOX25 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleepy's BOX25 Test",
        data=mock_sleepys_box25_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:25",
        entry_id="sleepys_box25_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# BOX15 Command Constants Tests
# -----------------------------------------------------------------------------


class TestSleepysBox15Commands:
    """Test BOX15 command constants."""

    def test_header_is_3_bytes(self):
        """Header should be exactly 3 bytes."""
        assert len(SleepysBox15Commands.HEADER) == 3
        assert bytes([0xE6, 0xFE, 0x16]) == SleepysBox15Commands.HEADER

    def test_motor_command_values(self):
        """Verify motor command values."""
        assert SleepysBox15Commands.STOP == 0x00
        assert SleepysBox15Commands.HEAD_UP == 0x01
        assert SleepysBox15Commands.HEAD_DOWN == 0x02
        assert SleepysBox15Commands.FOOT_UP == 0x04
        assert SleepysBox15Commands.FOOT_DOWN == 0x08
        assert SleepysBox15Commands.LUMBAR_UP == 0x10
        assert SleepysBox15Commands.LUMBAR_DOWN == 0x20

    def test_preset_byte_values(self):
        """Verify preset command byte values."""
        assert SleepysBox15Commands.FLAT_BYTE4 == 0x00
        assert SleepysBox15Commands.FLAT_BYTE6 == 0x08
        assert SleepysBox15Commands.ZERO_G_BYTE4 == 0x10
        assert SleepysBox15Commands.ZERO_G_BYTE6 == 0x00


class TestSleepysBox24Commands:
    """Test BOX24 command constants."""

    def test_header_is_6_bytes(self):
        """Header should be exactly 6 bytes."""
        assert len(SleepysBox24Commands.HEADER) == 6
        assert bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20]) == SleepysBox24Commands.HEADER

    def test_motor_command_values(self):
        """Verify motor command values."""
        assert SleepysBox24Commands.STOP == 0x00
        assert SleepysBox24Commands.HEAD_UP == 0x01
        assert SleepysBox24Commands.HEAD_DOWN == 0x02
        assert SleepysBox24Commands.FOOT_UP == 0x03
        assert SleepysBox24Commands.FOOT_DOWN == 0x04

    def test_preset_command_values(self):
        """Verify preset command values."""
        assert SleepysBox24Commands.FLAT == 0x66
        assert SleepysBox24Commands.ZERO_G == 0x60


# -----------------------------------------------------------------------------
# BOX15 Checksum Tests
# -----------------------------------------------------------------------------


class TestBox15Checksum:
    """Test BOX15 checksum calculation."""

    def test_checksum_is_inverted_sum(self):
        """Checksum should be one's complement of 8-bit sum."""
        data = bytes([0xE6, 0xFE, 0x16, 0x01, 0x00, 0x00, 0x00, 0x00])
        data_sum = sum(data) & 0xFF
        expected_checksum = (~data_sum) & 0xFF
        assert _calculate_box15_checksum(data) == expected_checksum

    def test_checksum_head_up_command(self):
        """Verify checksum for HEAD_UP command."""
        # [0xE6, 0xFE, 0x16, 0x01, 0x00, 0x00, 0x00, 0x00]
        data = bytes([0xE6, 0xFE, 0x16, 0x01, 0x00, 0x00, 0x00, 0x00])
        checksum = _calculate_box15_checksum(data)
        # Sum: 0xE6 + 0xFE + 0x16 + 0x01 = 0x195 -> 0x95, inverted = ~0x95 = 0x6A
        assert checksum == (~(0xE6 + 0xFE + 0x16 + 0x01)) & 0xFF

    def test_checksum_stop_command(self):
        """Verify checksum for STOP command."""
        data = bytes([0xE6, 0xFE, 0x16, 0x00, 0x00, 0x00, 0x00, 0x00])
        checksum = _calculate_box15_checksum(data)
        # Sum: 0xE6 + 0xFE + 0x16 = 0x194 -> 0x94, inverted = ~0x94 = 0x6B
        assert checksum == (~(0xE6 + 0xFE + 0x16)) & 0xFF

    def test_checksum_flat_preset(self):
        """Verify checksum for FLAT preset command."""
        # [0xE6, 0xFE, 0x16, 0x00, 0x00, 0x00, 0x08, 0x00]
        data = bytes([0xE6, 0xFE, 0x16, 0x00, 0x00, 0x00, 0x08, 0x00])
        checksum = _calculate_box15_checksum(data)
        # Sum: 0xE6 + 0xFE + 0x16 + 0x08 = 0x19C -> 0x9C, inverted = ~0x9C = 0x63
        assert checksum == (~(0xE6 + 0xFE + 0x16 + 0x08)) & 0xFF

    def test_checksum_zero_g_preset(self):
        """Verify checksum for ZERO_G preset command."""
        # [0xE6, 0xFE, 0x16, 0x00, 0x10, 0x00, 0x00, 0x00]
        data = bytes([0xE6, 0xFE, 0x16, 0x00, 0x10, 0x00, 0x00, 0x00])
        checksum = _calculate_box15_checksum(data)
        # Sum: 0xE6 + 0xFE + 0x16 + 0x10 = 0x1A4 -> 0xA4, inverted = ~0xA4 = 0x5B
        assert checksum == (~(0xE6 + 0xFE + 0x16 + 0x10)) & 0xFF


# -----------------------------------------------------------------------------
# BOX15 Controller Tests
# -----------------------------------------------------------------------------


class TestSleepysBox15Controller:
    """Test SleepysBox15Controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Keeson Base UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_stop_all(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 should support stop all."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_stop_all is True

    async def test_memory_slot_count_is_zero(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 should have no memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 0

    async def test_supports_memory_programming_is_false(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 should not support memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is False


class TestSleepysBox15CommandFormat:
    """Test BOX15 command packet format."""

    async def test_motor_command_is_9_bytes(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Motor commands should be exactly 9 bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_motor_command(SleepysBox15Commands.HEAD_UP)
        assert len(command) == 9

    async def test_motor_command_header(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Motor commands should start with correct header."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_motor_command(SleepysBox15Commands.HEAD_UP)
        assert command[0:3] == SleepysBox15Commands.HEADER

    async def test_motor_command_byte3_is_motor_cmd(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Byte 3 should contain the motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_motor_command(SleepysBox15Commands.FOOT_UP)
        assert command[3] == SleepysBox15Commands.FOOT_UP

    async def test_motor_command_bytes_4_to_7_are_zero(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Bytes 4-7 should be zero for motor commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_motor_command(SleepysBox15Commands.HEAD_UP)
        assert command[4:8] == bytes([0x00, 0x00, 0x00, 0x00])

    async def test_motor_command_last_byte_is_checksum(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Last byte should be the checksum."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_motor_command(SleepysBox15Commands.HEAD_DOWN)
        expected_checksum = _calculate_box15_checksum(command[0:8])
        assert command[8] == expected_checksum

    async def test_preset_command_is_9_bytes(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Preset commands should be exactly 9 bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_preset_command(
            SleepysBox15Commands.FLAT_BYTE4,
            SleepysBox15Commands.FLAT_BYTE6,
        )
        assert len(command) == 9

    async def test_preset_command_header(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Preset commands should start with correct header."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_preset_command(
            SleepysBox15Commands.ZERO_G_BYTE4,
            SleepysBox15Commands.ZERO_G_BYTE6,
        )
        assert command[0:3] == SleepysBox15Commands.HEADER

    async def test_preset_command_byte3_is_zero(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Byte 3 should be zero for preset commands (no motor)."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_preset_command(
            SleepysBox15Commands.FLAT_BYTE4,
            SleepysBox15Commands.FLAT_BYTE6,
        )
        assert command[3] == 0x00

    async def test_preset_command_byte4_and_byte6(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Bytes 4 and 6 should contain preset values."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_preset_command(
            SleepysBox15Commands.FLAT_BYTE4,
            SleepysBox15Commands.FLAT_BYTE6,
        )
        assert command[4] == SleepysBox15Commands.FLAT_BYTE4
        assert command[6] == SleepysBox15Commands.FLAT_BYTE6

    async def test_preset_command_checksum(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Preset command should have valid checksum."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_preset_command(
            SleepysBox15Commands.ZERO_G_BYTE4,
            SleepysBox15Commands.ZERO_G_BYTE6,
        )
        expected_checksum = _calculate_box15_checksum(command[0:8])
        assert command[8] == expected_checksum


class TestSleepysBox15Movement:
    """Test BOX15 movement commands."""

    async def test_move_head_up_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        # Should have multiple writes (pulse count + stop)
        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        # First calls are HEAD_UP command
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == SleepysBox15Commands.HEAD_UP

    async def test_move_head_down_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_down should send HEAD_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_down()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == SleepysBox15Commands.HEAD_DOWN

    async def test_move_feet_up_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """move_feet_up should send FOOT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_feet_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == SleepysBox15Commands.FOOT_UP

    async def test_move_feet_down_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """move_feet_down should send FOOT_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_feet_down()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == SleepysBox15Commands.FOOT_DOWN

    async def test_move_lumbar_up_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should send LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == SleepysBox15Commands.LUMBAR_UP

    async def test_move_lumbar_down_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_down should send LUMBAR_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_down()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == SleepysBox15Commands.LUMBAR_DOWN

    async def test_stop_all_sends_stop_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == SleepysBox15Commands.STOP

    async def test_movement_sends_stop_after_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should always send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP
        last_call_data = calls[-1][0][1]
        assert last_call_data[3] == SleepysBox15Commands.STOP


class TestSleepysBox15Presets:
    """Test BOX15 preset commands."""

    async def test_preset_flat_sends_correct_bytes(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send correct byte4 and byte6."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[4] == SleepysBox15Commands.FLAT_BYTE4
        assert first_call_data[6] == SleepysBox15Commands.FLAT_BYTE6

    async def test_preset_zero_g_sends_correct_bytes(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send correct byte4 and byte6."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[4] == SleepysBox15Commands.ZERO_G_BYTE4
        assert first_call_data[6] == SleepysBox15Commands.ZERO_G_BYTE6

    async def test_preset_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
    ):
        """Presets should send STOP after preset command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        last_call_data = calls[-1][0][1]
        assert last_call_data[3] == SleepysBox15Commands.STOP

    async def test_preset_memory_logs_warning(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """preset_memory should log warning that it's not supported."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        assert "don't support memory presets" in caplog.text

    async def test_program_memory_logs_warning(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """program_memory should log warning that it's not supported."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text


# -----------------------------------------------------------------------------
# BOX24 Controller Tests
# -----------------------------------------------------------------------------


class TestSleepysBox24Controller:
    """Test SleepysBox24Controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use BOX24 write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == SLEEPYS_BOX24_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX24 should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_has_lumbar_support_is_false(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX24 should NOT support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is False

    async def test_supports_stop_all(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX24 should support stop all."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_stop_all is True

    async def test_memory_slot_count_is_zero(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX24 should have no memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 0

    async def test_supports_memory_programming_is_false(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX24 should not support memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is False


class TestSleepysBox24CommandFormat:
    """Test BOX24 command packet format."""

    async def test_command_is_7_bytes(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX24 commands should be exactly 7 bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(SleepysBox24Commands.HEAD_UP)
        assert len(command) == 7

    async def test_command_header(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """Commands should start with correct header."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(SleepysBox24Commands.HEAD_UP)
        assert command[0:6] == SleepysBox24Commands.HEADER

    async def test_command_last_byte_is_motor_cmd(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """Last byte should be the motor/preset command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(SleepysBox24Commands.FOOT_DOWN)
        assert command[6] == SleepysBox24Commands.FOOT_DOWN

    async def test_stop_command_format(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """STOP command should have correct format."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(SleepysBox24Commands.STOP)
        expected = bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20, 0x00])
        assert command == expected

    async def test_flat_preset_command_format(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """FLAT preset command should have correct format."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(SleepysBox24Commands.FLAT)
        expected = bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20, 0x66])
        assert command == expected

    async def test_zero_g_preset_command_format(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """ZERO_G preset command should have correct format."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(SleepysBox24Commands.ZERO_G)
        expected = bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20, 0x60])
        assert command == expected


class TestSleepysBox24Movement:
    """Test BOX24 movement commands."""

    async def test_move_head_up_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[6] == SleepysBox24Commands.HEAD_UP

    async def test_move_head_down_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_down should send HEAD_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_down()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[6] == SleepysBox24Commands.HEAD_DOWN

    async def test_move_feet_up_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """move_feet_up should send FOOT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_feet_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[6] == SleepysBox24Commands.FOOT_UP

    async def test_move_feet_down_sends_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """move_feet_down should send FOOT_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_feet_down()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[6] == SleepysBox24Commands.FOOT_DOWN

    async def test_stop_all_sends_stop_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[6] == SleepysBox24Commands.STOP

    async def test_movement_sends_stop_after_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should always send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        last_call_data = calls[-1][0][1]
        assert last_call_data[6] == SleepysBox24Commands.STOP


class TestSleepysBox24Presets:
    """Test BOX24 preset commands."""

    async def test_preset_flat_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[6] == SleepysBox24Commands.FLAT

    async def test_preset_zero_g_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send ZERO_G command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[6] == SleepysBox24Commands.ZERO_G

    async def test_preset_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """Presets should send STOP after preset command."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        last_call_data = calls[-1][0][1]
        assert last_call_data[6] == SleepysBox24Commands.STOP

    async def test_preset_memory_logs_warning(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """preset_memory should log warning that it's not supported."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        assert "don't support memory presets" in caplog.text

    async def test_program_memory_logs_warning(
        self,
        hass: HomeAssistant,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """program_memory should log warning that it's not supported."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text


# -----------------------------------------------------------------------------
# Protocol Difference Tests
# -----------------------------------------------------------------------------


class TestSleepysProtocolDifferences:
    """Test differences between BOX15 and BOX24 protocols."""

    async def test_box15_has_lumbar_box24_does_not(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 supports lumbar, BOX24 does not."""
        box15_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await box15_coordinator.async_connect()

        box24_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await box24_coordinator.async_connect()

        assert box15_coordinator.controller.has_lumbar_support is True
        assert box24_coordinator.controller.has_lumbar_support is False

    async def test_box15_command_length_9_box24_length_7(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 uses 9-byte commands, BOX24 uses 7-byte commands."""
        box15_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await box15_coordinator.async_connect()

        box24_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await box24_coordinator.async_connect()

        box15_cmd = box15_coordinator.controller._build_motor_command(SleepysBox15Commands.HEAD_UP)
        box24_cmd = box24_coordinator.controller._build_command(SleepysBox24Commands.HEAD_UP)
        assert len(box15_cmd) == 9
        assert len(box24_cmd) == 7

    async def test_box15_has_checksum_box24_does_not(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 commands have checksum, BOX24 do not."""
        box15_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await box15_coordinator.async_connect()

        box24_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await box24_coordinator.async_connect()

        box15_cmd = box15_coordinator.controller._build_motor_command(SleepysBox15Commands.HEAD_UP)
        # BOX15 checksum is in last byte
        expected_checksum = _calculate_box15_checksum(box15_cmd[0:8])
        assert box15_cmd[8] == expected_checksum

        # BOX24 has no checksum - last byte is the command itself
        box24_cmd = box24_coordinator.controller._build_command(SleepysBox24Commands.HEAD_UP)
        assert box24_cmd[6] == SleepysBox24Commands.HEAD_UP

    async def test_different_characteristic_uuids(
        self,
        hass: HomeAssistant,
        mock_sleepys_box15_config_entry,
        mock_sleepys_box24_config_entry,
        mock_coordinator_connected,
    ):
        """BOX15 and BOX24 use different characteristic UUIDs."""
        box15_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box15_config_entry)
        await box15_coordinator.async_connect()

        box24_coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box24_config_entry)
        await box24_coordinator.async_connect()

        assert (
            box15_coordinator.controller.control_characteristic_uuid == KEESON_BASE_WRITE_CHAR_UUID
        )
        assert (
            box24_coordinator.controller.control_characteristic_uuid
            == SLEEPYS_BOX24_WRITE_CHAR_UUID
        )

    def test_different_headers(self):
        """BOX15 and BOX24 use different header bytes."""
        assert bytes([0xE6, 0xFE, 0x16]) == SleepysBox15Commands.HEADER
        assert bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20]) == SleepysBox24Commands.HEADER

    def test_different_foot_command_values(self):
        """BOX15 and BOX24 use different values for foot commands."""
        # BOX15: FOOT_UP=0x04, FOOT_DOWN=0x08
        assert SleepysBox15Commands.FOOT_UP == 0x04
        assert SleepysBox15Commands.FOOT_DOWN == 0x08
        # BOX24: FOOT_UP=0x03, FOOT_DOWN=0x04
        assert SleepysBox24Commands.FOOT_UP == 0x03
        assert SleepysBox24Commands.FOOT_DOWN == 0x04


class TestSleepysBox25Controller:
    """Test SleepysBox25Controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """BOX25 should use the Nordic UART write characteristic."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, SleepysBox25Controller)
        assert coordinator.controller.control_characteristic_uuid == NORDIC_UART_WRITE_CHAR_UUID

    async def test_motor_control_specs_expose_box25_layout(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """BOX25 should expose head/feet/lumbar/tilt and remove stale back/legs."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        assert [spec.key for spec in controller.motor_control_specs] == [
            "head",
            "feet",
            "lumbar",
            "tilt",
        ]
        assert controller.motor_control_specs[3].translation_key == "head_end_tilt"
        assert controller.stale_motor_entity_keys == {"back", "legs"}

    async def test_star_status_notifications_propagate_and_clamp_motor_positions(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """BOX25_STAR A5 0D status bytes should update and clamp motor positions."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        updates: list[tuple[str, float]] = []

        await controller.start_notify(lambda key, value: updates.append((key, value)))

        characteristic = MagicMock()
        characteristic.uuid = "test-char"
        controller._on_notification(
            characteristic,
            bytearray.fromhex("A5 0D 11 01 78 00 21 00 FF 00 00 00 70 01 01 00 00 00 00 00"),
        )

        assert updates == [("head", 100.0), ("feet", 33.0), ("lumbar", 100.0)]

    async def test_star_notification_parser_ignores_legacy_and_short_frames(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """The BOX25_STAR controller must not interpret legacy BOX25 packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda key, value: updates.append((key, value))
        characteristic = MagicMock(uuid="test-char")

        controller._on_notification(characteristic, bytearray.fromhex("03 00 32 00"))
        controller._on_notification(characteristic, bytearray.fromhex("A5 0D 00 00 32"))

        assert updates == []

    async def test_cancelled_write_command_does_not_mark_init_complete(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Pre-cancelled writes should skip wake/init and leave init incomplete."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        mock_client = coordinator._client
        # Connection setup follows the OEM session and has already sent wake
        # before subscribing. Reset here to exercise the pre-cancelled init path.
        controller._initialized = False
        mock_client.write_gatt_char.reset_mock()
        cancel_event = asyncio.Event()
        cancel_event.set()

        with patch(
            "custom_components.adjustable_bed.beds.sleepys_box25.asyncio.sleep",
            new=AsyncMock(),
        ):
            await controller.write_command(Box25Commands.HEAD_UP, cancel_event=cancel_event)

        assert controller._initialized is False
        mock_client.write_gatt_char.assert_not_called()

    async def test_failed_massage_exit_preserves_reported_state(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """A failed exit write must not report massage as stopped."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        for operation in (controller.massage_off, lambda: controller.set_massage_timer(0)):
            controller._massage_active = True
            controller._massage_timer_minutes = 20
            state_before = dict(coordinator.controller_state)
            with (
                patch.object(
                    controller,
                    "_write_motor_command",
                    AsyncMock(side_effect=ConnectionError("write failed")),
                ),
                pytest.raises(ConnectionError, match="write failed"),
            ):
                await operation()

            assert controller.get_massage_state()["active"] is True
            assert controller.get_massage_state()["timer_mode"] == "20"
            assert coordinator.controller_state == state_before

    async def test_all_controls_use_oem_box25_star_frames(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Motors, lights, and massage must use BOX25_STAR, not legacy BOX25."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        commands = (
            (controller.move_head_up, "5A0103103000A5"),
            (controller.move_head_down, "5A0103103001A5"),
            (controller.move_feet_up, "5A0103103002A5"),
            (controller.move_feet_down, "5A0103103003A5"),
            (controller.move_lumbar_up, "5A0103103006A5"),
            (controller.move_lumbar_down, "5A0103103007A5"),
            (controller.move_tilt_up, "5A010310300AA5"),
            (controller.move_tilt_down, "5A010310300BA5"),
            (controller.lights_on, "5A0103103073A5"),
            (controller.lights_off, "5A0103103074A5"),
            (controller.lights_toggle, "5A0103103071A5"),
            (controller.massage_off, "5A010310306FA5"),
            (controller.massage_intensity_up, "5A0103104060A5"),
            (controller.massage_intensity_down, "5A0103104061A5"),
            (controller.massage_head_up, "5A0103103060A5"),
            (controller.massage_head_down, "5A0103103061A5"),
            (controller.massage_foot_up, "5A0103103062A5"),
            (controller.massage_foot_down, "5A0103103063A5"),
        )
        for method, expected_hex in commands:
            with (
                patch.object(controller, "write_command", AsyncMock()) as mock_write,
                patch.object(controller, "_move_with_stop", AsyncMock()) as mock_move,
            ):
                await method()

            expected = bytes.fromhex(expected_hex)
            if mock_move.await_count:
                mock_move.assert_awaited_once_with(expected)
            else:
                mock_write.assert_awaited_once_with(expected, cancel_event=None)

    async def test_star_wake_uses_response_then_commands_do_not(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """The app wakes with response, then writes normal commands without it."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        # Connection setup sends wake before notifications. Reset the per-
        # connection flag so this test can assert both write modes together.
        controller._initialized = False

        with (
            patch.object(controller, "_write_gatt_with_retry", AsyncMock()) as mock_write,
        ):
            await controller.write_command(Box25Commands.HEAD_UP)

        assert mock_write.await_count == 2
        assert mock_write.call_args_list[0].args[1] == Box25Commands.WAKE
        assert mock_write.call_args_list[0].kwargs["response"] is True
        assert mock_write.call_args_list[1].args[1] == Box25Commands.HEAD_UP
        assert mock_write.call_args_list[1].kwargs["response"] is False

    async def test_massage_toggle_and_mode_cycle_use_star_frames(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Massage state changes should retain the OEM BOX25_STAR framing."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "write_command", AsyncMock()) as mock_write:
            await controller.massage_toggle()
            await controller.massage_mode_step()
            await controller.massage_mode_step()
            await controller.massage_toggle()

        assert [call.args[0] for call in mock_write.await_args_list] == [
            Box25Commands.MASSAGE_TOGGLE,
            Box25Commands.MASSAGE_WAVE1,
            Box25Commands.MASSAGE_WAVE2,
            Box25Commands.MASSAGE_TOGGLE,
        ]

    async def test_advanced_massage_and_light_controls_use_exact_extended_frames(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Direct OEM sliders should expose their proven ranges and encodings."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        assert controller.massage_intensity_zones == ["all"]
        assert controller.massage_intensity_max == 7
        assert controller.massage_timer_options == [10, 20, 30]
        assert controller.light_level_max == 6

        with patch.object(controller, "write_command", AsyncMock()) as mock_write:
            await controller.set_massage_intensity("all", 7)
            await controller.set_massage_timer(20)
            await controller.set_light_level(6)

        assert [call.args[0] for call in mock_write.await_args_list] == [
            bytes.fromhex("5A E0 04 06 08 08 00 A5"),
            bytes.fromhex("5A E0 04 07 02 00 00 A5"),
            bytes.fromhex("5A E0 04 00 06 00 00 A5"),
        ]
        assert controller.get_massage_state() == {
            "intensity": 7,
            "timer_mode": "20",
            "active": False,
        }
        assert coordinator.controller_state["light_level"] == 6

    async def test_massage_notification_maps_exact_duration_buckets(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """A5 0B uses big-endian seconds and the OEM 10/20/30 minute buckets."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        characteristic = MagicMock(uuid="test-char")

        controller._on_notification(
            characteristic,
            bytearray.fromhex("A5 0B 0E 00 02 59 00 00 00 00 00 00 00 00 00 00"),
        )

        assert controller.get_massage_state()["timer_mode"] == "20"
        assert coordinator.controller_state["massage_timer"] == 20
        assert coordinator.controller_state["massage_active"] is True

    async def test_preset_arms_then_commits_with_starcode_terminator(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Star presets arm with the StarCode key ×3, then the 0x0F terminator.

        Regression test for #372. These beds (Star252201…, app
        com.starcode.adjustablem1x12) use StarCode framing (5A 01 03 10 30 KK A5):
        flat()/callMemory() enqueue the preset key ×3 then the StarCode terminator
        0x0F to commit. The bed arms while it receives the key and only drives to
        the target once the terminator arrives. The earlier CB25 (05 02 …) preset
        bytes never committed on real hardware — the user had to manually Stop All.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with (
            patch.object(controller, "write_command", AsyncMock()) as mock_write,
            patch("custom_components.adjustable_bed.beds.sleepys_box25.asyncio.sleep", AsyncMock()),
        ):
            await controller.preset_flat()

        assert mock_write.await_count == 2
        # 1) StarCode flat key, repeated to arm the preset.
        arm_call = mock_write.call_args_list[0]
        assert arm_call.args[0] == Box25Commands.STAR_PRESET_FLAT
        assert arm_call.kwargs == {"repeat_count": 3, "repeat_delay_ms": 100}
        # 2) StarCode terminator commits it, with a fresh cancel event so a
        #    pending Stop All can't suppress the commit packet.
        commit_call = mock_write.call_args_list[1]
        assert commit_call.args[0] == Box25Commands.STAR_PRESET_TERMINATOR
        assert isinstance(commit_call.kwargs["cancel_event"], asyncio.Event)

    async def test_named_and_memory_presets_use_starcode_frames(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Every M1X12 preset sends its StarCode arm frame, then the terminator."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        cases = (
            (controller.preset_flat, Box25Commands.STAR_PRESET_FLAT),
            (controller.preset_tv, Box25Commands.STAR_PRESET_TV),
            (controller.preset_zero_g, Box25Commands.STAR_PRESET_ZERO_GRAVITY),
            (controller.preset_anti_snore, Box25Commands.STAR_PRESET_ANTI_SNORE),
            (controller.preset_lounge, Box25Commands.STAR_PRESET_LOUNGE),
            (lambda: controller.preset_memory(1), Box25Commands.STAR_PRESET_MEMORY_1),
            (lambda: controller.preset_memory(2), Box25Commands.STAR_PRESET_MEMORY_2),
        )
        for method, arm_frame in cases:
            # StarCode framing: 5A 01 … A5, 7 bytes.
            assert arm_frame[0:2] == bytes([0x5A, 0x01])
            assert arm_frame[-1] == 0xA5
            assert len(arm_frame) == 7

            with (
                patch.object(controller, "write_command", AsyncMock()) as mock_write,
                patch(
                    "custom_components.adjustable_bed.beds.sleepys_box25.asyncio.sleep",
                    AsyncMock(),
                ),
            ):
                await method()

            assert mock_write.call_args_list[0].args[0] == arm_frame
            assert mock_write.call_args_list[1].args[0] == Box25Commands.STAR_PRESET_TERMINATOR

    async def test_program_memory_uses_starcode_long_press_sequence(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Memory store repeats the StarCode save key like the M1X12 app."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        for slot, command in (
            (1, Box25Commands.STAR_STORE_MEMORY_1),
            (2, Box25Commands.STAR_STORE_MEMORY_2),
        ):
            with patch.object(controller, "write_command", AsyncMock()) as mock_write:
                await controller.program_memory(slot)

            mock_write.assert_awaited_once_with(
                command,
                repeat_count=110,
                repeat_delay_ms=100,
            )

    async def test_box25_exposes_only_the_two_app_memory_slots(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """M1X12 has Memory 1/2; stale guessed slots 3/4 must stay hidden."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 2

        with patch.object(coordinator.controller, "write_command", AsyncMock()) as mock_write:
            await coordinator.controller.preset_memory(3)
            await coordinator.controller.program_memory(3)

        mock_write.assert_not_awaited()

    async def test_set_motor_position_supports_lumbar(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """BOX25 direct position control should use lumbar zone 0x02."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "_write_motor_command", AsyncMock()) as mock_write:
            await controller.set_motor_position("lumbar", 57)

        mock_write.assert_awaited_once_with(bytes([0x5A, 0xF0, 0x03, 0x02, 57, 0x00, 0xA5]))

    async def test_read_positions_sends_star_status_query(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Position refresh should request the A5 0D status notification."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with patch.object(controller, "write_command", AsyncMock()) as mock_write:
            await controller.read_positions()

        mock_write.assert_awaited_once_with(Box25Commands.QUERY_STATUS)


class TestSleepysBox25RuntimeDialect:
    """Tests for the APK-proven 0x2A29 StarCode/legacy runtime switch."""

    @staticmethod
    def _factory_coordinator() -> MagicMock:
        coordinator = MagicMock()
        coordinator.cancel_command = asyncio.Event()
        coordinator.address = "AA:BB:CC:DD:EE:25"
        return coordinator

    @pytest.mark.parametrize(
        "controller_type",
        [SleepysBox25Controller, SleepysBox25LegacyController],
    )
    async def test_movement_enforces_oem_sender_cadence(
        self,
        controller_type: type[SleepysBox25Controller],
    ) -> None:
        """A stored 10 ms tuning value must not flood either CB25 wire dialect."""
        coordinator = self._factory_coordinator()
        coordinator.motor_pulse_count = 100
        coordinator.motor_pulse_delay_ms = 10
        controller = controller_type(coordinator)

        with patch.object(controller, "write_command", AsyncMock()) as write:
            await controller.move_head_up()

        assert write.await_args_list[0].args == (Box25Commands.HEAD_UP,)
        assert write.await_args_list[0].kwargs == {
            "repeat_count": 100,
            "repeat_delay_ms": 100,
        }

    @pytest.mark.parametrize(
        ("device_name", "manufacturer", "expected_type"),
        [
            ("Star252201011800", "STAR", SleepysBox25Controller),
            ("Star252201011800", "Okin", SleepysBox25LegacyController),
            ("Star252201011800", None, SleepysBox25LegacyController),
            # These F23/kneading identifiers are fixed StarCode classes in the
            # recovered M1X12/M5X5/SleepSpa creator tables.
            ("STAR254205-ABC", None, SleepysBox25Controller),
            ("STAR255403-ABC", "Okin", SleepysBox25Controller),
        ],
    )
    async def test_auto_variant_matches_device_information_runtime_branch(
        self,
        device_name: str,
        manufacturer: str | None,
        expected_type: type[SleepysBox25Controller],
    ) -> None:
        controller = await create_controller(
            self._factory_coordinator(),
            BED_TYPE_SLEEPYS_BOX25,
            VARIANT_AUTO,
            client=None,
            device_name=device_name,
            ble_manufacturer=manufacturer,
        )

        assert type(controller) is expected_type

    @pytest.mark.parametrize(
        ("variant", "expected_type"),
        [
            (SLEEPYS_BOX25_VARIANT_STAR, SleepysBox25Controller),
            (SLEEPYS_BOX25_VARIANT_LEGACY, SleepysBox25LegacyController),
        ],
    )
    async def test_manual_dialect_override_is_respected(
        self,
        variant: str,
        expected_type: type[SleepysBox25Controller],
    ) -> None:
        controller = await create_controller(
            self._factory_coordinator(),
            BED_TYPE_SLEEPYS_BOX25,
            variant,
            client=None,
            device_name="STAR254205-ABC",
            ble_manufacturer="STAR",
        )

        assert type(controller) is expected_type

    def test_box25_variants_are_available_to_config_flow(self) -> None:
        assert get_variants_for_bed_type(BED_TYPE_SLEEPYS_BOX25) == {
            VARIANT_AUTO: "Auto (Device Information manufacturer)",
            SLEEPYS_BOX25_VARIANT_STAR: "StarCode (5A-framed)",
            SLEEPYS_BOX25_VARIANT_LEGACY: "Legacy CB25 (05/04/08/03 frames)",
        }

    @pytest.mark.parametrize(
        ("star", "legacy"),
        [
            (Box25Commands.HEAD_UP, "05020000000100"),
            (Box25Commands.FOOT_DOWN, "05020000000800"),
            (Box25Commands.LUMBAR_UP, "05020000001000"),
            (Box25Commands.NECK_TILT_DOWN, "05020000008000"),
            (Box25Commands.MOTOR_STOP, "05020000000000"),
            (Box25Commands.STAR_PRESET_FLAT, "05020800000000"),
            (Box25Commands.STAR_PRESET_TV, "05020000400000"),
            (Box25Commands.STAR_PRESET_MEMORY_1, "05020001000000"),
            (Box25Commands.STAR_STORE_MEMORY_2, "05020804000000"),
            (Box25Commands.LIGHT_ON_WHITE, "04E001010000"),
            (Box25Commands.LIGHT_OFF, "04E001000000"),
            (Box25Commands.LIGHT_TOGGLE, "08020002000000000000"),
            (Box25Commands.MASSAGE_TOGGLE, "05020008000000"),
            (Box25Commands.MASSAGE_EXIT, "05020200000000"),
            (Box25Commands.MASSAGE_WAVE2, "08020000000000100000"),
            (Box25Commands.MASSAGE_INTENSITY_UP, "050200000C0000"),
            (Box25Commands.MASSAGE_HEAD_DOWN, "05020080000000"),
            (Box25Commands.QUERY_STATUS, "00D0"),
            (bytes.fromhex("5AF003023900A5"), "03F0023900"),
            (bytes.fromhex("5AE00406080800A5"), "04E006080800"),
        ],
    )
    def test_exact_legacy_command_translation(self, star: bytes, legacy: str) -> None:
        assert _translate_star_to_legacy(star) == bytes.fromhex(legacy)

    async def test_legacy_writer_preserves_repeat_timing_and_write_mode(self) -> None:
        controller = SleepysBox25LegacyController(self._factory_coordinator())
        controller._initialized = True

        with patch.object(controller, "_write_gatt_with_retry", AsyncMock()) as write:
            await controller.write_command(
                Box25Commands.HEAD_UP,
                repeat_count=7,
                repeat_delay_ms=100,
            )

        write.assert_awaited_once_with(
            NORDIC_UART_WRITE_CHAR_UUID,
            bytes.fromhex("05020000000100"),
            repeat_count=7,
            repeat_delay_ms=100,
            cancel_event=None,
            response=False,
        )

    async def test_pre_cancelled_legacy_write_skips_translation(self) -> None:
        """Unsupported input must not raise when cancellation already won."""
        controller = SleepysBox25LegacyController(self._factory_coordinator())
        cancel_event = asyncio.Event()
        cancel_event.set()

        with patch.object(controller, "_write_gatt_with_retry", AsyncMock()) as write:
            await controller.write_command(b"\xff", cancel_event=cancel_event)

        write.assert_not_awaited()
