"""Tests for Richmat bed controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.richmat import (
    RichmatCommands,
    RichmatController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    RICHMAT_NORDIC_CHAR_UUID,
    RICHMAT_PROTOCOL_PREFIX55,
    RICHMAT_PROTOCOL_PREFIXAA,
    RICHMAT_VARIANT_NORDIC,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_richmat_config_entry_data() -> dict:
    """Return mock config entry data for Richmat bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Richmat Test Bed",
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: RICHMAT_VARIANT_NORDIC,
    }


@pytest.fixture
def mock_richmat_config_entry(
    hass: HomeAssistant, mock_richmat_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Richmat bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Richmat Test Bed",
        data=mock_richmat_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="richmat_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestRichmatController:
    """Test Richmat controller."""

    async def test_control_characteristic_uuid_nordic(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports Nordic characteristic UUID by default."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == RICHMAT_NORDIC_CHAR_UUID

    async def test_build_command_nordic(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Nordic variant builds single-byte commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Nordic variant: single byte
        command = coordinator.controller._build_command(RichmatCommands.PRESET_FLAT)
        assert command == bytes([0x31])

    async def test_build_command_wilinke(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test WiLinke variant builds 5-byte commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Create a WiLinke controller directly
        controller = RichmatController(coordinator, is_wilinke=True)

        # WiLinke: [110, 1, 0, cmd, cmd+111]
        command = controller._build_command(RichmatCommands.PRESET_FLAT)
        assert len(command) == 5
        assert command[0] == 110
        assert command[1] == 1
        assert command[2] == 0
        assert command[3] == RichmatCommands.PRESET_FLAT
        # checksum = (cmd + 111) & 0xFF
        expected_checksum = (RichmatCommands.PRESET_FLAT + 111) & 0xFF
        assert command[4] == expected_checksum

    async def test_build_command_prefix55(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Prefix55 variant builds 5-byte commands with 0x55 prefix."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Create a Prefix55 controller directly
        controller = RichmatController(coordinator, command_protocol=RICHMAT_PROTOCOL_PREFIX55)

        # Prefix55: [0x55, 0x01, 0x00, cmd, (cmd + 0x56) & 0xFF]
        command = controller._build_command(RichmatCommands.PRESET_FLAT)
        assert len(command) == 5
        assert command[0] == 0x55
        assert command[1] == 0x01
        assert command[2] == 0x00
        assert command[3] == RichmatCommands.PRESET_FLAT
        # checksum = (cmd + 0x56) & 0xFF
        expected_checksum = (RichmatCommands.PRESET_FLAT + 0x56) & 0xFF
        assert command[4] == expected_checksum

    async def test_build_command_prefixaa(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test PrefixAA variant builds 5-byte commands with 0xAA prefix."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Create a PrefixAA controller directly
        controller = RichmatController(coordinator, command_protocol=RICHMAT_PROTOCOL_PREFIXAA)

        # PrefixAA: [0xAA, 0x01, 0x00, cmd, (cmd + 0xAB) & 0xFF]
        command = controller._build_command(RichmatCommands.PRESET_FLAT)
        assert len(command) == 5
        assert command[0] == 0xAA
        assert command[1] == 0x01
        assert command[2] == 0x00
        assert command[3] == RichmatCommands.PRESET_FLAT
        # checksum = (cmd + 0xAB) & 0xFF
        expected_checksum = (RichmatCommands.PRESET_FLAT + 0xAB) & 0xFF
        assert command[4] == expected_checksum

    async def test_wilinke_qrrm_uses_compat_stop_byte(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """WiLinke QRRM remotes should use compatibility stop byte 0x5E."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")
        stop_command = controller._build_stop_command()

        assert len(stop_command) == 5
        assert stop_command[3] == RichmatCommands.END_COMPAT

    async def test_wilinke_non_compat_remote_uses_standard_stop_byte(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """WiLinke non-compat remotes should keep standard stop byte 0x6E."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        controller = RichmatController(coordinator, is_wilinke=True, remote_code="v1rm")
        stop_command = controller._build_stop_command()

        assert len(stop_command) == 5
        assert stop_command[3] == RichmatCommands.END

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(RichmatCommands.END)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(
                coordinator.controller._build_command(RichmatCommands.END)
            )


class TestRichmatMovement:
    """Test Richmat movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be END command
        last_command = calls[-1][0][1]
        expected_end = coordinator.controller._build_command(RichmatCommands.END)
        assert last_command == expected_end

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_legs_up(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs up sends FEET_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be FEET_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(RichmatCommands.MOTOR_FEET_UP)
        assert first_command == expected

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends END command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_end = coordinator.controller._build_command(RichmatCommands.END)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_end, response=True
        )

    async def test_wilinke_qrrm_move_stop_uses_compat_byte(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """move_head_stop should use 0x5E for WiLinke QRRM compatibility."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        controller = RichmatController(coordinator, is_wilinke=True, remote_code="qrrm")
        mock_bleak_client.write_gatt_char.reset_mock()

        await controller.move_head_stop()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        sent_command = calls[0][0][1]
        assert sent_command[3] == RichmatCommands.END_COMPAT

    async def test_move_lumbar_up(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move lumbar up sends LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_lumbar_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be LUMBAR_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(RichmatCommands.MOTOR_LUMBAR_UP)
        assert first_command == expected

    async def test_move_lumbar_down(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move lumbar down sends LUMBAR_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_lumbar_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be LUMBAR_DOWN
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(RichmatCommands.MOTOR_LUMBAR_DOWN)
        assert first_command == expected

    async def test_move_pillow_up(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move pillow up sends PILLOW_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_pillow_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be PILLOW_UP
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(RichmatCommands.MOTOR_PILLOW_UP)
        assert first_command == expected

    async def test_move_pillow_down(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move pillow down sends PILLOW_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_pillow_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        # First call should be PILLOW_DOWN
        first_command = calls[0][0][1]
        expected = coordinator.controller._build_command(RichmatCommands.MOTOR_PILLOW_DOWN)
        assert first_command == expected

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Richmat controller reports lumbar support with default 'auto' remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_has_pillow_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test Richmat controller reports pillow support with default 'auto' remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_pillow_support is True


class TestRichmatFeatureDetection:
    """Test Richmat remote-based feature detection."""

    def test_v1rm_no_pillow_no_lumbar(self):
        """Test V1RM remote has no pillow or lumbar support."""
        from custom_components.adjustable_bed.beds.richmat import RichmatController

        # Create controller with V1RM remote code
        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="V1RM")

        assert controller.has_pillow_support is False
        assert controller.has_lumbar_support is False
        assert controller.supports_preset_zero_g is True
        assert controller.supports_preset_tv is False

    def test_190_0055_pillow_no_lumbar(self):
        """Test 190-0055 remote has pillow but no lumbar support."""
        from custom_components.adjustable_bed.beds.richmat import RichmatController

        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="190-0055")

        assert controller.has_pillow_support is True
        assert controller.has_lumbar_support is False

    def test_virm_full_features(self):
        """Test VIRM remote has full feature support."""
        from custom_components.adjustable_bed.beds.richmat import RichmatController

        coordinator = MagicMock()
        controller = RichmatController(coordinator, is_wilinke=False, remote_code="VIRM")

        assert controller.has_pillow_support is True
        assert controller.has_lumbar_support is True
        assert controller.supports_preset_zero_g is True
        assert controller.supports_preset_anti_snore is True


class TestRichmatPresets:
    """Test Richmat preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_FLAT)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_ZERO_G)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_TV)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.PRESET_ANTI_SNORE)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, RichmatCommands.PRESET_MEMORY_1),
            (2, RichmatCommands.PRESET_MEMORY_2),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    @pytest.mark.parametrize(
        "memory_num,expected_value",
        [
            (1, RichmatCommands.PROGRAM_MEMORY_1),
            (2, RichmatCommands.PROGRAM_MEMORY_2),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_value: int,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        expected_cmd = coordinator.controller._build_command(expected_value)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )


class TestRichmatLights:
    """Test Richmat light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.LIGHTS_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )


class TestRichmatMassage:
    """Test Richmat massage commands."""

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_TOGGLE)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_HEAD_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_toggle(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_toggle()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_FOOT_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage mode step command."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        expected_cmd = coordinator.controller._build_command(RichmatCommands.MASSAGE_PATTERN_STEP)
        mock_bleak_client.write_gatt_char.assert_called_with(
            RICHMAT_NORDIC_CHAR_UUID, expected_cmd, response=True
        )


class TestRichmatPositionNotifications:
    """Test Richmat position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_richmat_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_richmat_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()
