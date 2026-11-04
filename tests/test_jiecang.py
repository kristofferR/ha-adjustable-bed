"""Tests for Jiecang bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    JIECANG_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_jiecang_config_entry_data() -> dict:
    """Return mock config entry data for Jiecang bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Jiecang Test Bed",
        CONF_BED_TYPE: BED_TYPE_JIECANG,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_jiecang_config_entry(
    hass: HomeAssistant, mock_jiecang_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Jiecang bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jiecang Test Bed",
        data=mock_jiecang_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="jiecang_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestJiecangController:
    """Test Jiecang controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == JIECANG_CHAR_UUID

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        command = bytes.fromhex("f1f10801010a7e")
        await coordinator.controller.write_command(command, repeat_count=3, repeat_delay_ms=100)

        assert mock_bleak_client.write_gatt_char.call_count == 3

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(bytes.fromhex("f1f10801010a7e"))


class TestJiecangPresets:
    """Test Jiecang preset commands."""

    async def test_preset_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test preset memory with invalid number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        # Memory 4 is not supported on Jiecang (1-3 only)
        await coordinator.controller.preset_memory(4)

        assert "support memory presets 1-3 only" in caplog.text


class TestJiecangProgramMemory:
    """Test Jiecang program memory (supported via BLE)."""

    async def test_program_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory with invalid number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(4)

        assert "support memory presets 1-3 only" in caplog.text


class TestJiecangPositionNotifications:
    """Test Jiecang position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()

    async def test_stop_notify_noop(
        self,
        hass: HomeAssistant,
        mock_jiecang_config_entry,
        mock_coordinator_connected,
    ):
        """Test stop_notify completes without error."""
        coordinator = AdjustableBedCoordinator(hass, mock_jiecang_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.stop_notify()
