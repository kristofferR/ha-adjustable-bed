"""Tests for Okin Nordic UART bed controller.

Protocol reverse-engineered by David Delahoz (https://github.com/daviddelahoz/BLEAdjustableBase)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_nordic import (
    OkinNordicCommands,
    OkinNordicController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MATTRESSFIRM,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    MATTRESSFIRM_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_okin_nordic_config_entry_data() -> dict:
    """Return mock config entry data for Okin Nordic bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin Nordic Test Bed",
        CONF_BED_TYPE: BED_TYPE_MATTRESSFIRM,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_nordic_config_entry(
    hass: HomeAssistant, mock_okin_nordic_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin Nordic bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin Nordic Test Bed",
        data=mock_okin_nordic_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="mattressfirm_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def mock_okin_nordic_coordinator(
    hass: HomeAssistant, mock_okin_nordic_config_entry: MockConfigEntry
) -> AdjustableBedCoordinator:
    """Return a mock coordinator for Okin Nordic bed."""
    coordinator = AdjustableBedCoordinator(hass, mock_okin_nordic_config_entry)
    return coordinator


@pytest.mark.asyncio
class TestOkinNordicController:
    """Test Okin Nordic controller."""

    async def test_controller_initialization(
        self, mock_okin_nordic_coordinator: AdjustableBedCoordinator
    ):
        """Test controller initialization."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        assert controller.control_characteristic_uuid == MATTRESSFIRM_WRITE_CHAR_UUID
        assert not controller._initialized

    async def test_write_command_sends_init_sequence(
        self, mock_okin_nordic_coordinator: AdjustableBedCoordinator
    ):
        """Test that write_command sends initialization sequence on first command."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        mock_client = AsyncMock()
        mock_okin_nordic_coordinator._client = mock_client

        # Send a motor command - should trigger init sequence
        await controller.write_command(OkinNordicCommands.HEAD_UP, repeat_count=1)

        # Verify init commands were sent before motor command
        assert mock_client.write_gatt_char.call_count == 3
        calls = mock_client.write_gatt_char.call_args_list

        # First call: INIT_1
        assert calls[0][0][0] == MATTRESSFIRM_WRITE_CHAR_UUID
        assert calls[0][0][1] == OkinNordicCommands.INIT_1

        # Second call: INIT_2
        assert calls[1][0][0] == MATTRESSFIRM_WRITE_CHAR_UUID
        assert calls[1][0][1] == OkinNordicCommands.INIT_2

        # Third call: HEAD_UP
        assert calls[2][0][0] == MATTRESSFIRM_WRITE_CHAR_UUID
        assert calls[2][0][1] == OkinNordicCommands.HEAD_UP

    async def test_subsequent_commands_skip_init(
        self, mock_okin_nordic_coordinator: AdjustableBedCoordinator
    ):
        """Test that subsequent commands don't re-send init sequence."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        mock_client = AsyncMock()
        mock_okin_nordic_coordinator._client = mock_client

        # Send first command (with init)
        await controller.write_command(OkinNordicCommands.HEAD_UP, repeat_count=1)
        assert controller._initialized

        # Reset call count
        mock_client.reset_mock()

        # Send second command (should skip init)
        await controller.write_command(OkinNordicCommands.FOOT_UP, repeat_count=1)

        # Verify only the motor command was sent
        assert mock_client.write_gatt_char.call_count == 1
        calls = mock_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == OkinNordicCommands.FOOT_UP

    async def test_motor_commands(self, mock_okin_nordic_coordinator: AdjustableBedCoordinator):
        """Test motor control commands."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        mock_client = AsyncMock()
        mock_okin_nordic_coordinator._client = mock_client
        controller._initialized = True  # Skip init for this test

        # Test head up
        await controller.move_head_up()
        assert mock_client.write_gatt_char.called
        assert OkinNordicCommands.HEAD_UP in [
            call[0][1] for call in mock_client.write_gatt_char.call_args_list
        ]

        mock_client.reset_mock()

        # Test lumbar up (unique to Okin Nordic)
        await controller.move_lumbar_up()
        assert mock_client.write_gatt_char.called
        assert OkinNordicCommands.LUMBAR_UP in [
            call[0][1] for call in mock_client.write_gatt_char.call_args_list
        ]

    async def test_preset_commands(self, mock_okin_nordic_coordinator: AdjustableBedCoordinator):
        """Test preset position commands."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        mock_client = AsyncMock()
        mock_okin_nordic_coordinator._client = mock_client
        controller._initialized = True

        # Test flat preset
        await controller.preset_flat()
        assert mock_client.write_gatt_char.called
        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == OkinNordicCommands.FLAT

        mock_client.reset_mock()

        # Test lounge preset (unique to Okin Nordic)
        await controller.preset_lounge()
        assert mock_client.write_gatt_char.called
        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == OkinNordicCommands.LOUNGE

        mock_client.reset_mock()

        # Test incline preset (unique to Okin Nordic)
        await controller.preset_incline()
        assert mock_client.write_gatt_char.called
        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == OkinNordicCommands.INCLINE

    async def test_massage_commands(self, mock_okin_nordic_coordinator: AdjustableBedCoordinator):
        """Test massage control commands."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        mock_client = AsyncMock()
        mock_okin_nordic_coordinator._client = mock_client
        controller._initialized = True

        # Test massage on
        await controller.massage_on()
        assert mock_client.write_gatt_char.called
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == OkinNordicCommands.MASSAGE_1

        mock_client.reset_mock()

        # Test massage intensity up
        await controller.massage_intensity_up()
        assert mock_client.write_gatt_char.called
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == OkinNordicCommands.MASSAGE_UP

    async def test_light_commands(self, mock_okin_nordic_coordinator: AdjustableBedCoordinator):
        """Test light control commands."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        mock_client = AsyncMock()
        mock_okin_nordic_coordinator._client = mock_client
        controller._initialized = True

        # Test light cycle
        await controller.lights_on()
        assert mock_client.write_gatt_char.called
        assert mock_client.write_gatt_char.call_args_list[0][0][1] == OkinNordicCommands.LIGHT_CYCLE

        mock_client.reset_mock()

        # Test light off
        await controller.lights_off()
        assert mock_client.write_gatt_char.called
        # Should be called 3 times (repeat_count=3)
        assert mock_client.write_gatt_char.call_count == 3
        assert (
            mock_client.write_gatt_char.call_args_list[0][0][1] == OkinNordicCommands.LIGHT_OFF_HOLD
        )

    async def test_memory_not_supported(
        self, mock_okin_nordic_coordinator: AdjustableBedCoordinator
    ):
        """Test that memory programming raises NotImplementedError."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)

        with pytest.raises(NotImplementedError):
            await controller.preset_memory(1)

        with pytest.raises(NotImplementedError):
            await controller.program_memory(1)

    async def test_write_command_without_client(
        self, mock_okin_nordic_coordinator: AdjustableBedCoordinator
    ):
        """Test write_command raises error when client is not connected."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)
        # Client is None by default in coordinator, so no need to set it

        with pytest.raises(ConnectionError):
            await controller.write_command(OkinNordicCommands.HEAD_UP)

    async def test_position_feedback_not_supported(
        self, mock_okin_nordic_coordinator: AdjustableBedCoordinator
    ):
        """Test that position feedback is not supported."""
        controller = OkinNordicController(mock_okin_nordic_coordinator)

        # start_notify should be a no-op
        await controller.start_notify(lambda motor, angle: None)

        # read_positions should be a no-op
        await controller.read_positions(motor_count=2)
