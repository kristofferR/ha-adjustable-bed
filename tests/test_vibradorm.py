"""Tests for Vibradorm bed controller (VMAT single-byte protocol)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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

    async def test_vmat_basic_rf_cbi_disables_position_feedback(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """VMAT-BASIC-RF-CBI should follow the OEM app's write-only control path."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        coordinator._ble_model = "VMAT-BASIC-RF-CBI"

        assert coordinator.controller.supports_position_feedback is False

    async def test_disables_polling_during_commands(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Vibradorm should disable movement-time polling to avoid command interruption."""
        del mock_coordinator_connected
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

    async def test_vmat_basic_rf_cbi_does_not_use_secondary_command_uuid_for_movement(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """VMAT-BASIC-RF-CBI movement should stay on 0x1526 like the OEM app."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        coordinator._ble_model = "VMAT-BASIC-RF-CBI"
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
        assert first_call_char_uuid == VIBRADORM_COMMAND_CHAR_UUID

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

    async def test_resolves_command_char_on_standard_base_alias_service(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Controller should accept VMAT UUIDs normalized to the Bluetooth base UUID."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        service_uuid = "00001525-0000-1000-8000-00805f9b34fb"
        command_uuid = "00001526-0000-1000-8000-00805f9b34fb"
        service = _MockService(
            service_uuid,
            [
                _MockCharacteristic(command_uuid, ["write-without-response"]),
            ],
        )
        mock_client.services = _MockServices([service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        first_call_char_uuid = str(mock_client.write_gatt_char.call_args_list[0].args[0]).lower()
        assert first_call_char_uuid == command_uuid

    async def test_start_notify_and_position_request_use_standard_base_alias_uuids(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Notify and CBI resolution should accept VMAT UUIDs normalized to base UUIDs."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        service_uuid = "00001525-0000-1000-8000-00805f9b34fb"
        command_uuid = "00001526-0000-1000-8000-00805f9b34fb"
        cbi_uuid = "00001550-0000-1000-8000-00805f9b34fb"
        notify_uuid = "00001551-0000-1000-8000-00805f9b34fb"
        service = _MockService(
            service_uuid,
            [
                _MockCharacteristic(command_uuid, ["write-without-response"]),
                _MockCharacteristic(cbi_uuid, ["write-without-response"]),
                _MockCharacteristic(notify_uuid, ["notify"]),
            ],
        )
        mock_client.services = _MockServices([service])
        mock_client.start_notify.reset_mock()
        mock_client.write_gatt_char.reset_mock()

        await controller.start_notify(lambda *_: None)
        await controller.read_positions()

        started_notify_uuid = str(mock_client.start_notify.call_args_list[0].args[0]).lower()
        written_uuids = [str(call.args[0]).lower() for call in mock_client.write_gatt_char.call_args_list]

        assert started_notify_uuid == notify_uuid
        assert cbi_uuid in written_uuids

    async def test_vmat_basic_rf_cbi_skips_position_request(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """VMAT-BASIC-RF-CBI should not send CmdGetStatusMotMon in normal operation."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        coordinator._ble_model = "VMAT-BASIC-RF-CBI"
        mock_client = coordinator._client
        assert mock_client is not None
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.read_positions()

        mock_client.write_gatt_char.assert_not_called()

    async def test_async_connect_disables_angle_sensing_for_vmat_basic_rf_cbi(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """RF-CBI variants should skip angle sensing and notification startup at connect."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm RF-CBI Test Bed",
            data={**mock_vibradorm_config_entry_data, CONF_DISABLE_ANGLE_SENSING: False},
            unique_id="AA:BB:CC:DD:EE:FC",
            entry_id="vibradorm_rf_cbi_entry",
        )
        entry.add_to_hass(hass)

        with patch(
            "custom_components.adjustable_bed.coordinator.read_ble_device_info",
            new=AsyncMock(return_value=("Vibradorm GmbH", "VMAT-BASIC-RF-CBI")),
        ):
            coordinator = AdjustableBedCoordinator(hass, entry)
            connected = await coordinator.async_connect()

        assert connected is True
        assert coordinator.disable_angle_sensing is True
        assert coordinator.controller.supports_position_feedback is False
        coordinator._client.start_notify.assert_not_called()

    async def test_resolves_exact_command_uuid_even_when_write_properties_missing(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Known VMAT command UUIDs should win even if proxy metadata omits write flags."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        service = _MockService(
            VIBRADORM_SERVICE_UUID,
            [
                _MockCharacteristic(VIBRADORM_COMMAND_CHAR_UUID, []),
            ],
        )
        mock_client.services = _MockServices([service])
        mock_client.write_gatt_char.reset_mock()

        await coordinator.controller.move_head_up()

        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert str(first_call.args[0]).lower() == VIBRADORM_COMMAND_CHAR_UUID
        assert first_call.kwargs["response"] is True

    async def test_start_notify_uses_exact_notify_uuid_even_when_properties_missing(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ):
        """Known VMAT notify UUIDs should win even if proxy metadata omits notify flags."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        service = _MockService(
            VIBRADORM_SERVICE_UUID,
            [
                _MockCharacteristic(VIBRADORM_COMMAND_CHAR_UUID, ["write"]),
                _MockCharacteristic(VIBRADORM_NOTIFY_CHAR_UUID, []),
            ],
        )
        mock_client.services = _MockServices([service])
        mock_client.start_notify.reset_mock()

        await controller.start_notify(lambda *_: None)

        started_notify_uuid = str(mock_client.start_notify.call_args_list[0].args[0]).lower()
        assert started_notify_uuid == VIBRADORM_NOTIFY_CHAR_UUID

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

    def test_init_requested_flag_is_tracked(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Position notifications with bit 4 set should mark init_requested=True."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        )

        assert controller.init_requested is True
        assert controller.sync_active is False

    def test_sync_active_flag_is_tracked(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Position notifications with bit 6 set should mark sync_active=True."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        )

        assert controller.sync_active is True
        assert controller.init_requested is False

    def test_motor2_offset_uses_bytes_5_6_not_6_7(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """Motor 2 should read from bytes [5,6] (the decompiled APK has a typo
        that reads motor 2 from [6,7] and overlaps motor 1's MSB; see issue #403).
        """
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)

        updates: list[tuple[str, float]] = []
        controller._notify_callback = lambda motor, value: updates.append((motor, value))

        # bytes [3,4]=0x0000 back, [5,6]=0x0100 legs, [7,8]=0x0200 head (3-motor)
        controller._handle_notification(
            MagicMock(),
            bytearray([0x20, 0x3F, 0x02, 0x00, 0x00, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00]),
        )

        # Filter for the legs value (calibrated against the default 14000 max).
        # 256 / 14000 * 45 ≈ 0.82 — confirms motor 2 reads from [5,6], not
        # [6,7] (which would yield 0x0002 = 2/14000*45 ≈ 0.006).
        legs_update = next(value for motor, value in updates if motor == "legs")
        assert legs_update == pytest.approx(0.82, abs=0.05)


# -----------------------------------------------------------------------------
# Capability / manufacturer data tests
# -----------------------------------------------------------------------------


class TestVibradormManufacturerData:
    """Test detection of control version / motor count from manufacturer data."""

    def test_detect_motor_count_from_manufacturer_data(self) -> None:
        """Motor count should be derived from the vib identifier (BE u16 @ offset 2)."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            detect_motor_count_from_manufacturer_data,
        )

        # 0 → 2-motor, 1 → 4-motor, 4 → 3-motor, 5 → 2-motor
        for control_version, expected_motor_count in (
            (0, 2),
            (1, 4),
            (4, 3),
            (5, 2),
            (6, 3),
            (-1, 4),
        ):
            payload = bytes(
                [0xB0, 0x03, 0x00, control_version & 0xFF, 0x00, 0x00, 0x00, 0x00]
            )
            assert (
                detect_motor_count_from_manufacturer_data({944: payload})
                == expected_motor_count
            )

    def test_detect_motor_count_returns_none_for_unrecognised(self) -> None:
        """Unknown control versions should return None (fall back to user config)."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            detect_motor_count_from_manufacturer_data,
        )

        payload = bytes([0xB0, 0x03, 0x00, 0x42, 0x00, 0x00, 0x00, 0x00])
        assert detect_motor_count_from_manufacturer_data({944: payload}) is None

    def test_detect_motor_count_returns_none_for_missing_data(self) -> None:
        """Empty or missing manufacturer data should return None."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            detect_motor_count_from_manufacturer_data,
        )

        assert detect_motor_count_from_manufacturer_data(None) is None
        assert detect_motor_count_from_manufacturer_data({}) is None
        assert detect_motor_count_from_manufacturer_data({944: b""}) is None

    async def test_advertised_motor_count_exposed_on_controller(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Controller should expose the motor count detected from manufacturer data."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            detect_motor_count_from_manufacturer_data,
        )

        # Re-create the controller with manufacturer data carrying control version 1
        # (= 4-motor in the OEM app).
        entry_data = {
            **mock_vibradorm_config_entry.data,
        }
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Vibradorm 4-motor Test Bed",
            data=entry_data,
            unique_id="AA:BB:CC:DD:EE:F4",
            entry_id="vibradorm_test_entry_4_motor_advert",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        # The coordinator's create_controller() already passes manufacturer_data,
        # so we just verify the controller surfaces what was detected.
        payload = bytes([0xB0, 0x03, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
        # Force a fresh controller with the manufacturer data to make sure
        # the advertised_motor_count reflects the right input.
        fresh = VibradormController(coordinator, manufacturer_data={944: payload})
        assert fresh.advertised_motor_count == 4
        assert detect_motor_count_from_manufacturer_data({944: payload}) == 4


# -----------------------------------------------------------------------------
# CBI light / mood light / VRT tests
# -----------------------------------------------------------------------------


class TestVibradormLightLevel:
    """Test VMAT floor light level / timer commands."""

    async def test_set_light_level_uses_light_char_on_vmat_basic(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """VMAT-basic floor light should be a 3-byte packet on the LIGHT char."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        mock_client.write_gatt_char.reset_mock()
        await controller.set_light_level(5)

        # Find the LIGHT-char write (UUID contains 1529).
        light_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1529" in str(call.args[0]).lower()
        ]
        assert light_calls, "Expected a write to the LIGHT characteristic"
        data = light_calls[-1].args[1]
        assert data == bytes([5, 0, 0])

    async def test_set_light_level_uses_cbi_on_cbi_beds(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """CBI/XT-box floor light should be a 4-byte packet on the CBI char."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(
            is_vmat_basic=False, xt_box=False
        )
        mock_client.write_gatt_char.reset_mock()
        await controller.set_light_level(7)

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls, "Expected a write to the CBI characteristic"
        data = cbi_calls[-1].args[1]
        # [msb, lsb, level(0..8), timer]
        assert data[0] == 0x00  # toggle=0
        assert data[1] == 0x11  # CMD_DIM
        assert data[2] == 7
        assert data[3] == 0

    async def test_set_light_level_clamps_to_eight_on_cbi(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """CBI light level should be clamped to 0..8 (matches MC.setFloorLightLevel)."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(is_vmat_basic=False)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_light_level(42)

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        assert cbi_calls[-1].args[1][2] == 8

    async def test_set_light_timer_preserves_current_level(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """set_light_timer should keep the current light level when timer is set."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        await controller.set_light_level(3)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_light_timer("10")

        light_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1529" in str(call.args[0]).lower()
        ]
        assert light_calls
        data = light_calls[-1].args[1]
        assert data == bytes([3, 0, 10])


class TestVibradormMoodLight:
    """Test CBI RGB mood light (color / effect / speed / toggle)."""

    async def test_set_light_color_sends_cbi_packet(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """set_light_color should send a 7-byte mood color packet on CBI."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_mood_light=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_light_color((255, 128, 64))

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        # [msb(toggle|0x77), lsb, 0x01, 0x00, R, G, B]
        assert data[0] == 0x00  # toggle=0
        assert data[1] == 0x77  # CMD_COLOR
        assert data[2:7] == bytes([0x01, 0x00, 255, 128, 64])

    async def test_set_light_color_uses_bus_mask_for_xt_box(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """XT-box mood light should OR in the CBI bus mask (0x1000)."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_mood_light=True, xt_box=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_light_color((0, 0, 0))

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        # [msb(toggle|0x1077), lsb, …]
        assert (data[0] << 8) | data[1] == 0x1077

    async def test_set_light_color_raises_when_not_supported(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Calling set_light_color without mood light should raise NotImplementedError."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)

        with pytest.raises(NotImplementedError):
            await controller.set_light_color((255, 255, 255))


class TestVibradormMassage:
    """Test VRT (vibration / massage) commands."""

    async def test_set_massage_intensity_head(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """set_massage_intensity(head) should send a VxEFF packet with zone1 set."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_massage=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_massage_intensity("head", 4)

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        # [msb(toggle|0x30), lsb, effect, speed, zone1, zone2, 0,0,0, timer]
        assert data[0] == 0x00  # toggle=0
        assert data[1] == 0x30  # CMD_VxEFF
        assert data[4] == 4  # head intensity
        assert data[5] == 0  # foot intensity

    async def test_set_massage_intensity_foot(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """set_massage_intensity(foot) should send a VxEFF packet with zone2 set."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_massage=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_massage_intensity("foot", 3)

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        assert data[4] == 0  # head
        assert data[5] == 3  # foot

    async def test_set_massage_intensity_clamps_to_five(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Massage intensity should be clamped to 0..5."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_massage=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_massage_intensity("head", 99)

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        assert data[4] == 5

    async def test_set_massage_timer(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """set_massage_timer should send a VxEFF packet with timer field set."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_massage=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.set_massage_timer(20)

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        # timer is the last byte of the VxEFF payload.
        assert data[9] == 20

    async def test_massage_off_sends_vrt_zero(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """massage_off should send CmdVRT with on_off=0."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)
        mock_client = coordinator._client
        assert mock_client is not None

        controller.apply_capabilities(has_massage=True)
        mock_client.write_gatt_char.reset_mock()
        await controller.massage_off()

        cbi_calls = [
            call
            for call in mock_client.write_gatt_char.call_args_list
            if "1550" in str(call.args[0]).lower()
        ]
        assert cbi_calls
        data = cbi_calls[-1].args[1]
        # [msb(toggle|0x34), lsb, 0x00]
        assert data[1] == 0x34  # CMD_VRT
        assert data[2] == 0x00

    async def test_get_massage_state_reports_current_intensity(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """get_massage_state should return head/foot intensity from cached state."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        assert isinstance(controller, VibradormController)

        controller.apply_capabilities(has_massage=True)
        await controller.set_massage_intensity("head", 3)
        await controller.set_massage_intensity("foot", 5)

        state = controller.get_massage_state()
        assert state["head_intensity"] == 3
        assert state["foot_intensity"] == 5
        assert state["head_active"] is True
        assert state["foot_active"] is True


# -----------------------------------------------------------------------------
# EEPROM reassembly tests
# -----------------------------------------------------------------------------


class TestVibradormEeprom:
    """Test EEPROM reassembly from 32x8 row notifications."""

    def test_eeprom_not_complete_initially(self) -> None:
        """Empty EEPROM should report incomplete."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            VibradormEeprom,
        )

        eeprom = VibradormEeprom()
        assert not eeprom.all_received()
        assert eeprom.rows_received == 0

    def test_eeprom_completes_after_32_rows(self) -> None:
        """All 32 rows received should report complete."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            VibradormEeprom,
        )

        eeprom = VibradormEeprom()
        for i in range(32):
            offset = i * 8
            row = bytes([offset & 0xFF] * 8)
            pkt = bytes([0x00, 0x00, offset]) + row
            completed = eeprom.set_row(pkt)
            if i < 31:
                assert not completed
            else:
                assert completed
        assert eeprom.all_received()

    def test_eeprom_snapshots_known_fields(self) -> None:
        """Snapshot should decode the documented XMC EEPROM field offsets."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            EEPROM_OFFSET_H_BRIDGE_OVER_TEMP,
            EEPROM_OFFSET_LOCK,
            EEPROM_OFFSET_PULSE_MOT1,
            EEPROM_OFFSET_PULSE_MOT4,
            EEPROM_OFFSET_TEACH_INS,
            EEPROM_OFFSET_TOTAL_ON_TIME,
            VibradormEeprom,
        )

        eeprom = VibradormEeprom()
        # Build a full image with known values at known offsets.
        image = bytearray(256)
        image[EEPROM_OFFSET_LOCK] = 0x01
        image[EEPROM_OFFSET_PULSE_MOT1] = 0x10
        image[EEPROM_OFFSET_PULSE_MOT1 + 1] = 0x20  # pulse_mot1 = 0x1020 = 4128
        image[EEPROM_OFFSET_PULSE_MOT4] = 0x33
        image[EEPROM_OFFSET_PULSE_MOT4 + 1] = 0x44  # pulse_mot4 = 0x3344 = 13124
        image[EEPROM_OFFSET_TEACH_INS] = 0x00
        image[EEPROM_OFFSET_TEACH_INS + 1] = 0x05  # teach_in_count = 5
        # total_on_time at offset 100, 32-bit BE = 0x12345678
        image[EEPROM_OFFSET_TOTAL_ON_TIME] = 0x12
        image[EEPROM_OFFSET_TOTAL_ON_TIME + 1] = 0x34
        image[EEPROM_OFFSET_TOTAL_ON_TIME + 2] = 0x56
        image[EEPROM_OFFSET_TOTAL_ON_TIME + 3] = 0x78
        image[EEPROM_OFFSET_H_BRIDGE_OVER_TEMP] = 0xAA

        for i in range(32):
            offset = i * 8
            pkt = bytes([0x00, 0x00, offset]) + bytes(image[offset : offset + 8])
            eeprom.set_row(pkt)

        snap = eeprom.snapshot()
        assert snap.complete
        assert snap.lock_flag == 0x01
        assert snap.pulse_mot1 == 0x1020
        assert snap.pulse_mot4 == 0x3344
        assert snap.teach_in_count == 5
        assert snap.total_on_time == 0x12345678
        assert snap.h_bridge_over_temp == 0xAA

    def test_eeprom_ignores_unaligned_offsets(self) -> None:
        """Rows with non-row-aligned offsets should be rejected."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            VibradormEeprom,
        )

        eeprom = VibradormEeprom()
        # offset 1 is not row-aligned (rows are 8 bytes).
        assert eeprom.set_row(bytes([0x00, 0x00, 0x01] + [0xFF] * 8)) is False
        assert eeprom.rows_received == 0

    def test_eeprom_ignores_short_packets(self) -> None:
        """Packets shorter than 11 bytes should be rejected."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            VibradormEeprom,
        )

        eeprom = VibradormEeprom()
        assert eeprom.set_row(bytes([0x00, 0x00, 0x00, 0x01])) is False
        assert eeprom.rows_received == 0

    async def test_eeprom_reassembly_via_notification(
        self,
        hass: HomeAssistant,
        mock_vibradorm_config_entry,
    ) -> None:
        """The position-notification handler should also reassemble EEPROM rows."""
        coordinator = AdjustableBedCoordinator(hass, mock_vibradorm_config_entry)
        controller = VibradormController(coordinator)
        controller._notify_callback = lambda *_: None

        # Apply 32 row notifications in a row.
        for i in range(32):
            row = bytes([i] * 8)
            pkt = bytearray([0x00, 0x00, i * 8]) + bytearray(row)
            controller._handle_notification(MagicMock(), pkt)

        assert controller.eeprom.all_received()
        snap = controller.eeprom.snapshot()
        assert snap.complete


# -----------------------------------------------------------------------------
# Position parser unit tests
# -----------------------------------------------------------------------------


class TestVibradormPositionParser:
    """Test the protocol-module position notification parser."""

    def test_long_format_parses_motor1_motor2(self) -> None:
        """Long-format position notification should expose motor1/motor2 correctly."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            parse_position_notification,
        )

        pkt = bytearray([0x20, 0x3F, 0x02, 0x04, 0x27, 0x01, 0xA7, 0x00, 0x00, 0x00, 0x00])
        parsed = parse_position_notification(pkt)
        assert parsed is not None
        assert parsed.motor1 == 0x0427
        assert parsed.motor2 == 0x01A7
        assert parsed.motor3 == 0
        assert parsed.motor4 == 0
        assert parsed.init_requested is False
        assert parsed.sync_active is False

    def test_short_format_skips_0x20_prefix(self) -> None:
        """Short-format (no 0x20 prefix) should still parse motors correctly."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            parse_position_notification,
        )

        pkt = bytearray([0x3F, 0x02, 0x04, 0x27, 0x01, 0xA7, 0x00, 0x00, 0x00, 0x00])
        parsed = parse_position_notification(pkt)
        assert parsed is not None
        assert parsed.motor1 == 0x0427
        assert parsed.motor2 == 0x01A7

    def test_flags_init_and_sync_decoded(self) -> None:
        """Flags byte should drive init_requested and sync_active booleans."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            parse_position_notification,
        )

        pkt = bytearray([0x20, 0x3F, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        parsed = parse_position_notification(pkt)
        assert parsed is not None
        assert parsed.init_requested is True  # bit 4 (0x10)
        assert parsed.sync_active is False

        pkt = bytearray([0x20, 0x3F, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        parsed = parse_position_notification(pkt)
        assert parsed is not None
        assert parsed.sync_active is True  # bit 6 (0x40)
        assert parsed.init_requested is False

    def test_invalid_packets_return_none(self) -> None:
        """Packets with wrong prefixes or wrong length should return None."""
        from custom_components.adjustable_bed.beds.vibradorm_protocol import (
            parse_position_notification,
        )

        # Empty
        assert parse_position_notification(bytearray()) is None
        # Wrong first byte
        assert parse_position_notification(bytearray([0x21, 0x3F])) is None
        # Long format but too short
        assert parse_position_notification(bytearray([0x20, 0x3F, 0x02])) is None
        # Short format but too short
        assert parse_position_notification(bytearray([0x3F, 0x02])) is None
