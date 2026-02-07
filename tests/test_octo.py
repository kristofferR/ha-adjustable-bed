"""Tests for Octo bed controllers."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.octo import (
    OCTO_MOTOR_HEAD,
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
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


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
    hass: HomeAssistant, mock_octo_config_entry_data: dict
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
    hass: HomeAssistant, mock_octo_star2_config_entry_data: dict
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


class TestOctoVariantSelection:
    """Test Octo variant selection in controller creation."""

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
            response=True,
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


class TestOctoCommands:
    """Test Octo motor, light, and stop commands."""

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
                await controller._move_with_stop(OCTO_MOTOR_HEAD, "up")

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
            response=True,
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
            response=True,
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
            response=True,
        )
