"""Tests for Adjustable Bed config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    detect_bed_type,
    is_valid_mac_address,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OKIMAT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)


class TestMacAddressValidation:
    """Test MAC address validation."""

    def test_valid_mac_address_colon(self):
        """Test valid MAC address with colons."""
        assert is_valid_mac_address("AA:BB:CC:DD:EE:FF") is True
        assert is_valid_mac_address("aa:bb:cc:dd:ee:ff") is True
        assert is_valid_mac_address("00:11:22:33:44:55") is True

    def test_valid_mac_address_dash(self):
        """Test valid MAC address with dashes."""
        assert is_valid_mac_address("AA-BB-CC-DD-EE-FF") is True
        assert is_valid_mac_address("aa-bb-cc-dd-ee-ff") is True

    def test_invalid_mac_address(self):
        """Test invalid MAC addresses."""
        assert is_valid_mac_address("") is False
        assert is_valid_mac_address("not-a-mac") is False
        assert is_valid_mac_address("AA:BB:CC:DD:EE") is False  # Too short
        assert is_valid_mac_address("AA:BB:CC:DD:EE:FF:GG") is False  # Too long
        assert is_valid_mac_address("GG:HH:II:JJ:KK:LL") is False  # Invalid hex


class TestDetectBedType:
    """Test bed type detection."""

    def test_detect_linak_bed(self, mock_bluetooth_service_info: BluetoothServiceInfoBleak):
        """Test detection of Linak bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info)
        assert bed_type == BED_TYPE_LINAK

    def test_detect_richmat_nordic_bed(self, mock_bluetooth_service_info_richmat):
        """Test detection of Richmat bed (Nordic variant)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_richmat)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_richmat_wilinke_bed(self, mock_bluetooth_service_info_richmat_wilinke):
        """Test detection of Richmat bed (WiLinke variant)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_richmat_wilinke)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_keeson_bed(self, mock_bluetooth_service_info_keeson):
        """Test detection of Keeson bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_keeson)
        assert bed_type == BED_TYPE_KEESON

    def test_detect_solace_bed(self, mock_bluetooth_service_info_solace):
        """Test detection of Solace bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_solace)
        assert bed_type == BED_TYPE_SOLACE

    def test_detect_motosleep_bed(self, mock_bluetooth_service_info_motosleep):
        """Test detection of MotoSleep bed (by HHC name prefix)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_motosleep)
        assert bed_type == BED_TYPE_MOTOSLEEP

    def test_detect_leggett_platt_bed(self, mock_bluetooth_service_info_leggett):
        """Test detection of Leggett & Platt bed (Gen2)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_leggett)
        assert bed_type == BED_TYPE_LEGGETT_PLATT

    def test_detect_reverie_bed(self, mock_bluetooth_service_info_reverie):
        """Test detection of Reverie bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_reverie)
        assert bed_type == BED_TYPE_REVERIE

    def test_detect_okimat_bed(self, mock_bluetooth_service_info_okimat):
        """Test detection of Okimat bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_okimat)
        assert bed_type == BED_TYPE_OKIMAT

    def test_detect_unknown_device(
        self, mock_bluetooth_service_info_unknown: BluetoothServiceInfoBleak
    ):
        """Test detection returns None for unknown device."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_unknown)
        assert bed_type is None

    def test_detect_motosleep_lowercase_name(self):
        """Test MotoSleep detection with lowercase HHC prefix."""
        service_info = MagicMock()
        service_info.name = "hhc1234567890"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_MOTOSLEEP

    def test_detect_with_empty_name(self):
        """Test detection handles empty device name."""
        service_info = MagicMock()
        service_info.name = None
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type is None

    def test_detect_with_empty_service_uuids(self):
        """Test detection handles empty service UUIDs."""
        service_info = MagicMock()
        service_info.name = "Some Device"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type is None


class TestBluetoothDiscoveryFlow:
    """Test Bluetooth discovery flow."""

    async def test_bluetooth_discovery_creates_entry(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
    ):
        """Test Bluetooth discovery initiates config flow."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_bluetooth_discovery_confirm(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
    ):
        """Test confirming Bluetooth discovery creates entry."""
        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        # Confirm with user input
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My Bed",
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "My Bed"
        assert result["data"][CONF_ADDRESS] == mock_bluetooth_service_info.address
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_LINAK
        assert result["data"][CONF_MOTOR_COUNT] == 4
        assert result["data"][CONF_HAS_MASSAGE] is True
        assert result["data"][CONF_DISABLE_ANGLE_SENSING] is False

    async def test_bluetooth_discovery_not_supported(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_unknown: BluetoothServiceInfoBleak,
    ):
        """Test Bluetooth discovery aborts for unsupported devices."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_unknown,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "not_supported"

    async def test_bluetooth_discovery_already_configured(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
    ):
        """Test Bluetooth discovery aborts if already configured."""
        # Use the same address as the existing entry
        mock_bluetooth_service_info.address = mock_config_entry.data[CONF_ADDRESS]

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestManualFlow:
    """Test manual configuration flow."""

    async def test_manual_entry_no_devices_discovered(self, hass: HomeAssistant):
        """Test manual entry when no devices are discovered."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

    async def test_manual_entry_creates_entry(self, hass: HomeAssistant):
        """Test manual entry creates a config entry."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ADDRESS: "11:22:33:44:55:66",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_NAME: "Manual Bed",
                CONF_MOTOR_COUNT: 3,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Manual Bed"
        assert result["data"][CONF_ADDRESS] == "11:22:33:44:55:66"
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_LINAK
        assert result["data"][CONF_MOTOR_COUNT] == 3

    async def test_manual_entry_invalid_mac(self, hass: HomeAssistant):
        """Test manual entry with invalid MAC address shows error."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ADDRESS: "invalid-mac",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_NAME: "Manual Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "invalid_mac_address"

    async def test_manual_entry_normalizes_mac(self, hass: HomeAssistant):
        """Test manual entry normalizes MAC address format."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ADDRESS: "aa-bb-cc-dd-ee-ff",  # lowercase with dashes
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_NAME: "Manual Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_ADDRESS] == "AA:BB:CC:DD:EE:FF"  # Normalized


class TestUserFlow:
    """Test user-initiated flow with device selection."""

    async def test_user_flow_shows_discovered_devices(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
    ):
        """Test user flow shows discovered devices."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_user_flow_select_manual(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
    ):
        """Test user can select manual entry from device list."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_ADDRESS: "manual"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"


class TestOptionsFlow:
    """Test options flow."""

    async def test_options_flow(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test options flow allows changing settings."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Verify the config entry was updated
        assert mock_config_entry.data[CONF_MOTOR_COUNT] == 4
        assert mock_config_entry.data[CONF_HAS_MASSAGE] is True
        assert mock_config_entry.data[CONF_DISABLE_ANGLE_SENSING] is False
