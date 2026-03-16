"""Tests for support bundle generation and enriched diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.ble_diagnostics import (
    BLEDiagnosticRunner,
    DiagnosticReport,
)
from custom_components.adjustable_bed.const import (
    DEVICE_INFO_CHARS,
    LINAK_CONTROL_SERVICE_UUID,
    SOLACE_SERVICE_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.support_bundle import generate_support_bundle


class _FakeServices:
    """Simple BLE service collection for tests."""

    def __init__(self, services: list[MagicMock]) -> None:
        self._services = services

    def __iter__(self):
        return iter(self._services)

    def __len__(self) -> int:
        return len(self._services)

    def get_service(self, uuid: str) -> MagicMock | None:
        for service in self._services:
            if service.uuid == uuid:
                return service
        return None


def _build_unknown_service_info(*, source: str, connectable: bool, rssi: int) -> MagicMock:
    """Create a mock BLE advertisement snapshot."""
    service_info = MagicMock()
    service_info.name = "HHC3611243CDEF"
    service_info.address = "AA:BB:CC:DD:EE:FF"
    service_info.rssi = rssi
    service_info.manufacturer_data = {65535: b"AT"}
    service_info.service_data = {"test": b"OK"}
    service_info.service_uuids = [SOLACE_SERVICE_UUID]
    service_info.source = source
    service_info.device = MagicMock(
        address="AA:BB:CC:DD:EE:FF",
        name="HHC3611243CDEF",
        details={"source": source, "props": {"Paired": True, "Trusted": False}},
    )
    service_info.connectable = connectable
    service_info.time = 1_700_000_000
    return service_info


class TestBleDiagnosticsRunner:
    """Test enriched BLE diagnostics output."""

    async def test_run_diagnostics_enriches_detection_gatt_and_notifications(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Diagnostics should include detection, per-source advertisements, and summaries."""
        connectable_info = _build_unknown_service_info(
            source="proxy_1",
            connectable=True,
            rssi=-55,
        )
        fallback_info = _build_unknown_service_info(
            source="proxy_2",
            connectable=False,
            rssi=-70,
        )

        descriptor = MagicMock(uuid="00002902-0000-1000-8000-00805f9b34fb", handle=34)
        characteristic = MagicMock(
            uuid="0000ffe1-0000-1000-8000-00805f9b34fb",
            handle=33,
            properties=["read", "notify"],
            descriptors=[descriptor],
        )
        service = MagicMock(
            uuid="0000ffe0-0000-1000-8000-00805f9b34fb",
            handle=32,
            characteristics=[characteristic],
        )
        services = _FakeServices([service])

        client = MagicMock()
        client.is_connected = True
        client.services = services
        client._backend = MagicMock(
            _device=MagicMock(
                details={
                    "source": "proxy_1",
                    "props": {"Paired": True, "Trusted": False, "AddressType": "random"},
                }
            )
        )
        client.get_services = AsyncMock()

        async def _read_gatt_char(target):
            target_uuid = getattr(target, "uuid", target)
            if target_uuid == characteristic.uuid:
                return b"AT+INFO"
            if target_uuid == DEVICE_INFO_CHARS["manufacturer_name"]:
                return b"Acme\x00"
            if target_uuid == DEVICE_INFO_CHARS["model_number"]:
                return b"Base-1\x00"
            raise ValueError(f"unexpected read target {target_uuid}")

        async def _start_notify(target, handler):
            handler(MagicMock(), bytearray(b"OK"))

        client.read_gatt_char = AsyncMock(side_effect=_read_gatt_char)
        client.start_notify = AsyncMock(side_effect=_start_notify)
        client.stop_notify = AsyncMock()
        client.disconnect = AsyncMock()

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(connectable_info, True), (fallback_info, False)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.select_adapter",
                new=AsyncMock(
                    return_value=AdapterSelectionResult(
                        device=connectable_info.device,
                        source="proxy_1",
                        rssi=-55,
                        connectable=True,
                        available_sources=["proxy_1 (RSSI: -55)", "proxy_2 (RSSI: -70)"],
                    )
                ),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.establish_connection",
                new=AsyncMock(return_value=client),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=2,
            ),
        ):
            report = await BLEDiagnosticRunner(
                hass,
                "AA:BB:CC:DD:EE:FF",
                capture_duration=0,
            ).run_diagnostics()

        assert report.detection["bed_type"] == "motosleep"
        assert report.detection["supported_match"] is True
        assert len(report.advertisements_by_source) == 2
        assert report.advertisement["selected_for_connection"] is True
        assert report.device["pairing"]["paired"] is True
        assert report.device["scanner_count"] == 2
        assert report.gatt_services[0]["handle"] == 32
        assert report.gatt_services[0]["characteristics"][0]["handle"] == 33
        assert report.gatt_services[0]["characteristics"][0]["descriptors"][0]["handle"] == 34
        assert report.gatt_services[0]["characteristics"][0]["read_result"]["ascii_preview"] == "AT+INFO"
        assert report.gatt_services[0]["characteristics"][0]["notify_subscription"]["success"] is True
        assert report.notifications[0]["data_hex"] == "4f4b"
        assert report.notification_summary["by_characteristic"][characteristic.uuid]["count"] == 1
        assert report.notification_summary["by_characteristic"][characteristic.uuid][
            "observed_payload_lengths"
        ] == [2]


class TestSupportBundle:
    """Test support bundle orchestration."""

    async def test_generate_support_bundle_raw_address_has_standard_sections(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Raw-address bundles should keep configured-device sections empty but present."""
        diagnostic_report = DiagnosticReport(
            metadata={"version": "2.0"},
            device={
                "address": "AA:BB:CC:DD:EE:FF",
                "selected_source": "proxy_1",
                "actual_source": "proxy_1",
                "scanner_count": 2,
                "visible_sources": ["proxy_1", "proxy_2"],
                "non_connectable_fallback_used": False,
            },
            advertisement={"address": "AA:BB:CC:DD:EE:FF", "selected_for_connection": True},
            advertisements_by_source=[{"source": "proxy_1"}],
            detection={"bed_type": "linak", "supported_match": True},
            gatt_services=[{"uuid": LINAK_CONTROL_SERVICE_UUID}],
            gatt_summary={"available": True, "service_count": 1},
            device_information={"manufacturer_name": "Linak"},
            notifications=[],
            notification_summary={"total_notifications": 0, "by_characteristic": {}},
            adapter_details={},
            connection_history={},
            connection_attempt_details=[{"attempt": 1, "result": "connected"}],
            command_trace=[],
            errors=[],
        )

        with (
            patch.object(
                BLEDiagnosticRunner,
                "run_diagnostics",
                new=AsyncMock(return_value=diagnostic_report),
            ),
            patch(
                "custom_components.adjustable_bed.support_bundle.bluetooth.async_current_scanners",
                return_value=[MagicMock(source="proxy_1", name="Proxy 1", scanning=True)],
            ),
        ):
            report = await generate_support_bundle(
                hass,
                address="AA:BB:CC:DD:EE:FF",
                capture_duration=0,
                include_logs=False,
            )

        assert report["target"]["mode"] == "target_address"
        assert report["integration"]["configured_device"] is False
        assert report["controller"]["initialized"] is False
        assert report["command_trace"] == []
        assert report["bluetooth"]["advertisements_by_source"] == [{"source": "proxy_1"}]
        assert report["connection_attempt_details"][0]["result"] == "connected"

    async def test_coordinator_records_command_trace(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Integration-issued writes should be buffered for support bundles."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        assert controller is not None

        await controller.write_command(b"\x01\x02", repeat_count=2, repeat_delay_ms=25)

        trace = coordinator.command_trace
        assert trace
        assert trace[-1]["payload"]["hex"] == "0102"
        assert trace[-1]["repeat_count"] == 2
        assert trace[-1]["repeat_delay_ms"] == 25
