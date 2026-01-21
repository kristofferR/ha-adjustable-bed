"""Tests for Ergomotion bed controller (Keeson ergomotion variant)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import (
    KeesonCommands,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_ERGOMOTION,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    ERGOMOTION_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_ergomotion_config_entry_data() -> dict:
    """Return mock config entry data for Ergomotion bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Ergomotion Test Bed",
        CONF_BED_TYPE: BED_TYPE_ERGOMOTION,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,  # Ergomotion supports position feedback
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_ergomotion_config_entry(
    hass: HomeAssistant, mock_ergomotion_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Ergomotion bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Ergomotion Test Bed",
        data=mock_ergomotion_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="ergomotion_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestErgomotionController:
    """Test Keeson controller with ergomotion variant."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == ERGOMOTION_WRITE_CHAR_UUID

    async def test_build_command(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building with checksum."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        # Build a command and verify format
        command = coordinator.controller._build_command(0x1)  # HEAD_UP

        # Should be 8 bytes: header (3) + command (4) + checksum (1)
        assert len(command) == 8
        assert command[:3] == bytes([0xE5, 0xFE, 0x16])
        # Command 0x1 in big-endian (same as Serta - confirmed from APK analysis)
        assert command[3:7] == bytes([0x00, 0x00, 0x00, 0x01])

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            ERGOMOTION_WRITE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(coordinator.controller._build_command(0))


class TestErgomotionMovement:
    """Test Ergomotion movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends movement command then stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
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
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends zero command."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_stop = coordinator.controller._build_command(0)
        mock_bleak_client.write_gatt_char.assert_called_with(
            ERGOMOTION_WRITE_CHAR_UUID, expected_stop, response=True
        )


class TestErgomotionPresets:
    """Test Ergomotion preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.PRESET_TV)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, KeesonCommands.PRESET_MEMORY_1),
            (2, KeesonCommands.PRESET_MEMORY_2),
            (3, KeesonCommands.PRESET_MEMORY_3),
            (4, KeesonCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_program_memory_not_supported(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "don't support programming memory presets" in caplog.text


class TestErgomotionLights:
    """Test Ergomotion light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.TOGGLE_LIGHTS)
        mock_bleak_client.write_gatt_char.assert_called_with(
            ERGOMOTION_WRITE_CHAR_UUID, expected_cmd, response=True
        )


class TestErgomotionMassage:
    """Test Ergomotion massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.MASSAGE_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            ERGOMOTION_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.MASSAGE_HEAD_UP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            ERGOMOTION_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage intensity down."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        expected_cmd = coordinator.controller._build_command(KeesonCommands.MASSAGE_FOOT_DOWN)
        mock_bleak_client.write_gatt_char.assert_called_with(
            ERGOMOTION_WRITE_CHAR_UUID, expected_cmd, response=True
        )


class TestErgomotionPositionNotifications:
    """Test Ergomotion position notification handling."""

    async def test_start_notify(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test starting position notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        # Reset mock since coordinator already calls start_notify during connect
        mock_bleak_client.start_notify.reset_mock()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        # Should have called start_notify on the client
        mock_bleak_client.start_notify.assert_called_once()

    async def test_parse_ed_message(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
    ):
        """Test parsing 0xED position message."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # Create a mock 0xED message (16 bytes)
        # Header: 0xED
        # data1: head_pos (2), foot_pos (2), head_massage (1), foot_massage (1), padding (2)
        # data2: 7 bytes including movement status
        data = bytes(
            [
                0xED,  # Header
                0x32,
                0x00,  # Head position: 50
                0x19,
                0x00,  # Foot position: 25
                0x03,  # Head massage level
                0x02,  # Foot massage level
                0x00,
                0x00,  # Padding
                0x00,
                0x00,
                0x00,
                0x00,
                0x0F,
                0x00,
                0x00,  # data2 with status
            ]
        )

        coordinator.controller._parse_notification(data)

        # Callback should be called for head and feet positions
        assert callback.call_count == 2

    async def test_parse_f0_message(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
    ):
        """Test parsing 0xF0 position message."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # Create a mock 0xF0 message (19 bytes)
        data = bytes(
            [
                0xF0,  # Header
                0x64,
                0x00,  # Head position: 100
                0x32,
                0x00,  # Foot position: 50
                0x00,
                0x00,
                0x00,
                0x00,  # More data1
                0x00,
                0x00,
                0x00,
                0x00,
                0x0F,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,  # data2
            ]
        )

        coordinator.controller._parse_notification(data)

        # Callback should be called
        assert callback.call_count >= 1

    async def test_parse_invalid_message(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
    ):
        """Test parsing invalid message is ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        coordinator.controller._notify_callback = callback

        # Too short message
        data = bytes([0xED, 0x00])
        coordinator.controller._parse_notification(data)

        callback.assert_not_called()

    async def test_position_properties(
        self,
        hass: HomeAssistant,
        mock_ergomotion_config_entry,
        mock_coordinator_connected,
    ):
        """Test position property access."""
        coordinator = AdjustableBedCoordinator(hass, mock_ergomotion_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Initially None
        assert controller.head_position is None
        assert controller.foot_position is None
        assert controller.head_moving is False
        assert controller.foot_moving is False
        assert controller.head_massage_level == 0
        assert controller.foot_massage_level == 0
        assert controller.led_on is False
