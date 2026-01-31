"""Tests for Svane bed controller (LinonPI multi-service protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import (
    SvaneCommands,
    SvaneController,
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
        assert SvaneCommands.MOTOR_MOVE == bytes([0x01, 0x00])

    def test_motor_stop_command(self):
        """MOTOR_STOP should be [0x00, 0x00]."""
        assert SvaneCommands.MOTOR_STOP == bytes([0x00, 0x00])

    def test_svane_position_command(self):
        """SVANE_POSITION should be [0x03, 0x00]."""
        assert SvaneCommands.SVANE_POSITION == bytes([0x03, 0x00])
        assert len(SvaneCommands.SVANE_POSITION) == 2

    def test_memory_commands_are_6_bytes(self):
        """Memory commands should be 6 bytes."""
        assert len(SvaneCommands.FLATTEN) == 6
        assert len(SvaneCommands.SAVE_POSITION) == 6
        assert len(SvaneCommands.RECALL_POSITION) == 6
        assert len(SvaneCommands.READ_POSITION) == 6

    def test_flatten_command(self):
        """FLATTEN command should have correct bytes."""
        assert SvaneCommands.FLATTEN == bytes([0x3F, 0x81, 0x00, 0x00, 0x00, 0x00])

    def test_save_position_command(self):
        """SAVE_POSITION command should have correct bytes."""
        assert SvaneCommands.SAVE_POSITION == bytes([0x3F, 0x40, 0x00, 0x00, 0x00, 0x00])

    def test_recall_position_command(self):
        """RECALL_POSITION command should have correct bytes."""
        assert SvaneCommands.RECALL_POSITION == bytes([0x3F, 0x80, 0x00, 0x00, 0x00, 0x00])

    def test_light_commands_are_6_bytes(self):
        """Light commands should be 6 bytes."""
        assert len(SvaneCommands.LIGHT_ON) == 6
        assert len(SvaneCommands.LIGHT_OFF) == 6

    def test_light_on_command(self):
        """LIGHT_ON command should have brightness=80."""
        assert SvaneCommands.LIGHT_ON == bytes([0x13, 0x02, 0x50, 0x01, 0x00, 0x50])

    def test_light_off_command(self):
        """LIGHT_OFF command should be all zeros except header."""
        assert SvaneCommands.LIGHT_OFF == bytes([0x13, 0x02, 0x00, 0x00, 0x00, 0x00])


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

    async def test_memory_slot_count_is_one(
        self,
        hass: HomeAssistant,
        mock_svane_config_entry,
        mock_coordinator_connected,
    ):
        """Svane should have 1 memory slot."""
        coordinator = AdjustableBedCoordinator(hass, mock_svane_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 1

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
