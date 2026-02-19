"""Tests for Svane bed controller (LinonPI multi-service protocol)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import (
    SvaneCommands,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SVANE_CHAR_DOWN_UUID,
    SVANE_CHAR_MEMORY_UUID,
    SVANE_CHAR_POSITION_UUID,
    SVANE_CHAR_UP_UUID,
    SVANE_FEET_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_LIGHT_ON_OFF_UUID,
    SVANE_LIGHT_SERVICE_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_svane_config_entry_data() -> dict:
    """Return mock config entry data for Svane bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Svane Test Bed",
        CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_svane_config_entry(
    hass: HomeAssistant, mock_svane_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Svane bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Svane Test Bed",
        data=mock_svane_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="svane_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestSvaneCommands:
    """Test Svane command constants."""

    def test_motor_commands_are_2_bytes(self):
        """Motor commands should be 2 bytes."""
        assert len(SvaneCommands.MOTOR_MOVE) == 2
        assert len(SvaneCommands.MOTOR_STOP) == 2

    def test_motor_move_command(self):
        """MOTOR_MOVE should be [0x01, 0x00]."""
        assert bytes([0x01, 0x00]) == SvaneCommands.MOTOR_MOVE

    def test_motor_stop_command(self):
        """MOTOR_STOP should be [0x00, 0x00]."""
        assert bytes([0x00, 0x00]) == SvaneCommands.MOTOR_STOP

    def test_svane_position_command(self):
        """SVANE_POSITION should be [0x03, 0x00]."""
        assert bytes([0x03, 0x00]) == SvaneCommands.SVANE_POSITION
        assert len(SvaneCommands.SVANE_POSITION) == 2

    def test_memory_commands_are_6_bytes(self):
        """Memory commands should be 6 bytes."""
        assert len(SvaneCommands.FLATTEN) == 6
        assert len(SvaneCommands.SAVE_POSITION) == 6
        assert len(SvaneCommands.RECALL_POSITION) == 6
        assert len(SvaneCommands.READ_POSITION) == 6

    def test_flatten_command(self):
        """FLATTEN command should have correct bytes."""
        assert bytes([0x3F, 0x81, 0x00, 0x00, 0x00, 0x00]) == SvaneCommands.FLATTEN

    def test_save_position_command(self):
        """SAVE_POSITION command should have correct bytes."""
        assert bytes([0x3F, 0x40, 0x00, 0x00, 0x00, 0x00]) == SvaneCommands.SAVE_POSITION

    def test_recall_position_command(self):
        """RECALL_POSITION command should have correct bytes."""
        assert bytes([0x3F, 0x80, 0x00, 0x00, 0x00, 0x00]) == SvaneCommands.RECALL_POSITION

    def test_light_commands_are_6_bytes(self):
        """Light commands should be 6 bytes."""
        assert len(SvaneCommands.LIGHT_ON) == 6
        assert len(SvaneCommands.LIGHT_OFF) == 6

    def test_light_on_command(self):
        """LIGHT_ON command should have brightness=80."""
        assert bytes([0x13, 0x02, 0x50, 0x01, 0x00, 0x50]) == SvaneCommands.LIGHT_ON

    def test_light_off_command(self):
        """LIGHT_OFF command should be all zeros except header."""
        assert bytes([0x13, 0x02, 0x00, 0x00, 0x00, 0x00]) == SvaneCommands.LIGHT_OFF


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestSvaneController:
    """Test SvaneController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Svane UP characteristic."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == SVANE_CHAR_UP_UUID

    async def test_supports_preset_flat(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should support flat preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_flat is True

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should support zero-g preset (Svane Position)."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count_is_two(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should have 2 software memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should support memory programming."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True


# -----------------------------------------------------------------------------
# Multi-Service Protocol Tests
# -----------------------------------------------------------------------------


class TestSvaneMultiServiceProtocol:
    """Test Svane multi-service protocol (characteristic in service lookup)."""

    def test_head_service_uuid_defined(self):
        """Head service UUID should be defined."""
        assert SVANE_HEAD_SERVICE_UUID is not None
        assert len(SVANE_HEAD_SERVICE_UUID) > 0

    def test_feet_service_uuid_defined(self):
        """Feet service UUID should be defined."""
        assert SVANE_FEET_SERVICE_UUID is not None
        assert len(SVANE_FEET_SERVICE_UUID) > 0

    def test_light_service_uuid_defined(self):
        """Light service UUID should be defined."""
        assert SVANE_LIGHT_SERVICE_UUID is not None
        assert len(SVANE_LIGHT_SERVICE_UUID) > 0

    def test_different_services_for_motors(self):
        """Head and feet services should be different."""
        assert SVANE_HEAD_SERVICE_UUID != SVANE_FEET_SERVICE_UUID

    def test_direction_characteristic_uuids_defined(self):
        """UP and DOWN characteristic UUIDs should be defined."""
        assert SVANE_CHAR_UP_UUID is not None
        assert SVANE_CHAR_DOWN_UUID is not None
        assert SVANE_CHAR_UP_UUID != SVANE_CHAR_DOWN_UUID

    def test_memory_characteristic_uuid_defined(self):
        """Memory characteristic UUID should be defined."""
        assert SVANE_CHAR_MEMORY_UUID is not None

    def test_light_on_off_characteristic_uuid_defined(self):
        """Light on/off characteristic UUID should be defined."""
        assert SVANE_LIGHT_ON_OFF_UUID is not None


# -----------------------------------------------------------------------------
# Memory/Preset Command Tests
# -----------------------------------------------------------------------------


class _MockCharacteristic:
    """Simple mock BLE characteristic with UUID."""

    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class _MockService:
    """Simple mock BLE service with UUID + characteristics."""

    def __init__(self, uuid: str, characteristics: list[_MockCharacteristic]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics


class TestSvanePresetCommands:
    """Test Svane preset command routing to POSITION characteristic."""

    async def test_preset_flat_writes_to_head_and_feet_position_chars(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Flat preset should write to POSITION characteristic in both motor services.

        When MEMORY is not available, the primary MEMORY write fails gracefully
        and the command falls through to POSITION writes only.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        head_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        feet_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        mock_client.services = [
            _MockService(SVANE_HEAD_SERVICE_UUID, [head_position]),
            _MockService(SVANE_FEET_SERVICE_UUID, [feet_position]),
        ]
        mock_client.write_gatt_char.reset_mock()

        sleep_mock = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio.sleep", sleep_mock)

        await coordinator.controller.preset_flat()

        # 3 repeats * 2 POSITION chars = 6 writes (MEMORY path fails gracefully)
        assert mock_client.write_gatt_char.call_count == 3 * 2

        written_chars = {call.args[0] for call in mock_client.write_gatt_char.call_args_list}
        assert head_position in written_chars
        assert feet_position in written_chars
        assert all(
            call.args[1] == SvaneCommands.FLATTEN
            for call in mock_client.write_gatt_char.call_args_list
        )

    async def test_preset_flat_writes_memory_first_then_position(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Flat preset writes to MEMORY first (primary), then POSITION (secondary).

        The MEMORY path is tried first since it works on more firmware revisions
        (same approach as preset_zero_g). POSITION writes follow for compatibility
        with firmware that uses the POSITION characteristic for presets.
        See: https://github.com/kristofferR/ha-adjustable-bed/issues/152
        """
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        head_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        feet_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        head_memory = _MockCharacteristic(SVANE_CHAR_MEMORY_UUID)
        feet_memory = _MockCharacteristic(SVANE_CHAR_MEMORY_UUID)
        mock_client.services = [
            _MockService(SVANE_HEAD_SERVICE_UUID, [head_position, head_memory]),
            _MockService(SVANE_FEET_SERVICE_UUID, [feet_position, feet_memory]),
        ]
        mock_client.write_gatt_char.reset_mock()

        sleep_mock = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio.sleep", sleep_mock)

        await coordinator.controller.preset_flat()

        # 3 MEMORY writes (primary) + 3 repeats * 2 POSITION chars (secondary) = 9
        assert mock_client.write_gatt_char.call_count == 3 + (3 * 2)

        # First 3 writes should be to MEMORY in HEAD service
        memory_writes = mock_client.write_gatt_char.call_args_list[:3]
        assert all(call.args[0] == head_memory for call in memory_writes)
        assert all(call.args[1] == SvaneCommands.FLATTEN for call in memory_writes)

        # Remaining 6 writes should be to POSITION chars in both services
        position_writes = mock_client.write_gatt_char.call_args_list[3:]
        position_chars = {call.args[0] for call in position_writes}
        assert head_position in position_chars
        assert feet_position in position_chars

    async def test_program_memory_writes_to_position_chars(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Program memory should write to POSITION characteristic with repeated writes."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        head_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        feet_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        mock_client.services = [
            _MockService(SVANE_HEAD_SERVICE_UUID, [head_position]),
            _MockService(SVANE_FEET_SERVICE_UUID, [feet_position]),
        ]
        mock_client.write_gatt_char.reset_mock()

        sleep_mock = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio.sleep", sleep_mock)

        await coordinator.controller.program_memory(1)

        written_chars = {call.args[0] for call in mock_client.write_gatt_char.call_args_list}
        assert head_position in written_chars
        assert feet_position in written_chars

        expected_repeats = max(3, coordinator.motor_pulse_count)
        assert mock_client.write_gatt_char.call_count == expected_repeats * 2
        assert all(
            call.args[1] == SvaneCommands.SAVE_POSITION
            for call in mock_client.write_gatt_char.call_args_list
        )

    async def test_program_memory_stores_software_slot_and_recall_replays_raw_bytes(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Software memory should store raw bytes and replay them on recall."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        head_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        feet_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        mock_client.services = [
            _MockService(SVANE_HEAD_SERVICE_UUID, [head_position]),
            _MockService(SVANE_FEET_SERVICE_UUID, [feet_position]),
        ]
        mock_client.read_gatt_char = AsyncMock(side_effect=[b"\x11\x22", b"\x33\x44"])
        mock_client.write_gatt_char.reset_mock()

        sleep_mock = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio.sleep", sleep_mock)

        await coordinator.controller.program_memory(2)
        assert mock_client.write_gatt_char.call_count == 0

        await coordinator.controller.preset_memory(2)

        assert mock_client.write_gatt_char.call_count == 2
        assert mock_client.write_gatt_char.call_args_list[0].args[0] is head_position
        assert mock_client.write_gatt_char.call_args_list[0].args[1] == b"\x11\x22"
        assert mock_client.write_gatt_char.call_args_list[1].args[0] is feet_position
        assert mock_client.write_gatt_char.call_args_list[1].args[1] == b"\x33\x44"

    async def test_software_memory_recall_honors_cancel_before_feet_write(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Software recall should stop before the feet write when command is cancelled."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        head_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        feet_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        mock_client.services = [
            _MockService(SVANE_HEAD_SERVICE_UUID, [head_position]),
            _MockService(SVANE_FEET_SERVICE_UUID, [feet_position]),
        ]
        mock_client.read_gatt_char = AsyncMock(side_effect=[b"\x55\x66", b"\x77\x88"])

        await coordinator.controller.program_memory(1)
        mock_client.write_gatt_char.reset_mock()

        async def _cancel_during_delay(wait_coro, timeout):
            del timeout
            coordinator.cancel_command.set()
            await wait_coro
            return True

        wait_for_mock = AsyncMock(side_effect=_cancel_during_delay)
        monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio.wait_for", wait_for_mock)

        await coordinator.controller.preset_memory(1)

        assert wait_for_mock.await_count == 1
        assert mock_client.write_gatt_char.call_count == 1
        assert mock_client.write_gatt_char.call_args_list[0].args[0] is head_position
        assert mock_client.write_gatt_char.call_args_list[0].args[1] == b"\x55\x66"

    async def test_preset_memory_writes_to_position_chars(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Preset memory should write to POSITION characteristic with repeated writes."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        assert mock_client is not None

        head_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        feet_position = _MockCharacteristic(SVANE_CHAR_POSITION_UUID)
        mock_client.services = [
            _MockService(SVANE_HEAD_SERVICE_UUID, [head_position]),
            _MockService(SVANE_FEET_SERVICE_UUID, [feet_position]),
        ]
        mock_client.write_gatt_char.reset_mock()

        sleep_mock = AsyncMock()
        monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio.sleep", sleep_mock)

        await coordinator.controller.preset_memory(1)

        written_chars = {call.args[0] for call in mock_client.write_gatt_char.call_args_list}
        assert head_position in written_chars
        assert feet_position in written_chars

        expected_repeats = max(3, coordinator.motor_pulse_count)
        assert mock_client.write_gatt_char.call_count == expected_repeats * 2
        assert all(
            call.args[1] == SvaneCommands.RECALL_POSITION
            for call in mock_client.write_gatt_char.call_args_list
        )
