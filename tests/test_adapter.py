"""Tests for Bluetooth adapter helper fallbacks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.adapter import (
    get_ble_device_with_fallback,
    get_discovered_service_info,
)


class TestAdapterFallbacks:
    """Test discovery helpers that fall back to non-connectable records."""

    def test_get_discovered_service_info_includes_non_connectable(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Merged discovery should include non-connectable entries when requested."""
        connectable_info = MagicMock()
        connectable_info.address = "AA:BB:CC:DD:EE:FF"
        connectable_info.source = "proxy_1"
        connectable_info.connectable = True

        non_connectable_info = MagicMock()
        non_connectable_info.address = "11:22:33:44:55:66"
        non_connectable_info.source = "proxy_1"
        non_connectable_info.connectable = False

        with patch(
            "custom_components.adjustable_bed.adapter.bluetooth.async_discovered_service_info",
            side_effect=([connectable_info], [non_connectable_info]),
        ):
            discovered = get_discovered_service_info(
                hass,
                include_non_connectable=True,
            )

        assert discovered == [connectable_info, non_connectable_info]

    def test_get_ble_device_with_fallback_uses_non_connectable_service_info(
        self,
        hass: HomeAssistant,
    ) -> None:
        """A non-connectable scanner snapshot should still provide the BLEDevice."""
        fallback_device = MagicMock()
        fallback_device.address = "AA:BB:CC:DD:EE:FF"

        non_connectable_info = MagicMock()
        non_connectable_info.address = "AA:BB:CC:DD:EE:FF"
        non_connectable_info.device = fallback_device

        with (
            patch(
                "custom_components.adjustable_bed.adapter.bluetooth.async_ble_device_from_address",
                return_value=None,
            ),
            patch(
                "custom_components.adjustable_bed.adapter.bluetooth.async_last_service_info",
                side_effect=(None, non_connectable_info),
            ),
        ):
            device, connectable = get_ble_device_with_fallback(
                hass,
                "AA:BB:CC:DD:EE:FF",
                allow_non_connectable=True,
            )

        assert device is fallback_device
        assert connectable is False
