"""Tests for Vibradorm bed controller (VMAT single-byte protocol)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import MagicMock

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
    VIBRADORM_CBI_CHAR_UUID,
    VIBRADORM_COMMAND_CHAR_UUID,
    VIBRADORM_NOTIFY_CHAR_UUID,
    VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
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
        assert VibradormCommands.MEMORY_5 == 0x1B  # 27
        assert VibradormCommands.MEMORY_6 == 0x1C  # 28

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
        """Vibradorm should have 6 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 6

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

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should support memory preset recall entities."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_supports_position_feedback(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should report position feedback via notifications."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_position_feedback is True

    async def test_disables_polling_during_commands(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should disable movement-time polling to avoid command interruption."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.allow_position_polling_during_commands is False

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

        async def _write_side_effect(char_uuid: str, *_args: Any, **_kwargs: Any) -> None:
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

    async def test_retries_after_refresh_when_command_uuid_is_unchanged(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Retry write once after forced refresh even if command UUID remains unchanged."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        primary_service = _MockService(
            VIBRADORM_SERVICE_UUID,
            [
                _MockCharacteristic(
                    VIBRADORM_COMMAND_CHAR_UUID,
                    ["read", "write", "write-without-response"],
                ),
            ],
        )
        mock_client.services = _MockServices([primary_service])
        mock_client.write_gatt_char.reset_mock()

        controller._characteristics_initialized = True
        controller._command_char_uuid = VIBRADORM_COMMAND_CHAR_UUID

        call_count: int = 0

        async def _write_side_effect(char_uuid: str, *_args: Any, **_kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1 and str(char_uuid).lower() == VIBRADORM_COMMAND_CHAR_UUID:
                raise BleakCharacteristicNotFoundError(char_uuid)
            return None

        mock_client.write_gatt_char.side_effect = _write_side_effect

        await controller.write_command(
            bytes([VibradormCommands.HEAD_UP]),
            repeat_count=1,
        )

        called_uuids = [str(call.args[0]).lower() for call in mock_client.write_gatt_char.call_args_list]
        assert called_uuids == [VIBRADORM_COMMAND_CHAR_UUID, VIBRADORM_COMMAND_CHAR_UUID]

    async def test_start_notify_retries_after_refresh_when_notify_uuid_is_unchanged(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Retry notifications once after refresh even if notify UUID stays the same."""
        del mock_coordinator_connected  # Fixture used for side-effect setup

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        primary_service = _MockService(
            VIBRADORM_SERVICE_UUID,
            [
                _MockCharacteristic(VIBRADORM_NOTIFY_CHAR_UUID, ["notify"]),
            ],
        )
        mock_client.services = _MockServices([primary_service])
        mock_client.start_notify.reset_mock()

        controller._characteristics_initialized = True
        controller._notify_char_uuid = VIBRADORM_NOTIFY_CHAR_UUID

        call_count: int = 0

        async def _start_notify_side_effect(
            char_uuid: str, *_args: object, **_kwargs: object
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1 and str(char_uuid).lower() == VIBRADORM_NOTIFY_CHAR_UUID:
                raise BleakCharacteristicNotFoundError(char_uuid)
            return None

        mock_client.start_notify.side_effect = _start_notify_side_effect

        await controller.start_notify(lambda *_: None)

        called_uuids = [str(call.args[0]).lower() for call in mock_client.start_notify.call_args_list]
        assert called_uuids == [VIBRADORM_NOTIFY_CHAR_UUID, VIBRADORM_NOTIFY_CHAR_UUID]

    async def test_start_notify_uses_fallback_notifiable_characteristic(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Use a non-standard notifiable characteristic when UUID 1551 is absent."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        custom_notify_uuid = "00009998-9f03-0de5-96c5-b8f4f3081186"
        unknown_service = _MockService(
            "0000abcd-0000-1000-8000-00805f9b34fb",
            [
                _MockCharacteristic(custom_notify_uuid, ["notify"]),
            ],
        )
        mock_client.services = _MockServices([unknown_service])
        mock_client.start_notify.reset_mock()

        await controller.start_notify(lambda *_: None)

        first_call_char_uuid = str(mock_client.start_notify.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == custom_notify_uuid

    async def test_start_notify_fallback_ignores_service_changed_characteristic(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Fallback notify selection should not pick generic GATT service-changed char."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        custom_notify_uuid = "00009998-9f03-0de5-96c5-b8f4f3081186"
        unknown_service = _MockService(
            "0000abcd-0000-1000-8000-00805f9b34fb",
            [
                _MockCharacteristic("00002a05-0000-1000-8000-00805f9b34fb", ["indicate"]),
                _MockCharacteristic(custom_notify_uuid, ["notify"]),
            ],
        )
        mock_client.services = _MockServices([unknown_service])
        mock_client.start_notify.reset_mock()

        await controller.start_notify(lambda *_: None)

        first_call_char_uuid = str(mock_client.start_notify.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == custom_notify_uuid

    async def test_read_positions_skips_status_request_when_cbi_char_missing(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Status polling should be skipped when CBI characteristic is unavailable."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        primary_service = _MockService(
            VIBRADORM_SERVICE_UUID,
            [
                _MockCharacteristic(VIBRADORM_COMMAND_CHAR_UUID, ["write-without-response"]),
                _MockCharacteristic(VIBRADORM_NOTIFY_CHAR_UUID, ["notify"]),
            ],
        )
        mock_client.services = _MockServices([primary_service])
        mock_client.write_gatt_char.reset_mock()

        await controller.read_positions()

        assert controller._has_cbi_characteristic is False
        written_uuids = [str(call.args[0]).lower() for call in mock_client.write_gatt_char.call_args_list]
        assert VIBRADORM_CBI_CHAR_UUID not in written_uuids

    async def test_resolves_command_char_on_unknown_service(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Controller should find command characteristic on non-Vibradorm services."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        # Simulate a device with a different service UUID but containing the
        # known Vibradorm command characteristic (e.g. some firmware variants).
        unknown_service = _MockService(
            "0000abcd-0000-1000-8000-00805f9b34fb",
            [
                _MockCharacteristic(VIBRADORM_COMMAND_CHAR_UUID, ["write-without-response"]),
            ],
        )
        mock_client.services = _MockServices([unknown_service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        first_call_char_uuid = str(mock_client.write_gatt_char.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == VIBRADORM_COMMAND_CHAR_UUID

    async def test_resolves_writable_char_on_unknown_service_fallback(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Controller should fall back to vendor writable char when known UUIDs are absent."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        custom_char_uuid = "00009999-9f03-0de5-96c5-b8f4f3081186"
        unknown_service = _MockService(
            "0000abcd-0000-1000-8000-00805f9b34fb",
            [
                _MockCharacteristic(custom_char_uuid, ["write"]),
            ],
        )
        mock_client.services = _MockServices([unknown_service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        first_call_char_uuid = str(mock_client.write_gatt_char.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == custom_char_uuid

    async def test_writable_fallback_ignores_non_vendor_characteristics(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Fallback command resolution must not select generic non-Vibradorm UUIDs."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        unknown_service = _MockService(
            "0000abcd-0000-1000-8000-00805f9b34fb",
            [
                _MockCharacteristic("00002a00-0000-1000-8000-00805f9b34fb", ["write"]),
            ],
        )
        mock_client.services = _MockServices([unknown_service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        # If no vendor UUID is found, we keep the known default command UUID.
        assert controller._command_char_uuid == VIBRADORM_COMMAND_CHAR_UUID
        first_call_char_uuid = str(mock_client.write_gatt_char.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == VIBRADORM_COMMAND_CHAR_UUID

    async def test_start_notify_skips_non_vendor_notify_fallback(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Fallback notify resolution must not subscribe to generic non-Vibradorm UUIDs."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        unknown_service = _MockService(
            "0000abcd-0000-1000-8000-00805f9b34fb",
            [
                _MockCharacteristic("00002a05-0000-1000-8000-00805f9b34fb", ["indicate"]),
            ],
        )
        mock_client.services = _MockServices([unknown_service])
        mock_client.start_notify.reset_mock()

        await controller.start_notify(lambda *_: None)

        assert controller._has_notify_characteristic is False
        mock_client.start_notify.assert_not_called()


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

    async def test_move_head_up_uses_neck_command_on_3_motor(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """3-motor beds should map head movement to dedicated NH/NR commands."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm 3-motor Test Bed",
            data={**mock_vibradorm_config_entry_data, CONF_MOTOR_COUNT: 3},
            unique_id="AA:BB:CC:DD:EE:01",
            entry_id="vibradorm_test_entry_3_motor_head",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[0] == VibradormCommands.NECK_UP

    async def test_move_back_up_uses_back_command_on_3_motor(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """3-motor beds should keep back movement on KH/KR commands."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm 3-motor Test Bed",
            data={**mock_vibradorm_config_entry_data, CONF_MOTOR_COUNT: 3},
            unique_id="AA:BB:CC:DD:EE:02",
            entry_id="vibradorm_test_entry_3_motor_back",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_back_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[0] == VibradormCommands.HEAD_UP

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
    """Test Vibradorm preset commands.

    Presets use hold-to-run with 600 repeats (60s). Tests set the cancel event
    after the first write so the loop exits quickly.
    """

    @staticmethod
    def _cancel_after_first_write(coordinator: Any) -> Callable[..., Coroutine[Any, Any, None]]:
        """Return a side_effect that cancels after the first write."""
        call_count: int = 0

        async def _side_effect(*_args: Any, **_kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                coordinator._cancel_command.set()

        return _side_effect

    async def test_preset_flat_sends_all_down(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should send ALL_DOWN command with hold-to-run repeat."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        mock_client.write_gatt_char.side_effect = self._cancel_after_first_write(coordinator)

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data[0] == VibradormCommands.ALL_DOWN

    async def test_preset_memory_1_sends_motor_command(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should send 1-byte motor command via COMMAND char."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        mock_client.write_gatt_char.side_effect = self._cancel_after_first_write(coordinator)

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 1
        assert first_call_data[0] == VibradormCommands.MEMORY_1

    async def test_preset_memory_4_sends_motor_command(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(4) should send 1-byte motor command via COMMAND char."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        mock_client.write_gatt_char.side_effect = self._cancel_after_first_write(coordinator)

        await coordinator.controller.preset_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 1
        assert first_call_data[0] == VibradormCommands.MEMORY_4

    async def test_preset_memory_6_sends_motor_command(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(6) should send 1-byte motor command via COMMAND char."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        mock_client.write_gatt_char.side_effect = self._cancel_after_first_write(coordinator)

        await coordinator.controller.preset_memory(6)

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert len(first_call_data) == 1
        assert first_call_data[0] == VibradormCommands.MEMORY_6

    async def test_preset_memory_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory should send STOP after motor command (hold-to-run)."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client
        mock_client.write_gatt_char.side_effect = self._cancel_after_first_write(coordinator)

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        last_call_data = calls[-1][0][1]
        assert last_call_data[0] == VibradormCommands.STOP

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

    async def test_program_memory_6_sends_selected_slot(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory(6) should target memory slot 6 after STORE sequence."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(6)

        calls = mock_client.write_gatt_char.call_args_list
        sent = [call.args[1] for call in calls]
        assert sent[4] == bytes([0x00, VibradormCommands.MEMORY_6])  # toggle=0


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


class TestVibradormPositionFeedback:
    """Test Vibradorm notification decoding and position mapping."""

    def test_flat_position_packet_reports_zero_angles(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Flat position (all zeros) should report 0.0 angles."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # Real flat data: 20 3F 02 00 00 00 00 00 00 00 00 00
        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        )

        assert updates == [("back", 0.0), ("legs", 0.0)]

    def test_position_packet_updates_back_and_legs(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Position packet should parse back/legs at correct offsets with BE."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # nRF Connect capture - back up: 20 3F 15 04 27 01 A7 00 00 00 00
        # bytes[3:5] BE = 0x0427 = 1063 → back
        # bytes[5:7] BE = 0x01A7 = 423 → legs
        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x15, 0x04, 0x27, 0x01, 0xA7, 0x00, 0x00, 0x00, 0x00]),
        )

        # 1063 / 7000 * 68.0 ≈ 10.3
        # 423 / 14000 * 45.0 ≈ 1.4
        assert len(updates) == 2
        assert updates[0][0] == "back"
        assert updates[0][1] == pytest.approx(10.3, abs=0.1)
        assert updates[1][0] == "legs"
        assert updates[1][1] == pytest.approx(1.4, abs=0.1)

    def test_short_position_packet_without_0x20_prefix_updates_angles(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Short packet layout (3F ...) should still parse motor positions."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # Short format (no 0x20 prefix): 3F flags [positions BE...]
        # Same calibration data as long format test
        # bytes[2:4] BE = 0x0427 = 1063 → back
        # bytes[4:6] BE = 0x01A7 = 423 → legs
        controller._handle_notification(
            MagicMock(),
            bytearray([0x3F, 0x11, 0x04, 0x27, 0x01, 0xA7, 0x00, 0x00, 0x00, 0x00]),
        )

        # 1063 / 7000 * 68.0 ≈ 10.3
        # 423 / 14000 * 45.0 ≈ 1.4
        assert len(updates) == 2
        assert updates[0][0] == "back"
        assert updates[0][1] == pytest.approx(10.3, abs=0.1)
        assert updates[1][0] == "legs"
        assert updates[1][1] == pytest.approx(1.4, abs=0.1)

    def test_position_packet_legs_up(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Position packet with legs raised should parse correctly."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # Legs-up data: 20 3F 02 [back BE] [legs BE] ...
        # bytes[3:5] BE = 0x0000 = 0 → back (flat)
        # bytes[5:7] BE = 0x32C8 = 13000 → legs
        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x02, 0x00, 0x00, 0x32, 0xC8, 0x00, 0x00, 0x00, 0x00]),
        )

        assert updates[0] == ("back", 0.0)
        assert updates[1][0] == "legs"
        # 13000 / 14000 * 45.0 ≈ 41.8
        assert updates[1][1] == pytest.approx(41.8, abs=0.1)

    def test_4_motor_position_packet_parses_all_motors(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry_data: dict,
    ) -> None:
        """4-motor beds should parse all motor positions from a single packet."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm 4-motor Test Bed",
            data={**mock_vibradorm_config_entry_data, CONF_MOTOR_COUNT: 4},
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="vibradorm_test_entry_4_motor",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # All 4 motors with different values (big-endian at offset 3):
        # back=0x1922(6434), legs=0x3618(13848), head=0x0D80(3456), feet=0x1B58(7000)
        controller._handle_notification(
            MagicMock(),
            bytearray([
                0x20, 0x3F, 0x02,
                0x19, 0x22,  # back BE
                0x36, 0x18,  # legs BE
                0x0D, 0x80,  # head BE
                0x1B, 0x58,  # feet BE
            ]),
        )

        motor_names = [m for m, _ in updates]
        assert motor_names == ["back", "legs", "head", "feet"]

    def test_short_packet_ignored(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Packets shorter than 8 bytes should be ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x02, 0x00, 0x22]),
        )

        assert updates == []

    def test_wrong_header_ignored(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Packets with wrong header should be ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # Wrong first byte
        controller._handle_notification(
            MagicMock(),
            bytearray([0x21, 0x3F, 0x02, 0x00, 0x22, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        )

        assert updates == []
