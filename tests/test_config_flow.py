"""Tests for Adjustable Bed config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LINAK,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    RICHMAT_WILINKE_SERVICE_UUIDS,
)
from custom_components.adjustable_bed.detection import detect_bed_type


class TestDetectBedType:
    """Test bed type detection."""

    def test_detect_linak_bed(self, mock_bluetooth_service_info: BluetoothServiceInfoBleak):
        """Test detection of Linak bed."""
        bed_type = detect_bed_type(mock_bluetooth_service_info)
        assert bed_type == BED_TYPE_LINAK

    def test_detect_linak_bed_by_name(self, mock_bluetooth_service_info: BluetoothServiceInfoBleak):
        """Test detection of Linak bed by name pattern when no service UUIDs advertised."""
        # Some Linak beds don't advertise service UUIDs in their BLE beacon
        mock_bluetooth_service_info.name = "Bed 1696"
        mock_bluetooth_service_info.service_uuids = []
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

    def test_detect_motosleep_bed(self, mock_bluetooth_service_info_motosleep):
        """Test detection of MotoSleep bed (by HHC name prefix)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_motosleep)
        assert bed_type == BED_TYPE_MOTOSLEEP

    def test_detect_leggett_platt_bed(self, mock_bluetooth_service_info_leggett):
        """Test detection of Leggett & Platt bed (Gen2)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_leggett)
        assert bed_type == BED_TYPE_LEGGETT_GEN2

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

    def test_detect_ergomotion_bed(self, mock_bluetooth_service_info_ergomotion):
        """Test detection of Ergomotion bed by name."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_ergomotion)
        assert bed_type == BED_TYPE_ERGOMOTION

    def test_detect_ergomotion_ergo_name(self):
        """Test Ergomotion detection with 'ergo' in name."""
        service_info = MagicMock()
        service_info.name = "Ergo Adjust Pro"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_ERGOMOTION

    def test_detect_ergomotion_serta_i_name(self):
        """Test Ergomotion detection with 'serta-i' prefix (e.g., Serta-i490350)."""
        service_info = MagicMock()
        service_info.name = "Serta-i490350"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_ERGOMOTION

    def test_detect_keeson_base_i4_name(self):
        """Test Keeson detection with 'base-i4.' prefix (e.g., base-i4.00002574)."""
        service_info = MagicMock()
        service_info.name = "base-i4.00002574"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_KEESON

    def test_detect_coolbase_base_i5_name(self):
        """Test Cool Base detection with 'base-i5.' prefix (e.g., base-i5.00000682).

        Cool Base is a Keeson BaseI5 variant with additional fan control.
        """
        service_info = MagicMock()
        service_info.name = "base-i5.00000682"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_COOLBASE

    def test_detect_keeson_ksbt_name(self):
        """Test Keeson detection with 'KSBT' prefix (e.g., KSBT03C000015046)."""
        service_info = MagicMock()
        service_info.name = "KSBT03C000015046"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_KEESON

    def test_detect_richmat_qrrm_name(self):
        """Test Richmat detection with 'QRRM' prefix (e.g., QRRM157052)."""
        service_info = MagicMock()
        service_info.name = "QRRM157052"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_richmat_sleep_function_name(self):
        """Test Richmat detection with 'Sleep Function' prefix (I7RM remote)."""
        service_info = MagicMock()
        service_info.name = "Sleep Function 2.0"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_okimat_okin_prefix_name(self):
        """Test Okimat detection with 'OKIN-' prefix (e.g., OKIN-346311)."""
        from custom_components.adjustable_bed.const import OKIMAT_SERVICE_UUID

        service_info = MagicMock()
        service_info.name = "OKIN-346311"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = [OKIMAT_SERVICE_UUID]
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_OKIMAT

    def test_detect_jiecang_bed(self, mock_bluetooth_service_info_jiecang):
        """Test detection of Jiecang bed by name (JC- prefix)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_jiecang)
        assert bed_type == BED_TYPE_JIECANG

    def test_detect_jiecang_glide_name(self):
        """Test Jiecang detection with 'glide' in name."""
        service_info = MagicMock()
        service_info.name = "Glide Smart Base"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_JIECANG

    def test_detect_jiecang_dream_motion_name(self):
        """Test Jiecang detection with 'dream motion' in name."""
        service_info = MagicMock()
        service_info.name = "Dream Motion Base"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_JIECANG

    def test_detect_dewertokin_bed(self, mock_bluetooth_service_info_dewertokin):
        """Test detection of DewertOkin bed by name (A H Beard)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_dewertokin)
        assert bed_type == BED_TYPE_DEWERTOKIN

    def test_detect_dewertokin_dewert_name(self):
        """Test DewertOkin detection with 'dewert' in name."""
        service_info = MagicMock()
        service_info.name = "Dewert Base"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_DEWERTOKIN

    def test_detect_dewertokin_hankook_name(self):
        """Test DewertOkin detection with 'hankook' in name."""
        service_info = MagicMock()
        service_info.name = "HankookGallery Bed"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_DEWERTOKIN

    def test_detect_serta_bed(self, mock_bluetooth_service_info_serta):
        """Test detection of Serta bed by name - now returns BED_TYPE_SERTA."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_serta)
        assert bed_type == BED_TYPE_SERTA

    def test_detect_serta_motion_perfect_name(self):
        """Test Serta detection with 'motion perfect' in name - returns BED_TYPE_SERTA."""
        service_info = MagicMock()
        service_info.name = "Motion Perfect III"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_SERTA

    def test_detect_octo_bed(self, mock_bluetooth_service_info_octo):
        """Test detection of Octo bed by name containing 'octo'."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_octo)
        assert bed_type == BED_TYPE_OCTO

    def test_detect_octo_rc2_receiver(self, mock_bluetooth_service_info_octo_rc2):
        """Test detection of Octo RC2 receiver - defaults to Octo for shared UUID.

        Issue #73: Devices like RC2 that share the Solace UUID but don't have
        'solace' in the name should default to Octo since it's more common.
        """
        bed_type = detect_bed_type(mock_bluetooth_service_info_octo_rc2)
        assert bed_type == BED_TYPE_OCTO

    def test_detect_solace_bed(self, mock_bluetooth_service_info_solace):
        """Test detection of Solace bed by name containing 'solace'."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_solace)
        assert bed_type == BED_TYPE_SOLACE

    def test_detect_solace_bed_pattern(self, mock_bluetooth_service_info_solace_pattern):
        """Test detection of Solace bed by naming pattern like S4-Y-192-461000AD."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_solace_pattern)
        assert bed_type == BED_TYPE_SOLACE

    def test_detect_octo_star2_bed(self, mock_bluetooth_service_info_octo_star2):
        """Test detection of Octo Star2 bed by service UUID (not by name)."""
        bed_type = detect_bed_type(mock_bluetooth_service_info_octo_star2)
        assert bed_type == BED_TYPE_OCTO

    def test_detect_leggett_platt_mlrm_bed(self, mock_bluetooth_service_info_leggett_platt_richmat):
        """Test detection of Leggett & Platt MlRM variant bed (MlRM prefix).

        MlRM beds are now detected as BED_TYPE_LEGGETT_WILINKE.
        """
        bed_type = detect_bed_type(mock_bluetooth_service_info_leggett_platt_richmat)
        assert bed_type == BED_TYPE_LEGGETT_WILINKE

    def test_detect_leggett_platt_mlrm_case_insensitive(self):
        """Test L&P MlRM detection is case-insensitive (name is lowercased)."""
        # Test with uppercase MLRM
        service_info = MagicMock()
        service_info.name = "MLRM123456"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = [RICHMAT_WILINKE_SERVICE_UUIDS[1]]
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_LEGGETT_WILINKE

    def test_detect_leggett_mlrm_vs_generic_richmat(self):
        """Test L&P MlRM takes precedence over generic Richmat for mlrm prefix.

        Both L&P MlRM and generic Richmat use WiLinke UUIDs, but beds with
        'mlrm' prefix should be detected as L&P.
        """
        # Same UUID as generic Richmat WiLinke, but with mlrm prefix
        service_info = MagicMock()
        service_info.name = "mlrm157052"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = [RICHMAT_WILINKE_SERVICE_UUIDS[0]]  # First WiLinke UUID
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_LEGGETT_WILINKE

        # Verify generic Richmat still works for non-mlrm names
        service_info.name = "Generic WiLinke Bed"
        bed_type = detect_bed_type(service_info)
        assert bed_type == BED_TYPE_RICHMAT

    def test_detect_leggett_mlrm_without_service_uuid(self):
        """Test L&P MlRM needs both name pattern AND WiLinke service UUID.

        If the name matches but UUID doesn't, it should not be detected as L&P MlRM.
        """
        service_info = MagicMock()
        service_info.name = "MlRM157052"
        service_info.address = "AA:BB:CC:DD:EE:FF"
        service_info.service_uuids = []  # No service UUIDs
        service_info.manufacturer_data = {}

        bed_type = detect_bed_type(service_info)
        # Should NOT detect as L&P MlRM without UUID
        assert bed_type is None


class TestPinValidation:
    """Test PIN validation for Octo beds."""

    def test_valid_4_digit_pin(self):
        """Test that 4-digit PIN is accepted."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        assert validator("1234") == "1234"
        assert validator("0000") == "0000"
        assert validator("9999") == "9999"

    def test_empty_pin_allowed(self):
        """Test that empty PIN (no PIN) is allowed."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        assert validator("") == ""

    def test_invalid_pin_too_short(self):
        """Test that PIN shorter than 4 digits is rejected."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        with pytest.raises(vol.Invalid):
            validator("123")
        with pytest.raises(vol.Invalid):
            validator("1")

    def test_invalid_pin_too_long(self):
        """Test that PIN longer than 4 digits is rejected."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        with pytest.raises(vol.Invalid):
            validator("12345")
        with pytest.raises(vol.Invalid):
            validator("123456")

    def test_invalid_pin_non_digits(self):
        """Test that PIN with non-digit characters is rejected."""
        import voluptuous as vol

        validator = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))
        with pytest.raises(vol.Invalid):
            validator("abcd")
        with pytest.raises(vol.Invalid):
            validator("12ab")


class TestBluetoothDiscoveryFlow:
    """Test Bluetooth discovery flow."""

    async def test_bluetooth_discovery_creates_entry(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
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
        enable_custom_integrations,
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
        enable_custom_integrations,
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
        enable_custom_integrations,
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

    async def test_bluetooth_discovery_ambiguous_shows_disambiguation(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test that ambiguous BLE detection shows disambiguation step."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )

        # Should show disambiguation form instead of confirm
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_disambiguate"

    async def test_bluetooth_disambiguate_selects_type(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test selecting a bed type from disambiguation proceeds to confirm."""
        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        # Select a specific bed type from disambiguation
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": BED_TYPE_OKIMAT},
        )

        # Should proceed to confirm step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_bluetooth_disambiguate_show_all_option(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test selecting 'show all' from disambiguation proceeds to confirm."""
        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        # Select "show all bed types" option
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": "show_all"},
        )

        # Should proceed to confirm step with full bed type list available
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_bluetooth_disambiguate_creates_entry_with_selected_type(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info_ambiguous_okin: MagicMock,
        enable_custom_integrations,
    ):
        """Test that disambiguation selection results in correct bed type in entry."""
        from custom_components.adjustable_bed.const import BED_TYPE_OKIN_64BIT

        # Start the flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info_ambiguous_okin,
        )
        assert result["step_id"] == "bluetooth_disambiguate"

        # Select OKIN 64-bit from disambiguation options (doesn't require pairing)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"bed_type_choice": BED_TYPE_OKIN_64BIT},
        )
        assert result["step_id"] == "bluetooth_confirm"

        # Confirm with minimal input
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "My Bed",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
        )

        # Should create entry with the disambiguated type
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BED_TYPE] == BED_TYPE_OKIN_64BIT


class TestManualFlow:
    """Test manual configuration flow."""

    async def test_manual_select_shows_devices(
        self,
        hass: HomeAssistant,
        mock_bluetooth_service_info: BluetoothServiceInfoBleak,
        enable_custom_integrations,
    ):
        """Test manual select step shows all BLE devices."""
        # First go to user step and select manual
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[mock_bluetooth_service_info],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

    async def test_manual_no_devices_goes_to_entry(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Test manual step goes to manual_entry when no devices are found."""
        # First go to user step (no beds discovered, but form still shown)
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        # When no BLE devices, manual step redirects to manual_entry
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual_entry"

    async def test_manual_entry_creates_entry(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Test manual entry creates a config entry."""
        # First go to user step
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step - goes to manual_entry since no devices
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
            )

        # Now in manual_entry step, fill the form
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

    async def test_manual_entry_invalid_mac(self, hass: HomeAssistant, enable_custom_integrations):
        """Test manual entry with invalid MAC address shows error."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
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
        assert result["errors"] is not None
        assert result["errors"]["base"] == "invalid_mac_address"

    async def test_manual_entry_normalizes_mac(
        self, hass: HomeAssistant, enable_custom_integrations
    ):
        """Test manual entry normalizes MAC address format."""
        with patch(
            "custom_components.adjustable_bed.config_flow.async_discovered_service_info",
            return_value=[],
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
            )

            # Select manual from user step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_ADDRESS: "manual"},
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
        enable_custom_integrations,
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
        enable_custom_integrations,
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

            # Keep the patch active so manual step finds devices
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
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test options flow allows changing settings."""
        # Set up the integration first so the options flow handler is registered
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

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
