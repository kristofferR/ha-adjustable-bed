"""Tests for diagnostics module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.diagnostics import async_get_config_entry_diagnostics
from custom_components.adjustable_bed.redaction import (
    KEYS_TO_REDACT,
    MAC_ADDRESS_KEYS,
    _redact_mac_address,
)


@pytest.fixture
def mock_diagnostics_config_entry_data() -> dict:
    """Return mock config entry data for diagnostics test."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Test Bed",
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_diagnostics_config_entry(
    hass: HomeAssistant, mock_diagnostics_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for diagnostics test."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Bed",
        data=mock_diagnostics_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="diagnostics_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestDiagnosticsRedaction:
    """Test diagnostics data redaction."""

    def test_redact_keys(self):
        """Test that sensitive keys are in redaction lists."""
        # Name and PIN should be fully redacted
        assert CONF_NAME in KEYS_TO_REDACT
        # MAC address should be partially redacted (OUI kept)
        assert CONF_ADDRESS in MAC_ADDRESS_KEYS
        assert "address" in MAC_ADDRESS_KEYS

    def test_mac_address_partial_redaction(self):
        """Test that MAC addresses are partially redacted, keeping the OUI."""
        # Should keep first 3 bytes (OUI) and redact last 3
        assert _redact_mac_address("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:**:**:**"
        assert _redact_mac_address("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:**:**:**"
        # Should handle dash separators
        assert _redact_mac_address("AA-BB-CC-DD-EE-FF") == "AA-BB-CC-**-**-**"

    def test_mac_address_redaction_edge_cases(self):
        """Test _redact_mac_address handles edge cases correctly."""
        # Empty string should return as-is
        assert _redact_mac_address("") == ""

        # None should return as-is
        assert _redact_mac_address(None) is None

        # Non-string should return as-is
        assert _redact_mac_address(12345) == 12345

        # Invalid format (wrong number of parts) should be fully redacted
        assert _redact_mac_address("AA:BB:CC:DD:EE") == "**REDACTED**"
        assert _redact_mac_address("AA:BB:CC:DD:EE:FF:GG") == "**REDACTED**"
        assert _redact_mac_address("not-a-mac") == "**REDACTED**"

        # Single character should be fully redacted
        assert _redact_mac_address("X") == "**REDACTED**"


class TestDiagnosticsOutput:
    """Test diagnostics output structure."""

    async def test_diagnostics_not_connected(
        self,
        hass: HomeAssistant,
        mock_diagnostics_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test diagnostics when not connected."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        # Set up the coordinator and add to hass data
        coordinator = AdjustableBedCoordinator(hass, mock_diagnostics_config_entry)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_diagnostics_config_entry.entry_id] = coordinator

        # Mock disconnected state
        mock_bleak_client.is_connected = False

        result = await async_get_config_entry_diagnostics(hass, mock_diagnostics_config_entry)

        # Check structure
        assert "entry" in result
        assert "config" in result
        assert "coordinator" in result
        assert "ble" in result
        assert "controller" in result
        assert "position_data" in result
        assert "supported_bed_types" in result

    async def test_diagnostics_connected(
        self,
        hass: HomeAssistant,
        mock_diagnostics_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test diagnostics when connected."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        # Set up the coordinator
        coordinator = AdjustableBedCoordinator(hass, mock_diagnostics_config_entry)
        await coordinator.async_connect()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_diagnostics_config_entry.entry_id] = coordinator

        result = await async_get_config_entry_diagnostics(hass, mock_diagnostics_config_entry)

        # Check entry data
        assert result["entry"]["entry_id"] == "diagnostics_test_entry"
        # Title is redacted for privacy
        assert result["entry"]["title"] == "**REDACTED**"

        # Check config
        assert result["config"]["bed_type"] == BED_TYPE_LINAK
        assert result["config"]["motor_count"] == 2
        assert result["config"]["has_massage"] is False
        assert result["config"]["disable_angle_sensing"] is True

        # Check coordinator
        assert "is_connected" in result["coordinator"]
        assert "is_connecting" in result["coordinator"]

        # Check BLE info
        assert "connected" in result["ble"]

        # Check controller info
        assert "initialized" in result["controller"]

    async def test_diagnostics_redacts_sensitive_data(
        self,
        hass: HomeAssistant,
        mock_diagnostics_config_entry,
        mock_coordinator_connected,
    ):
        """Test that sensitive data is redacted."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        coordinator = AdjustableBedCoordinator(hass, mock_diagnostics_config_entry)
        await coordinator.async_connect()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_diagnostics_config_entry.entry_id] = coordinator

        result = await async_get_config_entry_diagnostics(hass, mock_diagnostics_config_entry)

        # Check data redaction in entry.data
        entry_data = result["entry"]["data"]
        # MAC address should be partially redacted (OUI kept: AA:BB:CC)
        assert entry_data.get(CONF_ADDRESS) == "AA:BB:CC:**:**:**"
        # Name should be fully redacted
        assert entry_data.get(CONF_NAME) == "**REDACTED**"

    async def test_diagnostics_controller_info(
        self,
        hass: HomeAssistant,
        mock_diagnostics_config_entry,
        mock_coordinator_connected,
    ):
        """Test diagnostics includes controller info when connected."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        coordinator = AdjustableBedCoordinator(hass, mock_diagnostics_config_entry)
        await coordinator.async_connect()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_diagnostics_config_entry.entry_id] = coordinator

        result = await async_get_config_entry_diagnostics(hass, mock_diagnostics_config_entry)

        controller_info = result["controller"]
        assert controller_info["initialized"] is True
        assert "class" in controller_info
        assert controller_info["class"] == "LinakController"
        assert "characteristic_uuid" in controller_info

    async def test_diagnostics_supported_bed_types(
        self,
        hass: HomeAssistant,
        mock_diagnostics_config_entry,
        mock_coordinator_connected,
    ):
        """Test diagnostics includes supported bed types."""
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        coordinator = AdjustableBedCoordinator(hass, mock_diagnostics_config_entry)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][mock_diagnostics_config_entry.entry_id] = coordinator

        result = await async_get_config_entry_diagnostics(hass, mock_diagnostics_config_entry)

        assert len(result["supported_bed_types"]) > 0
        assert "linak" in result["supported_bed_types"]
