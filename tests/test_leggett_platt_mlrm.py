"""Tests for Leggett & Platt MlRM variant bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.leggett_platt_mlrm import (
    LeggettPlattMlrmCommands,
)
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


class TestLeggettPlattMlrmCommands:
    """Test Leggett & Platt MlRM command constants."""

    def test_preset_commands(self):
        """Test preset command values."""
        assert LeggettPlattMlrmCommands.PRESET_FLAT == 0x31
        assert LeggettPlattMlrmCommands.PRESET_ANTI_SNORE == 0x46
        assert LeggettPlattMlrmCommands.PRESET_LOUNGE == 0x59
        assert LeggettPlattMlrmCommands.PRESET_MEMORY_1 == 0x2E
        assert LeggettPlattMlrmCommands.PRESET_MEMORY_2 == 0x2F
        assert LeggettPlattMlrmCommands.PRESET_TV == 0x58
        assert LeggettPlattMlrmCommands.PRESET_ZERO_G == 0x45

    def test_program_commands(self):
        """Test program command values."""
        assert LeggettPlattMlrmCommands.PROGRAM_ANTI_SNORE == 0x69
        assert LeggettPlattMlrmCommands.PROGRAM_LOUNGE == 0x65
        assert LeggettPlattMlrmCommands.PROGRAM_MEMORY_1 == 0x2B
        assert LeggettPlattMlrmCommands.PROGRAM_MEMORY_2 == 0x2C
        assert LeggettPlattMlrmCommands.PROGRAM_TV == 0x64
        assert LeggettPlattMlrmCommands.PROGRAM_ZERO_G == 0x66

    def test_motor_commands(self):
        """Test motor command values."""
        assert LeggettPlattMlrmCommands.MOTOR_PILLOW_UP == 0x3F
        assert LeggettPlattMlrmCommands.MOTOR_PILLOW_DOWN == 0x40
        assert LeggettPlattMlrmCommands.MOTOR_HEAD_UP == 0x24
        assert LeggettPlattMlrmCommands.MOTOR_HEAD_DOWN == 0x25
        assert LeggettPlattMlrmCommands.MOTOR_FEET_UP == 0x26
        assert LeggettPlattMlrmCommands.MOTOR_FEET_DOWN == 0x27
        assert LeggettPlattMlrmCommands.MOTOR_LUMBAR_UP == 0x41
        assert LeggettPlattMlrmCommands.MOTOR_LUMBAR_DOWN == 0x42
        assert LeggettPlattMlrmCommands.END == 0x6E

    def test_massage_discrete_commands(self):
        """Test discrete massage UP/DOWN command values.

        This is the KEY differentiator from standard Richmat WiLinke - discrete UP/DOWN
        instead of step/toggle commands.
        """
        assert LeggettPlattMlrmCommands.MASSAGE_HEAD_UP == 0x4C
        assert LeggettPlattMlrmCommands.MASSAGE_HEAD_DOWN == 0x4D
        assert LeggettPlattMlrmCommands.MASSAGE_FOOT_UP == 0x4E
        assert LeggettPlattMlrmCommands.MASSAGE_FOOT_DOWN == 0x4F
        assert LeggettPlattMlrmCommands.MASSAGE_MOTOR_STOP == 0x47

    def test_massage_additional_commands(self):
        """Test additional massage command values."""
        assert LeggettPlattMlrmCommands.MASSAGE_MOTOR1_ON_OFF == 0x32
        assert LeggettPlattMlrmCommands.MASSAGE_MOTOR2_ON_OFF == 0x33
        assert LeggettPlattMlrmCommands.MASSAGE_INCREASE_INTENSITY == 0x34
        assert LeggettPlattMlrmCommands.MASSAGE_DECREASE_INTENSITY == 0x35
        assert LeggettPlattMlrmCommands.MASSAGE_PATTERN_STEP == 0x38
        assert LeggettPlattMlrmCommands.MASSAGE_WAVE == 0x39

    def test_light_commands(self):
        """Test light command values."""
        assert LeggettPlattMlrmCommands.LIGHTS_TOGGLE == 0x3C


@pytest.fixture
def mock_leggett_mlrm_config_entry_data() -> dict:
    """Return mock config entry data for Leggett & Platt MlRM variant bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "L&P MlRM Test Bed",
        CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
        CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_MLRM,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_leggett_mlrm_config_entry(
    hass: HomeAssistant, mock_leggett_mlrm_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Leggett & Platt MlRM variant bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="L&P MlRM Test Bed",
        data=mock_leggett_mlrm_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="leggett_mlrm_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestLeggettPlattMlrmController:
    """Test Leggett & Platt MlRM controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == LEGGETT_RICHMAT_CHAR_UUID

    async def test_build_command_wilinke_format(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test command building produces correct WiLinke 5-byte format."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(LeggettPlattMlrmCommands.PRESET_FLAT)
        assert len(command) == 5
        assert command[0] == 0x6E
        assert command[1] == 0x01
        assert command[2] == 0x00
        assert command[3] == LeggettPlattMlrmCommands.PRESET_FLAT

    async def test_build_command_checksum(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test checksum calculation: (0x6E + 0x01 + 0x00 + cmd) & 0xFF."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        # Test with PRESET_FLAT (0x31)
        command = coordinator.controller._build_command(LeggettPlattMlrmCommands.PRESET_FLAT)
        expected_checksum = (0x6E + 0x01 + 0x00 + 0x31) & 0xFF
        assert command[4] == expected_checksum

        # Test with END command (0x6E) - checksum wraps around
        command = coordinator.controller._build_command(LeggettPlattMlrmCommands.END)
        expected_checksum = (0x6E + 0x01 + 0x00 + 0x6E) & 0xFF
        assert command[4] == expected_checksum

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(LeggettPlattMlrmCommands.END)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(LeggettPlattMlrmCommands.END)
            )


class TestLeggettPlattMlrmCapabilities:
    """Test controller capability properties."""

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports zero gravity preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports anti-snore preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports TV preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports lounge preset support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_preset_lounge is True

    async def test_has_no_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test L&P MlRM beds don't have lumbar support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.has_lumbar_support is False

    async def test_has_no_pillow_support(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test L&P MlRM beds don't have pillow support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.has_pillow_support is False

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports light support."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_lights is True

    async def test_no_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test lights are toggle-only (no discrete on/off)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_discrete_light_control is False

    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports 2 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller supports memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.supports_memory_programming is True

    async def test_has_discrete_motor_control(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test controller reports discrete motor control (uses buttons not covers)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()
        assert coordinator.controller.has_discrete_motor_control is True


class TestLeggettPlattMlrmMovement:
    """Test Leggett & Platt MlRM movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends correct command followed by END."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be END command
        last_command = calls[-1][0][1]
        expected_end = coordinator.controller._build_command(LeggettPlattMlrmCommands.END)
        assert last_command == expected_end

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down sends correct command followed by END."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends FEET_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be FEET_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(LeggettPlattMlrmCommands.MOTOR_FEET_UP)
        assert first_command == expected

    async def test_move_legs_down(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs down sends FEET_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(LeggettPlattMlrmCommands.MOTOR_FEET_DOWN)
        assert first_command == expected

    async def test_move_back_aliases_head(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move_back_up is an alias for move_head_up."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(LeggettPlattMlrmCommands.MOTOR_HEAD_UP)
        assert first_command == expected

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move_feet_up sends correct command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(LeggettPlattMlrmCommands.MOTOR_FEET_UP)
        assert first_command == expected

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends END command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_end = coordinator.controller._build_command(LeggettPlattMlrmCommands.END)
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_end, response=True
        )


class TestLeggettPlattMlrmPresets:
    """Test Leggett & Platt MlRM preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected_cmd = coordinator.controller._build_command(LeggettPlattMlrmCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.PRESET_ZERO_G
        )
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.PRESET_ANTI_SNORE
        )
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        expected_cmd = coordinator.controller._build_command(LeggettPlattMlrmCommands.PRESET_TV)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset lounge command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_lounge()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.PRESET_LOUNGE
        )
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        ("memory_num", "expected_value"),
        [
            (1, LeggettPlattMlrmCommands.PRESET_MEMORY_1),
            (2, LeggettPlattMlrmCommands.PRESET_MEMORY_2),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_memory_invalid(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test invalid memory number logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(3)

        assert "Invalid memory number 3" in caplog.text
        # Should not write any command
        assert mock_bleak_client.write_gatt_char.call_count == 0

    @pytest.mark.parametrize(
        ("memory_num", "expected_value"),
        [
            (1, LeggettPlattMlrmCommands.PROGRAM_MEMORY_1),
            (2, LeggettPlattMlrmCommands.PROGRAM_MEMORY_2),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )


class TestLeggettPlattMlrmLights:
    """Test Leggett & Platt MlRM light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.LIGHTS_TOGGLE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_lights_on_is_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights_on calls toggle (no discrete control)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.LIGHTS_TOGGLE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_lights_off_is_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights_off calls toggle (no discrete control)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_off()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.LIGHTS_TOGGLE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )


class TestLeggettPlattMlrmMassage:
    """Test Leggett & Platt MlRM massage commands.

    KEY DIFFERENTIATOR: This controller has discrete UP/DOWN commands for
    massage intensity (0x4C-0x4F) instead of just step/toggle commands.
    """

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage head up sends discrete UP command (0x4C)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_HEAD_UP
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_down(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage head down sends discrete DOWN command (0x4D)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_down()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_HEAD_DOWN
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_up(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage foot up sends discrete UP command (0x4E)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_up()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_FOOT_UP
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage foot down sends discrete DOWN command (0x4F)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_FOOT_DOWN
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_MOTOR_STOP
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_MOTOR1_ON_OFF
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_toggle()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_MOTOR1_ON_OFF
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_toggle()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_MOTOR2_ON_OFF
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_intensity_up(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test overall massage intensity up command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_intensity_up()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_INCREASE_INTENSITY
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_intensity_down(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test overall massage intensity down command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_intensity_down()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_DECREASE_INTENSITY
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage mode step command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_PATTERN_STEP
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_wave_toggle(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage wave toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_wave_toggle()

        expected_cmd = coordinator.controller._build_command(
            LeggettPlattMlrmCommands.MASSAGE_WAVE
        )
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_RICHMAT_CHAR_UUID, expected_cmd, response=True
        )


class TestLeggettPlattMlrmPositionNotifications:
    """Test Leggett & Platt MlRM position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that L&P MlRM doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_leggett_mlrm_config_entry,
        mock_coordinator_connected,  # noqa: ARG002
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_mlrm_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
