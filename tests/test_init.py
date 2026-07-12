"""Tests for Adjustable Bed integration setup and unload."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Import enable_custom_integrations fixture
from custom_components.adjustable_bed import (
    SERVICE_GENERATE_SUPPORT_BUNDLE,
    SERVICE_GOTO_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_SET_POSITION,
    SERVICE_STOP_ALL,
    SERVICE_TIMED_MOVE,
    async_migrate_entry,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_KAIDI,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_VIBRADORM,
    BEDTECH_MANUFACTURER_ID,
    BEDTECH_SERVICE_UUID,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_MALOUF_LAYOUT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DOMAIN,
    KAIDI_VARIANT_SEAT_1,
    MALOUF_LAYOUT_HILO,
    OKIN_HEAD_MAX_ANGLE,
)
from custom_components.adjustable_bed.pairing import is_paired


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
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)

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
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)

    async def test_setup_entry_timeout_disconnects_cleanly(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """A setup timeout must tear down the half-open connection."""

        async def _hangs(*args, **kwargs):
            await asyncio.Event().wait()

        with (
            patch("custom_components.adjustable_bed.SETUP_TIMEOUT", 0.1),
            patch(
                "custom_components.adjustable_bed.coordinator.AdjustableBedCoordinator.async_connect",
                new=_hangs,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.AdjustableBedCoordinator.async_disconnect",
                new_callable=AsyncMock,
            ) as mock_disconnect,
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY
        mock_disconnect.assert_awaited_once_with(reason="setup timeout cleanup")

    async def test_setup_entry_timeout_bounds_disconnect_cleanup(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """A stalled cleanup disconnect must not block the setup retry."""

        async def _hangs(*args, **kwargs):
            await asyncio.Event().wait()

        with (
            patch("custom_components.adjustable_bed.SETUP_TIMEOUT", 0.05),
            patch("custom_components.adjustable_bed.SETUP_CLEANUP_TIMEOUT", 0.05),
            patch(
                "custom_components.adjustable_bed.coordinator.AdjustableBedCoordinator.async_connect",
                new=_hangs,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.AdjustableBedCoordinator.async_disconnect",
                new_callable=AsyncMock,
                side_effect=_hangs,
            ) as mock_disconnect,
        ):
            async with asyncio.timeout(5):
                await hass.config_entries.async_setup(mock_config_entry.entry_id)
                await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY
        mock_disconnect.assert_awaited_once_with(reason="setup timeout cleanup")

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
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)

    async def test_setup_entry_connection_failed_still_creates_device(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """Setup-retry entries should still have a device registry target for diagnostics."""
        from homeassistant.helpers import device_registry as dr

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY
        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        assert devices[0].name == mock_config_entry.title

    async def test_setup_gen2_connect_failure_creates_pairing_repair(
        self,
        hass: HomeAssistant,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """An unbonded Gen2 timeout gets the guided pairing repair from #385."""
        from homeassistant.helpers import issue_registry as ir

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Smart Bed 22D8",
            data={
                CONF_ADDRESS: "08:3A:F2:1E:4B:7E",
                CONF_NAME: "Smart Bed 22D8",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="08:3A:F2:1E:4B:7E",
            entry_id="leggett_gen2_pairing_repair_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.SETUP_RETRY
        issue_registry = ir.async_get(hass)
        issue = issue_registry.async_get_issue(DOMAIN, "pairing_required_08_3a_f2_1e_4b_7e")
        assert issue is not None
        assert issue.translation_key == "pairing_required"

    async def test_setup_gen2_connect_failure_with_bond_skips_pairing_repair(
        self,
        hass: HomeAssistant,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """A bonded Gen2 entry that cannot connect is a transient failure, not
        a pairing problem — no repair issue."""
        from homeassistant.helpers import issue_registry as ir

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Smart Bed 22D8",
            data={
                CONF_ADDRESS: "08:3A:F2:1E:4B:7F",
                CONF_NAME: "Smart Bed 22D8",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id="08:3A:F2:1E:4B:7F",
            entry_id="leggett_gen2_bonded_no_repair_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.SETUP_RETRY
        issue_registry = ir.async_get(hass)
        assert (
            issue_registry.async_get_issue(DOMAIN, "pairing_required_08_3a_f2_1e_4b_7f") is None
        )

    async def test_setup_gen2_failure_after_bond_skips_pairing_repair(
        self,
        hass: HomeAssistant,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """A bond established during this setup attempt must be observed dynamically."""
        from homeassistant.helpers import issue_registry as ir

        address = "08:3A:F2:1E:4B:80"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Smart Bed 22D8",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: "Smart Bed 22D8",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=address,
            entry_id="leggett_gen2_bonded_during_setup_entry",
        )
        entry.add_to_hass(hass)

        async def _connect_then_fail(_coordinator) -> bool:
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_BLE_BOND_ESTABLISHED: True},
            )
            return False

        with (
            patch(
                "custom_components.adjustable_bed.AdjustableBedCoordinator.async_connect",
                autospec=True,
                side_effect=_connect_then_fail,
            ),
            patch(
                "custom_components.adjustable_bed.bluetooth.async_ble_device_from_address",
                return_value=None,
            ),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.SETUP_RETRY
        assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
        issue_registry = ir.async_get(hass)
        assert (
            issue_registry.async_get_issue(DOMAIN, "pairing_required_08_3a_f2_1e_4b_80") is None
        )

    async def test_setup_non_gated_pairing_bed_connect_failure_skips_repair(
        self,
        hass: HomeAssistant,
        mock_bluetooth_adapters,
        enable_custom_integrations,
    ):
        """Ordinary pairing-required beds (e.g. Okin CST) keep the existing
        behaviour: a plain connect failure before pairing creates no repair."""
        from homeassistant.helpers import issue_registry as ir

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Okin CST Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:20",
                CONF_NAME: "Okin CST Bed",
                CONF_BED_TYPE: BED_TYPE_OKIN_CST,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:20",
            entry_id="okin_cst_no_repair_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.SETUP_RETRY
        issue_registry = ir.async_get(hass)
        assert (
            issue_registry.async_get_issue(DOMAIN, "pairing_required_aa_bb_cc_dd_ee_20") is None
        )

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

    async def test_setup_entry_reclassifies_bedtech_qrrm_richmat_entry(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_async_ble_device_from_address: MagicMock,
        enable_custom_integrations,
    ):
        """A BedTech manufacturer advert should correct a persisted Richmat QRRM entry."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="QRRM157738",
            data={
                CONF_ADDRESS: "57:4C:54:30:76:51",
                CONF_NAME: "QRRM157738",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_RICHMAT_REMOTE: "qrrm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:54:30:76:51",
            entry_id="bedtech_qrrm_as_richmat",
        )
        entry.add_to_hass(hass)

        service_info = MagicMock()
        service_info.name = "QRRM157738"
        service_info.address = "57:4C:54:30:76:51"
        service_info.service_uuids = [BEDTECH_SERVICE_UUID]
        service_info.manufacturer_data = {
            BEDTECH_MANUFACTURER_ID: bytes.fromhex("54307651")
        }

        mock_async_ble_device_from_address.return_value.name = "QRRM157738"

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
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_BEDTECH
        assert CONF_RICHMAT_REMOTE not in entry.data
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator._bed_type == BED_TYPE_BEDTECH
        assert coordinator.controller.__class__.__name__ == "BedTechController"

    async def test_setup_entry_keeps_casper_qrrm_as_richmat_without_bedtech_manufacturer(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_async_ble_device_from_address: MagicMock,
        enable_custom_integrations,
    ):
        """A QRRM entry without the BedTech field should retain Casper RGB behavior."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Casper Adjustable Base Max",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:05",
                CONF_NAME: "Casper Adjustable Base Max",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_RICHMAT_REMOTE: "qrrm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:05",
            entry_id="casper_qrrm",
        )
        entry.add_to_hass(hass)

        service_info = MagicMock()
        service_info.name = "QRRM105550"
        service_info.address = "57:4C:62:C3:39:05"
        service_info.service_uuids = [BEDTECH_SERVICE_UUID]
        service_info.manufacturer_data = {}
        mock_async_ble_device_from_address.return_value.name = "QRRM105550"

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

        assert entry.data[CONF_BED_TYPE] == BED_TYPE_RICHMAT
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.controller.__class__.__name__ == "RichmatController"

    async def test_setup_entry_keeps_bedtech_qrrm_when_advertisement_data_is_missing(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_async_ble_device_from_address: MagicMock,
        enable_custom_integrations,
    ):
        """A missing manufacturer field is inconclusive and must not downgrade BedTech."""
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
        service_info.manufacturer_data = {}

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
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_BEDTECH
        assert CONF_RICHMAT_REMOTE not in entry.data
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator._bed_type == BED_TYPE_BEDTECH
        assert coordinator.controller.__class__.__name__ == "BedTechController"

    async def test_setup_entry_keeps_bedtech_qrrm_entry_with_bedtech_manufacturer(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_async_ble_device_from_address: MagicMock,
        enable_custom_integrations,
    ):
        """A BedTech entry whose advert carries the manufacturer field stays BedTech."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="QRRM157738",
            data={
                CONF_ADDRESS: "57:4C:54:30:76:51",
                CONF_NAME: "QRRM157738",
                CONF_BED_TYPE: BED_TYPE_BEDTECH,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:54:30:76:51",
            entry_id="bedtech_qrrm_confirmed",
        )
        entry.add_to_hass(hass)

        service_info = MagicMock()
        service_info.name = "QRRM157738"
        service_info.address = "57:4C:54:30:76:51"
        service_info.service_uuids = [BEDTECH_SERVICE_UUID]
        service_info.manufacturer_data = {
            BEDTECH_MANUFACTURER_ID: bytes.fromhex("54307651")
        }

        mock_async_ble_device_from_address.return_value.name = "QRRM157738"

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
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_BEDTECH
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.controller.__class__.__name__ == "BedTechController"


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
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)

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
        assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)


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
        assert entry.version == 4
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
        assert entry.version == 4
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
        assert entry.version == 4
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
        assert entry.version == 4
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
        assert entry.version == 4
        assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True

    @pytest.mark.parametrize(
        "bed_type",
        [
            BED_TYPE_LINAK,
            BED_TYPE_VIBRADORM,
            BED_TYPE_RICHMAT,
            BED_TYPE_KAIDI,
            BED_TYPE_OKIN_CST,
            BED_TYPE_REVERIE,
            BED_TYPE_SLEEPYS_BOX25,
        ],
    )
    async def test_migrate_v3_to_v4_is_byte_identical(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
        bed_type: str,
    ):
        """v3 -> v4 must be a strict no-op for every (non-paired) bed type.

        This migration runs for EVERY entry on upgrade, so a defect here would
        brick every user's bed — assert the data is byte-identical afterward.
        """
        data = {**mock_config_entry_data, CONF_BED_TYPE: bed_type}
        before = dict(data)

        entry = MockConfigEntry(
            domain=DOMAIN,
            title=f"{bed_type} v3->v4",
            data=data,
            unique_id=f"migration_v3v4_{bed_type}",
            entry_id=f"migration_v3v4_{bed_type}",
            version=3,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 4
        assert dict(entry.data) == before  # byte-identical, nothing added/removed
        assert is_paired(entry.data) is False

    async def test_migrate_rejects_future_version(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """An entry from a newer (v5) schema must be refused, not silently mangled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Future version",
            data={**mock_config_entry_data},
            unique_id="AA:BB:CC:DD:E5:01",
            entry_id="migration_future_v5",
            version=5,
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is False


class TestServices:
    """Test integration services."""

    async def test_generate_support_bundle_service(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
        tmp_path: Path,
    ):
        """Test generate_support_bundle service delegates to the bundle generator."""
        del enable_custom_integrations
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with (
            patch(
                "custom_components.adjustable_bed.support_bundle.generate_support_bundle",
                new=AsyncMock(return_value={"notifications": [], "errors": []}),
            ) as mock_generate_support_bundle,
            patch(
                "custom_components.adjustable_bed.support_bundle.save_support_bundle",
                return_value=tmp_path / "support_bundle.json",
            ) as mock_save_support_bundle,
        ):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GENERATE_SUPPORT_BUNDLE,
                {"device_id": [device_id]},
                blocking=True,
            )

        mock_generate_support_bundle.assert_awaited_once()
        kwargs = mock_generate_support_bundle.await_args.kwargs
        assert kwargs["device_id"] == device_id
        assert kwargs["entry"] == mock_config_entry
        assert kwargs["coordinator"] == hass.data[DOMAIN][mock_config_entry.entry_id]
        mock_save_support_bundle.assert_called_once()

    async def test_generate_support_bundle_service_rejects_invalid_target_address(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test generate_support_bundle validates raw MAC addresses."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError, match="Invalid MAC address format"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GENERATE_SUPPORT_BUNDLE,
                {"target_address": "not-a-mac"},
                blocking=True,
            )

    async def test_generate_support_bundle_service_accepts_setup_retry_device(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_adapters,
        enable_custom_integrations,
        tmp_path: Path,
    ):
        """Support bundles should still target devices whose entry is in SETUP_RETRY."""
        del mock_bluetooth_adapters, enable_custom_integrations
        from homeassistant.helpers import device_registry as dr

        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with (
            patch(
                "custom_components.adjustable_bed.support_bundle.generate_support_bundle",
                new=AsyncMock(return_value={"notifications": [], "errors": []}),
            ) as mock_generate_support_bundle,
            patch(
                "custom_components.adjustable_bed.support_bundle.save_support_bundle",
                return_value=tmp_path / "support_bundle_retry.json",
            ) as mock_save_support_bundle,
        ):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GENERATE_SUPPORT_BUNDLE,
                {"device_id": [device_id]},
                blocking=True,
            )

        mock_generate_support_bundle.assert_awaited_once()
        kwargs = mock_generate_support_bundle.await_args.kwargs
        assert kwargs["address"] == mock_config_entry.data[CONF_ADDRESS]
        assert kwargs["device_id"] == device_id
        assert kwargs["entry"] == mock_config_entry
        assert kwargs["coordinator"] is None
        mock_save_support_bundle.assert_called_once()

    async def test_generate_support_bundle_service_rejects_multiple_device_targets(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Support bundle generation should fail fast instead of silently ignoring extra devices."""
        del mock_coordinator_connected, enable_custom_integrations
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with pytest.raises(
            ServiceValidationError, match="only supports one configured device"
        ) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GENERATE_SUPPORT_BUNDLE,
                {"device_id": [device_id, "other-device-id"]},
                blocking=True,
            )

        assert err.value.translation_domain == DOMAIN
        assert err.value.translation_key == "multiple_device_targets_not_supported"

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
                CONF_MALOUF_LAYOUT: MALOUF_LAYOUT_HILO,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:10",
            entry_id="malouf_timed_move_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator."
            "AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
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

    async def test_timed_move_service_accepts_okin_rf_eco_bt_stair(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Timed move should accept the Stair motor for OKIN RF ECO BT."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Elda Stair",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:44",
                CONF_NAME: "Elda Stair",
                CONF_BED_TYPE: BED_TYPE_OKIN_RF_ECO_BT,
                CONF_MOTOR_COUNT: 1,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_MOTOR_PULSE_COUNT: 1,
                CONF_MOTOR_PULSE_DELAY_MS: 100,
            },
            unique_id="AA:BB:CC:DD:EE:44",
            entry_id="okin_rf_eco_bt_timed_move_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator."
            "AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TIMED_MOVE,
            {
                "device_id": [device_id],
                "motor": "stair",
                "direction": "up",
                "duration_ms": 200,
            },
            blocking=True,
        )

        payloads = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
        assert payloads == [
            bytes.fromhex("040200000001"),
            bytes.fromhex("040200000001"),
            bytes.fromhex("040200000000"),
            bytes.fromhex("040200000000"),
        ]

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

        with patch(
            "custom_components.adjustable_bed.coordinator."
            "AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
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

        with patch(
            "custom_components.adjustable_bed.AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)

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

    async def test_set_position_service_accepts_okin_cst_back_and_legs(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """CST set_position should accept only axes reported by position feedback."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OKIN CST Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:35",
                CONF_NAME: "OKIN CST Service Bed",
                CONF_BED_TYPE: BED_TYPE_OKIN_CST,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:35",
            entry_id="okin_cst_service_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator."
            "AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
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
                "motor": "back",
                "position": 50,
            },
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_POSITION,
            {
                "device_id": [device_id],
                "motor": "legs",
                "position": 40,
            },
            blocking=True,
        )

        assert [
            call.kwargs["position_key"] for call in coordinator.async_seek_position.await_args_list
        ] == ["back", "legs"]

    async def test_set_position_service_rejects_okin_cst_head_and_feet(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """CST set_position should reject axes without position data."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OKIN CST Invalid Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:36",
                CONF_NAME: "OKIN CST Invalid Service Bed",
                CONF_BED_TYPE: BED_TYPE_OKIN_CST,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:36",
            entry_id="okin_cst_invalid_service_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator."
            "AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        for motor in ("head", "feet"):
            with pytest.raises(ServiceValidationError, match="Valid motors: back, legs"):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_SET_POSITION,
                    {
                        "device_id": [device_id],
                        "motor": motor,
                        "position": 20,
                    },
                    blocking=True,
                )

    async def test_set_position_service_rejects_okin_cst_back_above_reported_range(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """CST back targets above reported feedback range should be rejected."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="OKIN CST Range Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:37",
                CONF_NAME: "OKIN CST Range Service Bed",
                CONF_BED_TYPE: BED_TYPE_OKIN_CST,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:37",
            entry_id="okin_cst_range_service_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator."
            "AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with pytest.raises(
            ServiceValidationError,
            match=rf"Valid range: 0-{OKIN_HEAD_MAX_ANGLE}°",
        ):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_POSITION,
                {
                    "device_id": [device_id],
                    "motor": "back",
                    "position": OKIN_HEAD_MAX_ANGLE + 1,
                },
                blocking=True,
            )

    async def test_set_position_service_accepts_kaidi_back_and_legs_percentages(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Kaidi direct-position support should accept back/legs percentage targets."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kaidi Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:41",
                CONF_NAME: "Kaidi Service Bed",
                CONF_BED_TYPE: BED_TYPE_KAIDI,
                CONF_PROTOCOL_VARIANT: KAIDI_VARIANT_SEAT_1,
                CONF_KAIDI_PRODUCT_ID: 135,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:41",
            entry_id="kaidi_service_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.AdjustableBedCoordinator.async_read_initial_positions",
            new=AsyncMock(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)

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
                "motor": "back",
                "position": 75,
            },
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_POSITION,
            {
                "device_id": [device_id],
                "motor": "legs",
                "position": 40,
            },
            blocking=True,
        )

        assert coordinator.async_seek_position.await_count == 2

    async def test_set_position_service_uses_configured_back_max_angle(
        self,
        hass: HomeAssistant,
    ):
        """Standard set_position validation should honor configured back/head calibration."""
        from homeassistant.helpers import device_registry as dr

        from custom_components.adjustable_bed import _async_register_services

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Calibrated Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:32",
                CONF_NAME: "Calibrated Service Bed",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BACK_MAX_ANGLE: 80.0,
            },
            unique_id="AA:BB:CC:DD:EE:32",
            entry_id="calibrated_service_entry",
        )
        entry.add_to_hass(hass)

        device_registry = dr.async_get(hass)
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
        )

        coordinator = MagicMock()
        coordinator.controller = MagicMock()
        coordinator.name = entry.title
        coordinator.entry = entry
        coordinator.disable_angle_sensing = False
        coordinator.get_max_angle.side_effect = lambda motor: {
            "back": 80.0,
            "head": 80.0,
            "legs": 45.0,
            "feet": 45.0,
        }[motor]
        coordinator.async_seek_position = AsyncMock()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await _async_register_services(hass)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_POSITION,
            {
                "device_id": [device.id],
                "motor": "back",
                "position": 75,
            },
            blocking=True,
        )

        coordinator.async_seek_position.assert_awaited_once()
        assert coordinator.async_seek_position.await_args.kwargs["position_key"] == "back"
        assert coordinator.async_seek_position.await_args.kwargs["target_angle"] == 75

    async def test_reverie_get_max_angle_uses_protocol_specific_back_limit(
        self,
        hass: HomeAssistant,
    ):
        """Reverie back/head validation should match the 60-degree protocol limit."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Reverie Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:34",
                CONF_NAME: "Reverie Service Bed",
                CONF_BED_TYPE: BED_TYPE_REVERIE,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BACK_MAX_ANGLE: 80.0,
            },
            unique_id="AA:BB:CC:DD:EE:34",
            entry_id="reverie_service_entry",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)

        assert coordinator.get_max_angle("back") == 60.0
        assert coordinator.get_max_angle("head") == 60.0
        assert coordinator.get_max_angle("legs") == 45.0

    async def test_set_position_service_rejects_targets_above_configured_back_max_angle(
        self,
        hass: HomeAssistant,
    ):
        """Standard set_position validation should reject targets above configured calibration."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError
        from homeassistant.helpers import device_registry as dr

        from custom_components.adjustable_bed import _async_register_services

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Tight Calibration Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:33",
                CONF_NAME: "Tight Calibration Service Bed",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BACK_MAX_ANGLE: 50.0,
            },
            unique_id="AA:BB:CC:DD:EE:33",
            entry_id="tight_calibration_service_entry",
        )
        entry.add_to_hass(hass)

        device_registry = dr.async_get(hass)
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
        )

        coordinator = MagicMock()
        coordinator.controller = MagicMock()
        coordinator.name = entry.title
        coordinator.entry = entry
        coordinator.disable_angle_sensing = False
        coordinator.is_connected = True
        coordinator.async_ensure_connected = AsyncMock()
        coordinator.get_max_angle.side_effect = lambda motor: {
            "back": 50.0,
            "head": 50.0,
            "legs": 45.0,
            "feet": 45.0,
        }[motor]
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await _async_register_services(hass)

        with pytest.raises(ServiceValidationError, match=r"Valid range: 0-50.0°"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_POSITION,
                {
                    "device_id": [device.id],
                    "motor": "back",
                    "position": 60,
                },
                blocking=True,
            )

        # A failed validation must release the bed it reconnected for the check,
        # so it doesn't sit connected with no idle timer.
        coordinator.async_ensure_connected.assert_awaited_with(reset_timer=True)

    async def test_set_position_service_rejects_kaidi_head_and_feet(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Kaidi direct-position support should not expose unsupported head/feet service motors."""
        import pytest
        from homeassistant.exceptions import ServiceValidationError

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kaidi Invalid Service Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:42",
                CONF_NAME: "Kaidi Invalid Service Bed",
                CONF_BED_TYPE: BED_TYPE_KAIDI,
                CONF_PROTOCOL_VARIANT: KAIDI_VARIANT_SEAT_1,
                CONF_KAIDI_PRODUCT_ID: 135,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:42",
            entry_id="kaidi_invalid_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert len(devices) == 1
        device_id = devices[0].id

        with pytest.raises(ServiceValidationError):
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
