"""Tests for Bluetooth adapter helper fallbacks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.adapter import (
    get_ble_device_with_fallback,
    get_discovered_service_info,
    read_ble_device_info,
)
from custom_components.adjustable_bed.const import (
    DEVICE_INFO_CHARS,
    DEVICE_INFO_SERVICE_UUID,
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


class TestReadBleDeviceInfo:
    """Device Information Service reads must be time-boxed."""

    async def test_hung_reads_are_time_boxed(self) -> None:
        """A characteristic that never answers cannot stall the read."""
        device_info_service = MagicMock()
        device_info_service.uuid = DEVICE_INFO_SERVICE_UUID

        client = MagicMock()
        client.services = [device_info_service]

        async def _never_answers(*args, **kwargs):
            await asyncio.Event().wait()

        client.read_gatt_char = AsyncMock(side_effect=_never_answers)

        with patch(
            "custom_components.adjustable_bed.adapter.DEVICE_INFO_READ_TIMEOUT",
            0.05,
        ):
            async with asyncio.timeout(5):
                manufacturer, model = await read_ble_device_info(
                    client, "AA:BB:CC:DD:EE:FF"
                )

        assert manufacturer is None
        assert model is None
        # Both characteristic reads were attempted and timed out.
        assert client.read_gatt_char.await_count == 2

    async def test_oserror_reads_degrade_to_missing_values(self) -> None:
        """Raw backend I/O errors must not abort the connection attempt."""
        device_info_service = MagicMock()
        device_info_service.uuid = DEVICE_INFO_SERVICE_UUID

        client = MagicMock()
        client.services = [device_info_service]
        client.read_gatt_char = AsyncMock(side_effect=OSError("GATT I/O failed"))

        manufacturer, model = await read_ble_device_info(
            client, "AA:BB:CC:DD:EE:FF"
        )

        assert manufacturer is None
        assert model is None
        assert client.read_gatt_char.await_count == 2

    async def test_recovers_wlt_model_from_duplicate_software_revision(self) -> None:
        """WLT's second 0x2A28 instance contains the actual QRRM controller model."""
        firmware_char = MagicMock(
            uuid=DEVICE_INFO_CHARS["software_revision"],
            handle=36,
        )
        model_char = MagicMock(
            uuid=DEVICE_INFO_CHARS["software_revision"],
            handle=42,
        )
        device_info_service = MagicMock(
            uuid=DEVICE_INFO_SERVICE_UUID,
            characteristics=[firmware_char, model_char],
        )
        client = MagicMock()
        client.is_connected = True
        client.services = [device_info_service]

        async def read_gatt_char(characteristic: object) -> bytes:
            if characteristic == DEVICE_INFO_CHARS["manufacturer_name"]:
                return b"WLT"
            if characteristic == DEVICE_INFO_CHARS["model_number"]:
                raise BleakError("model number characteristic missing")
            if characteristic is firmware_char:
                return b"V216.17.8"
            if characteristic is model_char:
                return b"WLT825X_H35"
            raise AssertionError(f"Unexpected characteristic: {characteristic}")

        client.read_gatt_char = AsyncMock(side_effect=read_gatt_char)

        manufacturer, model = await read_ble_device_info(
            client, "57:4C:54:30:76:51"
        )

        assert manufacturer == "WLT"
        assert model == "WLT825X_H35"

    async def test_recovers_wlt_model_when_standard_model_is_blank(self) -> None:
        """Blank standard model data should not block WLT vendor model recovery."""
        firmware_char = MagicMock(
            uuid=DEVICE_INFO_CHARS["software_revision"],
            handle=36,
        )
        model_char = MagicMock(
            uuid=DEVICE_INFO_CHARS["software_revision"],
            handle=42,
        )
        device_info_service = MagicMock(
            uuid=DEVICE_INFO_SERVICE_UUID,
            characteristics=[firmware_char, model_char],
        )
        client = MagicMock()
        client.is_connected = True
        client.services = [device_info_service]

        async def read_gatt_char(characteristic: object) -> bytes:
            if characteristic == DEVICE_INFO_CHARS["manufacturer_name"]:
                return b"WLT"
            if characteristic == DEVICE_INFO_CHARS["model_number"]:
                return b"\x00\x00"
            if characteristic is firmware_char:
                return b"V216.17.8"
            if characteristic is model_char:
                return b"WLT825X_H35"
            raise AssertionError(f"Unexpected characteristic: {characteristic}")

        client.read_gatt_char = AsyncMock(side_effect=read_gatt_char)

        manufacturer, model = await read_ble_device_info(
            client, "57:4C:54:30:76:51"
        )

        assert manufacturer == "WLT"
        assert model == "WLT825X_H35"
