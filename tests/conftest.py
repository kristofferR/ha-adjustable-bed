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
from pytest_homeassistant_custom_component.plugins import (  # noqa: E402
    enable_custom_integrations,  # noqa: F401
)

from custom_components.adjustable_bed.const import (  # noqa: E402
    BED_TYPE_LINAK,
    BEDTECH_SERVICE_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    JENSEN_SERVICE_UUID,
    KEESON_BASE_SERVICE_UUID,
    LEGGETT_GEN2_SERVICE_UUID,
    LINAK_CONTROL_SERVICE_UUID,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    REMACRO_SERVICE_UUID,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RONDURE_SERVICE_UUID,
    SOLACE_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
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
    client.read_gatt_char = AsyncMock(return_value=b"")
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
def mock_establish_connection(mock_bleak_client: MagicMock) -> Generator[AsyncMock]:
    """Mock bleak_retry_connector.establish_connection."""
    with patch(
        "custom_components.adjustable_bed.coordinator.establish_connection",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = mock_bleak_client
        yield mock


@pytest.fixture
def mock_async_ble_device_from_address() -> Generator[MagicMock]:
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
def mock_bluetooth_adapters() -> Generator[None]:
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
) -> None:
    """Provide all mocks needed for a connected coordinator.

    The fixture parameters are used for dependency injection only - pytest activates
    these fixtures when mock_coordinator_connected is used, even though the parameters
    aren't accessed directly in this function body.
    """
    # Fixtures are activated via dependency injection - no explicit usage needed
    del mock_establish_connection, mock_async_ble_device_from_address, mock_bluetooth_adapters
    return None


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
def mock_bluetooth_service_info_octo_rc2() -> MagicMock:
    """Return mock Bluetooth service info for an Octo RC2 receiver.

    This tests the scenario from issue #73 where devices named "RC2"
    should be detected as Octo (not Solace) since they share the same UUID.
    """
    service_info = MagicMock()
    service_info.name = "RC2"
    service_info.address = "EE:00:11:22:33:55"
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
def mock_bluetooth_service_info_solace() -> MagicMock:
    """Return mock Bluetooth service info for a Solace bed.

    This tests that devices with "solace" in the name are correctly
    detected as Solace (not Octo) even though they share the same UUID.
    """
    service_info = MagicMock()
    service_info.name = "Solace Smart Bed"
    service_info.address = "EE:00:11:22:33:66"
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
def mock_bluetooth_service_info_solace_pattern() -> MagicMock:
    """Return mock Bluetooth service info for a Solace bed with pattern name.

    Solace devices use naming convention like "S4-Y-192-461000AD".
    """
    service_info = MagicMock()
    service_info.name = "S4-Y-192-461000AD"
    service_info.address = "EE:00:11:22:33:77"
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


@pytest.fixture
def mock_bluetooth_service_info_leggett_platt_richmat() -> MagicMock:
    """Return mock Bluetooth service info for a Leggett & Platt MlRM variant bed.

    These beds use Richmat WiLinke hardware with the "MlRM" name prefix.
    They are detected as BED_TYPE_LEGGETT_PLATT; variant (mlrm) is detected
    at controller instantiation time based on the WiLinke service UUID.
    """
    service_info = MagicMock()
    service_info.name = "MlRM157052"  # Name starts with MlRM prefix
    service_info.address = "FF:11:22:33:44:55"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [RICHMAT_WILINKE_SERVICE_UUIDS[1]]  # fee9 UUID
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_jensen() -> MagicMock:
    """Return mock Bluetooth service info for a Jensen bed."""
    service_info = MagicMock()
    service_info.name = "JMC400"
    service_info.address = "11:22:33:44:55:66"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [JENSEN_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_vibradorm() -> MagicMock:
    """Return mock Bluetooth service info for a Vibradorm bed."""
    service_info = MagicMock()
    service_info.name = "VMAT12345"
    service_info.address = "22:33:44:55:66:77"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [VIBRADORM_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_svane() -> MagicMock:
    """Return mock Bluetooth service info for a Svane bed."""
    service_info = MagicMock()
    service_info.name = "Svane Bed"
    service_info.address = "33:44:55:66:77:88"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [SVANE_HEAD_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_malouf() -> MagicMock:
    """Return mock Bluetooth service info for a Malouf NEW_OKIN bed."""
    service_info = MagicMock()
    service_info.name = "Malouf Base"
    service_info.address = "44:55:66:77:88:99"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_sleepys() -> MagicMock:
    """Return mock Bluetooth service info for a Sleepy's Elite bed (BOX15, FFE5)."""
    service_info = MagicMock()
    service_info.name = "Sleepy's Elite"
    service_info.address = "55:66:77:88:99:AA"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [KEESON_BASE_SERVICE_UUID]  # FFE5 for BOX15
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_bedtech() -> MagicMock:
    """Return mock Bluetooth service info for a BedTech bed."""
    service_info = MagicMock()
    service_info.name = "BedTech Comfort"
    service_info.address = "66:77:88:99:AA:BB"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [BEDTECH_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_rondure() -> MagicMock:
    """Return mock Bluetooth service info for a Rondure/1500 Tilt Base bed."""
    service_info = MagicMock()
    service_info.name = "1500 Tilt Base"
    service_info.address = "77:88:99:AA:BB:CC"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [RONDURE_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_remacro() -> MagicMock:
    """Return mock Bluetooth service info for a Remacro/CheersSleep bed."""
    service_info = MagicMock()
    service_info.name = "CheersSleep Base"
    service_info.address = "88:99:AA:BB:CC:DD"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [REMACRO_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_reverie_nightstand() -> MagicMock:
    """Return mock Bluetooth service info for a Reverie Nightstand bed."""
    service_info = MagicMock()
    service_info.name = "Reverie Nightstand"
    service_info.address = "99:AA:BB:CC:DD:EE"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [REVERIE_NIGHTSTAND_SERVICE_UUID]
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info


@pytest.fixture
def mock_bluetooth_service_info_ambiguous_okin() -> MagicMock:
    """Return mock Bluetooth service info for ambiguous OKIN detection.

    Uses the OKIN service UUID (62741523) with a generic name, which triggers
    the disambiguation flow since this UUID is shared by Okimat, Leggett Okin,
    and OKIN 64-bit beds.
    """
    service_info = MagicMock()
    service_info.name = "Smart Bed Controller"  # Generic name, not matching any pattern
    service_info.address = "AA:BB:CC:DD:EE:00"
    service_info.rssi = -60
    service_info.manufacturer_data = {}
    service_info.service_data = {}
    service_info.service_uuids = [OKIMAT_SERVICE_UUID]  # 62741523 - shared by multiple types
    service_info.source = "local"
    service_info.device = MagicMock()
    service_info.advertisement = MagicMock()
    service_info.connectable = True
    service_info.time = 0
    service_info.tx_power = None
    return service_info
