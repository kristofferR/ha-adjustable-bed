"""Tests for Octo bed controllers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import cast
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# HA 2026.9 defines this here; 2026.10 re-exports it from const.
from homeassistant.components.light import (
    ATTR_RGB_COLOR,  # pyright: ignore[reportPrivateImportUsage]
    ATTR_RGBW_COLOR,  # pyright: ignore[reportPrivateImportUsage]
)
from homeassistant.components.light.const import ColorMode
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds import octo as octo_module
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.octo import (
    OCTO_FEATURE_END,
    OCTO_FEATURE_LIGHT,
    OCTO_FEATURE_LIGHT_AUTO,
    OCTO_FEATURE_LIGHT_DURATION,
    OCTO_FEATURE_LIGHT_RGB,
    OCTO_FEATURE_LIGHT_RGBWI,
    OCTO_FEATURE_LIGHT_SENSITIVITY,
    OCTO_FEATURE_MEMCOUNT,
    OCTO_FEATURE_MOTORCOUNT,
    OCTO_FEATURE_PIN,
    OCTO_FEATURE_REMOTE_CONTROL_LOCK,
    OCTO_FEATURE_REMOTE_TEACH,
    OCTO_FEATURE_SYNCHRO,
    OCTO_MAX_RESPONSE_BUFFER_SIZE,
    OCTO_MOTOR_HEAD,
    OCTO_MOTOR_LEGS,
    OCTO_PACKET_CHAR,
    OCTO_PROTOCOL_HOLD_INTERVAL_MS,
    OCTO_SYSTEM_PIN_LOCK,
    OCTO_SYSTEM_PIN_STATE,
    OCTO_SYSTEM_SET_DEFAULT_CONFIG,
    OctoCapabilityRecord,
    OctoController,
    OctoStar2Controller,
)
from custom_components.adjustable_bed.button import (
    BUTTON_DESCRIPTIONS,
    AdjustableBedButton,
    PairedBedCombinedButton,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_OCTO_PIN,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OCTO_CHAR_UUID,
    OCTO_STAR2_CHAR_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.light import (
    LIGHT_DESCRIPTION,
    AdjustableBedLight,
    _light_entities_for,
)
from custom_components.adjustable_bed.switch import (
    SWITCH_DESCRIPTIONS,
    AdjustableBedSwitch,
    _switch_entities_for,
)

_REAL_OCTO_DISCOVER_FEATURES = OctoController.discover_features


def _activate_capabilities(controller: OctoController, *records: OctoCapabilityRecord) -> None:
    """Apply a complete advertised capability set to a lightweight controller."""
    controller._pending_capability_records = {record.feature_id: record for record in records}
    controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])


def _complete_feature_data(controller: OctoController, data: list[int]) -> None:
    controller._pending_capability_records = {}
    controller._handle_feature_response(data)
    controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])


def _capability(
    feature_id: int,
    characteristic: bytes,
    value: bytes,
    *,
    value_type: int = 1,
    readonly: int = 0,
) -> OctoCapabilityRecord:
    return OctoCapabilityRecord(feature_id, readonly, characteristic, value_type, value)


def _packet(command: list[int], data: list[int]) -> dict[str, list[int]]:
    return {"command": command, "data": data, "wire_command": command}


async def _raise_timeout(awaitable: object, *, timeout: float) -> None:
    del timeout
    close = getattr(awaitable, "close", None)
    if close is not None:
        close()
    raise TimeoutError


@pytest.fixture
def mock_octo_config_entry_data() -> dict:
    """Return mock config entry data for an Octo bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Octo Test Bed",
        CONF_BED_TYPE: BED_TYPE_OCTO,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
        CONF_OCTO_PIN: "1234",
        CONF_MOTOR_PULSE_COUNT: 1,
        CONF_MOTOR_PULSE_DELAY_MS: 1,
    }


@pytest.fixture
def mock_octo_config_entry(
    hass: HomeAssistant,
    mock_octo_config_entry_data: dict,
) -> MockConfigEntry:
    """Return a mock config entry for an Octo bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Octo Test Bed",
        data=mock_octo_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="octo_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_octo_star2_config_entry_data(mock_octo_config_entry_data: dict) -> dict:
    """Return mock config entry data for an Octo Star2 bed."""
    data = dict(mock_octo_config_entry_data)
    data[CONF_PROTOCOL_VARIANT] = OCTO_VARIANT_STAR2
    data[CONF_OCTO_PIN] = ""
    return data


@pytest.fixture
def mock_octo_star2_config_entry(
    hass: HomeAssistant,
    mock_octo_star2_config_entry_data: dict,
) -> MockConfigEntry:
    """Return a mock config entry for an Octo Star2 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Octo Star2 Test Bed",
        data=mock_octo_star2_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:11",
        entry_id="octo_star2_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def octo_stream_controller() -> OctoController:
    """Return a lightweight Octo controller for response-stream tests."""
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.client = None
    return OctoController(coordinator)


def _build_octo_response(
    controller: OctoController,
    command: tuple[int, int],
    data: list[int] | None = None,
    *,
    declared_length: int | None = None,
) -> bytes:
    """Build a from-device OCTO response with escaping and checksum."""
    packet_data = data or []
    header_length = len(packet_data) if declared_length is None else declared_length
    data_len_high = (header_length >> 8) & 0xFF
    data_len_low = header_length & 0xFF
    checksum = controller._calculate_checksum(
        [0x80, *command, data_len_high, data_len_low, *packet_data]
    )
    payload = [
        *command,
        data_len_high,
        data_len_low,
        checksum,
        *packet_data,
    ]
    return bytes(
        [
            OCTO_PACKET_CHAR,
            *controller._escape_bytes(payload),
            OCTO_PACKET_CHAR,
        ]
    )


class TestOctoVariantSelection:
    """Test Octo variant selection in controller creation."""

    async def test_auto_variant_uses_star2_gatt_endpoint(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_bleak_client: MagicMock,
    ):
        """Auto should select Star2 when its writable GATT endpoint exists."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        star2_characteristic = MagicMock(uuid=OCTO_STAR2_CHAR_UUID)
        star2_service = MagicMock(uuid=OCTO_STAR2_SERVICE_UUID)
        star2_service.get_characteristic.side_effect = lambda uuid: (
            star2_characteristic if uuid.lower() == OCTO_STAR2_CHAR_UUID.lower() else None
        )
        mock_bleak_client.services = [star2_service]

        controller = await create_controller(
            coordinator,
            BED_TYPE_OCTO,
            VARIANT_AUTO,
            mock_bleak_client,
            device_name="DA1458x",
        )

        assert isinstance(controller, OctoStar2Controller)

    async def test_explicit_standard_overrides_star2_gatt_endpoint(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_bleak_client: MagicMock,
    ):
        """An explicit Standard selection should remain authoritative."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        star2_characteristic = MagicMock(uuid=OCTO_STAR2_CHAR_UUID)
        star2_service = MagicMock(uuid=OCTO_STAR2_SERVICE_UUID)
        star2_service.get_characteristic.return_value = star2_characteristic
        mock_bleak_client.services = [star2_service]

        controller = await create_controller(
            coordinator,
            BED_TYPE_OCTO,
            OCTO_VARIANT_STANDARD,
            mock_bleak_client,
            device_name="DA1458x",
        )

        assert isinstance(controller, OctoController)

    async def test_auto_variant_requires_star2_characteristic(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_bleak_client: MagicMock,
    ):
        """The Star2 service alone should not select Star2 in Auto mode."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        star2_service = MagicMock(uuid=OCTO_STAR2_SERVICE_UUID)
        star2_service.get_characteristic.return_value = None
        mock_bleak_client.services = [star2_service]

        controller = await create_controller(
            coordinator,
            BED_TYPE_OCTO,
            VARIANT_AUTO,
            mock_bleak_client,
            device_name="DA1458x",
        )

        assert isinstance(controller, OctoController)

    async def test_standard_variant_uses_octo_controller(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Standard variant should create OctoController."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, OctoController)

    async def test_star2_variant_uses_octo_star2_controller(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_octo_ready_transport,
    ):
        """Star2 variant should create OctoStar2Controller."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, OctoStar2Controller)


class TestOctoRequiredStartupDiscovery:
    """Only the Standard controller's declared session gate is mandatory."""

    async def test_false_required_discovery_cleans_up_and_retries_before_ready(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        coordinator._max_retries = 2
        states: list[bool] = []
        coordinator.register_connection_state_callback(states.append)

        with (
            patch.object(
                OctoController, "discover_features", new_callable=AsyncMock, return_value=False
            ) as discover,
            patch.object(OctoController, "send_pin", new_callable=AsyncMock) as send_pin,
            patch.object(AdjustableBedCoordinator, "_backfill_octo_snapshot") as backfill_snapshot,
        ):
            assert await coordinator.async_connect() is False

        assert discover.await_count == 2
        assert send_pin.await_count == 0
        backfill_snapshot.assert_not_called()
        assert mock_bleak_client.disconnect.await_count == 2
        assert mock_bleak_client.write_gatt_char.await_count == 0
        assert coordinator.connection_attempt_count == 2
        assert coordinator.controller is None
        assert coordinator.is_connected is False
        assert True not in states
        assert all(
            attempt["error_type"] == "ConnectionError"
            for attempt in coordinator.connection_attempt_details
        )

    async def test_successful_required_discovery_continues_startup(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        states: list[bool] = []
        coordinator.register_connection_state_callback(states.append)

        with (
            patch.object(
                OctoController, "discover_features", new_callable=AsyncMock, return_value=True
            ) as discover,
            patch.object(OctoController, "send_pin", new_callable=AsyncMock) as send_pin,
            patch.object(AdjustableBedCoordinator, "_backfill_octo_snapshot") as backfill_snapshot,
        ):
            assert await coordinator.async_connect() is True

        assert discover.await_count == 1
        assert send_pin.await_count == 1
        backfill_snapshot.assert_called_once_with()
        assert coordinator.is_connected is True
        assert states[-1] is True
        assert coordinator.controller is not None

    async def test_optional_legacy_discovery_may_return_none(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)

        with (
            patch.object(OctoController, "requires_ordered_discovery", False),
            patch.object(
                OctoController, "discover_features", new_callable=AsyncMock, return_value=None
            ) as discover,
            patch.object(OctoController, "send_pin", new_callable=AsyncMock),
        ):
            assert await coordinator.async_connect() is True

        discover.assert_awaited_once()
        assert coordinator.is_connected is True

    async def test_star2_startup_does_not_run_standard_required_discovery(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)

        with patch.object(
            OctoController, "discover_features", new_callable=AsyncMock, return_value=False
        ) as standard_discovery:
            assert await coordinator.async_connect() is True

        standard_discovery.assert_not_awaited()
        assert isinstance(coordinator.controller, OctoStar2Controller)
        assert coordinator.is_connected is True


class TestOctoNotificationStream:
    """Test OCTO packet reassembly across notified characteristic values."""

    def test_reassembles_at_every_encoded_byte_boundary(
        self, octo_stream_controller: OctoController
    ) -> None:
        """Every split point, including escaped pairs, should reassemble."""
        packet_data = [0x40, 0x3C, 0x4F, 0x41, 0x01]
        response = _build_octo_response(
            octo_stream_controller,
            (0x21, 0x71),
            packet_data,
        )
        expected = _packet([0x21, 0x71], packet_data)

        for split_at in range(1, len(response)):
            controller = OctoController(octo_stream_controller._coordinator)
            assert controller._extract_response_packets(response[:split_at]) == []
            assert controller._extract_response_packets(response[split_at:]) == [expected]
            assert controller._response_buffer == bytearray()

    def test_reassembles_one_byte_notifications(
        self, octo_stream_controller: OctoController
    ) -> None:
        """A response should survive the most fragmented possible delivery."""
        response = _build_octo_response(octo_stream_controller, (0x21, 0x7F))
        packets: list[dict[str, list[int]]] = []

        for byte in response:
            packets.extend(octo_stream_controller._extract_response_packets(bytes([byte])))

        assert packets == [_packet([0x21, 0x7F], [])]
        assert octo_stream_controller._response_buffer == bytearray()

    @pytest.mark.parametrize(
        ("flags", "address_count"),
        ((0x04, 1), (0x08, 1), (0x0C, 2)),
    )
    def test_normalizes_complete_six_byte_addresses(
        self,
        octo_stream_controller: OctoController,
        flags: int,
        address_count: int,
    ) -> None:
        addresses = [
            value for slot in range(address_count) for value in range(slot * 6, slot * 6 + 6)
        ]
        response = _build_octo_response(
            octo_stream_controller,
            (0x21 | flags, 0x71),
            [*addresses, 0xAA, 0xBB],
        )

        assert octo_stream_controller._extract_response_packets(response) == [
            {
                "command": [0x21, 0x71],
                "data": [0xAA, 0xBB],
                "wire_command": [0x21 | flags, 0x71],
            }
        ]

    @pytest.mark.parametrize(
        ("flags", "data"),
        ((0x04, [1, 2, 3, 4, 5]), (0x08, [1, 2, 3, 4, 5]), (0x0C, [1] * 11)),
    )
    def test_rejects_truncated_address_fields(
        self,
        octo_stream_controller: OctoController,
        flags: int,
        data: list[int],
    ) -> None:
        response = _build_octo_response(
            octo_stream_controller,
            (0x21 | flags, 0x71),
            data,
        )

        assert octo_stream_controller._parse_response_packet(response) is None

    def test_rejects_data_past_declared_length(
        self, octo_stream_controller: OctoController
    ) -> None:
        response = _build_octo_response(
            octo_stream_controller,
            (0x21, 0x71),
            [0xAA],
            declared_length=0,
        )

        assert octo_stream_controller._parse_response_packet(response) is None

    def test_extracts_multiple_packets_from_one_notification(
        self, octo_stream_controller: OctoController
    ) -> None:
        """One notified value may contain multiple complete protocol packets."""
        first = _build_octo_response(octo_stream_controller, (0x21, 0x7F))
        second = _build_octo_response(octo_stream_controller, (0x11, 0x72), [0x01])

        assert octo_stream_controller._extract_response_packets(first + second) == [
            _packet([0x21, 0x7F], []),
            _packet([0x11, 0x72], [0x01]),
        ]

    def test_resynchronizes_after_noise_and_a_malformed_frame(
        self, octo_stream_controller: OctoController
    ) -> None:
        """A bad candidate should not consume the next valid start delimiter."""
        malformed = bytearray(_build_octo_response(octo_stream_controller, (0x21, 0x7F)))
        malformed[-2] ^= 0x01
        valid = _build_octo_response(octo_stream_controller, (0x11, 0x72), [0x01])

        assert octo_stream_controller._extract_response_packets(
            b"\x00\xff" + malformed + valid
        ) == [_packet([0x11, 0x72], [0x01])]
        assert octo_stream_controller._response_buffer == bytearray()

    def test_resynchronizes_long_delimiter_run_without_losing_valid_start(
        self, octo_stream_controller: OctoController
    ) -> None:
        """Many malformed candidates should retain the final possible start."""
        delimiters = bytes([OCTO_PACKET_CHAR]) * 4096
        assert octo_stream_controller._extract_response_packets(delimiters) == []
        assert octo_stream_controller._response_buffer == bytearray([OCTO_PACKET_CHAR])

        valid = _build_octo_response(octo_stream_controller, (0x21, 0x7F))
        assert octo_stream_controller._extract_response_packets(valid) == [
            _packet([0x21, 0x7F], [])
        ]
        assert octo_stream_controller._response_buffer == bytearray()

    def test_bounds_incomplete_response_and_recovers(
        self, octo_stream_controller: OctoController
    ) -> None:
        """A missing end delimiter must not grow retained state indefinitely."""
        incomplete = bytes([OCTO_PACKET_CHAR]) + bytes([0x01] * OCTO_MAX_RESPONSE_BUFFER_SIZE)

        assert octo_stream_controller._extract_response_packets(incomplete) == []
        assert octo_stream_controller._response_buffer == bytearray()

        valid = _build_octo_response(octo_stream_controller, (0x21, 0x7F))
        assert octo_stream_controller._extract_response_packets(valid) == [
            _packet([0x21, 0x7F], [])
        ]

    def test_notification_dispatches_reassembled_packets_and_preserves_raw_chunks(
        self, octo_stream_controller: OctoController
    ) -> None:
        """Reassembly should dispatch all packets without altering diagnostics."""
        light_data = [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x01]
        end_data = [0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00]
        responses = _build_octo_response(
            octo_stream_controller,
            (0x21, 0x71),
            light_data,
        ) + _build_octo_response(
            octo_stream_controller,
            (0x21, 0x71),
            end_data,
        )
        first_chunk = bytearray(responses[:5])
        second_chunk = bytearray(responses[5:])
        raw_callback = MagicMock()
        octo_stream_controller.set_raw_notify_callback(raw_callback)

        octo_stream_controller._on_notification(MagicMock(), first_chunk)
        assert octo_stream_controller._has_lights is None
        octo_stream_controller._on_notification(MagicMock(), second_chunk)

        assert octo_stream_controller._has_lights is True
        assert octo_stream_controller._features_complete.is_set()
        assert raw_callback.call_args_list == [
            ((OCTO_CHAR_UUID, bytes(first_chunk)),),
            ((OCTO_CHAR_UUID, bytes(second_chunk)),),
        ]

    async def test_notification_lifecycle_clears_incomplete_data(
        self, octo_stream_controller: OctoController
    ) -> None:
        """Stale fragments must not cross notification subscriptions."""
        client = MagicMock()
        client.is_connected = True
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()
        octo_stream_controller._coordinator.client = client
        octo_stream_controller._response_buffer.extend(b"\x40\x21")

        await octo_stream_controller.start_notify()
        assert octo_stream_controller._response_buffer == bytearray()

        octo_stream_controller._response_buffer.extend(b"\x40\x21")
        await octo_stream_controller.stop_notify()
        assert octo_stream_controller._response_buffer == bytearray()

    def test_unmatched_config_debug_and_normal_feedback_are_noops(
        self, octo_stream_controller: OctoController
    ) -> None:
        _activate_capabilities(
            octo_stream_controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01"),
            _capability(OCTO_FEATURE_LIGHT_RGB, b"\x01", bytes((10, 20, 30)), value_type=0x03),
        )
        state_callback = MagicMock()
        octo_stream_controller._coordinator.handle_controller_state_updates = state_callback
        before = dict(octo_stream_controller._capability_records)

        for command in ((0x11, 0x7F), (0x11, 0x70), (0x31, 0x01), (0x01, 0x70)):
            response = _build_octo_response(octo_stream_controller, command, [0x99])
            octo_stream_controller._on_notification(MagicMock(), bytearray(response))

        assert octo_stream_controller._capability_records == before
        state_callback.assert_not_called()


class TestOctoOrderedSession:
    """Exercise the required P1 startup sequence with an in-process BLE fake."""

    @staticmethod
    def _feature_data(record: OctoCapabilityRecord) -> list[int]:
        return [
            (record.feature_id >> 16) & 0xFF,
            (record.feature_id >> 8) & 0xFF,
            record.feature_id & 0xFF,
            record.readonly,
            len(record.characteristic),
            *record.characteristic,
            record.value_type,
            *record.value,
        ]

    async def _controller_with_responder(
        self,
        info: bytes,
        records: tuple[OctoCapabilityRecord, ...] = (),
        *,
        missing_response: str | None = None,
        malformed_response: str | None = None,
    ) -> tuple[OctoController, list[bytes], list[str | None]]:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.handle_controller_state_updates = MagicMock()
        controller = OctoController(coordinator)
        client = MagicMock()
        client.is_connected = True
        notification_callback: Callable[..., None] | None = None

        async def start_notify(_uuid: str, callback) -> None:
            nonlocal notification_callback
            notification_callback = callback

        client.start_notify = AsyncMock(side_effect=start_notify)
        coordinator.client = client
        writes: list[bytes] = []
        active_stage: list[str | None] = [None]

        async def write_command(packet: bytes, *_args: object) -> None:
            nonlocal notification_callback
            writes.append(packet)
            assert notification_callback is not None
            if packet == controller._build_packet([0x20, 0x7F]):
                active_stage[0] = "ping"
                if missing_response != "ping":
                    data = [1] if malformed_response == "ping" else []
                    notification_callback(
                        MagicMock(),
                        bytearray(_build_octo_response(controller, (0x21, 0x7F), data)),
                    )
            elif packet == controller._build_packet([0x20, 0x70]):
                active_stage[0] = "device_info"
                if missing_response != "device_info":
                    response_info = bytes(9) if malformed_response == "device_info" else info
                    notification_callback(
                        MagicMock(),
                        bytearray(
                            _build_octo_response(controller, (0x21, 0x70), list(response_info))
                        ),
                    )
            elif packet == controller._build_packet([0x20, 0x71]):
                active_stage[0] = "capabilities"
                if missing_response != "capabilities":
                    if malformed_response == "capabilities":
                        capability_data = [1, 2]
                        notification_callback(
                            MagicMock(),
                            bytearray(
                                _build_octo_response(controller, (0x21, 0x71), capability_data)
                            ),
                        )
                    else:
                        for record in records:
                            notification_callback(
                                MagicMock(),
                                bytearray(
                                    _build_octo_response(
                                        controller,
                                        (0x21, 0x71),
                                        self._feature_data(record),
                                    )
                                ),
                            )
                        notification_callback(
                            MagicMock(),
                            bytearray(
                                _build_octo_response(
                                    controller,
                                    (0x21, 0x71),
                                    [0xFF, 0xFF, 0xFF, 0, 0, 0],
                                )
                            ),
                        )

        controller.write_command = AsyncMock(side_effect=write_command)
        coordinator.motor_pulse_count = 1
        coordinator.motor_pulse_delay_ms = 1
        return controller, writes, active_stage

    async def test_ordered_ping_info_caps_session_and_high_bit_device_info(self) -> None:
        info = bytes((0x80, 0x01, 0x02, 0x03, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06))
        motor_record = _capability(OCTO_FEATURE_MOTORCOUNT, b"\x04", b"\x00")
        controller, writes, _stage = await self._controller_with_responder(info, (motor_record,))

        assert await controller.discover_features() is True
        assert writes == [
            controller._build_packet([0x20, 0x7F]),
            controller._build_packet([0x20, 0x70]),
            controller._build_packet([0x20, 0x71]),
        ]
        assert controller._session_ready is True
        assert controller._device_info == {
            "cid": int.from_bytes(info[:4], "big"),
            "firmware": int.from_bytes(info[4:6], "big"),
            "pid": int.from_bytes(info[6:8], "big"),
            "hardware": int.from_bytes(info[8:10], "big"),
        }
        assert controller.discovered_motor_count == 4

    @pytest.mark.parametrize("info_length", (9, 11))
    async def test_invalid_device_info_length_blocks_capability_request(
        self, info_length: int
    ) -> None:
        controller, writes, _stage = await self._controller_with_responder(bytes(info_length))

        assert await controller.discover_features() is False
        assert writes == [
            controller._build_packet([0x20, 0x7F]),
            controller._build_packet([0x20, 0x70]),
        ]
        assert controller._session_ready is False
        assert controller._features_complete.is_set() is False

    @pytest.mark.parametrize("missing_response", ("ping", "device_info", "capabilities"))
    async def test_absent_session_reply_keeps_legacy_controls_available(
        self,
        missing_response: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        controller, writes, active_stage = await self._controller_with_responder(
            bytes(10), missing_response=missing_response
        )

        async def no_protocol_wait(awaitable, *, timeout: float):
            del timeout
            if active_stage[0] == missing_response:
                close = getattr(awaitable, "close", None)
                if close is not None:
                    close()
                raise TimeoutError
            return await awaitable

        monkeypatch.setattr(octo_module.asyncio, "wait_for", no_protocol_wait)

        assert await controller.discover_features() is True
        assert writes[:3] == [
            controller._build_packet([0x20, 0x7F]),
            controller._build_packet([0x20, 0x70]),
            controller._build_packet([0x20, 0x71]),
        ]
        assert controller._session_ready is True

        if missing_response == "capabilities":
            assert controller.legacy_light_fallback is True
            assert controller.controller_entity_discovery_complete is False
            assert controller.supports_lights is True
            assert controller._capability_records == {}
            await controller.lights_on()
            assert writes[-1] == controller._build_packet(
                [0x20, 0x72], [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x01]
            )

        writes.clear()
        await controller.move_back_up()
        assert writes == [
            controller._build_packet([0x02, 0x70], [0x02]),
            controller._build_packet([0x02, 0x73]),
        ]

    @pytest.mark.parametrize("malformed_response", ("ping", "device_info", "capabilities"))
    async def test_malformed_session_reply_remains_strict(
        self,
        malformed_response: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        controller, _writes, active_stage = await self._controller_with_responder(
            bytes(10), malformed_response=malformed_response
        )

        async def no_protocol_wait(awaitable, *, timeout: float):
            del timeout
            if malformed_response == "capabilities" and active_stage[0] == "capabilities":
                close = getattr(awaitable, "close", None)
                if close is not None:
                    close()
                raise TimeoutError
            return await awaitable

        monkeypatch.setattr(octo_module.asyncio, "wait_for", no_protocol_wait)

        assert await controller.discover_features() is False
        assert controller._session_ready is False
        assert controller.controller_entity_discovery_complete is False


class TestOctoPinAuth:
    """Test Octo PIN authentication flow."""

    async def test_periodic_pin_keepalive_uses_command_lane_and_disconnect_generation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        coordinator = MagicMock()
        coordinator.entry.data = {}
        coordinator.client = MagicMock(is_connected=True)
        controller = OctoController(coordinator, pin="1234")
        controller._session_ready = True
        controller._write_octo_command = AsyncMock()

        sleep_started = asyncio.Event()
        release_sleep = asyncio.Event()
        command_started = asyncio.Event()
        hold_command = asyncio.Event()
        intervals: list[float] = []

        async def fake_sleep(delay: float) -> None:
            intervals.append(delay)
            sleep_started.set()
            await release_sleep.wait()

        async def execute(command, **kwargs) -> None:
            await command(controller)
            coordinator.keepalive_options = kwargs
            command_started.set()
            await hold_command.wait()

        coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
        monkeypatch.setattr(octo_module.asyncio, "sleep", fake_sleep)

        await controller.start_keepalive()
        task = controller._keepalive_task
        assert task is not None
        await sleep_started.wait()
        release_sleep.set()
        await command_started.wait()

        assert intervals == [25]
        assert coordinator.keepalive_options == {
            "cancel_running": False,
            "skip_disconnect": True,
            "read_positions_after_operation": False,
        }
        controller._write_octo_command.assert_awaited_once()
        assert controller._write_octo_command.await_args.args[:2] == (
            [0x20, 0x43],
            [1, 2, 3, 4],
        )

        controller.on_disconnect()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert controller._keepalive_task is None

    async def test_periodic_pin_keepalive_does_not_start_without_configured_pin(self) -> None:
        coordinator = MagicMock()
        coordinator.entry.data = {}
        coordinator.client = MagicMock(is_connected=True)
        controller = OctoController(coordinator)
        controller._session_ready = True

        await controller.start_keepalive()

        assert controller._keepalive_task is None

    async def test_coordinator_starts_keepalive_after_octo_session(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        start_keepalive = AsyncMock()
        monkeypatch.setattr(OctoController, "start_keepalive", start_keepalive, raising=False)
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)

        try:
            await coordinator.async_connect()
            start_keepalive.assert_awaited_once()
        finally:
            await coordinator.async_disconnect()

    async def test_runtime_reconnect_waits_for_session_pin_acceptance_before_command(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A reconnect may send PIN first, but cannot dispatch the waiting action."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        await coordinator.async_disconnect()

        ready_discovery = OctoController.discover_features

        async def locked_discovery(controller: OctoController) -> bool:
            complete = await ready_discovery(controller)
            controller._pin_feature_active = True
            controller._has_pin = True
            controller._pin_locked = True
            return complete

        pin_sent = asyncio.Event()
        original_write = OctoController._write_octo_command

        async def capture_pin(
            controller: OctoController,
            command: list[int],
            data: list[int] | None = None,
            repeat_count: int = 1,
            repeat_delay_ms: int = 100,
            cancel_event: asyncio.Event | None = None,
        ) -> None:
            if command == [0x20, 0x43]:
                pin_sent.set()
                return
            await original_write(
                controller,
                command,
                data,
                repeat_count,
                repeat_delay_ms,
                cancel_event,
            )

        monkeypatch.setattr(OctoController, "discover_features", locked_discovery)
        monkeypatch.setattr(OctoController, "_write_octo_command", capture_pin)
        command_started = asyncio.Event()

        async def ordinary(_controller: BedController) -> None:
            command_started.set()

        task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                ordinary,
                cancel_running=False,
                read_positions_after_operation=False,
            )
        )
        await pin_sent.wait()
        assert command_started.is_set() is False

        controller = cast(OctoController, coordinator.controller)
        controller._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])
        await task

        assert command_started.is_set() is True

    async def test_send_pin_writes_auth_packet_when_pin_required(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """send_pin should write PIN packet when bed is PIN-locked."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True

        await controller.send_pin()

        expected_packet = controller._build_packet([0x20, 0x43], [1, 2, 3, 4])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_send_pin_skips_when_bed_not_locked(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """send_pin should skip writes when feature discovery shows unlocked bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = False

        await controller.send_pin()

        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_locked_pin_hides_motor_and_preset_controls_but_keeps_stop(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True

        cover = AdjustableBedCover(
            coordinator,
            _build_cover_description(controller.motor_control_specs[0]),
        )
        preset = AdjustableBedButton(
            coordinator,
            next(
                description
                for description in BUTTON_DESCRIPTIONS
                if description.key == "preset_flat"
            ),
        )
        stop = AdjustableBedButton(
            coordinator,
            next(description for description in BUTTON_DESCRIPTIONS if description.key == "stop"),
        )

        assert cover.available is False
        assert preset.available is False
        assert stop.available is True

        controller._pin_locked = False
        assert cover.available is True
        assert preset.available is True

    def test_paired_combined_controls_follow_octos_pin_gate(self) -> None:
        from types import SimpleNamespace

        coordinator = MagicMock()
        coordinator.pair_id = "pair"
        coordinator.device_info = {}
        octo = OctoController(MagicMock())
        octo._pin_feature_active = True
        octo._has_pin = True
        octo._pin_locked = True
        coordinator.children = {
            "left": SimpleNamespace(capability_controller=octo),
        }
        description = next(item for item in BUTTON_DESCRIPTIONS if item.key == "preset_flat")
        stop_description = next(item for item in BUTTON_DESCRIPTIONS if item.key == "stop")

        combined = PairedBedCombinedButton(coordinator, description)
        stop = PairedBedCombinedButton(coordinator, stop_description)

        assert combined.available is False
        assert stop.available is True
        octo._pin_locked = False
        assert combined.available is True

    async def test_send_pin_redacts_command_diagnostics(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """PIN packets should be written but redacted from traces and logs."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True
        coordinator._command_trace.clear()
        mock_bleak_client.write_gatt_char.reset_mock()
        caplog.set_level(logging.DEBUG, logger="custom_components.adjustable_bed.beds.base")
        caplog.clear()

        # This test targets packet redaction itself. Normal scheduled commands
        # correctly wait for PIN acceptance, so exercise the explicit auth send
        # path directly instead of pretending an auth packet is an ordinary
        # user control.
        await controller.send_pin()

        expected_packet = controller._build_packet([0x20, 0x43], [1, 2, 3, 4])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )
        assert len(coordinator.command_trace) == 1
        assert coordinator.command_trace[0]["payload"] == {
            "hex": "**REDACTED**",
            "length": len(expected_packet),
            "ascii_preview": None,
        }
        assert expected_packet.hex() not in caplog.text
        assert "**REDACTED**" in caplog.text

    async def test_enrollment_pin_is_redacted_from_logs_and_support_trace(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The escaped enrollment packet must never expose its four digits."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._pin_feature_active = True
        controller._has_pin = False
        controller._pin_locked = False
        coordinator._command_trace.clear()
        mock_bleak_client.write_gatt_char.reset_mock()
        caplog.set_level(logging.DEBUG, logger="custom_components.adjustable_bed.beds.base")
        caplog.clear()

        await controller.enroll_pin("0369")

        expected_packet = controller._build_packet([0x20, 0x41], [0, 3, 6, 9])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )
        assert expected_packet.hex() not in caplog.text
        assert coordinator.command_trace[-1]["payload"] == {
            "hex": "**REDACTED**",
            "length": len(expected_packet),
            "ascii_preview": None,
        }
        assert expected_packet.hex() not in repr(coordinator.command_trace)


class TestOctoCommands:
    """Test Octo motor, light, and stop commands."""

    def test_rtv_auto_layout_is_fallback_behind_discovery_and_override(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.ble_device_name = "RTV Lift"
        coordinator.entry.data = {CONF_OCTO_MOTOR_COUNT_OVERRIDE: "auto"}
        controller = OctoController(coordinator)

        assert controller.effective_motor_count == 1

        controller._discovered_motor_count = 4
        assert controller.effective_motor_count == 4

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "3"
        assert controller.effective_motor_count == 3

    def test_effective_motor_count_tracks_caps_and_octo_override(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        controller = OctoController(coordinator)

        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_MOTORCOUNT, b"\x04", b"\x00"),
        )
        assert controller.effective_motor_count == 4
        assert [spec.key for spec in controller.motor_control_specs] == [
            "back",
            "legs",
            "back_legs",
            "head",
            "feet",
            "head_feet",
        ]

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "1"
        assert controller.effective_motor_count == 1
        assert [spec.key for spec in controller.motor_control_specs] == ["tv_lift"]

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "auto"
        assert controller.effective_motor_count == 4

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "invalid"
        assert controller.effective_motor_count == 4

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "auto"
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_MOTORCOUNT, b"\x00", b"\x04"),
        )
        assert controller.discovered_motor_count is None
        assert controller.effective_motor_count is None
        assert controller.motor_control_specs == ()
        assert controller.stale_motor_entity_keys == frozenset(
            {"tv_lift", "back", "legs", "back_legs", "head", "feet", "head_feet"}
        )

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "3"
        assert controller.effective_motor_count == 3

        coordinator.entry.data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = "auto"
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_MOTORCOUNT, b"\x05", b"\x01"),
        )
        assert controller.effective_motor_count is None

    @pytest.mark.parametrize(
        ("control", "command", "data", "memory_count"),
        (("back_up", 0x70, [OCTO_MOTOR_HEAD], 0), ("memory_9", 0x72, [8], 9)),
    )
    async def test_bounded_hold_uses_protocol_cadence_and_fresh_stop(
        self,
        control: str,
        command: int,
        data: list[int],
        memory_count: int,
    ) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.cancel_command = asyncio.Event()
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller._memory_count = memory_count
        controller._write_octo_command = AsyncMock()

        with patch.object(asyncio, "wait_for", new=_raise_timeout):
            await controller.hold_control(control, duration_ms=700)

        calls = controller._write_octo_command.await_args_list
        assert len(calls) == 2
        assert calls[0].args[:2] == ([0x02, command], data)
        assert calls[0].kwargs["repeat_count"] == 2
        assert calls[0].kwargs["repeat_delay_ms"] == OCTO_PROTOCOL_HOLD_INTERVAL_MS
        assert calls[0].kwargs["cancel_event"] is coordinator.cancel_command
        assert calls[1].kwargs["command"] == [0x02, 0x73]
        fresh_stop_event = calls[1].kwargs["cancel_event"]
        assert isinstance(fresh_stop_event, asyncio.Event)
        assert fresh_stop_event is not coordinator.cancel_command

    def test_hold_control_preserves_existing_host_safety_bound(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        controller = OctoController(coordinator)

        controller.validate_hold_control("back_up", 60_000)
        with pytest.raises(ValueError, match="100..60000"):
            controller.validate_hold_control("back_up", 60_001)

    @pytest.mark.parametrize(
        ("motor_count", "control", "direction", "mask"),
        (
            (3, "back_legs_up", 0x70, 0x06),
            (3, "back_legs_down", 0x71, 0x06),
            (3, "all_down", 0x71, 0x0E),
            (4, "back_legs_up", 0x70, 0x06),
            (4, "back_legs_down", 0x71, 0x06),
            (4, "all_down", 0x71, 0x1E),
        ),
    )
    async def test_three_and_four_motor_artifact_holds_are_bounded_and_stopped(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        motor_count: int,
        control: str,
        direction: int,
        mask: int,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_MOTORCOUNT, bytes((motor_count,)), b"\x00"),
        )
        assert {"back_legs_up", "back_legs_down", "all_down"}.issubset(
            controller.held_control_options
        )
        back_legs = next(spec for spec in controller.motor_control_specs if spec.key == "back_legs")
        assert back_legs.hold is not None
        assert back_legs.hold.up_control == "back_legs_up"
        assert back_legs.hold.down_control == "back_legs_down"
        if control == "all_down":
            all_down = next(
                spec for spec in controller.controller_button_specs if spec.key == "octo_all_down"
            )
            assert all_down.hold is not None
            assert all_down.hold.control == "all_down"

        monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", AsyncMock())
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.octo.asyncio.wait_for", _raise_timeout
        )
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.hold_control(control, 100)

        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list] == [
            controller._build_packet([0x02, direction], [mask]),
            controller._build_packet([0x02, 0x73]),
        ]

    async def test_one_motor_override_keeps_advertised_accessories_and_uses_motor_one(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """A one-motor override changes axes without hiding independent capabilities."""
        lift_data = {
            **mock_octo_config_entry_data,
            CONF_NAME: "RTV",
            CONF_MOTOR_COUNT: 1,
            CONF_OCTO_PIN: "",
        }
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="RTV",
            data=lift_data,
            unique_id="AA:BB:CC:DD:EE:98",
            entry_id="octo_rtv_entry",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_MOTORCOUNT, b"\x01", b"\x04"),
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
            _capability(OCTO_FEATURE_LIGHT_RGBWI, b"\x01", bytes((1, 2, 3, 4, 5))),
            _capability(OCTO_FEATURE_MEMCOUNT, b"\x04", b"\x00"),
            _capability(OCTO_FEATURE_SYNCHRO, b"\x01", b"\x00"),
        )

        assert [spec.key for spec in controller.motor_control_specs] == ["tv_lift"]
        assert controller.supports_preset_flat is False
        assert controller.supports_preset_both_up is False
        assert controller.supports_lights is True
        assert controller.supports_light_color_control is True
        assert controller.supported_color_modes == frozenset({"rgbw"})
        assert controller.supports_memory_presets is True
        assert controller.memory_slot_count == 4
        assert controller.supports_synchro is True
        assert controller.stale_motor_entity_keys == frozenset(
            {"back", "legs", "back_legs", "head", "feet", "head_feet"}
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.motor_control_specs[0].open_fn(controller)

        payloads = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
        assert payloads == [
            controller._build_packet([0x02, 0x70], [OCTO_MOTOR_HEAD]),
            controller._build_packet([0x02, 0x73]),
        ]

    async def test_bed_layout_marks_tv_lift_entity_as_stale(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
    ):
        """Normal OCTO beds should clean up a former TV lift entity."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        controller = OctoController(coordinator)

        # This fixture is a 2-motor bed, so the 4-motor combined step is stale
        # here too and must not linger in the registry.
        assert controller.stale_motor_entity_keys == frozenset({"tv_lift", "head_feet"})

    async def test_star2_layout_marks_tv_lift_entity_as_stale(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
    ):
        """Star2 should clean up a former one-motor TV lift entity."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        controller = OctoStar2Controller(coordinator)

        assert controller.stale_motor_entity_keys == frozenset(
            {"tv_lift", "head", "feet", "head_feet"}
        )
        assert controller.auto_stops_on_idle is True
        assert controller.supports_preset_both_up is False
        assert controller.supports_preset_flat is False
        assert [spec.key for spec in controller.motor_control_specs] == [
            "back",
            "legs",
            "back_legs",
        ]

    async def test_move_head_up_sends_move_then_stop(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """move_head_up should send movement packet followed by stop packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 2

        move_packet = controller._build_packet([0x02, 0x70], [OCTO_MOTOR_HEAD])
        stop_packet = controller._build_packet([0x02, 0x73])

        assert calls[0][0][1] == move_packet
        assert calls[-1][0][1] == stop_packet

    async def test_standard_commands_are_recorded_for_support_bundles(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """Standard OCTO movement writes should appear in command traces."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        coordinator._command_trace.clear()

        controller = cast(OctoController, coordinator.controller)
        await coordinator.async_execute_controller_command(lambda active: active.move_head_up())

        move_packet = controller._build_packet([0x02, 0x70], [OCTO_MOTOR_HEAD])
        stop_packet = controller._build_packet([0x02, 0x73])
        trace = coordinator.command_trace

        assert [entry["payload"]["hex"] for entry in trace] == [
            move_packet.hex(),
            stop_packet.hex(),
        ]
        assert all(entry["characteristic_uuid"] == OCTO_CHAR_UUID for entry in trace)
        assert all(entry["write_mode"] == "without_response" for entry in trace)
        assert all(entry["operation_name"] == "command" for entry in trace)

    async def test_star2_commands_are_recorded_for_support_bundles(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Star2 movement writes should appear in command traces."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        await coordinator.async_connect()
        coordinator._command_trace.clear()

        controller = cast(OctoStar2Controller, coordinator.controller)
        await coordinator.async_execute_controller_command(lambda active: active.move_head_up())

        assert len(coordinator.command_trace) == 1
        trace = coordinator.command_trace[0]
        assert trace["payload"]["hex"] == controller.CMD_HEAD_UP.hex()
        assert trace["characteristic_uuid"] == OCTO_STAR2_CHAR_UUID
        assert trace["write_mode"] == "with_response"
        assert trace["operation_name"] == "command"
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_STAR2_CHAR_UUID,
            controller.CMD_HEAD_UP,
            response=True,
        )

    async def test_move_with_stop_sends_stop_on_error(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """_move_with_stop should always call _stop_motors in cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        with (
            patch.object(controller, "_move_motor", new_callable=AsyncMock) as mock_move,
            patch.object(controller, "_stop_motors", new_callable=AsyncMock) as mock_stop,
        ):
            mock_move.side_effect = RuntimeError("move failed")
            with pytest.raises(RuntimeError, match="move failed"):
                await controller._octo_move_with_stop(OCTO_MOTOR_HEAD, "up")

            mock_stop.assert_awaited_once()

    async def test_lights_on_off_send_expected_packets(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """lights_on/lights_off should send the expected feature-write packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(controller, _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"))

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_on()
        expected_on = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x01],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_on,
            response=False,
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.lights_off()
        expected_off = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x00],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_off,
            response=False,
        )

    async def test_stop_all_sends_stop_packet(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """stop_all should send the stop command packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.stop_all()

        expected_stop = controller._build_packet([0x02, 0x73])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_stop,
            response=False,
        )


class TestOctoRGBWIFeatureDetection:
    """Test OCTO RGBWI capability detection during feature discovery."""

    def _make_feature_data(
        self,
        feature_id: int,
        value: list[int],
        *,
        value_type: int = 0x05,
        skip_length: int = 1,
        skip_data: list[int] | None = None,
    ) -> list[int]:
        """Build feature response data matching _extract_feature_value_pair format.

        Format: [cap_id(3), flag(1), skip_length(1), skip_data(N), valueType(1), value(...)]
        """
        if skip_data is None:
            skip_data = [0x01] * skip_length
        return [
            (feature_id >> 16) & 0xFF,
            (feature_id >> 8) & 0xFF,
            feature_id & 0xFF,
            0x00,  # flag
            len(skip_data),
            *skip_data,
            value_type,
            *value,
        ]

    async def test_rgbwi_feature_sets_has_rgbwi(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """CAP_LIGHT_RGBWI (0x000104) should set _has_rgbwi to True."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert controller._has_rgbwi is False

        data = self._make_feature_data(
            OCTO_FEATURE_LIGHT_RGBWI,
            [255, 0, 0, 128, 200],  # R, G, B, W, I
            value_type=0x05,
        )
        controller._handle_feature_response(data)
        controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])

        assert controller._has_rgbwi is True

    async def test_rgbwi_feature_stores_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """RGBWI feature should store the valueType byte from the response."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert controller._rgbwi_value_type is None

        data = self._make_feature_data(
            OCTO_FEATURE_LIGHT_RGBWI,
            [255, 255, 255, 255, 255],
            value_type=0x07,
        )
        controller._handle_feature_response(data)
        controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])

        assert controller._rgbwi_value_type == 0x07

    async def test_no_rgbwi_feature_keeps_has_rgbwi_false(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """Only CAP_LIGHT (not RGBWI) should leave _has_rgbwi as False."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Send only basic light feature
        data = self._make_feature_data(
            OCTO_FEATURE_LIGHT,
            [0x01],
            value_type=0x01,
        )
        controller._handle_feature_response(data)
        controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])

        assert controller._has_rgbwi is False
        assert controller._has_lights is True

    async def test_rgbwi_properties_before_discovery(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """RGBWI properties should return correct defaults before feature discovery."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert controller.supports_light_color_control is False
        assert controller.supported_color_mode is None
        assert controller.default_light_rgb_color is None

    async def test_rgbwi_properties_after_discovery(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """RGBWI properties should reflect RGBWI support after feature detection."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((10, 20, 30, 40, 50)),
                value_type=0x05,
            ),
        )

        assert controller.supports_light_color_control is True
        assert controller.supported_color_mode == "rgbw"
        assert controller.default_light_rgb_color is None
        assert controller.supports_explicit_light_on_control is False

    async def test_star2_has_no_rgbwi_support(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_octo_ready_transport,
    ):
        """OctoStar2Controller should not have RGBWI support."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoStar2Controller, coordinator.controller)

        assert controller.supports_light_color_control is False
        assert controller.supported_color_mode is None

    async def test_discover_features_resets_rgbwi_state(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """discover_features should reset RGBWI state before requesting features."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Pre-set RGBWI state
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x07

        # All absent replies use deterministic fake time, not protocol waits.
        monkeypatch.setattr(octo_module.asyncio, "wait_for", _raise_timeout)
        await _REAL_OCTO_DISCOVER_FEATURES(controller)

        # Failed rediscovery preserves the prior complete capability state.
        assert controller._has_rgbwi is True
        assert controller._rgbwi_value_type == 0x07


class TestOctoRGBWICommands:
    """Test OCTO RGBWI set_light_color_rgbw command output."""

    async def test_set_light_color_rgbw_sends_expected_packet(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should send SYSTEM_SET_CAPS packet with RGBWI data."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((255, 0, 128, 64, 77)),
                value_type=0x05,
            ),
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((255, 0, 128, 64))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 255, 0, 128, 64, 77],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_uses_fallback_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw preserves the current value type and intensity."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((10, 20, 30, 40, 90)),
                value_type=0x07,
            ),
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((100, 200, 50, 150))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x07, 100, 200, 50, 150, 90],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_preserves_discovered_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should use the valueType from feature discovery."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((10, 20, 30, 40, 55)),
                value_type=0x0A,
            ),
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((0, 0, 0, 0))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x0A, 0, 0, 0, 0, 55],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_preserves_current_intensity(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """An omitted intensity leaves the advertised intensity byte unchanged."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((10, 20, 30, 40, 93)),
                value_type=0x05,
            ),
        )

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((10, 20, 30, 40))

        # Extract the data portion from the built packet
        call_args = mock_bleak_client.write_gatt_char.call_args
        sent_packet = call_args[0][1]

        # The final value byte is the intensity previously advertised by the bed.
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 10, 20, 30, 40, 93],
        )
        assert sent_packet == expected_packet


class TestOctoRGBWIFeatureValuePair:
    """Test _extract_feature_value_pair with valueType extraction."""

    async def test_extract_returns_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """_extract_feature_value_pair should return the valueType byte."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Build data: feature ID, readonly, characteristic length/data, type, value.
        data = [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 255, 128, 64, 200, 100]
        result = controller._extract_feature_value_pair(data)

        assert result is not None
        assert result == _capability(
            OCTO_FEATURE_LIGHT_RGBWI,
            b"\x01",
            bytes((255, 128, 64, 200, 100)),
            value_type=0x05,
        )

    async def test_extract_returns_none_for_short_data(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """_extract_feature_value_pair should return None for data too short."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        result = controller._extract_feature_value_pair([0x00, 0x01])
        assert result is None

    async def test_extract_end_sentinel(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """_extract_feature_value_pair should parse the end sentinel correctly."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # End sentinel: 0xFFFFFF
        data = [0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00]
        result = controller._extract_feature_value_pair(data)

        assert result is not None
        assert result.feature_id == OCTO_FEATURE_END


class TestOctoRGBWILightEntity:
    """Test light entity behavior with OCTO RGBWI color mode."""

    async def test_rgb_only_advertises_and_writes_rgb_record(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        rgb_record = _capability(
            OCTO_FEATURE_LIGHT_RGB,
            b"\x01\xa7",
            bytes((10, 20, 30)),
            value_type=0x03,
        )
        _activate_capabilities(controller, rgb_record)

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light.hass = hass
        assert light.supported_color_modes == {ColorMode.RGB}
        assert light.color_mode == ColorMode.RGB
        assert light.rgb_color == (10, 20, 30)

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(**{ATTR_RGB_COLOR: (40, 50, 60)})

        expected = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x07, 0x00, 0x02, 0x01, 0xA7, 0x03, 40, 50, 60],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID, expected, response=False
        )
        assert light.color_mode == ColorMode.RGB
        assert light.rgb_color == (40, 50, 60)
        light._cancel_light_auto_off_timer()

    async def test_both_modes_switch_to_the_requested_independent_record(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        rgb_record = _capability(
            OCTO_FEATURE_LIGHT_RGB,
            b"\x01\xa7",
            bytes((1, 2, 3)),
            value_type=0x03,
        )
        rgbwi_record = _capability(
            OCTO_FEATURE_LIGHT_RGBWI,
            b"\x01\xcc",
            bytes((11, 22, 33, 44, 77)),
            value_type=0x05,
        )
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01"),
            rgb_record,
            rgbwi_record,
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light.hass = hass
        assert light.supported_color_modes == {ColorMode.RGB, ColorMode.RGBW}
        assert light.color_mode == ColorMode.RGBW
        assert light.rgb_color == (1, 2, 3)
        assert light.rgbw_color == (11, 22, 33, 44)
        assert light.brightness == 77

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(**{ATTR_RGB_COLOR: (40, 50, 60)})

        expected_rgb = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x07, 0x00, 0x02, 0x01, 0xA7, 0x03, 40, 50, 60],
        )
        assert mock_bleak_client.write_gatt_char.call_args_list[-1].args[1] == expected_rgb
        assert controller._capability_records[OCTO_FEATURE_LIGHT_RGBWI] == rgbwi_record
        assert light.color_mode == ColorMode.RGB
        assert light.rgb_color == (40, 50, 60)
        assert light.rgbw_color == (11, 22, 33, 44)
        assert light.brightness == 77

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(**{ATTR_RGBW_COLOR: (100, 110, 120, 130), "brightness": 140})

        expected_rgbwi = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x02, 0x01, 0xCC, 0x05, 100, 110, 120, 130, 140],
        )
        assert mock_bleak_client.write_gatt_char.call_args_list[-1].args[1] == expected_rgbwi
        assert controller._capability_records[OCTO_FEATURE_LIGHT_RGB].value == bytes((40, 50, 60))
        assert light.color_mode == ColorMode.RGBW
        assert light.rgb_color == (40, 50, 60)
        assert light.rgbw_color == (100, 110, 120, 130)
        assert light.brightness == 140
        light._cancel_light_auto_off_timer()

    async def test_rgbwi_intensity_zero_survives_initial_state_updates_and_writes(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((12, 34, 56, 78, 0)),
                value_type=0x05,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light.hass = hass
        assert light.brightness == 0
        light.async_write_ha_state = MagicMock()
        light._attr_brightness = 9
        light._handle_light_state({"light_intensity": 0})
        assert light.brightness == 0

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(brightness=0)

        expected = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 12, 34, 56, 78, 0],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID, expected, response=False
        )
        assert light.brightness == 0
        light._cancel_light_auto_off_timer()

    async def test_pin_only_state_transitions_publish_light_availability(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_PIN, b"\x01", b"\x01\x01"),
            _capability(
                OCTO_FEATURE_LIGHT_RGB,
                b"\x01",
                bytes((20, 30, 40)),
                value_type=0x03,
            ),
        )
        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light._attr_is_on = True
        light.async_write_ha_state = MagicMock()
        remove_callback = coordinator.register_controller_state_callback(light._handle_light_state)
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.octo.OCTO_PIN_LOCK_RETRY_DELAY_SECONDS", 10
        )

        controller._handle_pin_notification(OCTO_SYSTEM_PIN_LOCK, [])
        assert light.available is False
        locked_write_count = light.async_write_ha_state.call_count
        assert locked_write_count >= 1

        await controller.stop_keepalive()
        controller._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])
        assert light.available is True
        assert light.async_write_ha_state.call_count > locked_write_count
        remove_callback()

    async def test_octolight_builder_preserves_incomplete_registry_and_retires_authoritatively(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ) -> None:
        from homeassistant.helpers import entity_registry as er

        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        registry = er.async_get(hass)
        unique_id = coordinator.entity_unique_id(LIGHT_DESCRIPTION.key)
        registry.async_get_or_create(
            "light",
            DOMAIN,
            unique_id,
            config_entry=mock_octo_config_entry,
            suggested_object_id="octo_test_light",
        )
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGB,
                b"\x01",
                bytes((1, 2, 3)),
                value_type=0x03,
            ),
        )

        controller._features_complete.clear()
        incomplete = _light_entities_for(hass, coordinator)
        assert incomplete == []
        assert registry.async_get_entity_id("light", DOMAIN, unique_id) is not None

        _activate_capabilities(controller)
        assert _light_entities_for(hass, coordinator) == []
        assert registry.async_get_entity_id("light", DOMAIN, unique_id) is None
        assert (
            registry.async_get_entity_id(
                "light",
                DOMAIN,
                coordinator.entity_unique_id("under_bed_lights_assumed"),
            )
            is None
        )

        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGB,
                b"\x01",
                bytes((4, 5, 6)),
                value_type=0x03,
            ),
        )
        regained = _light_entities_for(hass, coordinator)
        assert len(regained) == 1
        assert regained[0].unique_id == unique_id

    @pytest.mark.parametrize(
        ("characteristic", "readonly"),
        ((b"\x01", 1), (b"\x00", 0)),
    )
    async def test_readonly_or_gated_color_record_is_not_advertised(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        characteristic: bytes,
        readonly: int,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01"),
            _capability(
                OCTO_FEATURE_LIGHT_RGB,
                characteristic,
                bytes((1, 2, 3)),
                value_type=0x03,
                readonly=readonly,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        assert light.supported_color_modes == {ColorMode.ONOFF}
        assert light.color_mode == ColorMode.ONOFF
        with pytest.raises(ValueError, match="RGB color is not supported"):
            await light.async_turn_on(**{ATTR_RGB_COLOR: (40, 50, 60)})

    async def test_complete_capability_loss_and_regain_updates_active_mode(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT_RGB, b"\x01", bytes((1, 2, 3)), value_type=0x03),
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((11, 22, 33, 44, 77)),
                value_type=0x05,
            ),
        )
        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        assert light.supported_color_modes == {ColorMode.RGB, ColorMode.RGBW}

        _activate_capabilities(controller)
        with patch.object(light, "async_write_ha_state"):
            light._handle_light_state(
                {
                    "under_bed_lights_on": None,
                    "under_bed_lights_rgb": None,
                    "under_bed_lights_rgbw": None,
                    "light_intensity": None,
                }
            )
        assert light.supported_color_modes == set()
        assert light.color_mode is None
        assert light.available is False

        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT_RGB, b"\x01", bytes((90, 80, 70)), value_type=0x03),
        )
        with patch.object(light, "async_write_ha_state"):
            light._handle_light_state(
                {
                    "under_bed_lights_on": None,
                    "under_bed_lights_rgb": (90, 80, 70),
                    "under_bed_lights_rgbw": None,
                    "light_intensity": None,
                }
            )
        assert light.supported_color_modes == {ColorMode.RGB}
        assert light.color_mode == ColorMode.RGB
        assert light.rgb_color == (90, 80, 70)
        assert light.available is True

    def test_legacy_single_color_mode_derives_a_single_supported_mode(self) -> None:
        controller = object.__new__(OctoStar2Controller)
        with patch.object(
            BedController,
            "supported_color_mode",
            new_callable=PropertyMock,
            return_value="rgbw",
        ):
            assert controller.supported_color_modes == frozenset(("rgbw",))

    async def test_light_entity_uses_rgbw_color_mode(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """Light entity should use ColorMode.RGBW for RGBWI controllers."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((255, 255, 255, 255, 255)),
                value_type=0x05,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        assert light.color_mode == ColorMode.RGBW
        assert light.supported_color_modes == {ColorMode.RGBW}

    async def test_light_entity_default_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """Light entity should have a default RGBW color for RGBWI controllers."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((255, 255, 255, 255, 255)),
                value_type=0x05,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        assert light.rgbw_color == (255, 255, 255, 255)

    async def test_light_entity_without_rgbwi_uses_rgb(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
    ):
        """Light entity should fall back to ColorMode.RGB without RGBWI support."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        # _has_rgbwi defaults to False

        assert controller.supported_color_mode is None

    async def test_light_entity_turn_on_with_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Turning on with ATTR_RGBW_COLOR should call set_light_color_rgbw."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((255, 255, 255, 255, 80)),
                value_type=0x05,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light.hass = hass

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(**{ATTR_RGBW_COLOR: (100, 150, 200, 50)})

        # Verify the correct RGBWI packet was sent
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 100, 150, 200, 50, 80],
        )

        # Should have called lights_on() first, then set_light_color_rgbw()
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 2  # lights_on + set_light_color_rgbw

        # The RGBWI packet is the second call
        assert calls[1][0][1] == expected_packet

        assert light.is_on is True
        assert light.rgbw_color == (100, 150, 200, 50)
        light._cancel_light_auto_off_timer()

    async def test_light_entity_turn_on_uses_previous_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Turning on without color should use previously set RGBW color."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01"),
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((10, 20, 30, 40, 65)),
                value_type=0x05,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light.hass = hass
        # Set a specific color first
        light._attr_rgbw_color = (10, 20, 30, 40)

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on()

        # Should use the stored RGBW color
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 10, 20, 30, 40, 65],
        )
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[-1][0][1] == expected_packet
        light._cancel_light_auto_off_timer()

    async def test_light_entity_turn_off(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Turning off should send lights_off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01"),
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((255, 255, 255, 255, 255)),
                value_type=0x05,
            ),
        )

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light._attr_is_on = True  # Pretend it's on

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_off()

        # Should have called lights_off()
        expected_off = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x00],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_off,
            response=False,
        )
        assert light.is_on is False


class TestOctoCapabilityControls:
    """Settings update only the value bytes of their complete CAP record."""

    async def test_unrelated_settings_keep_latest_notification_owned_pin_state(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.handle_controller_state_updates = MagicMock()
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller.write_command = AsyncMock()
        pin = _capability(OCTO_FEATURE_PIN, b"\x01", b"\x01\x00")
        synchro = _capability(OCTO_FEATURE_SYNCHRO, b"\x01", b"\x00")
        controller._capability_records = {
            pin.feature_id: pin,
            synchro.feature_id: synchro,
        }
        controller._apply_capability_records(controller._capability_records)
        assert controller.normal_controls_available is False

        controller._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])
        assert controller.normal_controls_available is True

        await controller.set_synchro(True)

        assert controller._capability_records[OCTO_FEATURE_PIN] == pin
        assert controller._has_pin is True
        assert controller._pin_locked is False
        assert controller.normal_controls_available is True
        assert controller._capability_records[OCTO_FEATURE_SYNCHRO].value == b"\x01"

    async def test_setting_writes_preserve_each_advertised_record(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.handle_controller_state_updates = MagicMock()
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller.write_command = AsyncMock()

        records_and_actions = (
            (
                _capability(OCTO_FEATURE_SYNCHRO, b"\x01\xa1", b"\x00", value_type=0x31),
                lambda: controller.set_synchro(True),
                b"\x01",
            ),
            (
                _capability(
                    OCTO_FEATURE_REMOTE_CONTROL_LOCK, b"\x01\xa2", b"\x00", value_type=0x32
                ),
                lambda: controller.set_remote_control_lock(True),
                b"\x01",
            ),
            (
                _capability(OCTO_FEATURE_LIGHT, b"\x01\xa3", b"\x00", value_type=0x33),
                controller.lights_on,
                b"\x01",
            ),
            (
                _capability(
                    OCTO_FEATURE_LIGHT_DURATION,
                    b"\x01\xa4",
                    b"\x00\x05",
                    value_type=0x34,
                ),
                lambda: controller.set_light_duration(0),
                b"\x00\x00",
            ),
            (
                _capability(OCTO_FEATURE_LIGHT_AUTO, b"\x01\xa5", b"\x00", value_type=0x35),
                lambda: controller.set_automatic_light(True),
                b"\x01",
            ),
            (
                _capability(
                    OCTO_FEATURE_LIGHT_SENSITIVITY,
                    b"\x01\xa6",
                    b"\x00\x23",
                    value_type=0x36,
                ),
                lambda: controller.set_light_sensitivity(85),
                b"\x00\x55",
            ),
        )

        for record, action, new_value in records_and_actions:
            controller._capability_records = {record.feature_id: record}
            controller._apply_capability_records(controller._capability_records)
            await action()

            expected_payload = [
                (record.feature_id >> 16) & 0xFF,
                (record.feature_id >> 8) & 0xFF,
                record.feature_id & 0xFF,
                record.readonly,
                len(record.characteristic),
                *record.characteristic,
                record.value_type,
                *new_value,
            ]
            controller.write_command.assert_awaited_once()
            args = controller.write_command.await_args.args
            assert args[0] == controller._build_packet([0x20, 0x72], expected_payload)
            assert args[1:4] == (1, 100, None)
            if record.feature_id == OCTO_FEATURE_LIGHT_DURATION:
                assert controller._light_duration_minutes == 0
            controller.write_command.reset_mock()

    async def test_readonly_remote_teach_uses_exact_action_and_requires_unlocked_pin(
        self,
    ) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller._features_complete.set()
        controller.write_command = AsyncMock()
        record = _capability(
            OCTO_FEATURE_REMOTE_TEACH,
            b"\x01",
            b"\x01",
            value_type=1,
            readonly=1,
        )
        controller._capability_records = {record.feature_id: record}
        controller._apply_capability_records(controller._capability_records)
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True

        assert controller.supports_remote_teach is True
        assert controller.controller_button_available("octo_remote_teach") is False
        with pytest.raises(PermissionError, match="PIN must be unlocked"):
            await controller.teach_remote()
        controller.write_command.assert_not_awaited()

        controller._pin_locked = False
        assert controller.controller_button_available("octo_remote_teach") is True
        await controller.teach_remote()

        expected = controller._build_packet(
            [0x20, 0x72], [0x00, 0x00, 0x10, 0x01, 0x01, 0x01, 0x01, 0x01]
        )
        controller.write_command.assert_awaited_once_with(expected, 1, 100, None)

    async def test_setting_writer_rejects_readonly_or_inactive_record(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller.write_command = AsyncMock()
        readonly = _capability(
            OCTO_FEATURE_REMOTE_CONTROL_LOCK,
            b"\x01",
            b"\x00",
            readonly=1,
        )
        controller._capability_records = {readonly.feature_id: readonly}
        controller._apply_capability_records(controller._capability_records)

        assert controller.supports_remote_control_lock is False
        with pytest.raises(ValueError, match="not available"):
            await controller.set_remote_control_lock(True)
        controller.write_command.assert_not_awaited()

    async def test_light_duration_reports_positive_timeout_and_permanent_zero(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.handle_controller_state_updates = MagicMock()
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller.write_command = AsyncMock()
        record = _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x05")
        light = _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00")
        controller._capability_records = {record.feature_id: record, light.feature_id: light}
        controller._apply_capability_records(controller._capability_records)

        assert controller.light_auto_off_seconds == 300
        assert controller.controller_number_specs[0].native_min_value == 0
        assert controller.controller_number_specs[0].native_max_value == 60

        await controller.set_light_duration(0)

        assert controller._light_duration_minutes == 0
        assert controller.light_auto_off_seconds is None
        assert (
            coordinator.handle_controller_state_updates.call_args.args[0]["octo_light_duration"]
            == 0
        )

    def test_light_duration_absence_uses_legacy_five_minute_default(self) -> None:
        coordinator = MagicMock(motor_count=2)
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        light = _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00")
        controller._capability_records = {light.feature_id: light}
        controller._apply_capability_records(controller._capability_records)

        assert controller.light_auto_off_seconds == 300

    @pytest.mark.parametrize("malformed_duration", (b"\x05", b"\x00\x3d"))
    def test_malformed_light_duration_does_not_become_legacy_default(
        self, malformed_duration: bytes
    ) -> None:
        coordinator = MagicMock(motor_count=2)
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        light = _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00")
        duration = _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", malformed_duration)
        controller._capability_records = {light.feature_id: light, duration.feature_id: duration}
        controller._apply_capability_records(controller._capability_records)

        assert controller.light_auto_off_seconds is None

    async def test_onoff_only_light_keeps_legacy_switch_entity_identity(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ) -> None:
        from homeassistant.helpers import entity_registry as er

        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
        )
        registry = er.async_get(hass)
        unique_id = coordinator.entity_unique_id("under_bed_lights")
        legacy_row = registry.async_get_or_create(
            "switch",
            DOMAIN,
            unique_id,
            config_entry=mock_octo_config_entry,
            suggested_object_id="octo_under_bed_lights",
        )

        switches = _switch_entities_for(hass, coordinator)
        legacy_switches = [
            entity for entity in switches if entity.entity_description.key == "under_bed_lights"
        ]
        assert legacy_switches, "the legacy OCTO switch entity must remain registered"
        legacy_switch = legacy_switches[0]

        assert isinstance(legacy_switch, AdjustableBedSwitch)
        assert legacy_switch.unique_id == unique_id
        assert registry.async_get_entity_id("switch", DOMAIN, unique_id) == legacy_row.entity_id
        assert _light_entities_for(hass, coordinator) == []

        controller.lights_on = AsyncMock()

        async def execute(command, **_kwargs):
            await command(controller)

        coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
        legacy_switch.hass = hass
        legacy_switch.async_write_ha_state = MagicMock()
        await legacy_switch.async_added_to_hass()
        timers: list[tuple[float, Callable[[], None], MagicMock]] = []

        def capture_auto_off(
            delay: float,
            callback: Callable[..., None],
            *args: object,
        ) -> object:
            handle = MagicMock()
            timers.append((delay, lambda: callback(*args), handle))
            return handle

        try:
            with patch.object(hass.loop, "call_later", side_effect=capture_auto_off):
                await legacy_switch.async_turn_on()
                assert len(timers) == 1 and timers[0][0] == 300

                light_record = controller._capability_records[OCTO_FEATURE_LIGHT]
                controller._capability_records[OCTO_FEATURE_LIGHT] = light_record.with_value(
                    b"\x01"
                )
                controller._publish_capability_state()
                assert len(timers) == 1 and not timers[0][2].cancel.called

                # A deliberate repeated ON restarts the bed's hardware timeout;
                # identical state telemetry above leaves that deadline alone.
                await legacy_switch.async_turn_on()
                assert len(timers) == 2 and timers[0][2].cancel.called
                assert timers[1][0] == 300 and not timers[1][2].cancel.called
                controller._publish_capability_state()
                assert len(timers) == 2 and not timers[1][2].cancel.called

                records = dict(controller._capability_records)
                duration = _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x02")
                records[duration.feature_id] = duration
                controller._capability_records = records
                controller._apply_capability_records(records)
                controller._publish_capability_state()
                assert len(timers) == 3 and timers[1][2].cancel.called
                assert timers[2][0] == 120 and not timers[2][2].cancel.called
                controller._publish_capability_state()
                assert len(timers) == 3 and not timers[2][2].cancel.called

                await legacy_switch.async_turn_on()
                assert len(timers) == 4 and timers[2][2].cancel.called
                assert timers[3][0] == 120 and not timers[3][2].cancel.called

                replacement = OctoController(
                    coordinator, capability_snapshot=controller.capability_snapshot()
                )
                replacement._session_ready = True
                coordinator._controller = replacement
                coordinator._offline_controller = replacement
                replacement._publish_capability_state()
                assert len(timers) == 4, (
                    [delay for delay, _callback, _handle in timers],
                    replacement.light_auto_off_seconds,
                    legacy_switch._octo_light_auto_off_seconds,
                )
                assert not timers[3][2].cancel.called

                writes_before_expiry = mock_bleak_client.write_gatt_char.call_count
                for _delay, stale_callback, _handle in timers[:3]:
                    stale_callback()
                assert legacy_switch.is_on is True
                assert replacement._capability_records[OCTO_FEATURE_LIGHT].value == b"\x01"
                timers[3][1]()

            assert legacy_switch.is_on is False
            assert replacement._capability_records[OCTO_FEATURE_LIGHT].value == b"\x00"
            assert mock_bleak_client.write_gatt_char.call_count == writes_before_expiry
        finally:
            await legacy_switch.async_will_remove_from_hass()
            await controller.stop_keepalive()

    async def test_missing_capability_fallback_exposes_legacy_light_switch(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        controller = OctoController(coordinator)
        coordinator._controller = controller
        controller._session_ready = True
        controller._legacy_assumed_lights = True
        controller._has_lights = True

        switches = _switch_entities_for(hass, coordinator)
        under_bed_switches = [
            entity for entity in switches if entity.entity_description.key == "under_bed_lights"
        ]
        assert under_bed_switches, "missing OCTO capabilities retain the legacy light switch"
        under_bed_switch = under_bed_switches[0]

        assert isinstance(under_bed_switch, AdjustableBedSwitch)
        assert under_bed_switch.unique_id == coordinator.entity_unique_id("under_bed_lights")
        assert controller._capability_records == {}
        assert _light_entities_for(hass, coordinator) == []

    @pytest.mark.parametrize("finish", ["expire", "off", "remove", "failed_off"])
    async def test_color_light_tracks_hardware_timeout(self, hass, finish):
        coordinator = MagicMock(motor_count=2)
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        coordinator.controller = coordinator.capability_controller = controller
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
            _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x05"),
            _capability(OCTO_FEATURE_LIGHT_RGB, b"\x01", bytes((12, 34, 56)), value_type=0x03),
        )
        controller.lights_on = AsyncMock()
        controller.lights_off = AsyncMock()
        controller.set_light_color = AsyncMock()

        async def execute(command, **_kwargs):
            await command(controller)

        coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        light.hass = hass
        timer = MagicMock()
        with (
            patch.object(hass.loop, "call_later", return_value=timer) as schedule,
            patch.object(light, "async_write_ha_state"),
            patch.object(controller, "on_light_auto_off") as expired,
        ):
            await light.async_turn_on()
            assert light.is_on is True
            assert schedule.call_args.args[0] == 300
            expire = schedule.call_args.args[1]
            if finish == "off":
                await light.async_turn_off()
                assert light.is_on is False
                timer.cancel.assert_called_once()
                expired.assert_not_called()
            elif finish == "remove":
                await light.async_will_remove_from_hass()
                timer.cancel.assert_called_once()
                expired.assert_not_called()
            else:
                if finish == "failed_off":
                    controller.lights_off.side_effect = RuntimeError("disconnected")
                    with pytest.raises(RuntimeError, match="disconnected"):
                        await light.async_turn_off()
                    assert light.is_on is True
                    timer.cancel.assert_not_called()
                expire()
                assert light.is_on is False
                expired.assert_called_once()
            assert light._light_auto_off_timer is None

    def test_light_auto_off_updates_readonly_observation_without_granting_write_access(self):
        coordinator = MagicMock(motor_count=2)
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        controller.write_command = AsyncMock()
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01", readonly=1),
            _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x05"),
        )

        assert controller.supports_discrete_light_control is False
        controller.on_light_auto_off()

        record = controller._capability_records[OCTO_FEATURE_LIGHT]
        assert record.readonly == 1
        assert record.value == b"\x00"
        controller.write_command.assert_not_awaited()

    async def test_remote_lock_switch_ignores_light_auto_off_timer(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
            _capability(OCTO_FEATURE_PIN, b"\x01", b"\x00\x01"),
            _capability(OCTO_FEATURE_REMOTE_CONTROL_LOCK, b"\x01", b"\x00"),
            _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x05"),
        )
        assert controller.light_auto_off_seconds == 300
        controller.write_command = AsyncMock()

        async def execute(command, **_kwargs):
            await command(controller)

        coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
        lock_description = next(
            description
            for description in SWITCH_DESCRIPTIONS
            if description.key == "remote_control_lock"
        )
        lock_switch = AdjustableBedSwitch(coordinator, lock_description)
        lock_switch.hass = hass
        await lock_switch.async_added_to_hass()
        auto_off_callbacks: list[Callable[[], None]] = []
        original_call_later = hass.loop.call_later

        def capture_auto_off(
            delay: float,
            callback: Callable[..., None],
            *args: object,
        ) -> object:
            if getattr(callback, "__name__", "") == "auto_off_callback":
                auto_off_callbacks.append(lambda: callback(*args))
                return MagicMock()
            return original_call_later(delay, callback, *args)

        auto_off_handler = MagicMock(wraps=controller.on_light_auto_off)
        monkeypatch.setattr(controller, "on_light_auto_off", auto_off_handler)
        try:
            with (
                patch.object(hass.loop, "call_later", side_effect=capture_auto_off),
                patch.object(lock_switch, "async_write_ha_state"),
            ):
                await lock_switch.async_turn_on()
                assert lock_switch.is_on is True

                controller._remote_lock_active = False
                controller._publish_capability_state()
                assert lock_switch.is_on is False
                controller._remote_lock_active = True
                controller._publish_capability_state()
                assert lock_switch.is_on is True

                for callback in auto_off_callbacks:
                    callback()
                await hass.async_block_till_done()

            assert auto_off_callbacks == []
            auto_off_handler.assert_not_called()
            assert lock_switch.is_on is True
        finally:
            await lock_switch.async_will_remove_from_hass()

    async def test_octo_light_expiry_tracks_only_light_state_and_cleans_up(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The replacement light owns expiry, duration changes, and stale cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            controller,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
            _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x05"),
            _capability(OCTO_FEATURE_LIGHT_RGB, b"\x01", bytes((12, 34, 56)), value_type=0x03),
        )
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        light_unique_id = coordinator.entity_unique_id(LIGHT_DESCRIPTION.key)
        registry.async_get_or_create(
            "switch",
            DOMAIN,
            light_unique_id,
            config_entry=mock_octo_config_entry,
        )
        lights = _light_entities_for(hass, coordinator)
        assert len(lights) == 1 and isinstance(lights[0], AdjustableBedLight)
        assert registry.async_get_entity_id("switch", DOMAIN, light_unique_id) is not None
        light = lights[0]
        light.hass = hass
        await light.async_added_to_hass()

        timers: list[tuple[float, Callable[[], None], MagicMock]] = []
        original_call_later = hass.loop.call_later

        def capture_auto_off(
            delay: float,
            callback: Callable[..., None],
            *args: object,
        ) -> object:
            if getattr(callback, "__name__", "") == "auto_off_callback":
                handle = MagicMock()
                timers.append((delay, lambda: callback(*args), handle))
                return handle
            return original_call_later(delay, callback, *args)

        auto_off_handler = MagicMock(wraps=controller.on_light_auto_off)
        monkeypatch.setattr(controller, "on_light_auto_off", auto_off_handler)
        mock_bleak_client.write_gatt_char.reset_mock()
        try:
            with (
                patch.object(hass.loop, "call_later", side_effect=capture_auto_off),
                patch.object(light, "async_write_ha_state"),
            ):
                await light.async_turn_on()
                assert light.is_on is True
                assert len(timers) == 1 and timers[0][0] == 300

                controller._publish_capability_state()
                controller.forward_controller_state_updates({"automatic_light": True})
                assert len(timers) == 1
                assert timers[0][2].cancel.called is False

                await controller.set_light_duration(6)
                assert len(timers) == 2 and timers[1][0] == 360
                assert timers[0][2].cancel.called

                await light.async_turn_off()
                assert light.is_on is False
                assert timers[1][2].cancel.called

                current_light_record = controller._capability_records[OCTO_FEATURE_LIGHT]
                controller._capability_records[OCTO_FEATURE_LIGHT] = (
                    current_light_record.with_value(b"\x01")
                )
                controller._publish_capability_state()
                assert light.is_on is True
                assert len(timers) == 3 and timers[2][0] == 360

                timers[1][1]()  # canceled callbacks are still guarded by generation
                auto_off_handler.assert_not_called()
                writes_before_expiry = mock_bleak_client.write_gatt_char.call_count
                timers[2][1]()
                assert light.is_on is False
                auto_off_handler.assert_called_once()
                assert mock_bleak_client.write_gatt_char.call_count == writes_before_expiry

                await light.async_turn_on()
                assert len(timers) == 4
                await light.async_will_remove_from_hass()
                assert timers[3][2].cancel.called
                timers[3][1]()
                assert light.is_on is True
        finally:
            if getattr(light, "_unregister_light_state", None) is not None:
                await light.async_will_remove_from_hass()

    async def test_octo_light_expiry_survives_equivalent_controller_reconnect(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unchanged deadline expires against the new authoritative controller."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        original = cast(OctoController, coordinator.controller)
        _activate_capabilities(
            original,
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x00"),
            _capability(
                OCTO_FEATURE_LIGHT_RGB,
                b"\x01",
                bytes((10, 20, 30)),
                value_type=0x03,
            ),
            _capability(OCTO_FEATURE_LIGHT_DURATION, b"\x01", b"\x00\x05"),
        )
        lights = _light_entities_for(hass, coordinator)
        assert len(lights) == 1 and isinstance(lights[0], AdjustableBedLight)
        light = lights[0]
        light.hass = hass
        await light.async_added_to_hass()

        timers: list[tuple[float, Callable[[], None], MagicMock]] = []
        original_call_later = hass.loop.call_later

        def capture_auto_off(
            delay: float,
            callback: Callable[..., None],
            *args: object,
        ) -> object:
            if getattr(callback, "__name__", "") == "auto_off_callback":
                handle = MagicMock()
                timers.append((delay, lambda: callback(*args), handle))
                return handle
            return original_call_later(delay, callback, *args)

        try:
            with (
                patch.object(hass.loop, "call_later", side_effect=capture_auto_off),
                patch.object(light, "async_write_ha_state"),
            ):
                await light.async_turn_on()
                assert light.is_on is True
                assert len(timers) == 1 and timers[0][0] == 300
                assert timers[0][2].cancel.called is False

                replacement = OctoController(
                    coordinator, capability_snapshot=original.capability_snapshot()
                )
                replacement._session_ready = True
                coordinator._controller = replacement
                coordinator._offline_controller = replacement
                replacement._publish_capability_state()

                assert light.is_on is True
                assert len(timers) == 1
                assert timers[0][2].cancel.called is False
                writes_before_expiry = mock_bleak_client.write_gatt_char.call_count
                timers[0][1]()

                assert light.is_on is False
                assert light._light_auto_off_timer is None
                assert replacement._capability_records[OCTO_FEATURE_LIGHT].value == b"\x00"
                assert mock_bleak_client.write_gatt_char.call_count == writes_before_expiry
        finally:
            await light.async_will_remove_from_hass()
            await original.stop_keepalive()

    async def test_confirmed_reset_packet_disconnects_after_five_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.entry.data = {}
        coordinator.hass = MagicMock()
        coordinator.async_disconnect = AsyncMock()
        controller = OctoController(coordinator)
        controller._session_ready = True
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = False
        controller.write_command = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.octo.asyncio.sleep", sleep)

        await controller.reset_defaults()

        packet = controller.write_command.await_args.args[0]
        assert packet == controller._build_packet([0x20, OCTO_SYSTEM_SET_DEFAULT_CONFIG])
        assert isinstance(controller.write_command.await_args.args[3], asyncio.Event)
        background_task = coordinator.entry.async_create_background_task.call_args.args[1]
        await background_task

        sleep.assert_awaited_once_with(5)
        coordinator.async_disconnect.assert_awaited_once_with(serialize_with_commands=True)

    async def test_reset_rejects_missing_session_or_locked_pin(self) -> None:
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        controller = OctoController(coordinator)
        controller.write_command = AsyncMock()

        with pytest.raises(PermissionError, match="unlocked session"):
            await controller.reset_defaults()

        controller._session_ready = True
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True
        with pytest.raises(PermissionError, match="unlocked session"):
            await controller.reset_defaults()
        controller.write_command.assert_not_awaited()


class TestCapabilitySnapshot:
    """Phase 2.5 C3a: a live controller's discovered capabilities round-trip
    through a JSON snapshot so an OFFLINE paired side mints with the same gating."""

    @staticmethod
    def _coord():
        from types import SimpleNamespace

        return SimpleNamespace(
            motor_count=2,
            entry=SimpleNamespace(data={}),
            handle_controller_state_updates=lambda _updates: None,
        )

    def test_snapshot_roundtrip_restores_entity_gating(self):
        live = OctoController(self._coord())
        records = (
            _capability(OCTO_FEATURE_PIN, b"\x01", b"\x01\x01"),
            _capability(OCTO_FEATURE_MOTORCOUNT, b"\x02", b"\x00"),
            _capability(OCTO_FEATURE_MEMCOUNT, b"\x04", b"\x00"),
            _capability(OCTO_FEATURE_LIGHT, b"\x01", b"\x01"),
            _capability(
                OCTO_FEATURE_LIGHT_RGBWI,
                b"\x01",
                bytes((1, 2, 3, 4, 90)),
                value_type=0x05,
            ),
            _capability(OCTO_FEATURE_SYNCHRO, b"\x01", b"\x01"),
        )
        live._capability_records = {record.feature_id: record for record in records}
        live._apply_capability_records(live._capability_records)
        # A real discovery completes by receiving the 0xFFFFFF CAP_END sentinel,
        # which proves the record set is complete and makes the snapshot real.
        live._pending_capability_records = dict(live._capability_records)
        live._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])

        snap = live.capability_snapshot()
        assert snap is not None
        assert snap["device_info"] is None
        assert snap["capability_records"][str(OCTO_FEATURE_LIGHT_RGBWI)] == {
            "readonly": 0,
            "characteristic": [1],
            "value_type": 0x05,
            "value": [1, 2, 3, 4, 90],
        }

        # Minting a fresh controller from the snapshot restores entity gating
        # without any live discovery.
        offline = OctoController(self._coord(), capability_snapshot=snap)
        assert offline.supports_lights is True
        assert offline.supports_light_color_control is True
        assert offline.supports_memory_presets is True
        assert offline.supports_synchro is True

    def test_no_snapshot_when_nothing_discovered(self):
        # An all-unknown controller yields no snapshot (don't persist over a real
        # one with all-None).
        controller = OctoController(self._coord())
        assert controller.capability_snapshot() is None
        assert not controller.controller_entity_discovery_complete

    def test_no_snapshot_from_timeout_fallback(self):
        # When discover_features() times out it fills compatibility DEFAULTS
        # (has_lights=True, memory=0, synchro=False, pin from config) but never
        # sets _features_complete (no CAP_END sentinel). Those fallback values
        # must NOT be snapshotted — persisting them would overwrite a side's real
        # descriptor and mint a reduced offline profile on the next reload.
        controller = OctoController(self._coord())
        controller._has_lights = True  # fallback default (assume lights exist)
        controller._memory_count = 0
        controller._has_synchro = False
        controller._has_pin = True
        controller._pin_locked = True
        assert controller._features_complete.is_set() is False
        assert controller.capability_snapshot() is None

        # Only the real sentinel makes a complete current record set authoritative.
        controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])
        assert controller.controller_entity_discovery_complete
        assert controller.capability_snapshot() is not None

    def test_snapshots_keep_each_physical_receivers_records_independent(self) -> None:
        left_coordinator = self._coord()
        right_coordinator = self._coord()
        left = OctoController(left_coordinator)
        right = OctoController(right_coordinator)
        left_record = _capability(
            OCTO_FEATURE_LIGHT_RGB, b"\x01\xa1", bytes((1, 2, 3)), value_type=0x31
        )
        right_record = _capability(
            OCTO_FEATURE_LIGHT_RGB, b"\x01\xa2", bytes((9, 8, 7)), value_type=0x32
        )
        left._capability_records = {left_record.feature_id: left_record}
        right._capability_records = {right_record.feature_id: right_record}
        left._apply_capability_records(left._capability_records)
        right._apply_capability_records(right._capability_records)
        left._device_info = {"cid": 1, "firmware": 2, "pid": 3, "hardware": 4}
        right._device_info = {"cid": 5, "firmware": 6, "pid": 7, "hardware": 8}
        left._pending_capability_records = dict(left._capability_records)
        right._pending_capability_records = dict(right._capability_records)
        left._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])
        right._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])

        left_offline = OctoController(
            left_coordinator, capability_snapshot=left.capability_snapshot()
        )
        right_offline = OctoController(
            right_coordinator, capability_snapshot=right.capability_snapshot()
        )

        assert left_offline._device_info != right_offline._device_info
        assert left_offline._capability_records[OCTO_FEATURE_LIGHT_RGB] == left_record
        assert right_offline._capability_records[OCTO_FEATURE_LIGHT_RGB] == right_record
        left_offline._capability_records[OCTO_FEATURE_LIGHT_RGB] = left_record.with_value(
            bytes((4, 5, 6))
        )
        assert right_offline._capability_records[OCTO_FEATURE_LIGHT_RGB] == right_record


class TestOctoDynamicEntities:
    """Complete discovery retires identities; incomplete scans preserve them."""

    def test_incomplete_discovery_preserves_known_ids_then_allows_regain(self) -> None:
        from custom_components.adjustable_bed.entity_discovery import async_setup_dynamic_entities

        coordinator = MagicMock()
        controller = OctoController(coordinator)
        controller._apply_capability_records({})
        controller._features_complete.set()
        controller._capability_records_authoritative = True
        coordinator.capability_controller = controller
        coordinator.register_controller_state_callback = MagicMock()
        entry = MagicMock()
        add = MagicMock()
        initial = MagicMock()
        initial.unique_id = "bed_octo_light"
        regained = MagicMock()
        regained.unique_id = "bed_octo_light"
        current = [initial]
        async_setup_dynamic_entities(entry, coordinator, add, lambda: tuple(current))
        callback = coordinator.register_controller_state_callback.call_args.args[0]
        add.assert_called_once_with([initial])

        controller._features_complete.clear()
        callback({})  # failed/incomplete discovery retains the prior surface
        assert add.call_count == 1

        controller._handle_feature_response([0xFF, 0xFF, 0xFF, 0, 0, 0])
        current.clear()  # the complete capability set retires the Octo-owned row
        callback({})
        assert add.call_count == 1

        current.append(regained)
        callback({})  # a later complete list can add the same stable ID again
        assert add.call_count == 2
        assert add.call_args.args == ([regained],)
        snapshot = controller.capability_snapshot()
        assert snapshot is not None
        assert snapshot["has_pin"] is None
        assert snapshot["pin_locked"] is None
        assert snapshot["has_lights"] is False
        assert snapshot["memory_count"] == 0


class TestMemPosRelease:
    """Phase 2.5 C4: a memory recall always releases the motors, even when the
    stream fails part-way, because the STOP frame lives in a finally block.

    The streaming cadence itself is covered end-to-end by
    TestOctoMemoryInfoAndCombinedStep.
    """

    @staticmethod
    def _ctrl():
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.cancel_command = asyncio.Event()
        coordinator.handle_controller_state_updates = MagicMock()
        ctrl = OctoController(coordinator)
        ctrl._memory_count = 4  # supports memory presets
        return ctrl

    async def test_preset_memory_stops_even_if_stream_raises(self):
        ctrl = self._ctrl()
        ctrl.send_pin = AsyncMock()
        ctrl._write_octo_command = AsyncMock(side_effect=RuntimeError("boom"))
        ctrl._stop_motors = AsyncMock()
        with pytest.raises(RuntimeError):
            await ctrl.preset_memory(1)
        ctrl._stop_motors.assert_awaited_once()


class TestPinReauth:
    """A PIN_LOCK stops serialized movement before bounded PIN recovery."""

    @staticmethod
    def _ctrl():
        coordinator = MagicMock()
        coordinator.motor_count = 2
        coordinator.entry.data = {}
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.cancel_command = asyncio.Event()
        coordinator.handle_controller_state_updates = MagicMock()
        order: list[str] = []
        controller = OctoController(coordinator, pin="1234")
        controller._session_ready = True
        controller._pin_feature_active = True
        controller._has_pin = True

        async def _stop() -> None:
            order.append("stop")

        coordinator.async_stop_command = AsyncMock(side_effect=_stop)

        async def _execute(command, **_kwargs):
            order.append("execute")
            await controller.async_wait_for_pin_acceptance(coordinator.cancel_command)
            await command(controller)

        coordinator.async_execute_controller_command = AsyncMock(side_effect=_execute)

        async def _send_pin() -> None:
            order.append("pin")
            controller._pin_retry_auth_sent = controller._pin_retry_pending
            controller._pin_sent = True
            controller._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])

        controller.send_pin = AsyncMock(side_effect=_send_pin)
        return controller, coordinator, order

    async def test_pin_lock_schedules_resend(self, monkeypatch: pytest.MonkeyPatch):
        ctrl, coordinator, order = self._ctrl()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.octo.OCTO_PIN_LOCK_RETRY_DELAY_SECONDS", 0
        )
        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_LOCK, [])
        assert ctrl._pin_locked is True
        assert ctrl._pin_resend_task is not None
        await ctrl._pin_resend_task
        coordinator.async_stop_command.assert_awaited_once()
        assert order == ["stop", "execute", "pin"]
        ctrl.send_pin.assert_awaited_once()

    async def test_pin_lock_waits_exactly_one_second(self, monkeypatch: pytest.MonkeyPatch):
        ctrl, coordinator, order = self._ctrl()
        sleep = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.octo.asyncio.sleep", sleep)

        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_LOCK, [])
        assert ctrl._pin_resend_task is not None
        await ctrl._pin_resend_task

        sleep.assert_awaited_once_with(1.0)
        coordinator.async_stop_command.assert_awaited_once()
        assert order == ["stop", "execute", "pin"]
        ctrl.send_pin.assert_awaited_once()

    async def test_pin_lock_preempts_real_scheduled_held_control_before_reauth(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The real scheduler releases an active bounded hold before PIN retry."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._pin = "1234"
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = False
        controller._features_complete.set()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.octo.OCTO_PIN_LOCK_RETRY_DELAY_SECONDS", 0
        )

        packets: list[bytes] = []
        hold_write_started = asyncio.Event()
        move = controller._build_packet([0x02, 0x70], [OCTO_MOTOR_HEAD])
        stop = controller._build_packet([0x02, 0x73])
        pin = controller._build_packet([0x20, 0x43], [1, 2, 3, 4])

        async def scheduled_write(
            command: bytes,
            repeat_count: int = 1,
            repeat_delay_ms: int = 100,
            cancel_event: asyncio.Event | None = None,
        ) -> None:
            del repeat_count, repeat_delay_ms
            packets.append(command)
            if command == move:
                hold_write_started.set()
                assert cancel_event is not None
                await cancel_event.wait()
            elif command == pin:
                controller._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])

        monkeypatch.setattr(controller, "write_command", scheduled_write)
        mock_bleak_client.write_gatt_char.reset_mock()
        hold_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda active: cast(OctoController, active).hold_control("back_up", 60_000),
                cancel_running=False,
                read_positions_after_operation=False,
            )
        )
        await hold_write_started.wait()
        controller._handle_pin_notification(OCTO_SYSTEM_PIN_LOCK, [])
        retry_task = controller._pin_resend_task
        assert retry_task is not None

        await retry_task
        await hold_task

        assert packets[0] == move
        assert packets[-1] == pin
        assert packets.count(stop) == 2  # hold's fresh cleanup, then scheduler STOP
        assert controller.normal_controls_available is True

    async def test_fragmented_pin_lock_notification_schedules_resend(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A PIN challenge split across notifications is handled after reassembly."""
        ctrl, coordinator, order = self._ctrl()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.octo.OCTO_PIN_LOCK_RETRY_DELAY_SECONDS", 0
        )
        response = _build_octo_response(
            ctrl,
            (0x21, OCTO_SYSTEM_PIN_LOCK),
            [],
        )

        ctrl._on_notification(MagicMock(), bytearray(response[:4]))
        initial_resend_task = ctrl._pin_resend_task
        assert initial_resend_task is None
        ctrl._on_notification(MagicMock(), bytearray(response[4:]))

        assert ctrl._pin_locked is True
        resend_task = ctrl._pin_resend_task
        assert resend_task is not None
        await resend_task
        coordinator.async_stop_command.assert_awaited_once()
        assert order == ["stop", "execute", "pin"]
        ctrl.send_pin.assert_awaited_once()

    async def test_pin_state_tracks_lock(self):
        ctrl, _coordinator, _order = self._ctrl()
        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])  # unlocked
        assert ctrl._pin_locked is False
        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [0])  # locked
        assert ctrl._pin_locked is True

    async def test_pin_acceptance_wait_distinguishes_rejection_timeout_cancel_and_stale_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        rejected, _coordinator, _order = self._ctrl()
        rejected._pin_sent = True
        rejected._pin_locked = True
        rejected._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [0])
        with pytest.raises(PermissionError, match="rejected"):
            await rejected.async_wait_for_pin_acceptance(asyncio.Event())

        timed_out, _coordinator, _order = self._ctrl()
        timed_out._pin_sent = True
        timed_out._pin_locked = True
        timed_out._pin_state_event.clear()
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.octo.OCTO_PIN_ACCEPTANCE_TIMEOUT", 0
        )
        with pytest.raises(TimeoutError, match="Timed out"):
            await timed_out.async_wait_for_pin_acceptance(asyncio.Event())

        cancelled, _coordinator, _order = self._ctrl()
        cancelled._pin_sent = True
        cancelled._pin_locked = True
        cancel_event = asyncio.Event()
        cancel_event.set()
        with pytest.raises(asyncio.CancelledError):
            await cancelled.async_wait_for_pin_acceptance(cancel_event)

        stale, _coordinator, _order = self._ctrl()
        stale._pin_sent = False
        stale._pin_retry_pending = False
        stale.send_pin = AsyncMock(side_effect=stale.on_disconnect)
        with pytest.raises(ConnectionError, match="session changed"):
            await stale.async_wait_for_pin_acceptance(asyncio.Event())


class TestOctoPinLockDiagnostics:
    """A PIN-locked receiver accepts lights but ignores motors - say so."""

    def test_protocol_diagnostics_reports_discovery_state_without_leaking_pin(self):
        """The bundle needs the resolved capabilities, never the PIN itself."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.client = None
        controller = OctoController(coordinator, pin="1234")

        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True
        controller._has_lights = True
        controller._memory_count = 2
        controller._discovered_motor_count = 2
        controller._features_complete.set()
        controller._capability_records_authoritative = True

        state = controller.protocol_diagnostics

        assert state["feature_discovery_complete"] is True
        assert state["has_pin"] is True
        assert state["pin_locked"] is True
        assert state["pin_configured"] is True
        assert state["pin_sent"] is False
        assert state["memory_count"] == 2
        assert state["discovered_motor_count"] == 2
        assert "1234" not in str(state)

    def test_protocol_diagnostics_distinguishes_undiscovered_features(self):
        """None means the capability was never reported, not that it is absent."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.client = None
        controller = OctoController(coordinator)

        state = controller.protocol_diagnostics

        assert state["feature_discovery_complete"] is False
        assert state["has_pin"] is None
        assert state["has_lights"] is None
        assert state["pin_configured"] is False

    @pytest.mark.parametrize(
        ("has_pin", "pin_locked", "pin", "expected"),
        [
            (True, True, "", True),
            (True, True, "1234", False),
            (True, False, "", False),
            (False, False, "", False),
            # Discovery never resolved CAP_PIN: unknown, not "unlocked".
            (None, None, "", None),
        ],
    )
    def test_pin_locked_without_pin(
        self, has_pin: bool | None, pin_locked: bool | None, pin: str, expected: bool | None
    ):
        """Only a discovered lock with no configured PIN counts as the bad state."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.client = None
        controller = OctoController(coordinator, pin=pin)
        controller._pin_feature_active = has_pin
        controller._has_pin = has_pin
        controller._pin_locked = pin_locked

        assert controller.pin_locked_without_pin is expected

    async def test_connect_raises_and_clears_pin_required_repair(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Connecting to a locked receiver with no PIN must be user-visible."""
        from homeassistant.helpers import issue_registry as ir

        data = dict(mock_octo_config_entry_data)
        data[CONF_OCTO_PIN] = ""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Test Bed",
            data=data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="octo_pin_lock_entry",
        )
        entry.add_to_hass(hass)

        locked = True

        async def _fake_discovery(controller: OctoController) -> bool:
            controller._session_ready = True
            controller._features_loaded.set()
            controller._features_complete.set()
            controller._pin_feature_active = True
            controller._has_pin = True
            controller._pin_locked = locked
            return True

        issue_id = "octo_pin_required_aa_bb_cc_dd_ee_ff"
        registry = ir.async_get(hass)

        with patch.object(
            OctoController, "discover_features", autospec=True, side_effect=_fake_discovery
        ):
            coordinator = AdjustableBedCoordinator(hass, entry)
            await coordinator.async_connect()
            assert registry.async_get_issue(DOMAIN, issue_id) is not None

            # Unlocking the receiver on a later connection clears the repair.
            locked = False
            await coordinator.async_disconnect()
            await coordinator.async_connect()

        assert registry.async_get_issue(DOMAIN, issue_id) is None

    def test_support_bundle_controller_section_carries_protocol_state(self):
        """The bundle is the only evidence we get, so it must record the handshake."""
        from custom_components.adjustable_bed.support_report import _get_controller_info

        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.client = None
        controller = OctoController(coordinator, pin="")
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True
        coordinator.controller = controller

        info = _get_controller_info(coordinator)

        assert info["protocol_state"]["pin_locked_without_pin"] is True

    async def test_discovery_timeout_leaves_pin_state_unknown(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """A timeout must not report a configured-PIN guess as device state."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = OctoController(coordinator, pin="1234")

        # A second discovery attempt gets no reply and must not guess state.
        monkeypatch.setattr(octo_module.asyncio, "wait_for", _raise_timeout)
        await _REAL_OCTO_DISCOVER_FEATURES(controller)
        state = controller.protocol_diagnostics
        assert state["feature_discovery_complete"] is False
        assert state["has_pin"] is None
        assert state["pin_locked"] is None

    async def test_send_pin_is_not_suppressed_by_a_pending_stop(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Authentication must survive a pending cancel, or the bed stays locked."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True
        coordinator.cancel_command.set()
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.send_pin()

        expected_packet = controller._build_packet([0x20, 0x43], [1, 2, 3, 4])
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )
        assert controller.protocol_diagnostics["pin_sent"] is True

    async def test_pin_lock_warning_is_logged_once_per_transition(
        self,
        hass: HomeAssistant,
        caplog: pytest.LogCaptureFixture,
    ):
        """Repeated updates in one locked state should not flood logs."""
        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        caplog.set_level(logging.WARNING)
        caplog.clear()

        for _ in range(3):
            update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)

        assert caplog.text.count("reports its PIN lock engaged") == 1

        # Resolving and re-entering the state warns again - that is a real change.
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", False)
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)

        assert caplog.text.count("reports its PIN lock engaged") == 2

    async def test_saving_a_pin_clears_the_repair_without_reconnecting(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
    ):
        """The user follows the repair while the bed is offline; it must clear."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.adjustable_bed import _async_clear_stale_octo_pin_issue
        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        issue_id = "octo_pin_required_aa_bb_cc_dd_ee_ff"
        registry = ir.async_get(hass)
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)
        assert registry.async_get_issue(DOMAIN, issue_id) is not None

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Test Bed",
            data={**mock_octo_config_entry_data, CONF_OCTO_PIN: "1234"},
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="octo_pin_saved_entry",
        )
        entry.add_to_hass(hass)

        _async_clear_stale_octo_pin_issue(hass, entry)

        assert registry.async_get_issue(DOMAIN, issue_id) is None

    async def test_removing_the_entry_clears_the_repair(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
    ):
        """A leftover issue would keep nagging about a bed that is gone."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.adjustable_bed import async_remove_entry
        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        issue_id = "octo_pin_required_aa_bb_cc_dd_ee_ff"
        registry = ir.async_get(hass)
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)
        assert registry.async_get_issue(DOMAIN, issue_id) is not None

        await async_remove_entry(hass, mock_octo_config_entry)

        assert registry.async_get_issue(DOMAIN, issue_id) is None

    async def test_inconclusive_discovery_keeps_an_existing_repair(
        self,
        hass: HomeAssistant,
    ):
        """One failed reconnect must not retract a warning we already earned."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        issue_id = "octo_pin_required_aa_bb_cc_dd_ee_ff"
        registry = ir.async_get(hass)
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)
        assert registry.async_get_issue(DOMAIN, issue_id) is not None

        # Discovery timed out on a later connect: state unknown, not resolved.
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", None)

        assert registry.async_get_issue(DOMAIN, issue_id) is not None

    async def test_pin_repair_supplies_only_the_placeholders_its_text_uses(
        self,
        hass: HomeAssistant,
    ):
        """PIN repair guidance does not invent receiver-specific recovery steps."""
        import json
        import string as _string
        from pathlib import Path

        from homeassistant.helpers import issue_registry as ir

        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)
        issue = ir.async_get(hass).async_get_issue(DOMAIN, "octo_pin_required_aa_bb_cc_dd_ee_ff")
        assert issue is not None

        # Derived from __file__ so the test does not depend on pytest's CWD.
        strings_path = Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json"
        strings = json.loads(strings_path.read_text(encoding="utf-8"))
        text = strings["issues"]["octo_pin_required"]
        referenced = {
            field
            for value in (text["title"], text["description"])
            for _, field, _, _ in _string.Formatter().parse(value)
            if field
        }
        assert referenced <= set(issue.translation_placeholders or {})
        assert "http" not in text["description"]
        assert "recovery_url" not in (issue.translation_placeholders or {})

    async def test_star2_variant_clears_a_stale_standard_octo_repair(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry_data: dict,
    ):
        """Star2 has no PIN, and its controller could never clear the issue."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.adjustable_bed import _async_clear_stale_octo_pin_issue
        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        issue_id = "octo_pin_required_aa_bb_cc_dd_ee_ff"
        registry = ir.async_get(hass)
        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)
        assert registry.async_get_issue(DOMAIN, issue_id) is not None

        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Star2",
            data=mock_octo_star2_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="octo_star2_stale_entry",
        )
        entry.add_to_hass(hass)

        _async_clear_stale_octo_pin_issue(hass, entry)

        assert registry.async_get_issue(DOMAIN, issue_id) is None

    @pytest.mark.parametrize(
        ("motor_count", "expected_mask"),
        [(2, 0x06), (3, 0x0E), (4, 0x1E)],
    )
    async def test_flat_drives_every_motor_the_receiver_has(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
        motor_count: int,
        expected_mask: int,
    ):
        """M12-only flat leaves motors 3/4 parked on RC3, BM3 and 4M bases."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Test Bed",
            data={**mock_octo_config_entry_data, CONF_MOTOR_COUNT: motor_count},
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id=f"octo_flat_{motor_count}",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.preset_flat()

        expected = controller._build_packet([0x02, 0x71], [expected_mask])
        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        assert expected in written


class TestOctoMemoryInfoAndCombinedStep:
    """CAP_MEMINFO slot classes/names and the 4-motor M3+4 step."""

    @staticmethod
    def _meminfo_record(characteristic: list[int], value: list[int]) -> list[int]:
        """Build a CAP_MEMINFO feature record as the bed reports it."""
        # [cap_id(3), flag, char_len, characteristic..., value_type, value...]
        return [0x00, 0x00, 0x04, 0x00, len(characteristic), *characteristic, 0x05, *value]

    def _controller(self) -> OctoController:
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.client = None
        return OctoController(coordinator)

    def test_slot_classes_partition_standard_then_fix_then_lock(self):
        """Standard sits at the low indices; only locked slots block saving."""
        controller = self._controller()
        controller._memory_count = 6
        _complete_feature_data(controller, self._meminfo_record([6, 2, 1], [0] * 6))

        assert controller._memory_fix_count == 2
        assert controller._memory_lock_count == 1
        # 6 slots, 2 fix, 1 lock -> slots 1-3 standard, 4-5 fix, 6 lock.
        assert [controller._memory_slot_class(n) for n in range(1, 7)] == [
            "standard",
            "standard",
            "standard",
            "fix",
            "fix",
            "lock",
        ]

    def test_locked_slot_is_not_programmable(self):
        """A locked slot must not get a Save button the bed would refuse."""
        controller = self._controller()
        controller._memory_count = 4
        _complete_feature_data(controller, self._meminfo_record([4, 1, 1], [0] * 4))

        assert controller.is_memory_slot_programmable(1) is True
        assert controller.is_memory_slot_programmable(3) is True  # fix: save allowed
        assert controller.is_memory_slot_programmable(4) is False  # lock

    def test_slot_names_come_from_description_ids(self):
        """Known description IDs become names; unmapped ones stay unnamed."""
        controller = self._controller()
        controller._memory_count = 5
        _complete_feature_data(
            controller, self._meminfo_record([5, 0, 0], [0x00, 0x01, 0x02, 0x03, 0x07])
        )

        assert controller.memory_slot_names == (None, "Anti-Snore", "Zero-G", "Lordose", None)

    def test_short_characteristic_is_ignored_entirely(self):
        """The app ignores the record unless the characteristic is 3 bytes."""
        controller = self._controller()
        controller._memory_count = 4
        _complete_feature_data(controller, self._meminfo_record([4, 1], [0] * 4))

        assert controller._memory_fix_count == 0
        assert controller._memory_lock_count == 0

    def test_mismatched_value_length_drops_names_but_keeps_protection(self):
        """A short value block must not downgrade a locked slot to writable."""
        controller = self._controller()
        controller._memory_count = 4
        _complete_feature_data(controller, self._meminfo_record([4, 0, 1], [0x01, 0x02]))

        assert controller.memory_slot_names == ()
        assert controller._memory_lock_count == 1
        assert controller.is_memory_slot_programmable(4) is False

    def test_class_counts_are_clamped_into_the_slot_range(self):
        """Absurd counts must not push the partition out of range."""
        controller = self._controller()
        controller._memory_count = 3
        _complete_feature_data(controller, self._meminfo_record([3, 9, 9], [0] * 3))

        assert controller._memory_fix_count == 3
        assert controller._memory_lock_count == 0
        assert [controller._memory_slot_class(n) for n in range(1, 4)] == ["fix"] * 3

    async def test_memory_recall_is_streamed_and_released(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """MOTOR_MEMPOS is hold-to-run: firing once stalls the bed part-way."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Test Bed",
            data=mock_octo_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="octo_mem_recall",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._memory_count = 4
        mock_bleak_client.write_gatt_char.reset_mock()

        # Keep this focused on frame cadence and release, not a real hold timer.
        with (
            patch("custom_components.adjustable_bed.beds.base.asyncio.sleep", new=AsyncMock()),
            patch.object(asyncio, "wait_for", new=_raise_timeout),
        ):
            await controller.recall_memory(2, hold_ms=1_000)

        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        recall = controller._build_packet([0x02, 0x72], [0x01])  # 0-based slot
        stop = controller._build_packet([0x02, 0x73])
        # The requested bounded duration determines the 350ms packet cadence.
        expected_repeats = -(-1_000 // OCTO_PROTOCOL_HOLD_INTERVAL_MS)
        assert written.count(recall) == expected_repeats
        assert expected_repeats >= 3
        assert written[-1] == stop

    async def test_four_motor_bed_exposes_the_combined_step(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Motors 3+4 move together as one hardware step (CD_MOTOR34)."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Test Bed",
            data={**mock_octo_config_entry_data, CONF_MOTOR_COUNT: 4},
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="octo_m34",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert [s.key for s in controller.motor_control_specs] == [
            "back",
            "legs",
            "back_legs",
            "head",
            "feet",
            "head_feet",
        ]

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller._move_motor34_up()

        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        assert controller._build_packet([0x02, 0x70], [0x18]) in written

    async def test_two_motor_bed_exposes_combined_back_and_legs_control(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """The M1+2 command is hold-capable instead of a tap-only preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert [s.key for s in controller.motor_control_specs] == [
            "back",
            "legs",
            "back_legs",
        ]
        assert controller.supports_preset_both_up is False
        assert controller.supports_preset_flat is False
        assert "head_feet" not in [s.key for s in controller.motor_control_specs]

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.motor_control_specs[-1].open_fn(controller)

        expected = controller._build_packet(
            [0x02, 0x70],
            [OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS],
        )
        written = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
        assert written == [expected, controller._build_packet([0x02, 0x73])]

    def test_meminfo_before_memcount_still_classifies_correctly(self):
        """Capabilities arrive in the bed's order; MEMINFO must not need MEMCOUNT."""
        controller = self._controller()
        # No CAP_MEMCOUNT yet: _memory_count is still None.
        _complete_feature_data(controller, self._meminfo_record([4, 0, 1], [0] * 4))

        assert [controller._memory_slot_class(n) for n in range(1, 5)] == [
            "standard",
            "standard",
            "standard",
            "lock",
        ]
        assert controller.is_memory_slot_programmable(4) is False

    async def test_save_preset_service_path_refuses_a_locked_slot(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """The button is hidden, but automations call program_memory directly."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._memory_count = 4
        _complete_feature_data(
            controller,
            TestOctoMemoryInfoAndCombinedStep._meminfo_record([4, 0, 1], [0] * 4),
        )
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.program_memory(4)  # locked slot

        mock_bleak_client.write_gatt_char.assert_not_called()

        await controller.program_memory(1)  # standard slot

        expected = controller._build_packet([0x10, 0x70], [0x00])
        assert expected in [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]

    async def test_combined_cover_becomes_stale_when_motor_count_drops(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_octo_ready_transport,
    ):
        """Reconfiguring 4 motors down must not leave a ghost entity behind."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Octo Test Bed",
            data={**mock_octo_config_entry_data, CONF_MOTOR_COUNT: 2},
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="octo_stale_m34",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        assert "head_feet" in controller.stale_motor_entity_keys

    def test_absent_meminfo_leaves_every_slot_programmable(self):
        """CAP_MEMINFO is optional; without it we must not infer any locking."""
        controller = self._controller()
        controller._memory_count = 4  # CAP_MEMCOUNT only, no CAP_MEMINFO

        assert [controller._memory_slot_class(n) for n in range(1, 5)] == ["standard"] * 4
        assert all(controller.is_memory_slot_programmable(n) for n in range(1, 5))

    def test_invalid_meminfo_leaves_every_slot_programmable(self):
        """A malformed record is 'unknown', which must not mean 'locked'."""
        controller = self._controller()
        # Characteristic is not 3 bytes, so the record is rejected wholesale.
        _complete_feature_data(controller, self._meminfo_record([4, 1], [0] * 4))
        controller._memory_count = 4

        assert all(controller.is_memory_slot_programmable(n) for n in range(1, 5))

    async def test_long_recall_reauthenticates_so_the_link_survives(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Bounded recall uses only its requested hold packets and a final STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._memory_count = 4
        controller._has_pin = False
        controller._pin_locked = False
        mock_bleak_client.write_gatt_char.reset_mock()

        with (
            patch("custom_components.adjustable_bed.beds.base.asyncio.sleep", new=AsyncMock()),
            patch.object(asyncio, "wait_for", new=_raise_timeout),
        ):
            await controller.recall_memory(1, hold_ms=700)

        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        recall = controller._build_packet([0x02, 0x72], [0x00])
        stop = controller._build_packet([0x02, 0x73])
        assert written == [recall, recall, stop]

    async def test_cancelled_recall_stops_streaming(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_octo_ready_transport,
        mock_bleak_client: MagicMock,
    ):
        """Stop must end the recall, not just pause one chunk of it."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._memory_count = 4
        coordinator.cancel_command.set()
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.preset_memory(1)

        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        recall = controller._build_packet([0x02, 0x72], [0x00])
        stop = controller._build_packet([0x02, 0x73])
        assert recall not in written
        assert written == [stop]
