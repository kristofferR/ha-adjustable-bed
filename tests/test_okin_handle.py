"""Tests for DewertOkin/Okin 6-byte bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_DEWERTOKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OKIMAT_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class OkinHandleCommands:
    """Frames the pre-v5 DewertOkin controller sent, pinned as literals."""

    FLAT = bytes.fromhex("040210000000")
    ZERO_G = bytes.fromhex("040200004000")
    TV = bytes.fromhex("040200003000")
    QUIET_SLEEP = bytes.fromhex("040200008000")
    MEMORY_1 = bytes.fromhex("040200001000")
    MEMORY_2 = bytes.fromhex("040200002000")
    HEAD_UP = bytes.fromhex("040200000001")
    HEAD_DOWN = bytes.fromhex("040200000002")
    FOOT_UP = bytes.fromhex("040200000004")
    FOOT_DOWN = bytes.fromhex("040200000008")
    WAVE_MASSAGE = bytes.fromhex("040280000000")
    HEAD_MASSAGE = bytes.fromhex("040200000800")
    FOOT_MASSAGE = bytes.fromhex("040200000400")
    MASSAGE_OFF = bytes.fromhex("040202000000")
    UNDERLIGHT = bytes.fromhex("040200020000")
    STOP = bytes.fromhex("040200000000")


@pytest.fixture
def mock_okin_handle_config_entry_data() -> dict:
    """Return mock config entry data for Okin handle bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin Handle Test Bed",
        CONF_BED_TYPE: BED_TYPE_DEWERTOKIN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_handle_config_entry(
    hass: HomeAssistant, mock_okin_handle_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin handle bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin Handle Test Bed",
        data=mock_okin_handle_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_handle_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestOkinHandleController:
    """Test Okin handle controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports the stable Okin write characteristic."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == OKIMAT_WRITE_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        command = OkinHandleCommands.STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, command, response=True
        )

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        command = OkinHandleCommands.HEAD_UP
        await coordinator.controller.write_command(command, repeat_count=3, repeat_delay_ms=50)

        assert mock_bleak_client.write_gatt_char.call_count == 3

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(OkinHandleCommands.STOP)

    async def test_write_command_bleak_error(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command handles BleakError."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.write_gatt_char.side_effect = BleakError("Write failed")

        with pytest.raises(BleakError):
            await coordinator.controller.write_command(OkinHandleCommands.STOP)


class TestOkinHandlePresets:
    """Test Okin handle preset commands."""

    async def test_preset_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test preset memory with invalid number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        # Memory 3 is not supported on Okin handle beds
        await coordinator.controller.preset_memory(3)

        assert "only support memory presets 1 and 2" in caplog.text


class TestOkinHandleMassage:
    """Test Okin handle massage commands."""

    async def test_massage_foot_toggle(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, OkinHandleCommands.FOOT_MASSAGE, response=True
        )


class TestOkinHandlePositionNotifications:
    """Test Okin handle position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_okin_handle_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_handle_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
