"""Tests for Octo bed controllers."""

from __future__ import annotations

import asyncio
import logging
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.light import ATTR_RGBW_COLOR
from homeassistant.components.light.const import ColorMode
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.octo import (
    OCTO_FEATURE_END,
    OCTO_FEATURE_LIGHT,
    OCTO_FEATURE_LIGHT_RGBWI,
    OCTO_MAX_RESPONSE_BUFFER_SIZE,
    OCTO_MEMORY_RECALL_INTERVAL_MS,
    OCTO_MEMORY_RECALL_SECONDS,
    OCTO_MOTOR_HEAD,
    OCTO_MOTOR_LEGS,
    OCTO_PACKET_CHAR,
    OCTO_SYSTEM_PIN_LOCK,
    OCTO_SYSTEM_PIN_STATE,
    OctoController,
    OctoStar2Controller,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
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
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight


@pytest.fixture
def _shorten_mocked_feature_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep mocked feature-discovery timeouts from dominating unit tests."""
    monkeypatch.setattr("custom_components.adjustable_bed.beds.octo.OCTO_FEATURE_TIMEOUT", 0.01)


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
    _shorten_mocked_feature_timeout: None,
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
    _shorten_mocked_feature_timeout: None,
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
) -> bytes:
    """Build a from-device OCTO response with escaping and checksum."""
    packet_data = data or []
    data_len_high = (len(packet_data) >> 8) & 0xFF
    data_len_low = len(packet_data) & 0xFF
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
        star2_service.get_characteristic.side_effect = (
            lambda uuid: star2_characteristic
            if uuid.lower() == OCTO_STAR2_CHAR_UUID.lower()
            else None
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
        mock_coordinator_connected,
    ):
        """Standard variant should create OctoController."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, OctoController)

    async def test_star2_variant_uses_octo_star2_controller(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_coordinator_connected,
    ):
        """Star2 variant should create OctoStar2Controller."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_star2_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, OctoStar2Controller)


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
        expected = {"command": [0x21, 0x71], "data": packet_data}

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

        assert packets == [{"command": [0x21, 0x7F], "data": []}]
        assert octo_stream_controller._response_buffer == bytearray()

    def test_extracts_multiple_packets_from_one_notification(
        self, octo_stream_controller: OctoController
    ) -> None:
        """One notified value may contain multiple complete protocol packets."""
        first = _build_octo_response(octo_stream_controller, (0x21, 0x7F))
        second = _build_octo_response(octo_stream_controller, (0x11, 0x72), [0x01])

        assert octo_stream_controller._extract_response_packets(first + second) == [
            {"command": [0x21, 0x7F], "data": []},
            {"command": [0x11, 0x72], "data": [0x01]},
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
        ) == [{"command": [0x11, 0x72], "data": [0x01]}]
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
            {"command": [0x21, 0x7F], "data": []}
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
            {"command": [0x21, 0x7F], "data": []}
        ]

    def test_notification_dispatches_reassembled_packets_and_preserves_raw_chunks(
        self, octo_stream_controller: OctoController
    ) -> None:
        """Reassembly should dispatch all packets without altering diagnostics."""
        light_data = [0x00, 0x01, 0x02, 0x00, 0x00, 0x01, 0x01]
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


class TestOctoPinAuth:
    """Test Octo PIN authentication flow."""

    async def test_send_pin_writes_auth_packet_when_pin_required(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """send_pin should write PIN packet when bed is PIN-locked."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

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
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """send_pin should skip writes when feature discovery shows unlocked bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        mock_bleak_client.write_gatt_char.reset_mock()

        controller._has_pin = True
        controller._pin_locked = False

        await controller.send_pin()

        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_send_pin_redacts_command_diagnostics(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """PIN packets should be written but redacted from traces and logs."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_pin = True
        controller._pin_locked = True
        coordinator._command_trace.clear()
        mock_bleak_client.write_gatt_char.reset_mock()
        caplog.set_level(logging.DEBUG, logger="custom_components.adjustable_bed.beds.base")
        caplog.clear()

        await coordinator.async_execute_controller_command(
            lambda active: cast(OctoController, active).send_pin()
        )

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


class TestOctoCommands:
    """Test Octo motor, light, and stop commands."""

    async def test_one_motor_lift_exposes_only_tv_lift_and_uses_motor_one(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A one-motor OCTO controller should safely model an RTV TV lift."""
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

        controller._has_lights = True
        controller._has_rgbwi = True
        controller._memory_count = 4
        controller._has_synchro = True

        assert [spec.key for spec in controller.motor_control_specs] == ["tv_lift"]
        assert controller.supports_preset_flat is False
        assert controller.supports_preset_both_up is False
        assert controller.supports_lights is False
        assert controller.supports_light_color_control is False
        assert controller.supports_memory_presets is False
        assert controller.memory_slot_count == 0
        assert controller.supports_synchro is False
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
        mock_coordinator_connected,
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
        mock_coordinator_connected,
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
        mock_coordinator_connected,
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
        mock_coordinator_connected,
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
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """lights_on/lights_off should send the expected feature-write packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)

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
        mock_coordinator_connected,
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
        mock_coordinator_connected,
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

        assert controller._has_rgbwi is True

    async def test_rgbwi_feature_stores_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
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

        assert controller._rgbwi_value_type == 0x07

    async def test_no_rgbwi_feature_keeps_has_rgbwi_false(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
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

        assert controller._has_rgbwi is False
        assert controller._has_lights is True

    async def test_rgbwi_properties_before_discovery(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
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
        mock_coordinator_connected,
    ):
        """RGBWI properties should reflect RGBWI support after feature detection."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        assert controller.supports_light_color_control is True
        assert controller.supported_color_mode == "rgbw"
        assert controller.default_light_rgb_color == (255, 255, 255)
        assert controller.supports_explicit_light_on_control is True

    async def test_star2_has_no_rgbwi_support(
        self,
        hass: HomeAssistant,
        mock_octo_star2_config_entry,
        mock_coordinator_connected,
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
        mock_coordinator_connected,
    ):
        """discover_features should reset RGBWI state before requesting features."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Pre-set RGBWI state
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x07

        # discover_features will time out (no real BLE), but should reset state first
        await controller.discover_features()

        # After timeout, RGBWI state should be reset (not re-discovered without response)
        assert controller._has_rgbwi is False
        assert controller._rgbwi_value_type is None


class TestOctoRGBWICommands:
    """Test OCTO RGBWI set_light_color_rgbw command output."""

    async def test_set_light_color_rgbw_sends_expected_packet(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should send SYSTEM_SET_CAPS packet with RGBWI data."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((255, 0, 128, 64))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 255, 0, 128, 64, 255],
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
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should fall back to 0x05 when discovery hasn't happened."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        # Leave _rgbwi_value_type as None (no discovery)

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((100, 200, 50, 150))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 100, 200, 50, 150, 255],
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
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """set_light_color_rgbw should use the valueType from feature discovery."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x0A  # Non-default valueType

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((0, 0, 0, 0))

        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x0A, 0, 0, 0, 0, 255],
        )
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            OCTO_CHAR_UUID,
            expected_packet,
            response=False,
        )

    async def test_set_light_color_rgbw_intensity_always_255(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Intensity byte should always be 255 in RGBWI packets."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        mock_bleak_client.write_gatt_char.reset_mock()
        await controller.set_light_color_rgbw((10, 20, 30, 40))

        # Extract the data portion from the built packet
        call_args = mock_bleak_client.write_gatt_char.call_args
        sent_packet = call_args[0][1]

        # The last data byte before the end marker should be the intensity (255)
        # Rebuild to verify the data field includes intensity=255
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 10, 20, 30, 40, 255],
        )
        assert sent_packet == expected_packet


class TestOctoRGBWIFeatureValuePair:
    """Test _extract_feature_value_pair with valueType extraction."""

    async def test_extract_returns_value_type(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """_extract_feature_value_pair should return the valueType byte."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # Build data: feature_id=0x000104, flag=0x00, skip_len=1, skip=[0x01], valueType=0x05, value=[R,G,B,W,I]
        data = [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 255, 128, 64, 200, 100]
        result = controller._extract_feature_value_pair(data)

        assert result is not None
        feature_id, value, value_type = result
        assert feature_id == 0x000104
        assert value == [255, 128, 64, 200, 100]
        assert value_type == 0x05

    async def test_extract_returns_none_for_short_data(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
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
        mock_coordinator_connected,
    ):
        """_extract_feature_value_pair should parse the end sentinel correctly."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # End sentinel: 0xFFFFFF
        data = [0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00]
        result = controller._extract_feature_value_pair(data)

        assert result is not None
        feature_id, _, _ = result
        assert feature_id == OCTO_FEATURE_END


class TestOctoRGBWILightEntity:
    """Test light entity behavior with OCTO RGBWI color mode."""

    async def test_light_entity_uses_rgbw_color_mode(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Light entity should use ColorMode.RGBW for RGBWI controllers."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        assert light.color_mode == ColorMode.RGBW
        assert light.supported_color_modes == {ColorMode.RGBW}

    async def test_light_entity_default_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
    ):
        """Light entity should have a default RGBW color for RGBWI controllers."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        assert light.rgbw_color == (255, 255, 255, 255)

    async def test_light_entity_without_rgbwi_uses_rgb(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
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
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Turning on with ATTR_RGBW_COLOR should call set_light_color_rgbw."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on(**{ATTR_RGBW_COLOR: (100, 150, 200, 50)})

        # Verify the correct RGBWI packet was sent
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 100, 150, 200, 50, 255],
        )

        # Should have called lights_on() first, then set_light_color_rgbw()
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 2  # lights_on + set_light_color_rgbw

        # The RGBWI packet is the second call
        assert calls[1][0][1] == expected_packet

        assert light.is_on is True
        assert light.rgbw_color == (100, 150, 200, 50)

    async def test_light_entity_turn_on_uses_previous_rgbw_color(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Turning on without color should use previously set RGBW color."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._rgbwi_value_type = 0x05

        light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
        # Set a specific color first
        light._attr_rgbw_color = (10, 20, 30, 40)

        mock_bleak_client.write_gatt_char.reset_mock()
        with patch.object(light, "async_write_ha_state"):
            await light.async_turn_on()

        # Should use the stored RGBW color
        expected_packet = controller._build_packet(
            [0x20, 0x72],
            [0x00, 0x01, 0x04, 0x00, 0x01, 0x01, 0x05, 10, 20, 30, 40, 255],
        )
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[-1][0][1] == expected_packet

    async def test_light_entity_turn_off(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Turning off should send lights_off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._has_rgbwi = True
        controller._has_lights = True  # Needed for supports_discrete_light_control

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


class TestCapabilitySnapshot:
    """Phase 2.5 C3a: a live controller's discovered capabilities round-trip
    through a JSON snapshot so an OFFLINE paired side mints with the same gating."""

    @staticmethod
    def _coord():
        from types import SimpleNamespace

        return SimpleNamespace(motor_count=2)

    def test_snapshot_roundtrip_restores_entity_gating(self):
        live = OctoController(self._coord())
        live._has_lights = True
        live._has_rgbwi = True
        live._rgbwi_value_type = 0x05
        live._memory_count = 4
        live._discovered_motor_count = 2
        live._has_synchro = True
        live._has_pin = True
        live._pin_locked = False
        # A real discovery completes by receiving the 0xFFFFFF CAP_END sentinel,
        # which sets _features_complete; only then is the snapshot real.
        live._features_complete.set()

        snap = live.capability_snapshot()
        assert snap == {
            "has_pin": True,
            "pin_locked": False,
            "has_lights": True,
            "has_rgbwi": True,
            "rgbwi_value_type": 0x05,
            "memory_count": 4,
            "discovered_motor_count": 2,
            "has_synchro": True,
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

        # Once discovery actually completes (sentinel → _features_complete), the
        # very same fields DO produce a snapshot.
        controller._features_complete.set()
        assert controller.controller_entity_discovery_complete
        assert controller.capability_snapshot() == {
            "has_pin": True,
            "pin_locked": True,
            "has_lights": True,
            "has_rgbwi": False,
            "rgbwi_value_type": None,
            "memory_count": 0,
            "discovered_motor_count": None,
            "has_synchro": False,
        }


class TestMemPosRelease:
    """Phase 2.5 C4: a memory recall always releases the motors, even when the
    stream fails part-way, because the STOP frame lives in a finally block.

    The streaming cadence itself is covered end-to-end by
    TestOctoMemoryInfoAndCombinedStep.
    """

    @staticmethod
    def _ctrl():
        from types import SimpleNamespace

        ctrl = OctoController(
            SimpleNamespace(motor_count=2, cancel_command=asyncio.Event())
        )
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
    """Phase 2.5 C4: react to the bed's PIN_LOCK challenge by re-sending the PIN
    immediately (verified from the app), and track lock state from PIN_STATE."""

    @staticmethod
    def _ctrl():
        from types import SimpleNamespace

        return OctoController(SimpleNamespace(motor_count=2, address="AA:BB:CC:DD:EE:FF"))

    async def test_pin_lock_schedules_resend(self):
        ctrl = self._ctrl()
        ctrl.send_pin = AsyncMock()
        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_LOCK, [])
        assert ctrl._pin_locked is True
        assert ctrl._pin_resend_task is not None
        await ctrl._pin_resend_task
        ctrl.send_pin.assert_awaited_once()

    async def test_fragmented_pin_lock_notification_schedules_resend(self):
        """A PIN challenge split across notifications is handled after reassembly."""
        ctrl = self._ctrl()
        ctrl.send_pin = AsyncMock()
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
        ctrl.send_pin.assert_awaited_once()

    async def test_pin_state_tracks_lock(self):
        ctrl = self._ctrl()
        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [1])  # unlocked
        assert ctrl._pin_locked is False
        ctrl._handle_pin_notification(OCTO_SYSTEM_PIN_STATE, [0])  # locked
        assert ctrl._pin_locked is True
class TestOctoPinLockDiagnostics:
    """A PIN-locked receiver accepts lights but ignores motors - say so."""

    def test_protocol_diagnostics_reports_discovery_state_without_leaking_pin(self):
        """The bundle needs the resolved capabilities, never the PIN itself."""
        coordinator = MagicMock()
        coordinator.address = "AA:BB:CC:DD:EE:FF"
        coordinator.client = None
        controller = OctoController(coordinator, pin="1234")

        controller._has_pin = True
        controller._pin_locked = True
        controller._has_lights = True
        controller._memory_count = 2
        controller._discovered_motor_count = 2
        controller._features_complete.set()

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
        controller._has_pin = has_pin
        controller._pin_locked = pin_locked

        assert controller.pin_locked_without_pin is expected

    async def test_connect_raises_and_clears_pin_required_repair(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        _shorten_mocked_feature_timeout: None,
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
        controller._has_pin = True
        controller._pin_locked = True
        coordinator.controller = controller

        info = _get_controller_info(coordinator)

        assert info["protocol_state"]["pin_locked_without_pin"] is True

    async def test_discovery_timeout_leaves_pin_state_unknown(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        _shorten_mocked_feature_timeout: None,
    ):
        """A timeout must not report a configured-PIN guess as device state."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)

        # The mocked client never notifies, so connect-time discovery timed out.
        state = controller.protocol_diagnostics
        assert state["feature_discovery_complete"] is False
        assert state["has_pin"] is None
        assert state["pin_locked"] is None
        # requires_pin still falls back to the configured PIN.
        assert controller.requires_pin is True

    async def test_send_pin_is_not_suppressed_by_a_pending_stop(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Authentication must survive a pending cancel, or the bed stays locked."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()

        controller = cast(OctoController, coordinator.controller)
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
        """A locked bed reconnects every ~30s; the warning must not flood logs."""
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

    async def test_pin_repair_supplies_every_placeholder_its_text_uses(
        self,
        hass: HomeAssistant,
    ):
        """A placeholder with no value renders literally in the Repairs card."""
        import json
        import string as _string
        from pathlib import Path

        from homeassistant.helpers import issue_registry as ir

        from custom_components.adjustable_bed.unsupported import (
            update_octo_pin_required_issue,
        )

        update_octo_pin_required_issue(hass, "AA:BB:CC:DD:EE:FF", "Bed", True)
        issue = ir.async_get(hass).async_get_issue(
            DOMAIN, "octo_pin_required_aa_bb_cc_dd_ee_ff"
        )
        assert issue is not None

        # Derived from __file__ so the test does not depend on pytest's CWD.
        strings_path = (
            Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json"
        )
        strings = json.loads(strings_path.read_text(encoding="utf-8"))
        text = strings["issues"]["octo_pin_required"]
        referenced = {
            field
            for value in (text["title"], text["description"])
            for _, field, _, _ in _string.Formatter().parse(value)
            if field
        }
        assert referenced <= set(issue.translation_placeholders or {})

        # hassfest rejects literal URLs in translation strings; the recovery
        # link has to arrive as a placeholder instead.
        assert "http" not in text["description"]
        assert "http" in (issue.translation_placeholders or {})["recovery_url"]

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
        mock_coordinator_connected,
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
        controller._handle_feature_response(self._meminfo_record([6, 2, 1], [0] * 6))

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
        controller._handle_feature_response(self._meminfo_record([4, 1, 1], [0] * 4))

        assert controller.is_memory_slot_programmable(1) is True
        assert controller.is_memory_slot_programmable(3) is True  # fix: save allowed
        assert controller.is_memory_slot_programmable(4) is False  # lock

    def test_slot_names_come_from_description_ids(self):
        """Known description IDs become names; unmapped ones stay unnamed."""
        controller = self._controller()
        controller._memory_count = 5
        controller._handle_feature_response(
            self._meminfo_record([5, 0, 0], [0x00, 0x01, 0x02, 0x03, 0x07])
        )

        assert controller.memory_slot_names == (None, "Anti-Snore", "Zero-G", "Lordose", None)

    def test_short_characteristic_is_ignored_entirely(self):
        """The app ignores the record unless the characteristic is 3 bytes."""
        controller = self._controller()
        controller._memory_count = 4
        controller._handle_feature_response(self._meminfo_record([4, 1], [0] * 4))

        assert controller._memory_fix_count == 0
        assert controller._memory_lock_count == 0

    def test_mismatched_value_length_drops_names_but_keeps_protection(self):
        """A short value block must not downgrade a locked slot to writable."""
        controller = self._controller()
        controller._memory_count = 4
        controller._handle_feature_response(self._meminfo_record([4, 0, 1], [0x01, 0x02]))

        assert controller.memory_slot_names == ()
        assert controller._memory_lock_count == 1
        assert controller.is_memory_slot_programmable(4) is False

    def test_class_counts_are_clamped_into_the_slot_range(self):
        """Absurd counts must not push the partition out of range."""
        controller = self._controller()
        controller._memory_count = 3
        controller._handle_feature_response(self._meminfo_record([3, 9, 9], [0] * 3))

        assert controller._memory_fix_count == 3
        assert controller._memory_lock_count == 0
        assert [controller._memory_slot_class(n) for n in range(1, 4)] == ["fix"] * 3

    async def test_memory_recall_is_streamed_and_released(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_coordinator_connected,
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

        await controller.preset_memory(2)

        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        recall = controller._build_packet([0x02, 0x72], [0x01])  # 0-based slot
        stop = controller._build_packet([0x02, 0x73])
        # Streamed for the recall window, not the far shorter button cadence.
        expected_repeats = int(
            OCTO_MEMORY_RECALL_SECONDS * 1000 / OCTO_MEMORY_RECALL_INTERVAL_MS
        )
        assert written.count(recall) == expected_repeats
        assert expected_repeats > 3
        assert written[-1] == stop

    async def test_four_motor_bed_exposes_the_combined_step(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry_data: dict,
        mock_coordinator_connected,
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
        mock_coordinator_connected,
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
        controller._handle_feature_response(self._meminfo_record([4, 0, 1], [0] * 4))

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
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """The button is hidden, but automations call program_memory directly."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._memory_count = 4
        controller._handle_feature_response(
            TestOctoMemoryInfoAndCombinedStep._meminfo_record([4, 0, 1], [0] * 4)
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
        mock_coordinator_connected,
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
        controller._memory_count = 4
        # Characteristic is not 3 bytes, so the record is rejected wholesale.
        controller._handle_feature_response(self._meminfo_record([4, 1], [0] * 4))

        assert all(controller.is_memory_slot_programmable(n) for n in range(1, 5))

    async def test_long_recall_reauthenticates_so_the_link_survives(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """The recall holds the command lock, starving the PIN keep-alive task."""
        coordinator = AdjustableBedCoordinator(hass, mock_octo_config_entry)
        await coordinator.async_connect()
        controller = cast(OctoController, coordinator.controller)
        controller._memory_count = 4
        controller._has_pin = True
        controller._pin_locked = True
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.preset_memory(1)

        written = [c[0][1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        pin_packet = controller._build_packet([0x20, 0x43], [1, 2, 3, 4])
        recall = controller._build_packet([0x02, 0x72], [0x00])
        # A 30s recall spans more than one ~25s authentication window.
        assert written.count(pin_packet) >= 2
        assert written.index(pin_packet) < written.index(recall)

    async def test_cancelled_recall_stops_streaming(
        self,
        hass: HomeAssistant,
        mock_octo_config_entry,
        mock_coordinator_connected,
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
