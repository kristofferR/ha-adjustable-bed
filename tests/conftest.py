"""Fixtures for Adjustable Bed tests."""

from __future__ import annotations

import binascii
import json
import struct
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
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_FEET_UUID,
    LINAK_POSITION_HEAD_UUID,
    LINAK_POSITION_LEG_UUID,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    REMACRO_SERVICE_UUID,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RONDURE_SERVICE_UUID,
    SLEEP_NUMBER_MCR_RX_CHAR_UUID,
    SLEEP_NUMBER_MCR_TX_CHAR_UUID,
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

    mcr_sync = b"\x16\x16"
    sleep_number_preamble = b"fUzIoN"
    client = MagicMock(spec=BleakClient)
    notify_callbacks: dict[str, object] = {}
    readable_values: dict[str, bytes] = {}
    sleep_number_state: dict[str, object] = {
        "underbed_light_level": "high",
        "underbed_light_timer": 15,
        "left": {
            "sleep_number": 45,
            "bed_presence": "in",
            "footwarming_present": True,
            "footwarming_level": "medium",
            "footwarming_remaining": 90,
            "footwarming_total": 120,
            "frosty_present": True,
            "frosty_mode": "cooling_pull_low",
            "frosty_remaining": 120,
            "heidi_present": True,
            "heidi_mode": "heating_push_low",
            "heidi_remaining": 120,
        },
        "right": {
            "sleep_number": 65,
            "bed_presence": "out",
            "footwarming_present": True,
            "footwarming_level": "off",
            "footwarming_remaining": 0,
            "footwarming_total": 0,
            "frosty_present": True,
            "frosty_mode": "off",
            "frosty_remaining": 0,
            "heidi_present": True,
            "heidi_mode": "off",
            "heidi_remaining": 0,
        },
    }
    sleep_number_mcr_state = {
        "left_sleep_number": 35,
        "right_sleep_number": 65,
        "underbed_light_on": True,
        # 0.4.x BAM firmware on the tested i8 returns only 4 bytes here.
        "chamber_payload": b"\x01\x00\x00\x00",
    }

    def _build_sleep_number_blob(payload: str) -> bytes:
        encoded = payload.encode("utf-8")
        total_length = len(sleep_number_preamble) + 4 + len(encoded) + 4
        header = sleep_number_preamble + struct.pack("<I", total_length)
        checksum = binascii.crc32(header + encoded) & 0xFFFFFFFF
        return header + encoded + struct.pack("<I", checksum)

    def _mcr_crc(data: bytes) -> int:
        s, r = 0, 0
        for value in data:
            s += value
            r += s
        return r & 0xFFFF

    def _build_mcr_frame(
        *,
        command_type: int,
        target: int,
        sub_address: int,
        status: int,
        echo: int,
        function_code: int,
        side: int,
        payload: bytes = b"",
    ) -> bytes:
        header = bytes(
            [
                command_type,
                (target >> 8) & 0xFF,
                target & 0xFF,
                (sub_address >> 8) & 0xFF,
                sub_address & 0xFF,
                status,
                (echo >> 8) & 0xFF,
                echo & 0xFF,
                function_code,
                ((side & 0x0F) << 4) | (len(payload) & 0x0F),
            ]
        )
        body = header + payload
        return mcr_sync + body + struct.pack(">H", _mcr_crc(body))

    def _parse_mcr_frame(data: bytes) -> dict[str, int | bytes] | None:
        if len(data) < 14 or not data.startswith(mcr_sync):
            return None

        body = data[2:-2]
        payload_length = body[9] & 0x0F
        if len(data) != 14 + payload_length:
            return None
        if struct.unpack(">H", data[-2:])[0] != _mcr_crc(body):
            return None

        return {
            "command_type": body[0],
            "target": (body[1] << 8) | body[2],
            "sub_address": (body[3] << 8) | body[4],
            "status": body[5],
            "echo": (body[6] << 8) | body[7],
            "function_code": body[8] & 0x7F,
            "side": (body[9] >> 4) & 0x0F,
            "payload": body[10 : 10 + payload_length],
        }

    def _build_mcr_response(request: dict[str, int | bytes]) -> bytes | None:
        function_code = int(request["function_code"])
        side = int(request["side"])
        payload = bytes(request["payload"])

        response_payload = b""
        if function_code in {0, 2, 21}:
            pass
        elif function_code == 17:
            if len(payload) >= 2:
                value = payload[1]
                if side == 0:
                    sleep_number_mcr_state["left_sleep_number"] = value
                elif side == 1:
                    sleep_number_mcr_state["right_sleep_number"] = value
        elif function_code == 18:
            response_payload = bytes(
                [
                    1,
                    int(sleep_number_mcr_state["left_sleep_number"]),
                    int(sleep_number_mcr_state["right_sleep_number"]),
                    0,
                    0,
                ]
            )
        elif function_code == 19:
            if payload:
                sleep_number_mcr_state["underbed_light_on"] = bool(payload[0])
        elif function_code == 20:
            response_payload = bytes([1 if sleep_number_mcr_state["underbed_light_on"] else 0])
        elif function_code == 97:
            response_payload = bytes(sleep_number_mcr_state["chamber_payload"])
        else:
            return None

        # Echo the request's address fields back so this mock actually
        # exercises the controller's target/echo encoding. Hard-coding
        # ``mcr_bed_address`` would mask any controller bug that mis-encoded
        # the bed-address derived from the BLE MAC.
        request_target = int(request["target"])
        request_echo = int(request["echo"])
        return _build_mcr_frame(
            command_type=1,
            target=request_target,
            sub_address=int(request["sub_address"]),
            status=int(request["status"]),
            echo=request_echo if request_echo else request_target,
            function_code=function_code | 0x80,
            side=side,
            payload=response_payload,
        )

    def _decode_sleep_number_payload(data: bytes) -> str | None:
        if data.startswith(sleep_number_preamble):
            total_length = struct.unpack("<I", data[6:10])[0]
            if total_length != len(data):
                return None
            expected_crc = struct.unpack("<I", data[-4:])[0]
            if binascii.crc32(data[:-4]) & 0xFFFFFFFF != expected_crc:
                return None
            return data[10:-4].decode("utf-8", errors="ignore").strip()

        decoded = data.decode("utf-8", errors="ignore").strip()
        return decoded or None

    client.is_connected = True
    client.address = TEST_ADDRESS
    client.mtu_size = 23
    client.services = MagicMock()
    client.services.__iter__ = lambda self: iter([])
    client.services.__len__ = lambda self: 0
    # Return None for service lookups to avoid false positives in variant detection
    client.services.get_service = MagicMock(return_value=None)

    # Seed Linak position characteristics so startup hydration succeeds when
    # angle sensing is enabled in entity/config-flow tests.
    for linak_position_uuid in (
        LINAK_POSITION_BACK_UUID,
        LINAK_POSITION_LEG_UUID,
        LINAK_POSITION_HEAD_UUID,
        LINAK_POSITION_FEET_UUID,
    ):
        readable_values[linak_position_uuid] = b"\x00\x00"

    async def _start_notify(char_uuid: str, callback) -> None:
        notify_callbacks[char_uuid] = callback

    async def _stop_notify(char_uuid: str) -> None:
        notify_callbacks.pop(char_uuid, None)

    async def _write_gatt_char(char_uuid: str, data: bytes, response: bool = False) -> None:
        del response
        if str(char_uuid) == SLEEP_NUMBER_MCR_RX_CHAR_UUID:
            request = _parse_mcr_frame(data)
            callback = notify_callbacks.get(SLEEP_NUMBER_MCR_TX_CHAR_UUID)
            if request is None or callback is None:
                return
            response_frame = _build_mcr_response(request)
            if response_frame is None:
                return
            if len(response_frame) > 20:
                callback(SLEEP_NUMBER_MCR_TX_CHAR_UUID, bytearray(response_frame[:20]))
                callback(SLEEP_NUMBER_MCR_TX_CHAR_UUID, bytearray(response_frame[20:]))
                return
            callback(SLEEP_NUMBER_MCR_TX_CHAR_UUID, bytearray(response_frame))
            return

        decoded_payload = _decode_sleep_number_payload(data)
        callback = notify_callbacks.get(char_uuid)
        if decoded_payload is None:
            return

        response_text: str | None = None
        if decoded_payload == "UBLG":
            response_text = (
                "PASS:"
                f"{sleep_number_state['underbed_light_level']} "
                f"{sleep_number_state['underbed_light_timer']}"
            )
        elif decoded_payload.startswith("UBLS "):
            _, level, timer = decoded_payload.split(" ", maxsplit=2)
            sleep_number_state["underbed_light_level"] = level
            sleep_number_state["underbed_light_timer"] = int(timer)
            response_text = "PASS:ACK"
        elif decoded_payload.startswith("PSNG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = f"PASS:{side_state['sleep_number']}"
        elif decoded_payload.startswith("PSNS "):
            _, side, value = decoded_payload.split(" ", maxsplit=2)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            side_state["sleep_number"] = int(value)
            response_text = "PASS:ACK"
        elif decoded_payload.startswith("FWPG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = "PASS:true" if side_state["footwarming_present"] else "PASS:false"
        elif decoded_payload.startswith("FWTG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = (
                "PASS:"
                f"{side_state['footwarming_level']} "
                f"{side_state['footwarming_remaining']} "
                f"{side_state['footwarming_total']}"
            )
        elif decoded_payload.startswith("FWTS "):
            _, side, level, timer = decoded_payload.split(" ", maxsplit=3)
            timer_minutes = int(timer)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            side_state["footwarming_level"] = level
            side_state["footwarming_remaining"] = 0 if level == "off" else timer_minutes
            side_state["footwarming_total"] = 0 if level == "off" else timer_minutes
            response_text = "PASS:ACK"
        elif decoded_payload.startswith("CLPG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = "PASS:true" if side_state["frosty_present"] else "PASS:false"
        elif decoded_payload.startswith("CLMG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = f"PASS:{side_state['frosty_mode']} {side_state['frosty_remaining']}"
        elif decoded_payload.startswith("CLMS "):
            _, side, mode, timer = decoded_payload.split(" ", maxsplit=3)
            timer_minutes = int(timer)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            side_state["frosty_mode"] = mode
            side_state["frosty_remaining"] = 0 if mode == "off" else timer_minutes
            response_text = "PASS:ACK"
        elif decoded_payload.startswith("THPG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = "PASS:true" if side_state["heidi_present"] else "PASS:false"
        elif decoded_payload.startswith("THMG "):
            _, side = decoded_payload.split(" ", maxsplit=1)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            response_text = f"PASS:{side_state['heidi_mode']} {side_state['heidi_remaining']}"
        elif decoded_payload.startswith("THMS "):
            _, side, mode, timer = decoded_payload.split(" ", maxsplit=3)
            timer_minutes = int(timer)
            side_state = sleep_number_state[side]
            assert isinstance(side_state, dict)
            side_state["heidi_mode"] = mode
            side_state["heidi_remaining"] = 0 if mode == "off" else timer_minutes
            response_text = "PASS:ACK"
        elif decoded_payload.startswith("BAMG "):
            payload = decoded_payload.removeprefix("BAMG ").strip()
            queries = json.loads(payload)
            grouped_values: list[str] = []
            for query in queries:
                if query["bamkey"] != "LBPG":
                    grouped_values.append("FAIL:0")
                    continue
                side = query["args"]
                side_state = sleep_number_state[side]
                assert isinstance(side_state, dict)
                grouped_values.append(f"PASS:{side_state['bed_presence']}")
            response_text = f"PASS:{json.dumps(grouped_values, separators=(',', ':'))}"

        if response_text is None:
            return

        response_payload = _build_sleep_number_blob(response_text)
        readable_values[char_uuid] = response_payload
        if callback is not None:
            callback(char_uuid, bytearray(response_payload))

    async def _read_gatt_char(target) -> bytes:
        return readable_values.get(str(target), b"")

    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.write_gatt_char = AsyncMock(side_effect=_write_gatt_char)
    client.read_gatt_char = AsyncMock(side_effect=_read_gatt_char)
    client.start_notify = AsyncMock(side_effect=_start_notify)
    client.stop_notify = AsyncMock(side_effect=_stop_notify)

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
    service_info.name = "Okin Device"  # Generic name, not matching any specific bed pattern
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
