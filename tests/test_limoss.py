"""Tests for Limoss / Stawett controller."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.codec import limoss as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_LIMOSS,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_limoss_config_entry_data() -> dict:
    """Return mock config entry data for Limoss bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Limoss Test Bed",
        CONF_BED_TYPE: BED_TYPE_LIMOSS,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_limoss_config_entry(
    hass: HomeAssistant, mock_limoss_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Limoss bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Limoss Test Bed",
        data=mock_limoss_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="limoss_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestLimossController:
    """Test Limoss controller behavior."""

    async def test_position_notification_parsing(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Position response should be parsed and forwarded via callback."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        callback = MagicMock()
        controller._notify_callback = callback

        raw_position = 8000
        packet = codec.frame(b"\x10" + raw_position.to_bytes(4, byteorder="big"), 0)

        controller._handle_notification(MagicMock(), bytearray(packet))

        callback.assert_called_once()
        position_key, angle = callback.call_args.args
        assert position_key == "back"
        assert isinstance(angle, float)
        expected_angle = (
            (raw_position / controller._max_raw_estimate["back"])
            * coordinator.get_max_angle("back")
        )
        assert math.isclose(angle, expected_angle, rel_tol=1e-6, abs_tol=1e-6)

    async def test_move_head_up_uses_motor_3_when_four_motors_reported(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Head control should use motor 3 command on 4-motor Limoss beds."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        controller._reported_motor_count = 4
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.move_head_up()

        first_packet = mock_bleak_client.write_gatt_char.call_args_list[0].args[1]
        assert codec.decode(first_packet)[0] == 0x32

    async def test_move_feet_up_uses_motor_4_when_four_motors_reported(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Feet control should use motor 4 command on 4-motor Limoss beds."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        controller._reported_motor_count = 4
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.move_feet_up()

        first_packet = mock_bleak_client.write_gatt_char.call_args_list[0].args[1]
        assert codec.decode(first_packet)[0] == 0x42

    async def test_capability_response_updates_memory_slots(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Capability response should update dynamic memory slot count."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        # [cmd=0x02, button_count=8, system_type=0x12 (2 motors), vibration=1, mem=5]
        packet = codec.frame(bytes((0x02, 8, 0x12, 1, 0x05)), 0)
        controller._handle_notification(MagicMock(), bytearray(packet))

        assert controller._reported_motor_count == 2
        assert controller.memory_slot_count == 5

    async def test_read_positions_queries_each_motor(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """read_positions should send AskPos commands for requested motor count."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        await controller.read_positions(motor_count=3)

        decoded_packets = [
            codec.decode(call.args[1])
            for call in mock_bleak_client.write_gatt_char.call_args_list
        ]
        decoded_cmds = [packet[0] for packet in decoded_packets if packet is not None]
        assert {0x10, 0x20, 0x30} <= set(decoded_cmds)
        assert 0x40 not in decoded_cmds

    async def test_raw_to_angle_shrinks_overestimated_max_raw(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Repeated low-but-valid samples should shrink stale max-raw estimates."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        initial_max = controller._max_raw_estimate["back"]
        for _ in range(12):
            controller._raw_to_angle(8000, "back")

        assert controller._max_raw_estimate["back"] < initial_max

    async def test_reset_max_raw_estimate_restores_defaults(
        self,
        hass: HomeAssistant,
        mock_limoss_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """reset_max_raw_estimate should restore built-in normalization defaults."""
        coordinator = AdjustableBedCoordinator(hass, mock_limoss_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        controller._max_raw_estimate["back"] = 9000
        controller.reset_max_raw_estimate()

        assert controller._max_raw_estimate["back"] == 16000
