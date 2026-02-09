"""Tests for BedTech bed controller (5-byte ASCII protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.bedtech import (
    BedTechCommands,
    BedTechController,
    build_bedtech_command,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDTECH,
    BEDTECH_WRITE_CHAR_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_bedtech_config_entry_data() -> dict:
    """Return mock config entry data for BedTech bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "BedTech Test Bed",
        CONF_BED_TYPE: BED_TYPE_BEDTECH,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_bedtech_config_entry(
    hass: HomeAssistant, mock_bedtech_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for BedTech bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BedTech Test Bed",
        data=mock_bedtech_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="bedtech_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestBedTechCommands:
    """Test BedTech command constants."""

    def test_head_commands(self):
        """Head motor commands should be single characters."""
        assert BedTechCommands.HEAD_UP == "$"
        assert BedTechCommands.HEAD_DOWN == "%"

    def test_foot_commands(self):
        """Foot motor commands should be single characters."""
        assert BedTechCommands.FOOT_UP == "&"
        assert BedTechCommands.FOOT_DOWN == "'"

    def test_leg_commands(self):
        """Leg/pillow motor commands should be single characters."""
        assert BedTechCommands.LEG_UP == ")"
        assert BedTechCommands.LEG_DOWN == "*"

    def test_preset_commands(self):
        """Preset commands should be single characters."""
        assert BedTechCommands.PRESET_FLAT == "1"
        assert BedTechCommands.PRESET_ZERO_G == "E"
        assert BedTechCommands.PRESET_ANTI_SNORE == "F"
        assert BedTechCommands.PRESET_TV == "X"
        assert BedTechCommands.PRESET_LOUNGE == "e"

    def test_dual_base_commands_start_with_underscore(self):
        """Dual base commands should start with underscore."""
        assert BedTechCommands.HEAD2_UP == "_$"
        assert BedTechCommands.HEAD2_DOWN == "_%"
        assert BedTechCommands.PRESET2_FLAT == "_1"
        assert BedTechCommands.PRESET2_ZERO_G == "_E"

    def test_massage_commands(self):
        """Massage commands should be defined."""
        assert BedTechCommands.MASSAGE_ON == "]"
        assert BedTechCommands.MASSAGE_OFF == "^"
        assert BedTechCommands.MASSAGE_SWITCH == "H"

    def test_light_commands(self):
        """Light commands should be defined."""
        assert BedTechCommands.LIGHT_GO == "."
        assert BedTechCommands.LIGHT_OFF == "u"
        assert BedTechCommands.LIGHT_TOGGLE == "<"

    def test_memory_commands(self):
        """Memory commands should be defined."""
        assert BedTechCommands.MEMORY_GO == "/"
        assert BedTechCommands.MEMORY_SAVE == ","


# -----------------------------------------------------------------------------
# Command Building Tests
# -----------------------------------------------------------------------------


class TestBuildBedtechCommand:
    """Test build_bedtech_command function."""

    def test_single_char_command_is_5_bytes(self):
        """Single character commands should be 5 bytes."""
        command = build_bedtech_command("$")  # HEAD_UP
        assert len(command) == 5

    def test_single_char_command_format(self):
        """Single char format: [0x6E, 0x01, 0x00, char, char + 0x6F]."""
        command = build_bedtech_command("$")  # HEAD_UP = 0x24
        assert command[0] == 0x6E
        assert command[1] == 0x01
        assert command[2] == 0x00
        assert command[3] == ord("$")  # 0x24
        assert command[4] == (ord("$") + 0x6F) & 0xFF  # 0x93

    def test_dual_base_command_is_5_bytes(self):
        """Dual base commands should also be 5 bytes."""
        command = build_bedtech_command("_$")  # HEAD2_UP
        assert len(command) == 5

    def test_dual_base_command_format(self):
        """Dual base format: [0x6E, 0x01, 0x01, char2, char2 + 0x70]."""
        command = build_bedtech_command("_$")  # char2 = 0x24
        assert command[0] == 0x6E
        assert command[1] == 0x01
        assert command[2] == 0x01  # Dual base flag
        assert command[3] == ord("$")  # 0x24
        assert command[4] == (ord("$") + 0x70) & 0xFF  # 0x94

    def test_checksum_calculation_single(self):
        """Verify checksum calculation for single char commands."""
        # HEAD_UP: $ = 0x24, checksum = 0x24 + 0x6F = 0x93
        command = build_bedtech_command("$")
        assert command[4] == 0x93

        # FOOT_UP: & = 0x26, checksum = 0x26 + 0x6F = 0x95
        command = build_bedtech_command("&")
        assert command[4] == 0x95

    def test_checksum_calculation_dual(self):
        """Verify checksum calculation for dual base commands."""
        # HEAD2_UP: _$ -> $ = 0x24, checksum = 0x24 + 0x70 = 0x94
        command = build_bedtech_command("_$")
        assert command[4] == 0x94


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestBedTechController:
    """Test BedTechController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use BedTech write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == BEDTECH_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support lounge preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_lounge is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should have 2 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support lights."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_has_pillow_support(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support pillow/leg motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_pillow_support is True

    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_supports_stop_all(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
    ):
        """BedTech should support stop_all (BT6500 compatibility stop)."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_stop_all is True


class TestBedTechMovement:
    """Test BedTech movement commands."""

    async def test_move_head_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        # Should be 5-byte command with HEAD_UP character
        assert len(first_call_data) == 5
        assert first_call_data[3] == ord(BedTechCommands.HEAD_UP)

    async def test_move_feet_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """move_feet_up should send FOOT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_feet_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == ord(BedTechCommands.FOOT_UP)

    async def test_move_pillow_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """move_pillow_up should send LEG_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_pillow_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[3] == ord(BedTechCommands.LEG_UP)

class TestBedTechPresets:
    """Test BedTech preset commands."""

    async def test_preset_flat_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send PRESET_FLAT command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord(BedTechCommands.PRESET_FLAT)

    async def test_preset_zero_g_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send PRESET_ZERO_G command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord(BedTechCommands.PRESET_ZERO_G)

    async def test_preset_anti_snore_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """preset_anti_snore should send PRESET_ANTI_SNORE command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_anti_snore()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord(BedTechCommands.PRESET_ANTI_SNORE)


class TestBedTechLights:
    """Test BedTech light commands."""

    async def test_lights_on_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on should send LIGHT_GO command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord(BedTechCommands.LIGHT_GO)

    async def test_lights_off_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should send LIGHT_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord(BedTechCommands.LIGHT_OFF)

    async def test_lights_toggle_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """lights_toggle should send LIGHT_TOGGLE command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_toggle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord(BedTechCommands.LIGHT_TOGGLE)
