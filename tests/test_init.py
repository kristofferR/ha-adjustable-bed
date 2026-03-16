"""Tests for Adjustable Bed integration setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Import enable_custom_integrations fixture
from custom_components.adjustable_bed import (
    SERVICE_GENERATE_SUPPORT_REPORT,
    SERVICE_GOTO_PRESET,
    SERVICE_RUN_DIAGNOSTICS,
    SERVICE_SAVE_PRESET,
    SERVICE_SET_POSITION,
    SERVICE_STOP_ALL,
    SERVICE_TIMED_MOVE,
    async_migrate_entry,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_VIBRADORM,
    BEDTECH_SERVICE_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_RICHMAT_REMOTE,
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
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_RUN_DIAGNOSTICS)
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_REPORT)

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
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_RUN_DIAGNOSTICS)
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_REPORT)

    async def test_setup_entry_loads_diagnostic_device_without_connection(
        self,
        hass: HomeAssistant,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """Diagnostic entries should still load so they can be targeted by actions."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Diagnostic Device",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:10",
                CONF_NAME: "Diagnostic Device",
                CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC,
                CONF_MOTOR_COUNT: 0,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:10",
            entry_id="diagnostic_entry_id",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.controller is not None
        assert coordinator.controller.__class__.__name__ == "DiagnosticBedController"

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1

    async def test_setup_entry_reclassifies_legacy_bedtech_qrrm_entry(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_async_ble_device_from_address: MagicMock,
        enable_custom_integrations,
    ):
        """Legacy BedTech entries should be corrected to Richmat for QRRM devices."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Legacy BedTech QRRM",
            data={
                CONF_ADDRESS: "57:4C:54:30:77:FA",
                CONF_NAME: "Legacy Bed",
                CONF_BED_TYPE: BED_TYPE_BEDTECH,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:54:30:77:FA",
            entry_id="legacy_bedtech_qrrm",
        )
        entry.add_to_hass(hass)

        service_info = MagicMock()
        service_info.name = "QRRM138330"
        service_info.address = "57:4C:54:30:77:FA"
        service_info.service_uuids = [BEDTECH_SERVICE_UUID]

        mock_async_ble_device_from_address.return_value.name = "QRRM138330"

        with (
            patch(
                "custom_components.adjustable_bed.bluetooth.async_last_service_info",
                return_value=service_info,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_last_service_info",
                return_value=service_info,
            ),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_RICHMAT
        assert entry.data[CONF_RICHMAT_REMOTE] == "qrrm"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator._bed_type == BED_TYPE_RICHMAT
        assert coordinator.controller.__class__.__name__ == "RichmatController"


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

    async def test_unload_last_entry_keeps_services_available(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test unloading last entry keeps services available for diagnostics."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify services exist
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)

        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Services remain available so diagnostics can still be run without a loaded bed
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_SAVE_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_STOP_ALL)
        assert hass.services.has_service(DOMAIN, SERVICE_RUN_DIAGNOSTICS)
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_REPORT)

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

        # Services remain available after the final entry unload
        assert hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET)
        assert hass.services.has_service(DOMAIN, SERVICE_RUN_DIAGNOSTICS)


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

    async def test_timed_move_service_accepts_malouf_bed_height(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Timed move should accept the Hi-Lo bed_height motor for Malouf layouts."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Malouf Timed Move Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:10",
                CONF_NAME: "Malouf Timed Move Bed",
                CONF_BED_TYPE: BED_TYPE_MALOUF_LEGACY_OKIN,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:10",
            entry_id="malouf_timed_move_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        await hass.services.async_call(
            DOMAIN,
            SERVICE_TIMED_MOVE,
            {
                "device_id": [device_id],
                "motor": "bed_height",
                "direction": "up",
                "duration_ms": 1000,
            },
            blocking=True,
        )

        assert mock_bleak_client.write_gatt_char.call_count >= 1

    async def test_timed_move_service_rejects_bed_height_for_standard_layout(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Timed move should reject bed_height for beds that do not expose it."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with pytest.raises(ServiceValidationError, match="Valid motors: back, legs"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_TIMED_MOVE,
                {
                    "device_id": [device_id],
                    "motor": "bed_height",
                    "direction": "up",
                    "duration_ms": 1000,
                },
                blocking=True,
            )

    async def test_set_position_service_accepts_box25_head_and_feet(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """BOX25 set_position should accept head and feet only."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleepy's BOX25 Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:30",
                CONF_NAME: "Sleepy's BOX25 Service Bed",
                CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:30",
            entry_id="sleepys_box25_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        coordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator.async_seek_position = AsyncMock()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_POSITION,
            {
                "device_id": [device_id],
                "motor": "head",
                "position": 50,
            },
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_POSITION,
            {
                "device_id": [device_id],
                "motor": "feet",
                "position": 40,
            },
            blocking=True,
        )

        assert coordinator.async_seek_position.await_count == 2

    async def test_set_position_service_rejects_box25_back_and_legs(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """BOX25 set_position should reject legacy back/legs motors."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleepy's BOX25 Invalid Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:31",
                CONF_NAME: "Sleepy's BOX25 Invalid Service Bed",
                CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:31",
            entry_id="sleepys_box25_invalid_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with pytest.raises(ServiceValidationError, match="Valid motors: feet, head"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_POSITION,
                {
                    "device_id": [device_id],
                    "motor": "back",
                    "position": 20,
                },
                blocking=True,
            )

        with pytest.raises(ServiceValidationError, match="Valid motors: feet, head"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_POSITION,
                {
                    "device_id": [device_id],
                    "motor": "legs",
                    "position": 20,
                },
                blocking=True,
            )

    async def test_timed_move_service_accepts_box25_lumbar_and_tilt(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """BOX25 timed_move should follow the controller's lumbar and tilt surface."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleepy's BOX25 Timed Move Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:32",
                CONF_NAME: "Sleepy's BOX25 Timed Move Bed",
                CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:32",
            entry_id="sleepys_box25_timed_move_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        controller = hass.data[DOMAIN][entry.entry_id].controller
        controller.move_lumbar_up = AsyncMock()
        controller.move_lumbar_stop = AsyncMock()
        controller.move_tilt_up = AsyncMock()
        controller.move_tilt_stop = AsyncMock()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_TIMED_MOVE,
            {
                "device_id": [device_id],
                "motor": "lumbar",
                "direction": "up",
                "duration_ms": 1000,
            },
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TIMED_MOVE,
            {
                "device_id": [device_id],
                "motor": "tilt",
                "direction": "up",
                "duration_ms": 1000,
            },
            blocking=True,
        )

        controller.move_lumbar_up.assert_awaited_once()
        controller.move_lumbar_stop.assert_awaited_once()
        controller.move_tilt_up.assert_awaited_once()
        controller.move_tilt_stop.assert_awaited_once()
