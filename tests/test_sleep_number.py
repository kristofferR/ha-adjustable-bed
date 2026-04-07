"""Tests for Sleep Number Climate 360 / FlexFit controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sleep_number import SleepNumberController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SLEEP_NUMBER_AUTH_CHAR_UUID,
    SLEEP_NUMBER_BAMKEY_CHAR_UUID,
    SLEEP_NUMBER_TRANSFER_INFO_CHAR_UUID,
    SLEEP_NUMBER_VARIANT_LEFT,
    SLEEP_NUMBER_VARIANT_RIGHT,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _build_sleep_number_blob(payload: str) -> bytes:
    """Return a framed Sleep Number blob for transport assertions."""
    return SleepNumberController._build_bamkey_blob(payload)


def _decode_sleep_number_payload(payload: bytes) -> str:
    """Decode a framed Sleep Number blob back to its text payload."""
    return SleepNumberController._decode_bamkey_text(payload)


@pytest.fixture
def sleep_number_coordinator(hass: HomeAssistant, mock_coordinator_connected):
    """Create and connect a coordinator for a Sleep Number test device."""

    async def _create(
        *,
        address: str,
        name: str,
        entry_id: str,
        protocol_variant: str = VARIANT_AUTO,
        disable_angle_sensing: bool = True,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleep Number Test Bed",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER,
                CONF_PROTOCOL_VARIANT: protocol_variant,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: disable_angle_sensing,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=address,
            entry_id=entry_id,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        return coordinator

    return _create


class TestSleepNumberController:
    """Test Sleep Number controller behavior."""

    async def test_control_characteristic_uuid(self, sleep_number_coordinator) -> None:
        """Controller should use the BamKey response characteristic."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:21",
            name="Smart bed 0074E7",
            entry_id="sleep_number_uuid",
        )

        assert coordinator.controller.control_characteristic_uuid == SLEEP_NUMBER_BAMKEY_CHAR_UUID

    async def test_auto_variant_defaults_to_left_side(self, sleep_number_coordinator) -> None:
        """Auto variant should target the left side by default."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:22",
            name="Smart bed 0074E8",
            entry_id="sleep_number_auto_side",
        )

        assert coordinator.controller._side == SLEEP_NUMBER_VARIANT_LEFT

    async def test_right_variant_targets_right_side(self, sleep_number_coordinator) -> None:
        """Explicit right-side variant should be preserved by the factory."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:23",
            name="Smart bed 0074E9",
            entry_id="sleep_number_right_side",
            protocol_variant=SLEEP_NUMBER_VARIANT_RIGHT,
        )

        assert coordinator.controller._side == SLEEP_NUMBER_VARIANT_RIGHT

    async def test_requires_notification_channel(self, sleep_number_coordinator) -> None:
        """Sleep Number command acks should keep the notify channel active."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:24",
            name="Smart bed 0074EA",
            entry_id="sleep_number_notify",
        )

        assert coordinator.controller.requires_notification_channel is True
        assert coordinator.controller_state["under_bed_lights_on"] is True
        assert coordinator.controller_state["light_level"] == 3
        assert coordinator.controller_state["light_timer_option"] == "15 min"

    async def test_disables_position_polling_during_commands(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Sleep Number should not poll positions while another bamkey command is in flight."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2A",
            name="Smart bed 0074F0",
            entry_id="sleep_number_no_poll_during_commands",
        )

        assert coordinator.controller.allow_position_polling_during_commands is False

    async def test_set_motor_position_writes_bamkey_and_waits_for_ack(
        self,
        sleep_number_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Direct position writes should send an ACTS command and parse PASS:ACK."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:25",
            name="Smart bed 0074EB",
            entry_id="sleep_number_set_position",
        )
        mock_bleak_client.write_gatt_char.reset_mock()

        async def _write_side_effect(
            _char_uuid: str, payload: bytes, response: bool = False
        ) -> None:
            del response
            assert _decode_sleep_number_payload(payload) == "ACTS left head 57"
            coordinator.controller._handle_bamkey_notification(
                None,
                bytearray(_build_sleep_number_blob("PASS:ACK")),
            )

        mock_bleak_client.write_gatt_char.side_effect = _write_side_effect

        await coordinator.controller.set_motor_position("back", 57)

        mock_bleak_client.start_notify.assert_awaited_once_with(
            SLEEP_NUMBER_BAMKEY_CHAR_UUID,
            coordinator.controller._handle_bamkey_notification,
        )
        mock_bleak_client.write_gatt_char.assert_awaited_once_with(
            SLEEP_NUMBER_BAMKEY_CHAR_UUID,
            _build_sleep_number_blob("ACTS left head 57"),
            response=False,
        )

    async def test_set_motor_position_reads_ack_after_notification_hint(
        self,
        sleep_number_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Commands should support the notify-then-readback response flow."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:31",
            name="Smart bed 0074F7",
            entry_id="sleep_number_set_position_readback",
        )
        mock_bleak_client.write_gatt_char.reset_mock()

        async def _write_side_effect(
            _char_uuid: str, payload: bytes, response: bool = False
        ) -> None:
            assert response is False
            assert _decode_sleep_number_payload(payload) == "ACTS left head 42"
            coordinator.controller._handle_bamkey_notification(None, bytearray(b"hint"))

        async def _read_side_effect(target) -> bytes:
            if str(target) == SLEEP_NUMBER_BAMKEY_CHAR_UUID:
                return _build_sleep_number_blob("PASS:ACK")
            return b""

        mock_bleak_client.write_gatt_char.side_effect = _write_side_effect
        mock_bleak_client.read_gatt_char = AsyncMock(side_effect=_read_side_effect)

        await coordinator.controller.set_motor_position("back", 42)

        mock_bleak_client.read_gatt_char.assert_awaited_with(SLEEP_NUMBER_BAMKEY_CHAR_UUID)

    async def test_stop_all_only_stops_the_configured_side(
        self,
        sleep_number_coordinator,
    ) -> None:
        """stop_all should not send the global ACHA halt on split bases."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2B",
            name="Smart bed 0074F1",
            entry_id="sleep_number_stop_all",
            protocol_variant=SLEEP_NUMBER_VARIANT_RIGHT,
        )
        coordinator.controller._send_bamkey_command = AsyncMock(return_value=[])

        await coordinator.controller.stop_all()

        coordinator.controller._send_bamkey_command.assert_has_awaits(
            [
                call("ACTH", "right", "head"),
                call("ACTH", "right", "foot"),
            ]
        )

    async def test_stop_all_attempts_both_actuators_when_one_stop_fails(
        self,
        sleep_number_coordinator,
    ) -> None:
        """stop_all should still try the second actuator if the first stop fails."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2C",
            name="Smart bed 0074F2",
            entry_id="sleep_number_stop_all_best_effort",
        )
        coordinator.controller._send_stop_for_motor = AsyncMock(
            side_effect=[TimeoutError("head timeout"), None]
        )

        with pytest.raises(ExceptionGroup) as exc_info:
            await coordinator.controller.stop_all()

        assert len(exc_info.value.exceptions) == 1
        coordinator.controller._send_stop_for_motor.assert_has_awaits([call("back"), call("legs")])

    async def test_read_positions_maps_head_and_foot_to_back_and_legs(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Position reads should query both actuators and publish back/legs values."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:26",
            name="Smart bed 0074EC",
            entry_id="sleep_number_read_positions",
            disable_angle_sensing=False,
        )
        callback = MagicMock()
        coordinator.controller._notify_callback = callback
        coordinator.controller._send_bamkey_command = AsyncMock(side_effect=[["41"], ["19"]])

        await coordinator.controller.read_positions()

        coordinator.controller._send_bamkey_command.assert_has_awaits(
            [
                call("ACTG", "left", "head", expected_args=1),
                call("ACTG", "left", "foot", expected_args=1),
            ]
        )
        callback.assert_has_calls([call("back", 41.0), call("legs", 19.0)])

    async def test_preset_zero_g_uses_fuzion_preset_name(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Zero-G should map to the bamkey preset name used by the SleepIQ app."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:27",
            name="Smart bed 0074ED",
            entry_id="sleep_number_zero_g",
        )
        coordinator.controller._send_bamkey_command = AsyncMock(return_value=[])

        await coordinator.controller.preset_zero_g()

        coordinator.controller._send_bamkey_command.assert_awaited_once_with(
            "ACSP",
            "left",
            "zero_g",
            "0",
        )

    async def test_read_bed_presence_maps_in_to_true(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Grouped BAMG LBPG responses should map `in` to an occupied state."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:28",
            name="Smart bed 0074EE",
            entry_id="sleep_number_presence",
        )
        coordinator.controller._send_bamkey_raw_response = AsyncMock(return_value='PASS:["PASS:in"]')

        presence = await coordinator.controller.read_bed_presence()

        assert presence is True
        assert coordinator.controller._bed_presence_state == "in"
        assert coordinator.controller._send_bamkey_raw_response.await_args == call(
            "BAMG",
            '[{"bamkey":"LBPG","args":"left"}]',
        )
        assert coordinator.controller.get_light_state()["light_timer_option"] == "15 min"
        assert coordinator.controller._coordinator.controller_state["bed_presence"] == "in"

    async def test_read_bed_presence_primes_required_characteristics_once(
        self,
        sleep_number_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """LBPG should prime the Auth and TransferInfo reads once per connection."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2E",
            name="Smart bed 0074F4",
            entry_id="sleep_number_presence_prime",
        )
        coordinator.controller._send_bamkey_raw_response = AsyncMock(
            side_effect=['PASS:["PASS:out"]', 'PASS:["PASS:in"]']
        )
        mock_bleak_client.read_gatt_char.reset_mock()

        first = await coordinator.controller.read_bed_presence()
        second = await coordinator.controller.read_bed_presence()

        assert first is False
        assert second is True
        mock_bleak_client.read_gatt_char.assert_has_awaits(
            [
                call(SLEEP_NUMBER_AUTH_CHAR_UUID),
                call(SLEEP_NUMBER_TRANSFER_INFO_CHAR_UUID),
            ]
        )
        assert mock_bleak_client.read_gatt_char.await_count == 2

    async def test_read_bed_presence_reads_characteristic_after_notification_hint(
        self,
        sleep_number_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """LBPG should use a notify-triggered readback when the notification is only a hint."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2F",
            name="Smart bed 0074F5",
            entry_id="sleep_number_presence_fallback",
        )
        mock_bleak_client.write_gatt_char.reset_mock()

        async def _write_side_effect(
            _char_uuid: str, payload: bytes, response: bool = False
        ) -> None:
            assert response is False
            assert _decode_sleep_number_payload(payload) == 'BAMG [{"bamkey":"LBPG","args":"left"}]'
            coordinator.controller._handle_bamkey_notification(None, bytearray(b"hint"))

        async def _read_side_effect(target) -> bytes:
            if str(target) in {
                SLEEP_NUMBER_AUTH_CHAR_UUID,
                SLEEP_NUMBER_TRANSFER_INFO_CHAR_UUID,
            }:
                return b""
            if str(target) == SLEEP_NUMBER_BAMKEY_CHAR_UUID:
                return _build_sleep_number_blob('PASS:["PASS:in"]')
            return b""

        mock_bleak_client.write_gatt_char.side_effect = _write_side_effect
        mock_bleak_client.read_gatt_char = AsyncMock(side_effect=_read_side_effect)

        presence = await coordinator.controller.read_bed_presence()

        assert presence is True
        assert _decode_sleep_number_payload(
            mock_bleak_client.write_gatt_char.await_args.args[1]
        ) == 'BAMG [{"bamkey":"LBPG","args":"left"}]'

    async def test_bulk_transfer_notification_triggers_readback_hint(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Secondary Sleep Number notifications should queue a BamKey readback."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:32",
            name="Smart bed 0074F8",
            entry_id="sleep_number_bulk_hint",
        )

        coordinator.controller._handle_bamkey_readback_hint_notification(
            None,
            bytearray(b"\x01"),
        )

        assert await coordinator.controller._readback_hint_queue.get() is None

    async def test_bamkey_notification_handler_reassembles_blob_chunks(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Chunked bamkey notifications should be reassembled before parsing."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:30",
            name="Smart bed 0074F6",
            entry_id="sleep_number_chunked_notification",
        )
        blob = _build_sleep_number_blob("PASS:ACK")

        coordinator.controller._handle_bamkey_notification(None, bytearray(blob[:8]))
        assert coordinator.controller._response_queue.empty()

        coordinator.controller._handle_bamkey_notification(None, bytearray(blob[8:]))

        assert await coordinator.controller._response_queue.get() == "PASS:ACK"

    async def test_read_underbed_light_settings_updates_cached_state(
        self,
        sleep_number_coordinator,
    ) -> None:
        """UBLG should populate the cached light level and timer."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:29",
            name="Smart bed 0074EF",
            entry_id="sleep_number_light_read",
        )
        coordinator.controller._send_bamkey_command = AsyncMock(return_value=["medium", "45"])

        level, timer = await coordinator.controller._read_underbed_light_settings()

        assert (level, timer) == ("medium", 45)
        assert coordinator.controller.get_light_state() == {
            "is_on": True,
            "light_level": 2,
            "light_timer_minutes": 45,
            "light_timer_option": "45 min",
        }
        assert coordinator.controller._coordinator.controller_state["under_bed_lights_on"] is True
        assert (
            coordinator.controller._coordinator.controller_state["light_timer_option"] == "45 min"
        )

    async def test_read_light_state_returns_cached_underbed_light_values(
        self,
        sleep_number_coordinator,
    ) -> None:
        """read_light_state should issue UBLG and return the hydrated state snapshot."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2D",
            name="Smart bed 0074F3",
            entry_id="sleep_number_read_light_state",
        )
        coordinator.controller._send_bamkey_command = AsyncMock(return_value=["high", "15"])

        state = await coordinator.controller.read_light_state()

        assert state == {
            "is_on": True,
            "light_level": 3,
            "light_timer_minutes": 15,
            "light_timer_option": "15 min",
        }

    async def test_lights_on_preserves_timer_and_last_active_level(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Turning the light back on should reuse the last active brightness and timer."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2A",
            name="Smart bed 0074F0",
            entry_id="sleep_number_light_on",
        )
        coordinator.controller._underbed_light_level = "off"
        coordinator.controller._underbed_light_timer_minutes = 30
        coordinator.controller._underbed_light_last_active_level = "medium"
        coordinator.controller._send_bamkey_command = AsyncMock(return_value=[])

        await coordinator.controller.lights_on()

        coordinator.controller._send_bamkey_command.assert_awaited_once_with(
            "UBLS",
            "medium",
            "30",
        )
        assert coordinator.controller.get_light_state()["light_level"] == 2
        assert coordinator.controller.get_light_state()["light_timer_option"] == "30 min"

    async def test_set_light_timer_preserves_current_level(
        self,
        sleep_number_coordinator,
    ) -> None:
        """Changing the timer should keep the current brightness level."""
        coordinator = await sleep_number_coordinator(
            address="AA:BB:CC:DD:EE:2B",
            name="Smart bed 0074F1",
            entry_id="sleep_number_light_timer",
        )
        coordinator.controller._underbed_light_level = "high"
        coordinator.controller._underbed_light_timer_minutes = 15
        coordinator.controller._send_bamkey_command = AsyncMock(return_value=[])

        await coordinator.controller.set_light_timer("2 hr")

        coordinator.controller._send_bamkey_command.assert_awaited_once_with(
            "UBLS",
            "high",
            "120",
        )
        assert coordinator.controller.get_light_state()["light_timer_minutes"] == 120
        assert coordinator.controller.light_auto_off_seconds == 7200
