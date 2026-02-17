"""Tests for Vibradorm bed controller (VMAT single-byte protocol)."""

from __future__ import annotations

import pytest
from bleak.exc import BleakCharacteristicNotFoundError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.vibradorm import (
    VibradormCommands,
    VibradormController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_VIBRADORM,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    VIBRADORM_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_SERVICE_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_vibradorm_config_entry_data() -> dict:
    """Return mock config entry data for Vibradorm bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Vibradorm Test Bed",
        CONF_BED_TYPE: BED_TYPE_VIBRADORM,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_vibradorm_config_entry(
    hass: HomeAssistant, mock_vibradorm_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Vibradorm bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vibradorm Test Bed",
        data=mock_vibradorm_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="vibradorm_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class _MockCharacteristic:
    """Simple mock BLE characteristic."""

    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid = uuid
        self.properties = properties


class _MockService:
    """Simple mock BLE service with UUID and characteristics."""

    def __init__(self, uuid: str, characteristics: list[_MockCharacteristic]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics

    def get_characteristic(self, uuid: str) -> _MockCharacteristic | None:
        """Return characteristic by UUID."""
        for char in self.characteristics:
            if str(char.uuid).lower() == uuid.lower():
                return char
        return None


class _MockServices:
    """Simple mock BLE service collection."""

    def __init__(self, services: list[_MockService]) -> None:
        self._services = services

    def __iter__(self):
        return iter(self._services)

    def __len__(self) -> int:
        return len(self._services)

    def get_service(self, uuid: str) -> _MockService | None:
        for service in self._services:
            if str(service.uuid).lower() == uuid.lower():
                return service
        return None


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestVibradormCommands:
    """Test Vibradorm command constants."""

    def test_stop_command(self):
        """STOP should be 0xFF."""
        assert VibradormCommands.STOP == 0xFF

    def test_head_commands(self):
        """Head commands should be correct values."""
        assert VibradormCommands.HEAD_UP == 0x0B  # 11 = KH (Kopf Hoch)
        assert VibradormCommands.HEAD_DOWN == 0x0A  # 10 = KR (Kopf Runter)

    def test_legs_commands(self):
        """Legs/thigh commands should be correct values."""
        assert VibradormCommands.LEGS_UP == 0x09  # 9 = OSH (Oberschenkel Hoch)
        assert VibradormCommands.LEGS_DOWN == 0x08  # 8 = OSR (Oberschenkel Runter)

    def test_foot_commands_for_4_motor(self):
        """Foot commands (4-motor beds) should be correct values."""
        assert VibradormCommands.FOOT_UP == 0x05  # 5 = FH (Fuß Hoch)
        assert VibradormCommands.FOOT_DOWN == 0x04  # 4 = FR (Fuß Runter)

    def test_neck_commands_for_4_motor(self):
        """Neck commands (4-motor beds) should be correct values."""
        assert VibradormCommands.NECK_UP == 0x03  # 3 = NH (Nacken Hoch)
        assert VibradormCommands.NECK_DOWN == 0x02  # 2 = NR (Nacken Runter)

    def test_all_motors_commands(self):
        """All motors commands should be correct values."""
        assert VibradormCommands.ALL_UP == 0x10  # 16 = AH
        assert VibradormCommands.ALL_DOWN == 0x00  # 0 = AR (also flat preset)

    def test_memory_preset_commands(self):
        """Memory preset commands should be correct values."""
        assert VibradormCommands.MEMORY_1 == 0x0E  # 14
        assert VibradormCommands.MEMORY_2 == 0x0F  # 15
        assert VibradormCommands.MEMORY_3 == 0x0C  # 12
        assert VibradormCommands.MEMORY_4 == 0x1A  # 26

    def test_store_command(self):
        """STORE command should be 0x0D."""
        assert VibradormCommands.STORE == 0x0D  # 13


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestVibradormController:
    """Test VibradormController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Vibradorm command UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == VIBRADORM_COMMAND_CHAR_UUID

    async def test_supports_preset_flat(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should support flat preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_flat is True

    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should have 4 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 4

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should support memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is True

    async def test_supports_light_cycle(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should support light cycle."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_light_cycle is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_resolves_secondary_service_command_characteristic(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Controller should use secondary VMAT command UUID when primary is unavailable."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        secondary_service = _MockService(
            VIBRADORM_SECONDARY_SERVICE_UUID,
            [
                _MockCharacteristic(VIBRADORM_SECONDARY_COMMAND_CHAR_UUID, ["read", "write"]),
            ],
        )
        mock_client.services = _MockServices([secondary_service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        first_call_char_uuid = str(mock_client.write_gatt_char.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == VIBRADORM_SECONDARY_COMMAND_CHAR_UUID

    async def test_resolves_secondary_alt_command_characteristic(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Controller should fall back to UUID 1534 when 1528 is missing."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        secondary_service = _MockService(
            VIBRADORM_SECONDARY_SERVICE_UUID,
            [
                _MockCharacteristic(
                    VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID,
                    ["read", "write", "write-without-response"],
                ),
            ],
        )
        mock_client.services = _MockServices([secondary_service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        first_call_char_uuid = str(mock_client.write_gatt_char.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID

    async def test_retries_with_secondary_characteristic_when_primary_missing(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Retry with secondary command characteristic after primary UUID lookup failure."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        secondary_service = _MockService(
            VIBRADORM_SECONDARY_SERVICE_UUID,
            [
                _MockCharacteristic(VIBRADORM_SECONDARY_COMMAND_CHAR_UUID, ["read", "write"]),
            ],
        )
        mock_client.services = _MockServices([secondary_service])
        mock_client.write_gatt_char.reset_mock()

        # Simulate cached primary UUID that no longer exists on this proxy path.
        controller._characteristics_initialized = True
        controller._command_char_uuid = VIBRADORM_COMMAND_CHAR_UUID

        async def _write_side_effect(char_uuid: str, *_args, **_kwargs):
            if str(char_uuid).lower() == VIBRADORM_COMMAND_CHAR_UUID:
                raise BleakCharacteristicNotFoundError(char_uuid)
            return None

        mock_client.write_gatt_char.side_effect = _write_side_effect

        await controller.write_command(
            bytes([VibradormCommands.HEAD_UP]),
            repeat_count=1,
        )

        called_uuids = [str(call.args[0]).lower() for call in mock_client.write_gatt_char.call_args_list]
        assert VIBRADORM_COMMAND_CHAR_UUID in called_uuids
        assert VIBRADORM_SECONDARY_COMMAND_CHAR_UUID in called_uuids


class TestVibradormMovement:
    """Test Vibradorm movement commands."""

    async def test_move_head_up_sends_single_byte(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should send single-byte HEAD_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        calls = mock_client.write_gatt_char.call_args_list
        # Commands are single bytes
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 1
        assert first_call_data[0] == VibradormCommands.HEAD_UP

    async def test_move_legs_up_sends_single_byte(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """move_legs_up should send single-byte LEGS_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_legs_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[0] == VibradormCommands.LEGS_UP

    async def test_stop_all_sends_stop_command(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should send STOP command (0xFF)."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[0] == VibradormCommands.STOP

    async def test_movement_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP
        last_call_data = calls[-1][0][1]
        assert last_call_data[0] == VibradormCommands.STOP


class TestVibradormPresets:
    """Test Vibradorm preset commands."""

    async def test_preset_flat_sends_all_down(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send ALL_DOWN command."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[0] == VibradormCommands.ALL_DOWN

    async def test_preset_memory_1_sends_cbi_command(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should send 2-byte CBI command with MEMORY_1."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        # First call: CBI command [0x00, MEMORY_1] (toggle=False -> 0x0000)
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 2
        assert first_call_data[1] == VibradormCommands.MEMORY_1

    async def test_preset_memory_4_sends_cbi_command(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(4) should send 2-byte CBI command with MEMORY_4."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 2
        assert first_call_data[1] == VibradormCommands.MEMORY_4

    async def test_program_memory_sends_store_sequence(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory should send STORE×4 + slot + STOP×4 via CBI."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        sent = [call.args[1] for call in calls]

        # First 4 calls: STORE to CBI with alternating toggle
        assert sent[0] == bytes([0x00, VibradormCommands.STORE])  # toggle=0
        assert sent[1] == bytes([0x80, VibradormCommands.STORE])  # toggle=1
        assert sent[2] == bytes([0x00, VibradormCommands.STORE])  # toggle=0
        assert sent[3] == bytes([0x80, VibradormCommands.STORE])  # toggle=1

        # 5th call: memory slot to CBI
        assert sent[4] == bytes([0x00, VibradormCommands.MEMORY_1])  # toggle=0

        # Last 4 calls: STOP (1-byte motor commands)
        for i in range(5, 9):
            assert sent[i] == bytes([VibradormCommands.STOP])


class TestVibradormCommandFormat:
    """Test Vibradorm single-byte command format."""

    def test_all_commands_are_single_bytes(self):
        """All commands should fit in a single byte (0-255)."""
        commands = [
            VibradormCommands.STOP,
            VibradormCommands.HEAD_UP,
            VibradormCommands.HEAD_DOWN,
            VibradormCommands.LEGS_UP,
            VibradormCommands.LEGS_DOWN,
            VibradormCommands.FOOT_UP,
            VibradormCommands.FOOT_DOWN,
            VibradormCommands.NECK_UP,
            VibradormCommands.NECK_DOWN,
            VibradormCommands.ALL_UP,
            VibradormCommands.ALL_DOWN,
            VibradormCommands.MEMORY_1,
            VibradormCommands.MEMORY_2,
            VibradormCommands.MEMORY_3,
            VibradormCommands.MEMORY_4,
            VibradormCommands.STORE,
        ]
        for cmd in commands:
            assert 0 <= cmd <= 255

    def test_no_duplicate_commands(self):
        """All motor commands should be unique."""
        motor_commands = [
            VibradormCommands.HEAD_UP,
            VibradormCommands.HEAD_DOWN,
            VibradormCommands.LEGS_UP,
            VibradormCommands.LEGS_DOWN,
            VibradormCommands.FOOT_UP,
            VibradormCommands.FOOT_DOWN,
            VibradormCommands.NECK_UP,
            VibradormCommands.NECK_DOWN,
            VibradormCommands.ALL_UP,
        ]
        assert len(motor_commands) == len(set(motor_commands))
