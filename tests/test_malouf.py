"""Tests for Malouf bed controllers (NEW_OKIN and LEGACY_OKIN protocols)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.malouf import (
    MaloufCommands,
    MaloufLegacyOkinController,
    MaloufNewOkinController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
    MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_malouf_new_config_entry_data() -> dict:
    """Return mock config entry data for Malouf NEW_OKIN bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Malouf Test Bed",
        CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_malouf_new_config_entry(
    hass: HomeAssistant, mock_malouf_new_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Malouf NEW_OKIN bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malouf Test Bed",
        data=mock_malouf_new_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="malouf_new_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_malouf_legacy_config_entry_data() -> dict:
    """Return mock config entry data for Malouf LEGACY_OKIN bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Malouf Legacy Test Bed",
        CONF_BED_TYPE: BED_TYPE_MALOUF_LEGACY_OKIN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_malouf_legacy_config_entry(
    hass: HomeAssistant, mock_malouf_legacy_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Malouf LEGACY_OKIN bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malouf Legacy Test Bed",
        data=mock_malouf_legacy_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="malouf_legacy_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestMaloufCommands:
    """Test Malouf command constants."""

    def test_motor_command_values(self):
        """Test motor command values are single-bit flags."""
        assert MaloufCommands.HEAD_UP == 0x1
        assert MaloufCommands.HEAD_DOWN == 0x2
        assert MaloufCommands.FOOT_UP == 0x4
        assert MaloufCommands.FOOT_DOWN == 0x8
        assert MaloufCommands.HEAD_TILT_UP == 0x10
        assert MaloufCommands.HEAD_TILT_DOWN == 0x20
        assert MaloufCommands.LUMBAR_UP == 0x40
        assert MaloufCommands.LUMBAR_DOWN == 0x80

    def test_dual_commands_combine_flags(self):
        """Test dual motor commands are combinations of single flags."""
        assert MaloufCommands.DUAL_UP == MaloufCommands.HEAD_UP | MaloufCommands.FOOT_UP
        assert MaloufCommands.DUAL_DOWN == MaloufCommands.HEAD_DOWN | MaloufCommands.FOOT_DOWN

    def test_stop_command_is_zero(self):
        """Test STOP command is 0."""
        assert MaloufCommands.STOP == 0

    def test_preset_command_values(self):
        """Test preset command values."""
        assert MaloufCommands.ALL_FLAT == 0x8000000
        assert MaloufCommands.ZERO_G == 0x1000
        assert MaloufCommands.LOUNGE == 0x2000
        assert MaloufCommands.ANTI_SNORE == 0x8000
        assert MaloufCommands.TV_READ == 0x4000
        assert MaloufCommands.MEMORY_1 == 0x10000
        assert MaloufCommands.MEMORY_2 == 0x40000


class TestMaloufNewOkinController:
    """Test Malouf NEW_OKIN controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == MALOUF_NEW_OKIN_WRITE_CHAR_UUID

    async def test_build_command_format(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test NEW_OKIN command format is 8 bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(MaloufCommands.HEAD_UP)

        # Format: [0x05, 0x02, (cmd>>24)&0xFF, (cmd>>16)&0xFF, (cmd>>8)&0xFF, cmd&0xFF, 0x00, 0x00]
        assert len(command) == 8
        assert command[0] == 0x05
        assert command[1] == 0x02
        assert command[-2:] == b"\x00\x00"

    async def test_build_command_encodes_value(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test command value is correctly encoded in big-endian."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        # Test with HEAD_UP (0x01)
        command = coordinator.controller._build_command(MaloufCommands.HEAD_UP)
        assert command[5] == 0x01  # Lowest byte
        assert command[4] == 0x00
        assert command[3] == 0x00
        assert command[2] == 0x00

    async def test_build_command_large_value(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test encoding of larger command values."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        # Test with ALL_FLAT (0x8000000)
        command = coordinator.controller._build_command(MaloufCommands.ALL_FLAT)
        # 0x8000000 = 0x08, 0x00, 0x00, 0x00 in big-endian
        assert command[2] == 0x08
        assert command[3] == 0x00
        assert command[4] == 0x00
        assert command[5] == 0x00


class TestMaloufLegacyOkinController:
    """Test Malouf LEGACY_OKIN controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID

    async def test_build_command_format(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test LEGACY_OKIN command format is 9 bytes."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(MaloufCommands.HEAD_UP)

        # Format: [0xE6, 0xFE, 0x16, cmd&0xFF, (cmd>>8)&0xFF, (cmd>>16)&0xFF, (cmd>>24)&0xFF, 0x00, checksum]
        assert len(command) == 9
        assert command[0] == 0xE6
        assert command[1] == 0xFE
        assert command[2] == 0x16
        assert command[7] == 0x00

    async def test_build_command_checksum(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test LEGACY_OKIN checksum calculation."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(MaloufCommands.HEAD_UP)

        # Checksum: (~sum(bytes[0:8])) & 0xFF
        data_sum = sum(command[:8])
        expected_checksum = (~data_sum) & 0xFF
        assert command[8] == expected_checksum

    async def test_build_command_encodes_value_little_endian(
        self,
        hass: HomeAssistant,
        mock_malouf_legacy_config_entry,
        mock_coordinator_connected,
    ):
        """Test command value is correctly encoded in little-endian."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_legacy_config_entry)
        await coordinator.async_connect()

        # Test with HEAD_UP (0x01)
        command = coordinator.controller._build_command(MaloufCommands.HEAD_UP)
        assert command[3] == 0x01  # Lowest byte
        assert command[4] == 0x00
        assert command[5] == 0x00
        assert command[6] == 0x00


class TestMaloufNewOkinMovement:
    """Test Malouf NEW_OKIN movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends HEAD_UP command followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be HEAD_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MaloufCommands.HEAD_UP)
        assert first_command == expected
        # Last call should be STOP
        last_command = calls[-1][0][1]
        stop_cmd = coordinator.controller._build_command(MaloufCommands.STOP)
        assert last_command == stop_cmd

    async def test_move_feet_down(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet down sends FOOT_DOWN command followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MaloufCommands.FOOT_DOWN)
        assert first_command == expected

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_all sends STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
            coordinator.controller._build_command(MaloufCommands.STOP),
            response=True,
        )


class TestMaloufNewOkinPresets:
    """Test Malouf NEW_OKIN preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = coordinator.controller._build_command(MaloufCommands.ALL_FLAT)
        expected_stop = coordinator.controller._build_command(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero-G sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = coordinator.controller._build_command(MaloufCommands.ZERO_G)
        expected_stop = coordinator.controller._build_command(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop

    async def test_preset_memory_1(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory 1 sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = coordinator.controller._build_command(MaloufCommands.MEMORY_1)
        expected_stop = coordinator.controller._build_command(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop

    async def test_preset_memory_2(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory 2 sends command then STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(2)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        sent_commands = [call.args[1] for call in calls]
        expected_preset = coordinator.controller._build_command(MaloufCommands.MEMORY_2)
        expected_stop = coordinator.controller._build_command(MaloufCommands.STOP)
        assert expected_preset in sent_commands
        assert sent_commands[-1] == expected_stop


class TestMaloufCapabilities:
    """Test Malouf capability properties."""

    async def test_supports_lumbar(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test Malouf reports lumbar support."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_tilt(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test Malouf reports tilt support."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_tilt_support is True

    async def test_supports_lights_toggle_only(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test Malouf supports lights but only toggle control."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True
        assert coordinator.controller.supports_discrete_light_control is False

    async def test_memory_slot_count_is_two(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test Malouf reports 2 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 2

    async def test_does_not_support_memory_programming(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
    ):
        """Test Malouf does not support programming memory positions."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is False


class TestMaloufLumbarAndTilt:
    """Test Malouf lumbar and tilt motor control."""

    async def test_move_lumbar_up(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move lumbar up sends LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_lumbar_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MaloufCommands.LUMBAR_UP)
        assert first_command == expected

    async def test_move_tilt_up(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move tilt up sends HEAD_TILT_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_tilt_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(MaloufCommands.HEAD_TILT_UP)
        assert first_command == expected


class TestMaloufMassage:
    """Test Malouf massage commands."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        expected = coordinator.controller._build_command(MaloufCommands.MASSAGE_OFF)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage head intensity up command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected = coordinator.controller._build_command(MaloufCommands.MASSAGE_HEAD)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_massage_head_down(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage head intensity down command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_down()

        expected = coordinator.controller._build_command(MaloufCommands.MASSAGE_HEAD_MINUS)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID, expected, response=True
        )


class TestMaloufLights:
    """Test Malouf light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected = coordinator.controller._build_command(MaloufCommands.LIGHT_SWITCH)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_lights_on_calls_toggle(
        self,
        hass: HomeAssistant,
        mock_malouf_new_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights_on calls toggle (no discrete control)."""
        coordinator = AdjustableBedCoordinator(hass, mock_malouf_new_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()

        expected = coordinator.controller._build_command(MaloufCommands.LIGHT_SWITCH)
        mock_bleak_client.write_gatt_char.assert_called_with(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID, expected, response=True
        )
