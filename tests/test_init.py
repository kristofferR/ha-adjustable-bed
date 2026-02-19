"""Tests for Adjustable Bed integration setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Import enable_custom_integrations fixture
from custom_components.adjustable_bed import (
    SERVICE_GOTO_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_STOP_ALL,
    async_migrate_entry,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_VIBRADORM,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    DOMAIN,
)


class TestIntegrationSetup:
    """Test integration setup."""

    async def test_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test successful setup of config entry."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]

    async def test_setup_entry_registers_services(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test setup registers services."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_SAVE_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_STOP_ALL)

    async def test_setup_entry_connection_timeout(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """Test setup fails on connection timeout."""
        with patch(
            "custom_components.adjustable_bed.coordinator.establish_connection",
            new_callable=AsyncMock,
            side_effect=TimeoutError("Connection timed out"),
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY

    async def test_setup_entry_connection_failed(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """Test setup fails when connection fails."""
        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY


class TestIntegrationUnload:
    """Test integration unload."""

    async def test_unload_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test successful unload of config entry."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert result is True
        assert mock_config_entry.state == ConfigEntryState.NOT_LOADED
        mock_bleak_client.disconnect.assert_called()

    async def test_unload_last_entry_removes_services(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test unloading last entry removes services."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify services exist
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)

        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

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
        enable_custom_integrations,
    ):
        """Test services are kept when other entries remain."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        # Set up first entry
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify services exist
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)

        # Create and set up a second entry
        second_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Second Bed",
            data={**mock_config_entry_data, "address": "11:22:33:44:55:66"},
            unique_id="11:22:33:44:55:66",
            entry_id="second_entry_id",
        )
        second_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

        # Unload first entry
        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Services should still exist because second entry is still loaded
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)

        # Clean up second entry
        await hass.config_entries.async_unload(second_entry.entry_id)
        await hass.async_block_till_done()

        # Now services should be removed
        assert not hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)


class TestMigration:
    """Test config entry migrations."""

    async def test_migrate_v1_vibradorm_enables_angle_sensing(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """V1 legacy Vibradorm entries should enable angle sensing when setting is missing."""
        legacy_data = {**mock_config_entry_data, CONF_BED_TYPE: BED_TYPE_VIBRADORM}
        legacy_data.pop(CONF_DISABLE_ANGLE_SENSING, None)

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm Migration Test",
            data=legacy_data,
            unique_id="AA:BB:CC:DD:EE:01",
            entry_id="migration_vibradorm_v1",
            version=1,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 3
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is False

    async def test_migrate_v1_non_vibradorm_keeps_existing_setting(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """V1 non-Vibradorm entries should keep disable_angle_sensing unchanged."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Linak Migration Test",
            data={
                **mock_config_entry_data,
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_DISABLE_ANGLE_SENSING: True,
            },
            unique_id="AA:BB:CC:DD:EE:02",
            entry_id="migration_linak_v1",
            version=1,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 3
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True

    async def test_migrate_v2_vibradorm_enables_angle_sensing(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """V2 legacy Vibradorm entries should enable angle sensing when setting is missing."""
        legacy_data = {**mock_config_entry_data, CONF_BED_TYPE: BED_TYPE_VIBRADORM}
        legacy_data.pop(CONF_DISABLE_ANGLE_SENSING, None)

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm Migration V2 Test",
            data=legacy_data,
            unique_id="AA:BB:CC:DD:EE:03",
            entry_id="migration_vibradorm_v2",
            version=2,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 3
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is False

    async def test_migrate_v1_vibradorm_keeps_existing_enabled_angle_setting(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """V1 Vibradorm entries should keep explicit disable_angle_sensing=False unchanged."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm Migration Explicit False Test",
            data={
                **mock_config_entry_data,
                CONF_BED_TYPE: BED_TYPE_VIBRADORM,
                CONF_DISABLE_ANGLE_SENSING: False,
            },
            unique_id="AA:BB:CC:DD:EE:05",
            entry_id="migration_vibradorm_v1_explicit_false",
            version=1,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 3
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is False

    async def test_migrate_v2_non_vibradorm_keeps_existing_setting(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """V2 non-Vibradorm entries keep disable_angle_sensing unchanged."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Linak Migration V2 Test",
            data={
                **mock_config_entry_data,
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_DISABLE_ANGLE_SENSING: True,
            },
            unique_id="AA:BB:CC:DD:EE:04",
            entry_id="migration_linak_v2",
            version=2,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 3
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True


class TestServices:
    """Test integration services."""

    async def test_goto_preset_service(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test goto_preset service calls controller."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

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

    async def test_goto_preset_service_reconnects_before_capability_check(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test goto_preset reconnects when controller is temporarily unavailable."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
        original_controller = coordinator.controller
        assert original_controller is not None
        coordinator._controller = None

        async def _restore_controller(reset_timer: bool = True) -> bool:
            coordinator._controller = original_controller
            return True

        with (
            patch.object(
                coordinator,
                "async_ensure_connected",
                new=AsyncMock(side_effect=_restore_controller),
            ) as mock_ensure_connected,
            patch.object(
                coordinator,
                "async_execute_controller_command",
                new=AsyncMock(),
            ) as mock_execute,
        ):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GOTO_PRESET,
                {"device_id": [device_id], "preset": 1},
                blocking=True,
            )

        mock_ensure_connected.assert_awaited_once_with(reset_timer=False)
        mock_execute.assert_awaited_once()

    async def test_goto_preset_service_rejects_invalid_slot_number(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test goto_preset raises error when preset exceeds memory_slot_count."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
        controller = coordinator.controller

        # Patch the controller to support presets but only 3 slots
        with (
            patch.object(type(controller), "supports_memory_presets", new_callable=lambda: property(lambda self: True)),
            patch.object(type(controller), "memory_slot_count", new_callable=lambda: property(lambda self: 3)),
            pytest.raises(ServiceValidationError, match="only supports memory presets 1-3"),
        ):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GOTO_PRESET,
                {"device_id": [device_id], "preset": 4},
                blocking=True,
            )

    async def test_stop_all_service(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test stop_all service calls controller."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

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
