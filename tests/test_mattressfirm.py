"""Tests for Mattress Firm 900 bed controller.

Protocol reverse-engineered by David Delahoz (https://github.com/daviddelahoz/BLEAdjustableBase)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.mattressfirm import (
    MattressFirmCommands,
    MattressFirmController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MATTRESSFIRM,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    MATTRESSFIRM_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestMattressFirmCommands:
    """Test Mattress Firm 900 command constants."""

    def test_init_commands(self):
        """Test initialization command values."""
        assert MattressFirmCommands.INIT_1 == bytes.fromhex("09050A23050000")
        assert MattressFirmCommands.INIT_2 == bytes.fromhex("5A0B00A5")

    def test_motor_commands(self):
        """Test motor command values."""
        assert MattressFirmCommands.HEAD_UP == bytes.fromhex("5A0103103000A5")
        assert MattressFirmCommands.HEAD_DOWN == bytes.fromhex("5A0103103001A5")
        assert MattressFirmCommands.FOOT_UP == bytes.fromhex("5A0103103002A5")
        assert MattressFirmCommands.FOOT_DOWN == bytes.fromhex("5A0103103003A5")
        assert MattressFirmCommands.LUMBAR_UP == bytes.fromhex("5A0103103006A5")
        assert MattressFirmCommands.LUMBAR_DOWN == bytes.fromhex("5A0103103007A5")

    def test_preset_commands(self):
        """Test preset command values."""
        assert MattressFirmCommands.FLAT == bytes.fromhex("5A0103103010A5")
        assert MattressFirmCommands.ZERO_GRAVITY == bytes.fromhex("5A0103103013A5")
        assert MattressFirmCommands.ANTI_SNORE == bytes.fromhex("5A0103103016A5")
        assert MattressFirmCommands.LOUNGE == bytes.fromhex("5A0103103017A5")
        assert MattressFirmCommands.INCLINE == bytes.fromhex("5A0103103018A5")

    def test_massage_commands(self):
        """Test massage command values."""
        assert MattressFirmCommands.MASSAGE_1 == bytes.fromhex("5A0103103052A5")
        assert MattressFirmCommands.MASSAGE_2 == bytes.fromhex("5A0103103053A5")
        assert MattressFirmCommands.MASSAGE_3 == bytes.fromhex("5A0103103054A5")
        assert MattressFirmCommands.MASSAGE_STOP == bytes.fromhex("5A010310306FA5")
        assert MattressFirmCommands.MASSAGE_UP == bytes.fromhex("5A0103104060A5")
        assert MattressFirmCommands.MASSAGE_DOWN == bytes.fromhex("5A0103104063A5")

    def test_light_commands(self):
        """Test light command values."""
        assert MattressFirmCommands.LIGHT_CYCLE == bytes.fromhex("5A0103103070A5")
        assert MattressFirmCommands.LIGHT_OFF_HOLD == bytes.fromhex("5A0103103074A5")


@pytest.fixture
def mock_mattressfirm_config_entry_data() -> dict:
    """Return mock config entry data for Mattress Firm 900 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Mattress Firm 900 Test Bed",
        CONF_BED_TYPE: BED_TYPE_MATTRESSFIRM,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_mattressfirm_config_entry(
    hass: HomeAssistant, mock_mattressfirm_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Mattress Firm 900 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Mattress Firm 900 Test Bed",
        data=mock_mattressfirm_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="mattressfirm_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def mock_mattressfirm_coordinator(
    hass: HomeAssistant, mock_mattressfirm_config_entry: MockConfigEntry
) -> AdjustableBedCoordinator:
    """Return a mock coordinator for Mattress Firm 900 bed."""
    coordinator = AdjustableBedCoordinator(hass, mock_mattressfirm_config_entry)
    return coordinator


@pytest.mark.asyncio
class TestMattressFirmController:
    """Test Mattress Firm 900 controller."""

    async def test_controller_initialization(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test controller initialization."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        assert controller.control_characteristic_uuid == MATTRESSFIRM_CHAR_UUID
        assert not controller._initialized

    async def test_write_command_sends_init_sequence(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test that write_command sends initialization sequence on first command."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        mock_client = AsyncMock()
        controller.client = mock_client

        # Send a motor command - should trigger init sequence
        await controller.write_command(MattressFirmCommands.HEAD_UP, repeat_count=1)

        # Verify init commands were sent before motor command
        assert mock_client.write_gatt_char.call_count == 3
        calls = mock_client.write_gatt_char.call_args_list

        # First call: INIT_1
        assert calls[0][0][0] == MATTRESSFIRM_CHAR_UUID
        assert calls[0][0][1] == MattressFirmCommands.INIT_1

        # Second call: INIT_2
        assert calls[1][0][0] == MATTRESSFIRM_CHAR_UUID
        assert calls[1][0][1] == MattressFirmCommands.INIT_2

        # Third call: HEAD_UP
        assert calls[2][0][0] == MATTRESSFIRM_CHAR_UUID
        assert calls[2][0][1] == MattressFirmCommands.HEAD_UP

    async def test_subsequent_commands_skip_init(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test that subsequent commands don't re-send init sequence."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        mock_client = AsyncMock()
        controller.client = mock_client

        # Send first command (with init)
        await controller.write_command(MattressFirmCommands.HEAD_UP, repeat_count=1)
        assert controller._initialized

        # Reset call count
        mock_client.reset_mock()

        # Send second command (should skip init)
        await controller.write_command(MattressFirmCommands.FOOT_UP, repeat_count=1)

        # Verify only the motor command was sent
        assert mock_client.write_gatt_char.call_count == 1
        calls = mock_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == MattressFirmCommands.FOOT_UP

    async def test_motor_commands(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test motor control commands."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        mock_client = AsyncMock()
        controller.client = mock_client
        controller._initialized = True  # Skip init for this test

        # Test head up
        await controller.move_head_up()
        assert mock_client.write_gatt_char.called
        assert MattressFirmCommands.HEAD_UP in [
            call[0][1] for call in mock_client.write_gatt_char.call_args_list
        ]

        mock_client.reset_mock()

        # Test lumbar up (unique to Mattress Firm)
        await controller.move_lumbar_up()
        assert mock_client.write_gatt_char.called
        assert MattressFirmCommands.LUMBAR_UP in [
            call[0][1] for call in mock_client.write_gatt_char.call_args_list
        ]

    async def test_preset_commands(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test preset position commands."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        mock_client = AsyncMock()
        controller.client = mock_client
        controller._initialized = True

        # Test flat preset
        await controller.preset_flat()
        assert mock_client.write_gatt_char.called
        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == MattressFirmCommands.FLAT

        mock_client.reset_mock()

        # Test lounge preset (unique to Mattress Firm)
        await controller.preset_lounge()
        assert mock_client.write_gatt_char.called
        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == MattressFirmCommands.LOUNGE

        mock_client.reset_mock()

        # Test incline preset (unique to Mattress Firm)
        await controller.preset_incline()
        assert mock_client.write_gatt_char.called
        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == MattressFirmCommands.INCLINE

    async def test_massage_commands(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test massage control commands."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        mock_client = AsyncMock()
        controller.client = mock_client
        controller._initialized = True

        # Test massage on
        await controller.massage_on()
        assert mock_client.write_gatt_char.called
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == MattressFirmCommands.MASSAGE_1

        mock_client.reset_mock()

        # Test massage intensity up
        await controller.massage_intensity_up()
        assert mock_client.write_gatt_char.called
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == MattressFirmCommands.MASSAGE_UP

    async def test_light_commands(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test light control commands."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        mock_client = AsyncMock()
        controller.client = mock_client
        controller._initialized = True

        # Test light cycle
        await controller.lights_on()
        assert mock_client.write_gatt_char.called
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == MattressFirmCommands.LIGHT_CYCLE

        mock_client.reset_mock()

        # Test light off
        await controller.lights_off()
        assert mock_client.write_gatt_char.called
        # Should be called 3 times (repeat_count=3)
        assert mock_client.write_gatt_char.call_count == 3
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == MattressFirmCommands.LIGHT_OFF_HOLD

    async def test_memory_not_supported(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test that memory programming raises NotImplementedError."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)

        with pytest.raises(NotImplementedError):
            await controller.preset_memory(1)

        with pytest.raises(NotImplementedError):
            await controller.program_memory(1)

    async def test_write_command_without_client(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test write_command raises error when client is not connected."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)
        controller.client = None

        with pytest.raises(ConnectionError):
            await controller.write_command(MattressFirmCommands.HEAD_UP)

    async def test_position_feedback_not_supported(
        self, mock_mattressfirm_coordinator: AdjustableBedCoordinator
    ):
        """Test that position feedback is not supported."""
        controller = MattressFirmController(mock_mattressfirm_coordinator)

        # start_notify should be a no-op
        await controller.start_notify(lambda motor, angle: None)

        # read_positions should be a no-op
        await controller.read_positions(motor_count=2)
