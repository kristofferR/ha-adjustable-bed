"""Tests for Okin 7-byte bed controller."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_7byte import (
    OKIN_7BYTE_CONFIG,
    _cmd,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_7BYTE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    NECTAR_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_okin_7byte_config_entry_data() -> dict:
    """Return mock config entry data for Okin 7-byte bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin 7-byte Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIN_7BYTE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_7byte_config_entry(
    hass: HomeAssistant, mock_okin_7byte_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin 7-byte bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin 7-byte Test Bed",
        data=mock_okin_7byte_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_7byte_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestOkin7ByteCommands:
    """Test Okin 7-byte command building."""

    def test_cmd_produces_7_bytes(self):
        """_cmd should produce exactly 7 bytes for any input."""
        for byte_val in [0x00, 0x01, 0x0F, 0x10, 0x58, 0x73]:
            cmd = _cmd(byte_val)
            assert len(cmd) == 7, f"_cmd(0x{byte_val:02x}) is not 7 bytes"

    def test_command_header_format(self):
        """Commands should start with 5A 01 03 10 30."""
        header = bytes.fromhex("5A01031030")
        for byte_val in [0x00, 0x0F, 0x10]:
            cmd = _cmd(byte_val)
            assert cmd[0:5] == header, f"_cmd(0x{byte_val:02x}) has wrong header"

    def test_command_trailer(self):
        """Commands should end with A5."""
        for byte_val in [0x00, 0x0F, 0x10]:
            cmd = _cmd(byte_val)
            assert cmd[6] == 0xA5, f"_cmd(0x{byte_val:02x}) doesn't end with A5"

    def test_command_variable_byte(self):
        """_cmd should place the variable byte at index 5."""
        assert _cmd(0x00)[5] == 0x00  # HEAD_UP
        assert _cmd(0x01)[5] == 0x01  # HEAD_DOWN
        assert _cmd(0x02)[5] == 0x02  # FOOT_UP
        assert _cmd(0x03)[5] == 0x03  # FOOT_DOWN
        assert _cmd(0x04)[5] == 0x04  # LUMBAR_UP (7-byte variant)
        assert _cmd(0x07)[5] == 0x07  # LUMBAR_DOWN
        assert _cmd(0x0F)[5] == 0x0F  # STOP
        assert _cmd(0x10)[5] == 0x10  # FLAT
        assert _cmd(0x11)[5] == 0x11  # LOUNGE (7-byte variant)
        assert _cmd(0x13)[5] == 0x13  # ZERO_GRAVITY
        assert _cmd(0x16)[5] == 0x16  # ANTI_SNORE
        assert _cmd(0x58)[5] == 0x58  # MASSAGE_ON
        assert _cmd(0x59)[5] == 0x59  # MASSAGE_WAVE
        assert _cmd(0x5A)[5] == 0x5A  # MASSAGE_OFF
        assert _cmd(0x73)[5] == 0x73  # LIGHT_ON
        assert _cmd(0x74)[5] == 0x74  # LIGHT_OFF

    def test_config_lumbar_up_byte(self):
        """7-byte config should use the verified Nectar lumbar-up byte."""
        assert OKIN_7BYTE_CONFIG.lumbar_up_byte == 0x04

    def test_config_lounge_byte(self):
        """7-byte config should use the verified Nectar TV/lounge byte."""
        assert OKIN_7BYTE_CONFIG.lounge_byte == 0x11

    def test_config_uses_write_without_response(self):
        """Nectar traffic uses ATT write command / no response."""
        assert OKIN_7BYTE_CONFIG.write_with_response is False


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestOkin7ByteController:
    """Test Okin7ByteController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Nectar write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == NECTAR_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lounge preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_lounge is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lights."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_memory_presets_supported(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True


class TestOkin7ByteMovement:
    """Test Okin 7-byte movement commands."""

    async def test_move_head_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 7
        assert first_call_data == _cmd(0x00)

    async def test_move_lumbar_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should send LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == _cmd(0x04)

    async def test_move_head_up_writes_without_response(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Nectar commands should use write-without-response."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call.kwargs["response"] is False

    async def test_stop_all_sends_stop_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x0F)

    async def test_movement_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP
        last_call_data = calls[-1][0][1]
        assert last_call_data == _cmd(0x0F)


class TestOkin7BytePresets:
    """Test Okin 7-byte preset commands."""

    async def test_preset_flat_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == _cmd(0x10)

    async def test_preset_zero_g_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send ZERO_GRAVITY command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == _cmd(0x13)


class TestOkin7ByteMassage:
    """Test Okin 7-byte massage commands."""

    async def test_massage_toggle_starts_massage(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """The exposed massage toggle button should send the verified on command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.massage_toggle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x58)

    async def test_massage_off_sends_verified_off_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Nectar massage off is 0x5A; 0x6F was captured as no-op."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.massage_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x5A)


class TestOkin7ByteLights:
    """Test Okin 7-byte light commands."""

    async def test_lights_on_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on should send LIGHT_ON command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x73)

    async def test_lights_off_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should send LIGHT_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x74)
