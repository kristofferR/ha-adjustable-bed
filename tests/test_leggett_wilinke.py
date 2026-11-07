"""Tests for Leggett & Platt WiLinke bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_PLATT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_RICHMAT_CHAR_UUID,
    LEGGETT_VARIANT_MLRM,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_leggett_wilinke_config_entry_data() -> dict:
    """Return mock config entry data for Leggett & Platt WiLinke variant bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "L&P WiLinke Test Bed",
        CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
        CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_MLRM,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_leggett_wilinke_config_entry(
    hass: HomeAssistant, mock_leggett_wilinke_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Leggett & Platt WiLinke variant bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="L&P WiLinke Test Bed",
        data=mock_leggett_wilinke_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="leggett_mlrm_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestLeggettWilinkeController:
    """Test Leggett & Platt WiLinke controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == LEGGETT_RICHMAT_CHAR_UUID

    async def test_build_command_wilinke_format(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test command building produces correct WiLinke 5-byte format."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0x31)
        assert len(command) == 5
        assert command[0] == 0x6E
        assert command[1] == 0x01
        assert command[2] == 0x00
        assert command[3] == 0x31

    async def test_build_command_checksum(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test checksum calculation: (0x6E + 0x01 + 0x00 + cmd) & 0xFF."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        # Test with PRESET_FLAT (0x31)
        command = coordinator.controller._build_command(0x31)
        expected_checksum = (0x6E + 0x01 + 0x00 + 0x31) & 0xFF
        assert command[4] == expected_checksum

        # Test with END command (0x6E) - checksum wraps around
        command = coordinator.controller._build_command(0x6E)
        expected_checksum = (0x6E + 0x01 + 0x00 + 0x6E) & 0xFF
        assert command[4] == expected_checksum

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0x6E)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, command, response=True
        )

    async def test_write_command_records_a_command_trace(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """The L&P write loop bypasses the shared helper but still reaches support bundles."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0x6E)
        with patch("custom_components.adjustable_bed.beds.leggett.wilinke.asyncio.sleep"):
            await coordinator.controller.write_command(command, repeat_count=3, repeat_delay_ms=50)

        (trace,) = coordinator.command_trace
        assert trace["payload"]["hex"] == command.hex()
        assert trace["characteristic_uuid"] == LEGGETT_RICHMAT_CHAR_UUID
        assert trace["write_mode"] == "with_response"
        assert (trace["repeat_count"], trace["repeat_delay_ms"]) == (3, 50)
        assert trace["controller_class"] == "LeggettWilinkeController"

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(coordinator.controller._build_command(0x6E))


class TestLeggettWilinkeCapabilities:
    """Test controller capability properties."""

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports zero gravity preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports anti-snore preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports TV preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports lounge preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_lounge is True

    async def test_has_no_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test L&P WiLinke beds don't have lumbar support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.has_lumbar_support is False

    async def test_has_no_pillow_support(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test L&P WiLinke beds don't have pillow support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.has_pillow_support is False

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports light support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_lights is True

    async def test_no_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test lights are toggle-only (no discrete on/off)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_discrete_light_control is False

    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports 2 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller supports memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_memory_programming is True

    async def test_has_discrete_motor_control(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports discrete motor control (uses buttons not covers)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.has_discrete_motor_control is True


class TestLeggettWilinkePresets:
    """Test Leggett & Platt WiLinke preset commands."""

    async def test_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset lounge command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        with patch("custom_components.adjustable_bed.beds.leggett.wilinke.asyncio.sleep"):
            await coordinator.controller.preset_lounge()

        expected_cmd = coordinator.controller._build_command(0x59)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test invalid memory number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(3)

        assert "Invalid memory number 3" in caplog.text
        # Should not write any command
        assert mock_bleak_client.write_gatt_char.call_count == 0


class TestLeggettWilinkeMassage:
    """Test Leggett & Platt WiLinke massage commands.

    KEY DIFFERENTIATOR: This controller has discrete UP/DOWN commands for
    massage intensity (0x4C-0x4F) instead of just step/toggle commands.
    """

    async def test_massage_wave_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage wave toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_wave_toggle()

        expected_cmd = coordinator.controller._build_command(0x39)
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )


class TestLeggettWilinkePositionNotifications:
    """Test Leggett & Platt WiLinke position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_leggett_wilinke_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_wilinke_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
