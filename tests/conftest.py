"""Fixtures for Adjustable Bed tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Enable custom component loading
pytest_plugins = "pytest_homeassistant_custom_component"

# Re-export enable_custom_integrations fixture so it's available in tests
from pytest_homeassistant_custom_component.plugins import enable_custom_integrations  # noqa: F401

from custom_components.adjustable_bed.const import (
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
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
    KEESON_BASE_SERVICE_UUID,
    LEGGETT_GEN2_SERVICE_UUID,
    LINAK_CONTROL_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SOLACE_SERVICE_UUID,
)

# Test constants
TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"
TEST_NAME = "Test Bed"


@pytest.fixture
def mock_config_entry_data() -> dict:
    """Return mock config entry data."""
    return {
        CONF_ADDRESS: TEST_ADDRESS,
        CONF_NAME: TEST_NAME,
        CONF_BED_TYPE: BED_TYPE_LINAK,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_config_entry(hass: HomeAssistant, mock_config_entry_data: dict) -> MockConfigEntry:
    """Return a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data=mock_config_entry_data,
        unique_id=TEST_ADDRESS,
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_bleak_client() -> MagicMock:
    """Mock BleakClient."""
    from bleak import BleakClient

    client = MagicMock(spec=BleakClient)
    client.is_connected = True
    client.address = TEST_ADDRESS
    client.mtu_size = 23
    client.services = MagicMock()
    client.services.__iter__ = lambda self: iter([])
    client.services.__len__ = lambda self: 0
    # Return None for service lookups to avoid false positives in variant detection
    client.services.get_service = MagicMock(return_value=None)

    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()

    return client


@pytest.fixture
def mock_bluetooth_service_info() -> MagicMock:
    """Return mock Bluetooth service info for a Linak bed."""
    service_info = MagicMock()
    service_info.name = TEST_NAME
    service_info.address = TEST_ADDRESS
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [LINAK_CONTROL_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_unknown() -> MagicMock:
    """Return mock Bluetooth service info for an unknown device."""
    service_info = MagicMock()
    service_info.name = "Unknown Device"
    service_info.address = "11:22:33:44:55:66"
    service_info.rssi = -70
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = ["00001800-0000-1000-8000-00805f9b34fb"]  # Generic Access
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_richmat() -> MagicMock:
    """Return mock Bluetooth service info for a Richmat bed (Nordic variant)."""
    service_info = MagicMock()
    service_info.name = "Richmat Bed"
    service_info.address = "22:33:44:55:66:77"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [RICHMAT_NORDIC_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_richmat_wilinke() -> MagicMock:
    """Return mock Bluetooth service info for a Richmat bed (WiLinke variant)."""
    service_info = MagicMock()
    service_info.name = "Richmat WiLinke"
    service_info.address = "33:44:55:66:77:88"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [RICHMAT_WILINKE_SERVICE_UUIDS[0]]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_keeson() -> MagicMock:
    """Return mock Bluetooth service info for a Keeson bed."""
    service_info = MagicMock()
    service_info.name = "Keeson Bed"
    service_info.address = "44:55:66:77:88:99"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [KEESON_BASE_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_solace() -> MagicMock:
    """Return mock Bluetooth service info for a Solace bed."""
    service_info = MagicMock()
    service_info.name = "Solace Bed"
    service_info.address = "55:66:77:88:99:AA"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [SOLACE_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_motosleep() -> MagicMock:
    """Return mock Bluetooth service info for a MotoSleep bed (HHC controller)."""
    service_info = MagicMock()
    service_info.name = "HHC3611243CDEF"  # Name starts with HHC
    service_info.address = "66:77:88:99:AA:BB"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [SOLACE_SERVICE_UUID]  # Same UUID as Solace
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_leggett() -> MagicMock:
    """Return mock Bluetooth service info for a Leggett & Platt bed (Gen2)."""
    service_info = MagicMock()
    service_info.name = "Leggett Bed"
    service_info.address = "77:88:99:AA:BB:CC"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [LEGGETT_GEN2_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_reverie() -> MagicMock:
    """Return mock Bluetooth service info for a Reverie bed."""
    service_info = MagicMock()
    service_info.name = "Reverie Bed"
    service_info.address = "88:99:AA:BB:CC:DD"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [REVERIE_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_okimat() -> MagicMock:
    """Return mock Bluetooth service info for an Okimat bed."""
    service_info = MagicMock()
    service_info.name = "Okimat Bed"
    service_info.address = "99:AA:BB:CC:DD:EE"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [OKIMAT_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_establish_connection(mock_bleak_client: MagicMock) -> Generator[AsyncMock, None, None]:
    """Mock bleak_retry_connector.establish_connection."""
    with patch(
        "custom_components.adjustable_bed.coordinator.establish_connection",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = mock_bleak_client
        yield mock


@pytest.fixture
def mock_async_ble_device_from_address() -> Generator[MagicMock, None, None]:
    """Mock bluetooth.async_ble_device_from_address."""
    with patch(
        "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address"
    ) as mock:
        device = MagicMock()
        device.address = TEST_ADDRESS
        device.name = TEST_NAME
        device.details = {"source": "local"}
        mock.return_value = device
        yield mock


@pytest.fixture
def mock_bluetooth_adapters() -> Generator[None, None, None]:
    """Mock bluetooth adapter functions."""
    patches = [
        patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_scanner_count",
            return_value=1,
        ),
        patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_last_service_info",
            return_value=None,
        ),
        patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_register_connection_params",
            create=True,  # Allow patching even if attribute doesn't exist
        ),
    ]

    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def mock_coordinator_connected(
    mock_establish_connection: AsyncMock,
    mock_async_ble_device_from_address: MagicMock,
    mock_bluetooth_adapters: None,
) -> Generator[None, None, None]:
    """Provide all mocks needed for a connected coordinator."""
    yield


@pytest.fixture
def mock_bluetooth_service_info_ergomotion() -> MagicMock:
    """Return mock Bluetooth service info for an Ergomotion bed."""
    service_info = MagicMock()
    service_info.name = "Ergomotion Bed"
    service_info.address = "AA:00:11:22:33:44"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = []
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_jiecang() -> MagicMock:
    """Return mock Bluetooth service info for a Jiecang bed."""
    service_info = MagicMock()
    service_info.name = "JC-35TK1WT"  # Typical Jiecang name
    service_info.address = "BB:00:11:22:33:44"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = []
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_dewertokin() -> MagicMock:
    """Return mock Bluetooth service info for a DewertOkin bed."""
    service_info = MagicMock()
    service_info.name = "A H Beard Bed"  # A H Beard uses DewertOkin
    service_info.address = "CC:00:11:22:33:44"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = []
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_serta() -> MagicMock:
    """Return mock Bluetooth service info for a Serta bed."""
    service_info = MagicMock()
    service_info.name = "Serta Motion Perfect"
    service_info.address = "DD:00:11:22:33:44"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = []
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_octo() -> MagicMock:
    """Return mock Bluetooth service info for an Octo bed."""
    service_info = MagicMock()
    service_info.name = "Octo Smart Bed"
    service_info.address = "EE:00:11:22:33:44"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [SOLACE_SERVICE_UUID]  # Shares UUID with Solace
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_octo_star2() -> MagicMock:
    """Return mock Bluetooth service info for an Octo Star2 bed."""
    service_info = MagicMock()
    service_info.name = "Star2 Bed"  # Name doesn't contain "octo"
    service_info.address = "FF:00:11:22:33:44"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [OCTO_STAR2_SERVICE_UUID]  # Detected by service UUID
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info
