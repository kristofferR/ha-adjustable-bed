"""Tests for support bundle generation and enriched diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.ble_diagnostics import (
    BLEDiagnosticRunner,
    DiagnosticReport,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DEVICE_INFO_CHARS,
    DOMAIN,
    LINAK_CONTROL_SERVICE_UUID,
    NORDIC_DFU_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
    SOLACE_SERVICE_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.support_bundle import (
    _build_evidence_summary,
    _build_nearby_device_inventory,
    _build_pairing_assessment,
    _build_scanner_status,
    generate_support_bundle,
)


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


def _build_nearby_service_info(
    *,
    address: str,
    name: str,
    source: str,
    rssi: int,
    service_uuids: list[str] | None = None,
    connectable: bool = True,
) -> SimpleNamespace:
    """Create a nearby-device advertisement for inventory tests."""
    return SimpleNamespace(
        address=address,
        name=name,
        source=source,
        rssi=rssi,
        connectable=connectable,
        service_uuids=service_uuids or [],
        manufacturer_data={},
        service_data={},
    )


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

    async def test_run_diagnostics_initially_connects_through_coordinator(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Configured diagnostics should use pairing and adapter logic from the coordinator."""
        service_info = _build_unknown_service_info(
            source="proxy_1",
            connectable=True,
            rssi=-58,
        )
        client = _build_diagnostic_client(_FakeServices([]))
        coordinator = MagicMock()
        coordinator.client = None
        coordinator.is_connected = False
        coordinator.connection_source = None
        coordinator.connection_rssi = None
        coordinator.disable_angle_sensing = True
        coordinator.adapter_details = {}
        coordinator.connection_history = {}
        coordinator.connection_attempt_details = []
        coordinator.command_trace = []
        coordinator.controller = MagicMock(requires_notification_channel=True)
        coordinator.async_start_notify_for_diagnostics = AsyncMock()

        async def _connect_through_coordinator(*, reset_timer):
            assert reset_timer is False
            coordinator.client = client
            coordinator.is_connected = True
            coordinator.connection_source = "proxy_1"
            coordinator.connection_rssi = -58
            return True

        coordinator.async_ensure_connected = AsyncMock(
            side_effect=_connect_through_coordinator
        )

        with (
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
                return_value=[(service_info, True)],
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.bluetooth.async_scanner_count",
                return_value=1,
            ),
            patch(
                "custom_components.adjustable_bed.ble_diagnostics.select_adapter"
            ) as select_adapter,
        ):
            report = await BLEDiagnosticRunner(
                hass,
                service_info.address,
                capture_duration=0,
                coordinator=coordinator,
            ).run_diagnostics()

        coordinator.async_ensure_connected.assert_awaited_once_with(reset_timer=False)
        select_adapter.assert_not_called()
        assert report.device["connection_path"] == "coordinator_connected_for_diagnostics"
        assert report.device["actual_source"] == "proxy_1"
        coordinator.pause_disconnect_timer.assert_called_once()
        coordinator.resume_disconnect_timer.assert_called_once()
        coordinator.async_start_notify_for_diagnostics.assert_not_called()
        coordinator.controller.stop_notify.assert_not_called()
        client.disconnect.assert_not_awaited()

    async def test_coordinator_attempts_are_retained_before_standalone_fallback(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """A successful raw fallback must not hide the configured connection failure."""
        service_info = _build_unknown_service_info(
            source="proxy_1",
            connectable=True,
            rssi=-61,
        )
        client = _build_diagnostic_client(_FakeServices([]))
        coordinator = MagicMock()
        coordinator.client = None
        coordinator.is_connected = False
        coordinator.entry.data = {CONF_PREFERRED_ADAPTER: "proxy_1"}
        coordinator.adapter_details = {}
        coordinator.connection_history = {}
        coordinator.connection_attempt_details = [
            {
                "attempt": 1,
                "result": "failed",
                "error_category": "PAIRING FAILED",
            }
        ]
        coordinator.command_trace = []
        coordinator.async_ensure_connected = AsyncMock(return_value=False)

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
                        rssi=-61,
                        connectable=True,
                        available_sources=["proxy_1 (RSSI: -61)"],
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
                service_info.address,
                capture_duration=0,
                coordinator=coordinator,
            ).run_diagnostics()

        assert len(report.connection_attempt_details) == 2
        configured_attempt, fallback_attempt = report.connection_attempt_details
        assert configured_attempt["error_category"] == "PAIRING FAILED"
        assert (
            configured_attempt["diagnostic_connection_path"]
            == "configured_coordinator"
        )
        assert fallback_attempt["result"] == "connected"
        assert (
            fallback_attempt["diagnostic_connection_path"]
            == "standalone_after_coordinator_failure"
        )


class TestSupportBundle:
    """Test support bundle orchestration."""

    async def test_nearby_device_inventory_ranks_deduplicates_and_caps(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ):
        """Nearby inventory should favor likely beds, then strong advertisements."""
        del enable_custom_integrations
        nearby = [
            _build_nearby_service_info(
                address=f"02:00:00:00:00:{index:02X}",
                name=f"Nearby {index:02d}",
                source="proxy_1",
                rssi=-20 - index,
            )
            for index in range(35)
        ]
        nearby.extend(
            [
                _build_nearby_service_info(
                    address="AA:BB:CC:DD:EE:FF",
                    name="RC2 Left",
                    source="proxy_1",
                    rssi=-95,
                    service_uuids=[SOLACE_SERVICE_UUID],
                ),
                _build_nearby_service_info(
                    address="AA:BB:CC:DD:EE:FF",
                    name="RC2 Left",
                    source="proxy_2",
                    rssi=-40,
                    service_uuids=[SOLACE_SERVICE_UUID],
                ),
            ]
        )

        with patch(
            "custom_components.adjustable_bed.support_bundle.get_discovered_service_info",
            return_value=nearby,
        ):
            inventory = _build_nearby_device_inventory(
                hass,
                target_address="02:00:00:00:00:00",
            )

        assert inventory["limit"] == 30
        assert inventory["total_visible"] == 36
        assert inventory["included"] == 30
        assert inventory["truncated"] is True
        assert len(inventory["devices"]) == 30
        assert [device["rank"] for device in inventory["devices"]] == list(range(1, 31))

        likely_bed = inventory["devices"][0]
        assert likely_bed["address"] == "AA:BB:CC:DD:EE:FF"
        assert likely_bed["detection"]["bed_type"] == "octo"
        assert likely_bed["detection"]["supported_match"] is True
        assert likely_bed["rssi"] == -40
        assert likely_bed["source_count"] == 2
        assert likely_bed["sources"][0]["source"] == "proxy_2"

        strongest_unknown = inventory["devices"][1]
        assert strongest_unknown["address"] == "02:00:00:00:00:00"
        assert strongest_unknown["is_target"] is True
        assert strongest_unknown["rssi"] == -20
        assert all(device["address"] != "02:00:00:00:00:22" for device in inventory["devices"])

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
        assert report["metadata"]["report_version"] == "2.2"
        assert report["integration"]["configured_device"] is False
        assert report["integration"]["kaidi_product_id"] is None
        assert report["integration"]["kaidi_sofa_acu_no"] is None
        assert report["integration"]["kaidi_adv_type"] is None
        assert report["integration"]["kaidi_resolved_variant"] is None
        assert report["integration"]["kaidi_variant_source"] is None
        assert report["controller"]["initialized"] is False
        assert report["command_trace"] == []
        assert report["bluetooth"]["advertisements_by_source"] == [{"source": "proxy_1"}]
        assert report["bluetooth"]["nearby_devices"]["limit"] == 30
        assert report["bluetooth"]["nearby_devices"]["devices"] == []
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

    async def test_pairing_section_distinguishes_marker_from_backend_bond(
        self,
        hass: HomeAssistant,
        enable_custom_integrations,
    ) -> None:
        """Bundles should expose persisted and backend bond state independently."""
        del enable_custom_integrations
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Smart Bed 22D8",
            data={
                CONF_ADDRESS: "08:3A:F2:1E:4B:7E",
                CONF_NAME: "Smart Bed 22D8",
                CONF_BED_TYPE: BED_TYPE_LEGGETT_GEN2,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_BLE_BOND_ESTABLISHED: True,
            },
            unique_id="08:3A:F2:1E:4B:7E",
            entry_id="leggett_pairing_diagnostics",
        )
        entry.add_to_hass(hass)
        diagnostic_report = DiagnosticReport(
            metadata={"version": "2.0"},
            device={
                "address": "08:3A:F2:1E:4B:7E",
                "pairing": {
                    "paired": False,
                    "bonded": False,
                    "trusted": False,
                    "address_type": "public",
                },
            },
            advertisement={},
            advertisements_by_source=[],
            detection={"bed_type": BED_TYPE_LEGGETT_GEN2, "supported_match": True},
            gatt_services=[],
            gatt_summary={"available": False, "service_count": 0},
            device_information={},
            notifications=[],
            notification_summary={"total_notifications": 0, "by_characteristic": {}},
            adapter_details={},
            connection_history={},
            connection_attempt_details=[{"attempt": 1, "result": "failed"}],
            command_trace=[],
            errors=["Failed to connect"],
        )

        with (
            patch.object(
                BLEDiagnosticRunner,
                "run_diagnostics",
                new=AsyncMock(return_value=diagnostic_report),
            ),
            patch(
                "custom_components.adjustable_bed.support_bundle.bluetooth.async_current_scanners",
                return_value=[],
            ),
        ):
            report = await generate_support_bundle(
                hass,
                address="08:3A:F2:1E:4B:7E",
                capture_duration=0,
                include_logs=False,
                coordinator=None,
                entry=entry,
                device_id="leggett-device-id",
            )

        pairing = report["pairing"]
        assert report["metadata"]["report_version"] == "2.2"
        assert pairing["required"] is True
        assert pairing["connection_gated_by_bond"] is True
        assert pairing["persisted_bond_marker"] is True
        assert pairing["runtime_bond_established"] is None
        assert pairing["diagnostic_backend"]["paired"] is False
        assert pairing["diagnostic_backend"]["bonded"] is False

    async def test_scanner_status_includes_esphome_proxy_runtime_and_slots(
        self,
        hass: HomeAssistant,
    ):
        """Proxy rows should expose firmware, API, availability, and BLE slot health."""
        runtime = SimpleNamespace(
            available=True,
            api_version=SimpleNamespace(major=1, minor=12),
            device_info=SimpleNamespace(
                name="bed_proxy",
                friendly_name="Bed Proxy",
                model="ESP32-C3",
                manufacturer="Espressif",
                esphome_version="2026.7.1",
                compilation_time="2026-07-10 12:00:00",
                project_name="esphome.bluetooth-proxy",
                project_version="1.0",
                bluetooth_mac_address="11:22:33:44:55:66",
                bluetooth_proxy_feature_flags=0x0F,
            ),
            bluetooth_device=SimpleNamespace(
                available=True,
                ble_connections_free=2,
                ble_connections_limit=3,
            ),
        )
        proxy_entry = MockConfigEntry(
            domain="esphome",
            title="Bed Proxy",
            data={},
            entry_id="esphome_proxy_entry",
        )
        proxy_entry.runtime_data = runtime
        proxy_entry.add_to_hass(hass)
        bluetooth_entry = MockConfigEntry(
            domain="bluetooth",
            title="Bed Proxy Bluetooth",
            data={
                "source": "11:22:33:44:55:66",
                "source_domain": "esphome",
                "source_model": "ESP32-C3",
                "source_config_entry_id": proxy_entry.entry_id,
                "source_device_id": "proxy-device-id",
            },
            unique_id="11:22:33:44:55:66",
        )
        bluetooth_entry.add_to_hass(hass)

        scanner = MagicMock()
        scanner.source = "11:22:33:44:55:66"
        scanner.name = "bed-proxy"
        scanner.scanning = True
        scanner.connectable = True
        scanner.connector = MagicMock()
        scanner.current_mode = "active"
        scanner.requested_mode = "active"
        scanner.connecting_count = 1
        scanner.connections_in_progress = 1
        scanner.connection_failures = 0
        scanner.details = {"source": scanner.source, "type": "ESPHomeScanner"}
        scanner.async_diagnostics = AsyncMock(
            return_value={
                "scanner_state": "running",
                "discovered_devices_and_advertisement_data": {"omitted": True},
            }
        )

        with patch(
            "custom_components.adjustable_bed.support_bundle.bluetooth.async_current_scanners",
            return_value=[scanner],
        ):
            rows = await _build_scanner_status(
                hass,
                [
                    {
                        "source": scanner.source,
                        "rssi": -71,
                        "connectable": True,
                        "selected_for_connection": True,
                    }
                ],
            )

        assert len(rows) == 1
        row = rows[0]
        assert row["scanner_type"] == "esphome_proxy"
        assert row["target_visible"] is True
        assert row["target_rssi"] == -71
        assert row["diagnostics"] == {"scanner_state": "running"}
        proxy = row["esphome_proxy"]
        assert proxy["available"] is True
        assert proxy["api_version"] == {"major": 1, "minor": 12}
        assert proxy["device"]["esphome_version"] == "2026.7.1"
        assert proxy["device"]["pairing_supported"] is True
        assert proxy["bluetooth"]["connections_free"] == 2
        assert proxy["bluetooth"]["connections_limit"] == 3

    def test_pairing_and_evidence_call_out_stale_bond_and_missing_reproduction(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Bundles should explain contradictory bond state and missing evidence."""
        hass.config_entries.async_update_entry(
            mock_config_entry,
            data={
                **mock_config_entry.data,
                CONF_BED_TYPE: BED_TYPE_OKIN_CST,
                CONF_PREFERRED_ADAPTER: "proxy_1",
                CONF_BLE_BOND_ESTABLISHED: True,
            },
        )
        diagnostics = {
            "detection": {"bed_type": BED_TYPE_OKIN_CST},
            "device": {
                "selected_source": "proxy_1",
                "actual_source": "proxy_1",
                "pairing": {"paired": None, "bonded": None},
            },
            "gatt_services": [
                {
                    "uuid": "0000180a-0000-1000-8000-00805f9b34fb",
                    "characteristics": [
                        {
                            "uuid": DEVICE_INFO_CHARS["model_number"],
                            "handle": 24,
                            "read_result": None,
                            "read_error": (
                                "Bluetooth GATT Error handle=24 error=5 "
                                "description=Insufficient authentication"
                            ),
                        }
                    ],
                }
            ],
            "command_trace": [{"command_origin": "query_config"}],
            "notification_summary": {"total_notifications": 0},
        }
        pairing = _build_pairing_assessment(
            diagnostics,
            entry=mock_config_entry,
            coordinator=SimpleNamespace(pairing_supported=True),
        )

        evidence = _build_evidence_summary(
            capture_duration=120,
            include_logs=True,
            recent_logs=[
                {
                    "timestamp": "2026-07-12T00:00:00+00:00",
                    "level": "INFO",
                    "name": "adjustable_bed",
                    "message": "Could not read /config/home-assistant.log: missing",
                }
            ],
            diagnostic_report=diagnostics,
            reproduction_command_trace=[],
            pairing=pairing,
            bluetooth_info={"scanners": []},
            configured=True,
            controller={"initialized": False},
        )

        assert pairing["status"] == "authentication_failed"
        assert pairing["configured_bond_conflicts_with_capture"] is True
        assert pairing["source"]["matches_preference"] is True
        assert evidence["command_trace_count"] == 1
        assert evidence["reproduction_command_trace_count"] == 0
        assert evidence["non_reproduction_command_trace_count"] == 1
        assert evidence["notification_count"] == 0
        assert evidence["log_capture_status"] == "unavailable"
        assert evidence["complete"] is False
        assert any("saved bond marker" in warning for warning in evidence["warnings"])
        assert any("No user command reproduction" in warning for warning in evidence["warnings"])

        raw_auth_failure = _build_pairing_assessment(
            {
                **diagnostics,
                "detection": {"bed_type": "linak"},
            },
            entry=None,
            coordinator=None,
        )
        assert raw_auth_failure["required"] is False
        assert raw_auth_failure["status"] == "authentication_failed"

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
        assert trace[-1]["operation_name"] is None

        async def _user_command(active_controller):
            await active_controller.write_command(b"\x03\x04")

        await coordinator.async_execute_controller_command(_user_command)
        assert coordinator.command_trace[-1]["operation_name"] == "command"
