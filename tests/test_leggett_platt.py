"""Tests for Leggett & Platt bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.leggett_platt import (
    LeggettPlattController,
    LeggettPlattGen2Commands,
    LeggettPlattOkinCommands,
    int_to_bytes,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_PLATT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    LEGGETT_GEN2_WRITE_CHAR_UUID,
    LEGGETT_OKIN_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestLeggettPlattHelpers:
    """Test Leggett & Platt helper functions."""

    def test_int_to_bytes(self):
        """Test integer to big-endian bytes conversion."""
        assert int_to_bytes(0x1) == [0x00, 0x00, 0x00, 0x01]
        assert int_to_bytes(0x100) == [0x00, 0x00, 0x01, 0x00]
        assert int_to_bytes(0x8000000) == [0x08, 0x00, 0x00, 0x00]


class TestLeggettPlattGen2Commands:
    """Test Leggett & Platt Gen2 ASCII command constants."""

    def test_preset_commands(self):
        """Test preset command values."""
        assert LeggettPlattGen2Commands.PRESET_FLAT == b"MEM 0"
        assert LeggettPlattGen2Commands.PRESET_UNWIND == b"MEM 1"
        assert LeggettPlattGen2Commands.PRESET_SLEEP == b"MEM 2"
        assert LeggettPlattGen2Commands.PRESET_WAKE_UP == b"MEM 3"
        assert LeggettPlattGen2Commands.PRESET_RELAX == b"MEM 4"
        assert LeggettPlattGen2Commands.PRESET_ANTI_SNORE == b"SNR"

    def test_program_commands(self):
        """Test program command values."""
        assert LeggettPlattGen2Commands.PROGRAM_UNWIND == b"SMEM 1"
        assert LeggettPlattGen2Commands.PROGRAM_SLEEP == b"SMEM 2"
        assert LeggettPlattGen2Commands.PROGRAM_WAKE_UP == b"SMEM 3"
        assert LeggettPlattGen2Commands.PROGRAM_RELAX == b"SMEM 4"

    def test_control_commands(self):
        """Test control command values."""
        assert LeggettPlattGen2Commands.STOP == b"STOP"
        assert LeggettPlattGen2Commands.GET_STATE == b"GET STATE"

    def test_rgb_set(self):
        """Test RGB color command factory."""
        cmd = LeggettPlattGen2Commands.rgb_set(255, 128, 64, 200)
        assert cmd == b"RGBSET 0:FF8040C8"

    def test_massage_head_strength(self):
        """Test head massage strength command factory."""
        cmd = LeggettPlattGen2Commands.massage_head_strength(5)
        assert cmd == b"MVI 0:5"

    def test_massage_foot_strength(self):
        """Test foot massage strength command factory."""
        cmd = LeggettPlattGen2Commands.massage_foot_strength(7)
        assert cmd == b"MVI 1:7"


class TestLeggettPlattOkinCommands:
    """Test Leggett & Platt Okin command constants."""

    def test_preset_commands(self):
        """Test preset command values."""
        assert LeggettPlattOkinCommands.PRESET_FLAT == 0x8000000
        assert LeggettPlattOkinCommands.PRESET_ZERO_G == 0x1000
        assert LeggettPlattOkinCommands.PRESET_MEMORY_1 == 0x2000
        assert LeggettPlattOkinCommands.PRESET_MEMORY_2 == 0x4000
        assert LeggettPlattOkinCommands.PRESET_MEMORY_3 == 0x8000
        assert LeggettPlattOkinCommands.PRESET_MEMORY_4 == 0x10000

    def test_motor_commands(self):
        """Test motor command values."""
        assert LeggettPlattOkinCommands.MOTOR_HEAD_UP == 0x1
        assert LeggettPlattOkinCommands.MOTOR_HEAD_DOWN == 0x2
        assert LeggettPlattOkinCommands.MOTOR_FEET_UP == 0x4
        assert LeggettPlattOkinCommands.MOTOR_FEET_DOWN == 0x8


@pytest.fixture
def mock_leggett_gen2_config_entry_data() -> dict:
    """Return mock config entry data for Leggett & Platt Gen2 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Leggett Gen2 Test Bed",
        CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_leggett_gen2_config_entry(
    hass: HomeAssistant, mock_leggett_gen2_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Leggett & Platt Gen2 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Leggett Gen2 Test Bed",
        data=mock_leggett_gen2_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="leggett_gen2_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestLeggettPlattControllerGen2:
    """Test Leggett & Platt Gen2 controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == LEGGETT_GEN2_WRITE_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        command = LeggettPlattGen2Commands.STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, command, response=True
        )


class TestLeggettPlattControllerOkin:
    """Test Leggett & Platt Okin controller variant."""

    async def test_build_okin_command(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
    ):
        """Test Okin variant command format."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        # Create an Okin controller directly
        controller = LeggettPlattController(coordinator, variant="okin")

        # Okin format: [0x04, 0x02, ...int_bytes]
        command = controller._build_okin_command(LeggettPlattOkinCommands.MOTOR_HEAD_UP)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])


class TestLeggettPlattMovement:
    """Test Leggett & Platt movement commands."""

    async def test_move_head_up_gen2_warns(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test move head up on Gen2 logs warning (position-based control)."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        assert "position-based control" in caplog.text

    async def test_move_head_stop_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head stop sends STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_stop()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettPlattGen2Commands.STOP, response=True
        )

    async def test_stop_all_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends STOP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettPlattGen2Commands.STOP, response=True
        )


class TestLeggettPlattPresets:
    """Test Leggett & Platt preset commands."""

    async def test_preset_flat_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == LeggettPlattGen2Commands.PRESET_FLAT

    async def test_preset_anti_snore_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == LeggettPlattGen2Commands.PRESET_ANTI_SNORE

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LeggettPlattGen2Commands.PRESET_UNWIND),
            (2, LeggettPlattGen2Commands.PRESET_SLEEP),
            (3, LeggettPlattGen2Commands.PRESET_WAKE_UP),
            (4, LeggettPlattGen2Commands.PRESET_RELAX),
        ],
    )
    async def test_preset_memory_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_command

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LeggettPlattGen2Commands.PROGRAM_UNWIND),
            (2, LeggettPlattGen2Commands.PROGRAM_SLEEP),
            (3, LeggettPlattGen2Commands.PROGRAM_WAKE_UP),
            (4, LeggettPlattGen2Commands.PROGRAM_RELAX),
        ],
    )
    async def test_program_memory_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test program memory commands on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected_command, response=True
        )


class TestLeggettPlattLights:
    """Test Leggett & Platt light commands."""

    async def test_lights_toggle_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle on Gen2 sends RGB_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettPlattGen2Commands.RGB_OFF, response=True
        )

    async def test_lights_on_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights on Gen2 sends RGB white command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()

        expected = LeggettPlattGen2Commands.rgb_set(255, 255, 255, 255)
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_lights_off_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights off Gen2 sends RGB_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettPlattGen2Commands.RGB_OFF, response=True
        )


class TestLeggettPlattMassage:
    """Test Leggett & Platt massage commands."""

    async def test_massage_off_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_off()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # Should send head(0) and foot(0)
        assert len(calls) >= 2

    async def test_massage_head_up_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage up on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        # Level should increment to 1
        expected = LeggettPlattGen2Commands.massage_head_strength(1)
        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, expected, response=True
        )

    async def test_massage_toggle_gen2(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle on Gen2."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LEGGETT_GEN2_WRITE_CHAR_UUID, LeggettPlattGen2Commands.MASSAGE_WAVE_ON, response=True
        )


class TestLeggettPlattPositionNotifications:
    """Test Leggett & Platt position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_leggett_gen2_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Leggett & Platt doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_leggett_gen2_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text
