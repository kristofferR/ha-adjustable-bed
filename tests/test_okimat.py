"""Tests for Okimat bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okimat import (
    OkimatCommands,
    OkimatController,
    int_to_bytes,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OKIMAT_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestOkimatHelpers:
    """Test Okimat helper functions."""

    def test_int_to_bytes(self):
        """Test integer to big-endian bytes conversion."""
        assert int_to_bytes(0x1) == [0x00, 0x00, 0x00, 0x01]
        assert int_to_bytes(0x100) == [0x00, 0x00, 0x01, 0x00]
        assert int_to_bytes(0x8000000) == [0x08, 0x00, 0x00, 0x00]


class TestOkimatCommands:
    """Test Okimat command constants."""

    def test_preset_commands(self):
        """Test preset command values (same as Keeson/Okin protocol)."""
        assert OkimatCommands.PRESET_FLAT == 0x8000000
        assert OkimatCommands.PRESET_ZERO_G == 0x1000
        assert OkimatCommands.PRESET_MEMORY_1 == 0x2000
        assert OkimatCommands.PRESET_MEMORY_2 == 0x4000
        assert OkimatCommands.PRESET_MEMORY_3 == 0x8000
        assert OkimatCommands.PRESET_MEMORY_4 == 0x10000

    def test_motor_commands(self):
        """Test motor command values."""
        assert OkimatCommands.MOTOR_HEAD_UP == 0x1
        assert OkimatCommands.MOTOR_HEAD_DOWN == 0x2
        assert OkimatCommands.MOTOR_FEET_UP == 0x4
        assert OkimatCommands.MOTOR_FEET_DOWN == 0x8
        assert OkimatCommands.MOTOR_TILT_UP == 0x10
        assert OkimatCommands.MOTOR_TILT_DOWN == 0x20
        assert OkimatCommands.MOTOR_LUMBAR_UP == 0x40
        assert OkimatCommands.MOTOR_LUMBAR_DOWN == 0x80

    def test_massage_commands(self):
        """Test massage command values."""
        assert OkimatCommands.MASSAGE_HEAD_UP == 0x800
        assert OkimatCommands.MASSAGE_HEAD_DOWN == 0x800000
        assert OkimatCommands.MASSAGE_FOOT_UP == 0x400
        assert OkimatCommands.MASSAGE_FOOT_DOWN == 0x1000000
        assert OkimatCommands.MASSAGE_STEP == 0x100
        assert OkimatCommands.MASSAGE_TIMER_STEP == 0x200

    def test_light_commands(self):
        """Test light command values."""
        assert OkimatCommands.TOGGLE_LIGHTS == 0x20000


@pytest.fixture
def mock_okimat_config_entry_data() -> dict:
    """Return mock config entry data for Okimat bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okimat Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okimat_config_entry(
    hass: HomeAssistant, mock_okimat_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okimat bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okimat Test Bed",
        data=mock_okimat_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestOkimatController:
    """Test Okimat controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == OKIMAT_WRITE_CHAR_UUID

    async def test_build_command(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building format."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        # Okimat format: [0x04, 0x02, ...int_bytes]
        command = coordinator.controller._build_command(OkimatCommands.MOTOR_HEAD_UP)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(0)
            )


class TestOkimatMovement:
    """Test Okimat movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be stop (zero command)
        last_command = calls[-1][0][1]
        expected_stop = coordinator.controller._build_command(0)
        assert last_command == expected_stop

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends zero command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_stop = coordinator.controller._build_command(0)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_stop, response=True
        )


class TestOkimatPresets:
    """Test Okimat preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected_cmd = coordinator.controller._build_command(OkimatCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, OkimatCommands.PRESET_MEMORY_1),
            (2, OkimatCommands.PRESET_MEMORY_2),
            (3, OkimatCommands.PRESET_MEMORY_3),
            (4, OkimatCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_program_memory_not_supported(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text


class TestOkimatLights:
    """Test Okimat light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected_cmd = coordinator.controller._build_command(OkimatCommands.TOGGLE_LIGHTS)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )


class TestOkimatMassage:
    """Test Okimat massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(OkimatCommands.MASSAGE_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected_cmd = coordinator.controller._build_command(OkimatCommands.MASSAGE_HEAD_UP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage intensity down."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        expected_cmd = coordinator.controller._build_command(OkimatCommands.MASSAGE_FOOT_DOWN)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage timer step."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        expected_cmd = coordinator.controller._build_command(OkimatCommands.MASSAGE_TIMER_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )


class TestOkimatPositionNotifications:
    """Test Okimat position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
        caplog,
    ):
        """Test that Okimat doesn't support position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert "don't support position notifications" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_okimat_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okimat_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
