"""Tests for Reverie Nightstand bed controller (Protocol 110)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie_nightstand import (
    ReverieNightstandCommands,
    ReverieNightstandController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE_NIGHTSTAND,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    REVERIE_NIGHTSTAND_LED_UUID,
    REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID,
    REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
    REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID,
    REVERIE_NIGHTSTAND_PRESETS_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_reverie_nightstand_config_entry_data() -> dict:
    """Return mock config entry data for Reverie Nightstand bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Reverie Nightstand Test Bed",
        CONF_BED_TYPE: BED_TYPE_REVERIE_NIGHTSTAND,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_reverie_nightstand_config_entry(
    hass: HomeAssistant, mock_reverie_nightstand_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Reverie Nightstand bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reverie Nightstand Test Bed",
        data=mock_reverie_nightstand_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="reverie_nightstand_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Command Constants Tests
# -----------------------------------------------------------------------------


class TestReverieNightstandCommands:
    """Test Reverie Nightstand command constants."""

    def test_motor_control_values(self):
        """Motor control values should be correct."""
        assert ReverieNightstandCommands.MOTOR_UP == 0x01
        assert ReverieNightstandCommands.MOTOR_DOWN == 0x02
        assert ReverieNightstandCommands.MOTOR_STOP == 0x00

    def test_led_control_values(self):
        """LED control values should be correct."""
        assert ReverieNightstandCommands.LED_ON == 0x64  # 100 decimal
        assert ReverieNightstandCommands.LED_OFF == 0x00

    def test_preset_mode_values(self):
        """Preset mode values should be correct."""
        assert ReverieNightstandCommands.MODE_1 == 0x01
        assert ReverieNightstandCommands.MODE_2 == 0x02
        assert ReverieNightstandCommands.MODE_3 == 0x03

    def test_memory_preset_calculation(self):
        """memory_preset() should return memory_num + 3."""
        assert ReverieNightstandCommands.memory_preset(1) == 0x04
        assert ReverieNightstandCommands.memory_preset(2) == 0x05
        assert ReverieNightstandCommands.memory_preset(3) == 0x06
        assert ReverieNightstandCommands.memory_preset(4) == 0x07

    def test_store_memory_calculation(self):
        """store_memory() should return memory_num + 83."""
        assert ReverieNightstandCommands.store_memory(1) == 0x54  # 84
        assert ReverieNightstandCommands.store_memory(2) == 0x55  # 85
        assert ReverieNightstandCommands.store_memory(3) == 0x56  # 86
        assert ReverieNightstandCommands.store_memory(4) == 0x57  # 87


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestReverieNightstandController:
    """Test ReverieNightstandController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should be linear head UUID."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert (
            coordinator.controller.control_characteristic_uuid
            == REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID
        )

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support memory presets."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count_is_4(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should have 4 memory slots."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 4

    async def test_supports_memory_programming(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support memory programming."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_programming is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support discrete light control."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Reverie Nightstand should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True


class TestReverieNightstandMovement:
    """Test Reverie Nightstand movement commands."""

    async def test_move_head_up_writes_to_head_char(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """move_head_up should write to linear head characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        assert mock_client.write_gatt_char.called
        # First call should be to head characteristic with MOTOR_UP
        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MOTOR_UP])

    async def test_move_legs_up_writes_to_foot_char(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """move_legs_up should write to linear foot characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_legs_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MOTOR_UP])

    async def test_move_lumbar_up_writes_to_lumbar_char(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should write to linear lumbar characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MOTOR_UP])

    async def test_movement_sends_stop_after(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """Movement should send STOP after motor command."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        calls = mock_client.write_gatt_char.call_args_list
        # Last call should be STOP to head char
        last_call = calls[-1]
        assert last_call[0][0] == REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID
        assert last_call[0][1] == bytes([ReverieNightstandCommands.MOTOR_STOP])

    async def test_stop_all_writes_to_all_motor_chars(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """stop_all should write STOP to head, foot, and lumbar characteristics."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.stop_all()

        calls = mock_client.write_gatt_char.call_args_list
        # Should have 3 calls (head, foot, lumbar)
        assert len(calls) == 3

        # Extract UUIDs written to
        uuids = [call[0][0] for call in calls]
        assert REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID in uuids
        assert REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID in uuids
        assert REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID in uuids

        # All should be STOP command
        for call in calls:
            assert call[0][1] == bytes([ReverieNightstandCommands.MOTOR_STOP])


class TestReverieNightstandPresets:
    """Test Reverie Nightstand preset commands."""

    async def test_preset_flat_writes_mode_1(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_flat should write MODE_1 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_flat()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MODE_1])

    async def test_preset_zero_g_writes_mode_2(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_zero_g should write MODE_2 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_zero_g()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.MODE_2])

    async def test_preset_memory_1_writes_correct_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(1) should write 0x04 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x04])  # memory_preset(1) = 4

    async def test_preset_memory_4_writes_correct_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """preset_memory(4) should write 0x07 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.preset_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x07])  # memory_preset(4) = 7

    async def test_program_memory_1_writes_store_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory(1) should write 0x54 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(1)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x54])  # store_memory(1) = 84

    async def test_program_memory_4_writes_store_value(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """program_memory(4) should write 0x57 to presets characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.program_memory(4)

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_PRESETS_UUID
        assert first_call[0][1] == bytes([0x57])  # store_memory(4) = 87


class TestReverieNightstandLights:
    """Test Reverie Nightstand light commands."""

    async def test_lights_on_writes_led_on(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on should write LED_ON (0x64) to LED characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LED_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.LED_ON])

    async def test_lights_off_writes_led_off(
        self,
        hass: HomeAssistant,
        mock_reverie_nightstand_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should write LED_OFF (0x00) to LED characteristic."""
        coordinator = AdjustableBedCoordinator(
            hass, mock_reverie_nightstand_config_entry
        )
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        first_call = calls[0]
        assert first_call[0][0] == REVERIE_NIGHTSTAND_LED_UUID
        assert first_call[0][1] == bytes([ReverieNightstandCommands.LED_OFF])


class TestReverieNightstandMultiCharacteristic:
    """Test Reverie Nightstand multi-characteristic protocol."""

    def test_all_characteristic_uuids_defined(self):
        """All characteristic UUIDs should be defined."""
        assert REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID is not None
        assert REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID is not None
        assert REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID is not None
        assert REVERIE_NIGHTSTAND_PRESETS_UUID is not None
        assert REVERIE_NIGHTSTAND_LED_UUID is not None

    def test_characteristic_uuids_are_different(self):
        """All motor characteristics should be different UUIDs."""
        uuids = [
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
            REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID,
            REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID,
        ]
        assert len(uuids) == len(set(uuids))

    def test_single_byte_commands(self):
        """All motor commands should be single bytes."""
        assert ReverieNightstandCommands.MOTOR_UP <= 0xFF
        assert ReverieNightstandCommands.MOTOR_DOWN <= 0xFF
        assert ReverieNightstandCommands.MOTOR_STOP <= 0xFF
        assert ReverieNightstandCommands.LED_ON <= 0xFF
        assert ReverieNightstandCommands.LED_OFF <= 0xFF
