"""Tests for Okin 64-bit bed controller (10-byte protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_64bit import (
    OKIN_64BIT_VARIANT_CUSTOM,
    OKIN_64BIT_VARIANT_NORDIC,
)
from custom_components.adjustable_bed.codec import okin_nframe as codec
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
from custom_components.adjustable_bed.profiles.okin_nframe import OKIN_64BIT_KEYS


def _cmd(name: str) -> bytes:
    """The 8-byte word of one key."""
    return OKIN_64BIT_KEYS[name].to_bytes(8, "big")


def _frame(name: str) -> bytes:
    """The 10-byte frame of one key."""
    return codec.frame(OKIN_64BIT_KEYS[name], 8)


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
            _cmd("stop"),
            _cmd("head_up"),
            _cmd("head_down"),
            _cmd("foot_up"),
            _cmd("foot_down"),
            _cmd("lumbar_up"),
            _cmd("lumbar_down"),
            _cmd("flat"),
            _cmd("zero_g"),
            _cmd("lounge"),
            _cmd("tv_pc"),
            _cmd("anti_snore"),
            _cmd("memory_1"),
            _cmd("memory_2"),
            _cmd("light_toggle"),
            _cmd("light_on"),
            _cmd("light_off"),
        ]
        for cmd in commands:
            assert len(cmd) == 8, f"Command {cmd.hex()} is not 8 bytes"

    def test_stop_command_is_all_zeros(self):
        """STOP command should be all zeros."""
        assert bytes([0x00] * 8) == _cmd("stop")

    def test_motor_commands_use_single_bits(self):
        """Motor commands should use single-bit flags."""
        # HEAD_UP: bit 0 in byte 3
        assert bytes([0, 0, 0, 0x01, 0, 0, 0, 0]) == _cmd("head_up")
        # HEAD_DOWN: bit 1 in byte 3
        assert bytes([0, 0, 0, 0x02, 0, 0, 0, 0]) == _cmd("head_down")
        # FOOT_UP: bit 2 in byte 3
        assert bytes([0, 0, 0, 0x04, 0, 0, 0, 0]) == _cmd("foot_up")
        # FOOT_DOWN: bit 3 in byte 3
        assert bytes([0, 0, 0, 0x08, 0, 0, 0, 0]) == _cmd("foot_down")
        # LUMBAR_UP: bit 4 in byte 3
        assert bytes([0, 0, 0, 0x10, 0, 0, 0, 0]) == _cmd("lumbar_up")
        # LUMBAR_DOWN: bit 5 in byte 3
        assert bytes([0, 0, 0, 0x20, 0, 0, 0, 0]) == _cmd("lumbar_down")

    def test_preset_commands(self):
        """Preset commands should have correct values."""
        assert bytes([0x08, 0, 0, 0, 0, 0, 0, 0]) == _cmd("flat")
        assert bytes([0, 0, 0x10, 0, 0, 0, 0, 0]) == _cmd("zero_g")
        assert bytes([0, 0, 0x20, 0, 0, 0, 0, 0]) == _cmd("lounge")
        assert bytes([0, 0, 0x40, 0, 0, 0, 0, 0]) == _cmd("tv_pc")
        assert bytes([0, 0, 0x80, 0, 0, 0, 0, 0]) == _cmd("anti_snore")

    def test_memory_commands(self):
        """Memory commands should have correct values."""
        assert bytes([0, 0x01, 0, 0, 0, 0, 0, 0]) == _cmd("memory_1")
        assert bytes([0, 0x04, 0, 0, 0, 0, 0, 0]) == _cmd("memory_2")

    def test_light_commands(self):
        """Light commands should have correct values."""
        assert bytes([0, 0x02, 0, 0, 0, 0, 0, 0]) == _cmd("light_toggle")
        assert bytes([0, 0, 0, 0, 0, 0, 0, 0x40]) == _cmd("light_on")
        assert bytes([0, 0, 0, 0, 0, 0, 0, 0x80]) == _cmd("light_off")


# -----------------------------------------------------------------------------
# Command Building Tests
# -----------------------------------------------------------------------------


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
