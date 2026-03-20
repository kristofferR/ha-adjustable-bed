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

from custom_components.adjustable_bed.beds.sleepys_box25 import (
    Box25Commands,
    SleepysBox25Controller,
)
from custom_components.adjustable_bed.beds.sleepys import (
    SleepysBox15Commands,
    SleepysBox15Controller,
    SleepysBox24Commands,
    SleepysBox24Controller,
    _calculate_box15_checksum,
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
    DOMAIN,
    KEESON_BASE_WRITE_CHAR_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    SLEEPYS_BOX24_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


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
        assert SleepysBox15Commands.HEADER == bytes([0xE6, 0xFE, 0x16])

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
        assert SleepysBox24Commands.HEADER == bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20])

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

        box15_cmd = box15_coordinator.controller._build_motor_command(
            SleepysBox15Commands.HEAD_UP
        )
        box24_cmd = box24_coordinator.controller._build_command(
            SleepysBox24Commands.HEAD_UP
        )
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

        box15_cmd = box15_coordinator.controller._build_motor_command(
            SleepysBox15Commands.HEAD_UP
        )
        # BOX15 checksum is in last byte
        expected_checksum = _calculate_box15_checksum(box15_cmd[0:8])
        assert box15_cmd[8] == expected_checksum

        # BOX24 has no checksum - last byte is the command itself
        box24_cmd = box24_coordinator.controller._build_command(
            SleepysBox24Commands.HEAD_UP
        )
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
            box15_coordinator.controller.control_characteristic_uuid
            == KEESON_BASE_WRITE_CHAR_UUID
        )
        assert (
            box24_coordinator.controller.control_characteristic_uuid
            == SLEEPYS_BOX24_WRITE_CHAR_UUID
        )

    def test_different_headers(self):
        """BOX15 and BOX24 use different header bytes."""
        assert SleepysBox15Commands.HEADER == bytes([0xE6, 0xFE, 0x16])
        assert SleepysBox24Commands.HEADER == bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x20])

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

    async def test_lumbar_notifications_propagate(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Lumbar position notifications should reach coordinator callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        updates: list[tuple[str, float]] = []

        await controller.start_notify(lambda key, value: updates.append((key, value)))

        characteristic = MagicMock()
        characteristic.uuid = "test-char"
        controller._on_notification(characteristic, bytearray([0x03, 0x02, 55, 0x00]))

        assert updates == [("lumbar", 55.0)]

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
        cancel_event = asyncio.Event()
        cancel_event.set()

        with patch(
            "custom_components.adjustable_bed.beds.sleepys_box25.asyncio.sleep",
            new=AsyncMock(),
        ):
            await controller.write_command(Box25Commands.HEAD_UP, cancel_event=cancel_event)

        assert controller._motor_initialized is False
        mock_client.write_gatt_char.assert_not_called()

    async def test_preset_cleanup_always_sends_stop(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Preset failures should still run STOP cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with (
            patch.object(
                controller,
                "_write_motor_command",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(controller, "_send_stop", AsyncMock()) as mock_stop,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await controller.preset_flat()

        mock_stop.assert_awaited_once()

    async def test_program_memory_cleanup_always_sends_stop(
        self,
        hass: HomeAssistant,
        mock_sleepys_box25_config_entry,
        mock_coordinator_connected,
    ):
        """Memory-program failures should still run STOP cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_sleepys_box25_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        with (
            patch.object(
                controller,
                "_write_motor_command",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(controller, "_send_stop", AsyncMock()) as mock_stop,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await controller.program_memory(1)

        mock_stop.assert_awaited_once()

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

        mock_write.assert_awaited_once_with(bytes([0x03, 0xF0, 0x02, 57, 0x00]))
