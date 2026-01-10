"""Tests for Adjustable Bed integration setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.adjustable_bed import (
    SERVICE_GOTO_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_STOP_ALL,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.adjustable_bed.const import DOMAIN


class TestIntegrationSetup:
    """Test integration setup."""

    async def test_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test successful setup of config entry."""
        assert await async_setup_entry(hass, mock_config_entry)

        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]

    async def test_setup_entry_registers_services(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test setup registers services."""
        await async_setup_entry(hass, mock_config_entry)

        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_SAVE_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_STOP_ALL)

    async def test_setup_entry_connection_timeout(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_adapters,
    ):
        """Test setup raises ConfigEntryNotReady on connection timeout."""
        with patch(
            "custom_components.adjustable_bed.coordinator.establish_connection",
            new_callable=AsyncMock,
            side_effect=TimeoutError("Connection timed out"),
        ):
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, mock_config_entry)

    async def test_setup_entry_connection_failed(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_adapters,
    ):
        """Test setup raises ConfigEntryNotReady when connection fails."""
        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, mock_config_entry)


class TestIntegrationUnload:
    """Test integration unload."""

    async def test_unload_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test successful unload of config entry."""
        await async_setup_entry(hass, mock_config_entry)

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        assert mock_config_entry.entry_id not in hass.data[DOMAIN]
        mock_bleak_client.disconnect.assert_called()

    async def test_unload_last_entry_removes_services(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test unloading last entry removes services."""
        await async_setup_entry(hass, mock_config_entry)

        # Verify services exist
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)

        await async_unload_entry(hass, mock_config_entry)

        # Services should be removed
        assert not hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert not hass.services.has_service(DOMAIN, SERVICE_SAVE_PRESET)
        assert not hass.services.has_service(DOMAIN, SERVICE_STOP_ALL)

    async def test_unload_keeps_services_with_remaining_entries(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test services are kept when other entries remain."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        # Create a second entry
        second_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Second Bed",
            data={**mock_config_entry_data, "address": "11:22:33:44:55:66"},
            unique_id="11:22:33:44:55:66",
            entry_id="second_entry_id",
        )
        second_entry.add_to_hass(hass)

        # Set up both entries
        await async_setup_entry(hass, mock_config_entry)
        await async_setup_entry(hass, second_entry)

        # Unload first entry
        await async_unload_entry(hass, mock_config_entry)

        # Services should still exist
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)

        # Clean up second entry
        await async_unload_entry(hass, second_entry)

        # Now services should be removed
        assert not hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)


class TestServices:
    """Test integration services."""

    async def test_goto_preset_service(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test goto_preset service calls controller."""
        await async_setup_entry(hass, mock_config_entry)

        # Get the device ID from the device registry
        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)

        # Find the device created by the integration
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        # Call the service
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GOTO_PRESET,
            {"device_id": [device_id], "preset": 1},
            blocking=True,
        )

        # Verify write_gatt_char was called (preset command)
        assert mock_bleak_client.write_gatt_char.call_count >= 1

    async def test_stop_all_service(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_all service calls controller."""
        await async_setup_entry(hass, mock_config_entry)

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        device_id = devices[0].id

        await hass.services.async_call(
            DOMAIN,
            SERVICE_STOP_ALL,
            {"device_id": [device_id]},
            blocking=True,
        )

        # Verify command was sent
        mock_bleak_client.write_gatt_char.assert_called()
