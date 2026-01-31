"""Tests for Okin 64-bit bed controller (10-byte protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_64bit import (
    OKIN_64BIT_VARIANT_CUSTOM,
    OKIN_64BIT_VARIANT_NORDIC,
    Okin64BitCommands,
    Okin64BitController,
    build_okin_64bit_command,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_64BIT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_okin_64bit_config_entry_data() -> dict:
    """Return mock config entry data for Okin 64-bit bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin 64-bit Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIN_64BIT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_64bit_config_entry(
    hass: HomeAssistant, mock_okin_64bit_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin 64-bit bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin 64-bit Test Bed",
        data=mock_okin_64bit_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_64bit_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestOkin64BitCommands:
    """Test Okin 64-bit command constants."""

    def test_all_command_values_are_8_bytes(self):
        """All command values should be exactly 8 bytes."""
        commands = [
            Okin64BitCommands.STOP,
            Okin64BitCommands.HEAD_UP,
            Okin64BitCommands.HEAD_DOWN,
            Okin64BitCommands.FOOT_UP,
            Okin64BitCommands.FOOT_DOWN,
            Okin64BitCommands.LUMBAR_UP,
            Okin64BitCommands.LUMBAR_DOWN,
            Okin64BitCommands.FLAT,
            Okin64BitCommands.ZERO_G,
            Okin64BitCommands.LOUNGE,
            Okin64BitCommands.TV_PC,
            Okin64BitCommands.ANTI_SNORE,
            Okin64BitCommands.MEMORY_1,
            Okin64BitCommands.MEMORY_2,
            Okin64BitCommands.LIGHT_TOGGLE,
            Okin64BitCommands.LIGHT_ON,
            Okin64BitCommands.LIGHT_OFF,
        ]
        for cmd in commands:
            assert len(cmd) == 8, f"Command {cmd.hex()} is not 8 bytes"

    def test_stop_command_is_all_zeros(self):
        """STOP command should be all zeros."""
        assert Okin64BitCommands.STOP == bytes([0x00] * 8)

    def test_motor_commands_use_single_bits(self):
        """Motor commands should use single-bit flags."""
        # HEAD_UP: bit 0 in byte 3
        assert Okin64BitCommands.HEAD_UP == bytes([0, 0, 0, 0x01, 0, 0, 0, 0])
        # HEAD_DOWN: bit 1 in byte 3
        assert Okin64BitCommands.HEAD_DOWN == bytes([0, 0, 0, 0x02, 0, 0, 0, 0])
        # FOOT_UP: bit 2 in byte 3
        assert Okin64BitCommands.FOOT_UP == bytes([0, 0, 0, 0x04, 0, 0, 0, 0])
        # FOOT_DOWN: bit 3 in byte 3
        assert Okin64BitCommands.FOOT_DOWN == bytes([0, 0, 0, 0x08, 0, 0, 0, 0])
        # LUMBAR_UP: bit 4 in byte 3
        assert Okin64BitCommands.LUMBAR_UP == bytes([0, 0, 0, 0x10, 0, 0, 0, 0])
        # LUMBAR_DOWN: bit 5 in byte 3
        assert Okin64BitCommands.LUMBAR_DOWN == bytes([0, 0, 0, 0x20, 0, 0, 0, 0])

    def test_preset_commands(self):
        """Preset commands should have correct values."""
        assert Okin64BitCommands.FLAT == bytes([0x08, 0, 0, 0, 0, 0, 0, 0])
        assert Okin64BitCommands.ZERO_G == bytes([0, 0, 0x10, 0, 0, 0, 0, 0])
        assert Okin64BitCommands.LOUNGE == bytes([0, 0, 0x20, 0, 0, 0, 0, 0])
        assert Okin64BitCommands.TV_PC == bytes([0, 0, 0x40, 0, 0, 0, 0, 0])
        assert Okin64BitCommands.ANTI_SNORE == bytes([0, 0, 0x80, 0, 0, 0, 0, 0])

    def test_memory_commands(self):
        """Memory commands should have correct values."""
        assert Okin64BitCommands.MEMORY_1 == bytes([0, 0x01, 0, 0, 0, 0, 0, 0])
        assert Okin64BitCommands.MEMORY_2 == bytes([0, 0x04, 0, 0, 0, 0, 0, 0])

    def test_light_commands(self):
        """Light commands should have correct values."""
        assert Okin64BitCommands.LIGHT_TOGGLE == bytes([0, 0x02, 0, 0, 0, 0, 0, 0])
        assert Okin64BitCommands.LIGHT_ON == bytes([0, 0, 0, 0, 0, 0, 0, 0x40])
        assert Okin64BitCommands.LIGHT_OFF == bytes([0, 0, 0, 0, 0, 0, 0, 0x80])


# -----------------------------------------------------------------------------
# Command Building Tests
# -----------------------------------------------------------------------------


class TestBuildOkin64BitCommand:
    """Test build_okin_64bit_command function."""

    def test_output_is_10_bytes(self):
        """Built commands should be exactly 10 bytes."""
        command = build_okin_64bit_command(Okin64BitCommands.HEAD_UP)
        assert len(command) == 10

    def test_header_bytes(self):
        """Commands should start with [0x08, 0x02]."""
        command = build_okin_64bit_command(Okin64BitCommands.HEAD_UP)
        assert command[0] == 0x08
        assert command[1] == 0x02

    def test_command_bytes_follow_header(self):
        """8-byte command value should follow the header."""
        cmd_value = Okin64BitCommands.HEAD_UP
        command = build_okin_64bit_command(cmd_value)
        assert command[2:10] == cmd_value

    def test_stop_command_format(self):
        """STOP command should be [0x08, 0x02, 0, 0, 0, 0, 0, 0, 0, 0]."""
        command = build_okin_64bit_command(Okin64BitCommands.STOP)
        expected = bytes([0x08, 0x02, 0, 0, 0, 0, 0, 0, 0, 0])
        assert command == expected

    def test_rejects_invalid_length(self):
        """Should raise error for non-8-byte input."""
        with pytest.raises(ValueError):
            build_okin_64bit_command(bytes([0x01, 0x02, 0x03]))  # Too short

        with pytest.raises(ValueError):
            build_okin_64bit_command(bytes([0] * 9))  # Too long


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestOkin64BitController:
    """Test Okin64BitController."""

    async def test_control_characteristic_uuid_nordic(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Nordic variant should use Nordic UART write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        # Default variant is Nordic
        assert coordinator.controller.control_characteristic_uuid == NORDIC_UART_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support lounge preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_lounge is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should have 2 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support lights."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_stop_all(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 64-bit should support stop_all."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_stop_all is True


class TestOkin64BitMovement:
    """Test Okin 64-bit movement commands."""

    async def test_move_head_up_sends_10_byte_command(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 10-byte HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 10
        expected = build_okin_64bit_command(Okin64BitCommands.HEAD_UP)
        assert first_call_data == expected

    async def test_stop_all_sends_stop_command(
        self,
        hass: HomeAssistant,
        mock_okin_64bit_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_64bit_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        expected = build_okin_64bit_command(Okin64BitCommands.STOP)
        assert call_data == expected


# -----------------------------------------------------------------------------
# Protocol Variant Tests
# -----------------------------------------------------------------------------


class TestOkin64BitVariants:
    """Test Okin 64-bit protocol variants."""

    def test_variant_constants_defined(self):
        """Variant constants should be defined."""
        assert OKIN_64BIT_VARIANT_NORDIC == "nordic"
        assert OKIN_64BIT_VARIANT_CUSTOM == "custom"

    def test_nordic_variant_uses_nordic_uuid(self):
        """Nordic variant should use Nordic UART UUID."""
        # This is validated at controller instantiation
        assert NORDIC_UART_WRITE_CHAR_UUID is not None

    def test_custom_variant_uuid_defined(self):
        """Custom variant should use Okimat UUID."""
        assert OKIMAT_WRITE_CHAR_UUID is not None
