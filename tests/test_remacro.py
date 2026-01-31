"""Tests for Remacro bed controller (SynData protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.remacro import (
    RemacroCommands,
    RemacroController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REMACRO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    REMACRO_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_remacro_config_entry_data() -> dict:
    """Return mock config entry data for Remacro bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Remacro Test Bed",
        CONF_BED_TYPE: BED_TYPE_REMACRO,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_remacro_config_entry(
    hass: HomeAssistant, mock_remacro_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Remacro bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Remacro Test Bed",
        data=mock_remacro_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="remacro_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestRemacroCommands:
    """Test Remacro command constants."""

    def test_control_pid_constants(self):
        """Control PID constants should be correct."""
        assert RemacroCommands.CPID_CTRL == 0x01
        assert RemacroCommands.CPID_GET_STATE == 0x02
        assert RemacroCommands.CPID_SET_PARA == 0x03

    def test_stop_commands(self):
        """Stop commands should be correct values."""
        assert RemacroCommands.STOP == 0x0000
        assert RemacroCommands.STOP_MOTOR == 0x0001
        assert RemacroCommands.STOP_MASSAGE == 0x0002
        assert RemacroCommands.CTRL_HOLD == 0x0003

    def test_motor_1_commands(self):
        """Motor 1 (head) commands should be correct."""
        assert RemacroCommands.M1_STOP == 256  # 0x0100
        assert RemacroCommands.M1_UP == 257  # 0x0101
        assert RemacroCommands.M1_DOWN == 258  # 0x0102
        assert RemacroCommands.M1_RUN == 259  # 0x0103

    def test_motor_2_commands(self):
        """Motor 2 (foot) commands should be correct."""
        assert RemacroCommands.M2_STOP == 260  # 0x0104
        assert RemacroCommands.M2_UP == 261  # 0x0105
        assert RemacroCommands.M2_DOWN == 262  # 0x0106
        assert RemacroCommands.M2_RUN == 263  # 0x0107

    def test_motor_3_commands(self):
        """Motor 3 (lumbar) commands should be correct."""
        assert RemacroCommands.M3_STOP == 264  # 0x0108
        assert RemacroCommands.M3_UP == 265  # 0x0109
        assert RemacroCommands.M3_DOWN == 266  # 0x010A
        assert RemacroCommands.M3_RUN == 267  # 0x010B

    def test_motor_4_commands(self):
        """Motor 4 (tilt/neck) commands should be correct."""
        assert RemacroCommands.M4_STOP == 268  # 0x010C
        assert RemacroCommands.M4_UP == 269  # 0x010D
        assert RemacroCommands.M4_DOWN == 270  # 0x010E
        assert RemacroCommands.M4_RUN == 271  # 0x010F

    def test_all_motors_commands(self):
        """All motors commands should be correct."""
        assert RemacroCommands.M_UP == 272  # 0x0110
        assert RemacroCommands.M_DOWN == 273  # 0x0111

    def test_motor_combination_commands(self):
        """Motor combination commands should be correct."""
        assert RemacroCommands.M12_UP == 274
        assert RemacroCommands.M12_DOWN == 275
        assert RemacroCommands.M13_UP == 276
        assert RemacroCommands.M13_DOWN == 277
        assert RemacroCommands.M23_UP == 278
        assert RemacroCommands.M23_DOWN == 279

    def test_massage_zone_commands(self):
        """Massage zone commands should be correct."""
        assert RemacroCommands.MM12_RUN == 288  # 0x0120
        assert RemacroCommands.MM1_RUN == 289  # 0x0121
        assert RemacroCommands.MM2_RUN == 290  # 0x0122
        assert RemacroCommands.MM1_STOP == 291  # 0x0123
        assert RemacroCommands.MM2_STOP == 292  # 0x0124

    def test_massage_mode_commands(self):
        """Massage mode commands should be correct."""
        assert RemacroCommands.MMODE_STOP == 512  # 0x0200
        assert RemacroCommands.MMODE1_RUN == 513  # 0x0201
        assert RemacroCommands.MMODE2_RUN == 514  # 0x0202
        assert RemacroCommands.MMODE3_RUN == 515  # 0x0203
        assert RemacroCommands.MMODE4_RUN == 516  # 0x0204
        assert RemacroCommands.MMODE5_RUN == 517  # 0x0205

    def test_memory_recall_commands(self):
        """Memory recall commands should be correct."""
        assert RemacroCommands.MOV_ML1 == 785  # 0x0311
        assert RemacroCommands.MOV_ML2 == 787  # 0x0313
        assert RemacroCommands.MOV_ML3 == 789  # 0x0315
        assert RemacroCommands.MOV_ML4 == 791  # 0x0317

    def test_memory_save_commands(self):
        """Memory save commands should be correct."""
        assert RemacroCommands.SET_ML1 == 784  # 0x0310
        assert RemacroCommands.SET_ML2 == 786  # 0x0312
        assert RemacroCommands.SET_ML3 == 788  # 0x0314
        assert RemacroCommands.SET_ML4 == 790  # 0x0316

    def test_default_preset_commands(self):
        """Default preset commands should be correct."""
        assert RemacroCommands.DEF_ML1 == 769  # 0x0301 - Flat
        assert RemacroCommands.DEF_ML2 == 770  # 0x0302 - Zero-G
        assert RemacroCommands.DEF_ML3 == 771  # 0x0303 - TV
        assert RemacroCommands.DEF_ML4 == 772  # 0x0304 - Anti-snore

    def test_led_commands(self):
        """LED commands should be correct."""
        assert RemacroCommands.LED_OFF == 1280  # 0x0500
        assert RemacroCommands.LED_RGBV == 1281  # 0x0501
        assert RemacroCommands.LED_W == 1282  # 0x0502
        assert RemacroCommands.LED_R == 1283  # 0x0503
        assert RemacroCommands.LED_G == 1284  # 0x0504
        assert RemacroCommands.LED_B == 1285  # 0x0505
        assert RemacroCommands.LED_RG == 1286  # 0x0506
        assert RemacroCommands.LED_RB == 1287  # 0x0507
        assert RemacroCommands.LED_GB == 1288  # 0x0508
        assert RemacroCommands.LED_M1 == 1289  # 0x0509
        assert RemacroCommands.LED_M2 == 1290  # 0x050A
        assert RemacroCommands.LED_M3 == 1291  # 0x050B

    def test_heat_commands(self):
        """Heat commands should be correct."""
        assert RemacroCommands.HEAT_OFF == 28672  # 0x7000
        assert RemacroCommands.HEAT_M1 == 28673  # 0x7001
        assert RemacroCommands.HEAT_M2 == 28674  # 0x7002
        assert RemacroCommands.HEAT_M3 == 28675  # 0x7003


# -----------------------------------------------------------------------------
# Packet Building Tests
# -----------------------------------------------------------------------------


class TestRemacroPacketBuilding:
    """Test Remacro packet building."""

    def test_packet_is_8_bytes(self):
        """Packets should be exactly 8 bytes."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())
        packet = controller._build_packet(RemacroCommands.M1_UP)

        assert len(packet) == 8

    def test_packet_starts_with_serial_number(self):
        """Packet should start with serial number."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())

        # First packet should have serial 1
        packet1 = controller._build_packet(RemacroCommands.M1_UP)
        assert packet1[0] == 1

        # Second packet should have serial 2
        packet2 = controller._build_packet(RemacroCommands.M1_UP)
        assert packet2[0] == 2

    def test_serial_wraps_at_255(self):
        """Serial number should wrap from 255 to 1."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())
        controller._serial = 255

        packet1 = controller._build_packet(RemacroCommands.M1_UP)
        assert packet1[0] == 255

        packet2 = controller._build_packet(RemacroCommands.M1_UP)
        assert packet2[0] == 1  # Wraps to 1, not 0

    def test_packet_has_control_pid(self):
        """Packet byte 1 should be CPID_CTRL (0x01)."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())
        packet = controller._build_packet(RemacroCommands.M1_UP)

        assert packet[1] == RemacroCommands.CPID_CTRL

    def test_command_bytes_little_endian(self):
        """Command bytes should be in little-endian order."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())

        # M1_UP = 257 = 0x0101
        packet = controller._build_packet(RemacroCommands.M1_UP)

        # Bytes 2-3 are command in little-endian
        assert packet[2] == 0x01  # LSB
        assert packet[3] == 0x01  # MSB

    def test_parameter_bytes_little_endian(self):
        """Parameter bytes should be in little-endian order."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())

        # Test with parameter = 0x12345678
        packet = controller._build_packet(0x0100, parameter=0x12345678)

        # Bytes 4-7 are parameter in little-endian
        assert packet[4] == 0x78  # LSB
        assert packet[5] == 0x56
        assert packet[6] == 0x34
        assert packet[7] == 0x12  # MSB

    def test_default_parameter_is_zero(self):
        """Default parameter should be all zeros."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())
        packet = controller._build_packet(RemacroCommands.M1_UP)

        assert packet[4] == 0x00
        assert packet[5] == 0x00
        assert packet[6] == 0x00
        assert packet[7] == 0x00


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestRemacroController:
    """Test RemacroController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Remacro write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == REMACRO_WRITE_CHAR_UUID

    async def test_supports_preset_flat(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support flat preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_flat is True

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_massage(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support massage."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_massage is True

    async def test_supports_light(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_light is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_has_tilt_support(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Remacro should support tilt motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_tilt_support is True


class TestRemacroMovement:
    """Test Remacro movement commands."""

    async def test_move_head_up_sends_8_byte_packet(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send 8-byte packet."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 8

    async def test_stop_all_sends_stop_motor_command(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP_MOTOR command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # STOP_MOTOR = 0x0001 in little-endian: [0x01, 0x00]
        assert call_data[2] == 0x01
        assert call_data[3] == 0x00

    async def test_movement_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP_MOTOR
        last_call_data = calls[-1][0][1]
        assert last_call_data[2] == 0x01  # STOP_MOTOR LSB
        assert last_call_data[3] == 0x00  # STOP_MOTOR MSB


class TestRemacroPresets:
    """Test Remacro preset commands."""

    async def test_preset_flat_sends_def_ml1(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send DEF_ML1 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # DEF_ML1 = 769 = 0x0301 in little-endian: [0x01, 0x03]
        assert call_data[2] == 0x01
        assert call_data[3] == 0x03

    async def test_preset_zero_g_sends_def_ml2(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should send DEF_ML2 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # DEF_ML2 = 770 = 0x0302 in little-endian: [0x02, 0x03]
        assert call_data[2] == 0x02
        assert call_data[3] == 0x03

    async def test_preset_memory_1_sends_mov_ml1(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should send MOV_ML1 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MOV_ML1 = 785 = 0x0311 in little-endian: [0x11, 0x03]
        assert call_data[2] == 0x11
        assert call_data[3] == 0x03

    async def test_preset_memory_4_sends_mov_ml4(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(4) should send MOV_ML4 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # MOV_ML4 = 791 = 0x0317 in little-endian: [0x17, 0x03]
        assert call_data[2] == 0x17
        assert call_data[3] == 0x03

    async def test_program_memory_1_sends_set_ml1(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory(1) should send SET_ML1 command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # SET_ML1 = 784 = 0x0310 in little-endian: [0x10, 0x03]
        assert call_data[2] == 0x10
        assert call_data[3] == 0x03


class TestRemacroLights:
    """Test Remacro light commands."""

    async def test_lights_on_sends_led_w(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on should send LED_W command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # LED_W = 1282 = 0x0502 in little-endian: [0x02, 0x05]
        assert call_data[2] == 0x02
        assert call_data[3] == 0x05

    async def test_lights_off_sends_led_off(
        self,
        hass: HomeAssistant,
        mock_remacro_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should send LED_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_remacro_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        # LED_OFF = 1280 = 0x0500 in little-endian: [0x00, 0x05]
        assert call_data[2] == 0x00
        assert call_data[3] == 0x05


class TestRemacroSerialNumber:
    """Test Remacro serial number handling."""

    def test_serial_starts_at_1(self):
        """Serial should start at 1."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())

        assert controller._serial == 1

    def test_next_serial_returns_and_increments(self):
        """_next_serial should return current and increment."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())

        assert controller._next_serial() == 1
        assert controller._next_serial() == 2
        assert controller._next_serial() == 3

    def test_serial_never_zero(self):
        """Serial should never be zero (wraps from 255 to 1)."""
        from unittest.mock import MagicMock
        controller = RemacroController(MagicMock())

        # Generate 256 serial numbers
        serials = [controller._next_serial() for _ in range(256)]

        # Zero should never appear
        assert 0 not in serials

        # Should contain 1-255, then back to 1
        assert serials[:255] == list(range(1, 256))
        assert serials[255] == 1
