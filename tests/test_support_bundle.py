"""Tests for support bundle generation and enriched diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.ble_diagnostics import (
    BLEDiagnosticRunner,
    DiagnosticReport,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    DEVICE_INFO_CHARS,
    LINAK_CONTROL_SERVICE_UUID,
    NORDIC_DFU_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
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

    def get_characteristic(self, specifier: int | str) -> MagicMock | None:
        for service in self._services:
            for characteristic in service.characteristics:
                if specifier in (characteristic.handle, characteristic.uuid):
                    return characteristic
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


def _build_reconnect_test_service() -> MagicMock:
    """Create a service whose second characteristic read drops the connection."""
    char_ok = MagicMock(
        uuid="0000ffe1-0000-1000-8000-00805f9b34fb",
        handle=33,
        properties=["read", "notify"],
        descriptors=[],
    )
    char_kill = MagicMock(
        uuid="0000ffe2-0000-1000-8000-00805f9b34fb",
        handle=35,
        properties=["read"],
        descriptors=[],
    )
    char_after = MagicMock(
        uuid="0000ffe3-0000-1000-8000-00805f9b34fb",
        handle=37,
        properties=["read"],
        descriptors=[],
    )
    return MagicMock(
        uuid="0000ffe0-0000-1000-8000-00805f9b34fb",
        handle=32,
        characteristics=[char_ok, char_kill, char_after],
    )


def _build_diagnostic_client(services: _FakeServices) -> MagicMock:
    """Create a mock BleakClient backed by the given service collection."""
    client = MagicMock()
    client.is_connected = True
    client.services = services
    client._backend = MagicMock(
        _device=MagicMock(details={"source": "proxy_1", "props": {"Paired": False}})
    )
    client.get_services = AsyncMock()
    client.read_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    return client


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

    async def test_run_diagnostics_detects_okin_rf_eco_bt_from_gatt_signature(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Diagnostics should identify OKIN RF ECO BT from connected GATT services."""
        service_info = MagicMock()
        service_info.name = "OKIN-050226"
        service_info.address = "AA:BB:CC:DD:EE:44"
        service_info.rssi = -64
        service_info.manufacturer_data = {}
        service_info.service_data = {}
        service_info.service_uuids = []
        service_info.source = "proxy_1"
        service_info.device = MagicMock(
            address="AA:BB:CC:DD:EE:44",
            name="OKIN-050226",
            details={"source": "proxy_1", "props": {"Paired": True}},
        )
        service_info.connectable = True
        service_info.time = 1_700_000_000

        okin_write = MagicMock(
            uuid=OKIMAT_WRITE_CHAR_UUID,
            handle=18,
            properties=["write"],
            descriptors=[],
        )
        css_write = MagicMock(
            uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
            handle=43,
            properties=["write"],
            descriptors=[],
        )
        services = _FakeServices(
            [
                MagicMock(
                    uuid=OKIMAT_SERVICE_UUID,
                    handle=12,
                    characteristics=[okin_write],
                ),
                MagicMock(
                    uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                    handle=35,
                    characteristics=[css_write],
                ),
            ]
        )

        client = MagicMock()
        client.is_connected = True
        client.services = services
        client._backend = MagicMock(
            _device=MagicMock(details={"source": "proxy_1", "props": {"Paired": True}})
        )
        client.get_services = AsyncMock()
        client.read_gatt_char = AsyncMock()
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()
        client.disconnect = AsyncMock()

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(service_info, True)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.select_adapter",
                new=AsyncMock(
                    return_value=AdapterSelectionResult(
                        device=service_info.device,
                        source="proxy_1",
                        rssi=-64,
                        connectable=True,
                        available_sources=["proxy_1 (RSSI: -64)"],
                    )
                ),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.establish_connection",
                new=AsyncMock(return_value=client),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=1,
            ),
        ):
            report = await BLEDiagnosticRunner(
                hass,
                "AA:BB:CC:DD:EE:44",
                capture_duration=0,
            ).run_diagnostics()

        assert report.detection["bed_type"] == BED_TYPE_OKIN_RF_ECO_BT
        assert report.detection["supported_match"] is True
        assert "gatt_char:okin_smart_remote_css_write" in report.detection["signals"]

    async def test_run_diagnostics_detects_okin_cst_dual_stack_signature(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Diagnostics should not classify full OKIN CST beds as RF ECO BT."""
        service_info = MagicMock()
        service_info.name = "OKIN-441954"
        service_info.address = "AA:BB:CC:DD:EE:55"
        service_info.rssi = -59
        service_info.manufacturer_data = {}
        service_info.service_data = {}
        service_info.service_uuids = [OKIMAT_SERVICE_UUID]
        service_info.source = "proxy_1"
        service_info.device = MagicMock(
            address="AA:BB:CC:DD:EE:55",
            name="OKIN-441954",
            details={"source": "proxy_1", "props": {"Paired": True}},
        )
        service_info.connectable = True
        service_info.time = 1_700_000_000

        okin_write = MagicMock(
            uuid=OKIMAT_WRITE_CHAR_UUID,
            handle=19,
            properties=["read", "write"],
            descriptors=[],
        )
        css_write = MagicMock(
            uuid=OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
            handle=42,
            properties=["read", "write"],
            descriptors=[],
        )
        services = _FakeServices(
            [
                MagicMock(
                    uuid=OKIMAT_SERVICE_UUID,
                    handle=12,
                    characteristics=[okin_write],
                ),
                MagicMock(
                    uuid=OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
                    handle=33,
                    characteristics=[css_write],
                ),
                MagicMock(
                    uuid=NORDIC_DFU_SERVICE_UUID,
                    handle=43,
                    characteristics=[],
                ),
            ]
        )

        client = MagicMock()
        client.is_connected = True
        client.services = services
        client._backend = MagicMock(
            _device=MagicMock(details={"source": "proxy_1", "props": {"Paired": True}})
        )
        client.get_services = AsyncMock()
        client.read_gatt_char = AsyncMock()
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()
        client.disconnect = AsyncMock()

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(service_info, True)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.select_adapter",
                new=AsyncMock(
                    return_value=AdapterSelectionResult(
                        device=service_info.device,
                        source="proxy_1",
                        rssi=-59,
                        connectable=True,
                        available_sources=["proxy_1 (RSSI: -59)"],
                    )
                ),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.establish_connection",
                new=AsyncMock(return_value=client),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=1,
            ),
        ):
            report = await BLEDiagnosticRunner(
                hass,
                "AA:BB:CC:DD:EE:55",
                capture_duration=0,
            ).run_diagnostics()

        assert report.detection["bed_type"] == BED_TYPE_OKIN_CST
        assert report.detection["supported_match"] is True
        assert "gatt_service:nordic_dfu" in report.detection["signals"]

    async def test_run_diagnostics_reconnects_after_mid_enumeration_disconnect(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """A disconnect during enumeration should reconnect and continue the capture."""
        connectable_info = _build_unknown_service_info(
            source="proxy_1",
            connectable=True,
            rssi=-55,
        )

        service1 = _build_reconnect_test_service()
        char_ok1, char_kill1, _char_after1 = service1.characteristics
        client1 = _build_diagnostic_client(_FakeServices([service1]))

        service2 = _build_reconnect_test_service()
        char_after2 = service2.characteristics[2]
        client2 = _build_diagnostic_client(_FakeServices([service2]))

        async def _read_gatt_char_1(target):
            target_uuid = getattr(target, "uuid", target)
            if target_uuid == char_ok1.uuid:
                return b"\x01"
            if target_uuid == char_kill1.uuid:
                client1.is_connected = False
                raise BleakError("")
            raise BleakError(f"unexpected read on client1: {target_uuid}")

        async def _read_gatt_char_2(target):
            target_uuid = getattr(target, "uuid", target)
            if target_uuid == char_after2.uuid:
                return b"\x02"
            raise BleakError(f"unexpected read on client2: {target_uuid}")

        async def _start_notify_2(target, handler):
            handler(MagicMock(), bytearray(b"OK"))

        client1.read_gatt_char = AsyncMock(side_effect=_read_gatt_char_1)
        client2.read_gatt_char = AsyncMock(side_effect=_read_gatt_char_2)
        client2.start_notify = AsyncMock(side_effect=_start_notify_2)

        establish_mock = AsyncMock(side_effect=[client1, client2])

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(connectable_info, True)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.select_adapter",
                new=AsyncMock(
                    return_value=AdapterSelectionResult(
                        device=connectable_info.device,
                        source="proxy_1",
                        rssi=-55,
                        connectable=True,
                        available_sources=["proxy_1 (RSSI: -55)"],
                    )
                ),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.establish_connection",
                new=establish_mock,
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=1,
            ),
        ):
            report = await BLEDiagnosticRunner(
                hass,
                "AA:BB:CC:DD:EE:FF",
                capture_duration=0,
            ).run_diagnostics()

        assert establish_mock.await_count == 2
        chars = report.gatt_services[0]["characteristics"]
        assert chars[0]["read_result"]["hex"] == "01"
        assert chars[1]["read_error"] == "BleakError"
        assert chars[2]["read_result"]["hex"] == "02"
        assert any("reconnecting" in error for error in report.errors)
        assert chars[0]["notify_subscription"]["success"] is True
        assert report.notifications[0]["data_hex"] == "4f4b"
        client2.stop_notify.assert_awaited()
        client2.disconnect.assert_awaited()

    async def test_run_diagnostics_degrades_gracefully_when_reconnect_fails(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """If the device cannot be reconnected, remaining steps are skipped with clear errors."""
        connectable_info = _build_unknown_service_info(
            source="proxy_1",
            connectable=True,
            rssi=-55,
        )

        service = _build_reconnect_test_service()
        char_ok, char_kill, _char_after = service.characteristics
        client = _build_diagnostic_client(_FakeServices([service]))

        async def _read_gatt_char(target):
            target_uuid = getattr(target, "uuid", target)
            if target_uuid == char_ok.uuid:
                return b"\x01"
            if target_uuid == char_kill.uuid:
                client.is_connected = False
                raise BleakError("")
            raise BleakError(f"unexpected read: {target_uuid}")

        client.read_gatt_char = AsyncMock(side_effect=_read_gatt_char)

        establish_mock = AsyncMock(
            side_effect=[client] + [BleakError("boom")] * 4,
        )

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(connectable_info, True)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.select_adapter",
                new=AsyncMock(
                    return_value=AdapterSelectionResult(
                        device=connectable_info.device,
                        source="proxy_1",
                        rssi=-55,
                        connectable=True,
                        available_sources=["proxy_1 (RSSI: -55)"],
                    )
                ),
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.establish_connection",
                new=establish_mock,
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=1,
            ),
        ):
            report = await BLEDiagnosticRunner(
                hass,
                "AA:BB:CC:DD:EE:FF",
                capture_duration=0,
            ).run_diagnostics()

        chars = report.gatt_services[0]["characteristics"]
        assert chars[0]["read_result"]["hex"] == "01"
        assert chars[1]["read_error"] == "BleakError"
        assert chars[2]["read_error"] == "Skipped: connection lost during service enumeration"
        assert chars[0]["notify_subscription"]["attempted"] is False
        assert report.notifications == []
        assert any(error.startswith("Reconnect failed") for error in report.errors)
        assert any("Skipped notification capture" in error for error in report.errors)

    async def test_run_diagnostics_reconnects_via_coordinator_when_shared_connection_drops(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Diagnostics reusing the coordinator connection should reconnect through it."""
        connectable_info = _build_unknown_service_info(
            source="proxy_1",
            connectable=True,
            rssi=-55,
        )

        service1 = _build_reconnect_test_service()
        char_ok1, char_kill1, _char_after1 = service1.characteristics
        client1 = _build_diagnostic_client(_FakeServices([service1]))

        service2 = _build_reconnect_test_service()
        char_after2 = service2.characteristics[2]
        client2 = _build_diagnostic_client(_FakeServices([service2]))

        coordinator = MagicMock()
        coordinator.client = client1
        coordinator.is_connected = True
        coordinator.connection_source = "proxy_1"
        coordinator.connection_rssi = -55
        coordinator.disable_angle_sensing = False
        coordinator.adapter_details = {}
        coordinator.connection_history = {}
        coordinator.connection_attempt_details = []
        coordinator.command_trace = []

        async def _read_gatt_char_1(target):
            target_uuid = getattr(target, "uuid", target)
            if target_uuid == char_ok1.uuid:
                return b"\x01"
            if target_uuid == char_kill1.uuid:
                # The drop clears the coordinator's client; auto-reconnect has
                # not fired yet when the next read comes around.
                client1.is_connected = False
                coordinator.client = None
                coordinator.is_connected = False
                raise BleakError("")
            raise BleakError(f"unexpected read on client1: {target_uuid}")

        async def _read_gatt_char_2(target):
            target_uuid = getattr(target, "uuid", target)
            if target_uuid == char_after2.uuid:
                return b"\x02"
            raise BleakError(f"unexpected read on client2: {target_uuid}")

        client1.read_gatt_char = AsyncMock(side_effect=_read_gatt_char_1)
        client2.read_gatt_char = AsyncMock(side_effect=_read_gatt_char_2)

        async def _coordinator_reconnect(reset_timer=True):
            coordinator.client = client2
            coordinator.is_connected = True
            return True

        coordinator.async_ensure_connected = AsyncMock(side_effect=_coordinator_reconnect)

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(connectable_info, True)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=1,
            ),
        ):
            report = await BLEDiagnosticRunner(
                hass,
                "AA:BB:CC:DD:EE:FF",
                capture_duration=0,
                coordinator=coordinator,
            ).run_diagnostics()

        coordinator.async_ensure_connected.assert_awaited_once_with(reset_timer=False)
        chars = report.gatt_services[0]["characteristics"]
        assert chars[0]["read_result"]["hex"] == "01"
        assert chars[1]["read_error"] == "BleakError"
        assert chars[2]["read_result"]["hex"] == "02"
        assert any("reconnecting" in error for error in report.errors)
        coordinator.pause_disconnect_timer.assert_called_once()
        coordinator.resume_disconnect_timer.assert_called_once()
        coordinator.set_raw_notify_callback.assert_called_with(None)
        client2.disconnect.assert_not_awaited()


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
        assert report["integration"]["kaidi_product_id"] is None
        assert report["integration"]["kaidi_sofa_acu_no"] is None
        assert report["integration"]["kaidi_adv_type"] is None
        assert report["integration"]["kaidi_resolved_variant"] is None
        assert report["integration"]["kaidi_variant_source"] is None
        assert report["controller"]["initialized"] is False
        assert report["command_trace"] == []
        assert report["bluetooth"]["advertisements_by_source"] == [{"source": "proxy_1"}]
        assert report["connection_attempt_details"][0]["result"] == "connected"

    async def test_generate_support_bundle_configured_device_without_coordinator_keeps_target(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        enable_custom_integrations,
    ):
        """Configured-device bundles should still identify the entry when setup is retrying."""
        del enable_custom_integrations
        diagnostic_report = DiagnosticReport(
            metadata={"version": "2.0"},
            device={
                "address": mock_config_entry.data["address"],
                "selected_source": "proxy_1",
                "actual_source": "proxy_1",
                "scanner_count": 1,
                "visible_sources": ["proxy_1"],
                "non_connectable_fallback_used": False,
            },
            advertisement={"address": mock_config_entry.data["address"], "selected_for_connection": True},
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
                address=mock_config_entry.data["address"],
                capture_duration=0,
                include_logs=False,
                coordinator=None,
                entry=mock_config_entry,
                device_id="retry-device-id",
            )

        assert report["target"]["mode"] == "configured_device"
        assert report["target"]["address"] == mock_config_entry.data["address"]
        assert report["target"]["device_id"] == "retry-device-id"
        assert report["target"]["entry_id"] == mock_config_entry.entry_id
        assert report["target"]["title"] == mock_config_entry.title
        assert report["integration"]["entry_id"] == mock_config_entry.entry_id
        assert report["integration"]["address"] == mock_config_entry.data["address"]
        assert report["controller"]["initialized"] is False
        assert report["command_trace"] == []

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
