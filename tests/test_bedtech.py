"""Tests for BedTech bed controller (5-byte ASCII protocol)."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDTECH,
    BEDTECH_WRITE_CHAR_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_bedtech_config_entry_data() -> dict:
    """Return mock config entry data for BedTech bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "BedTech Test Bed",
        CONF_BED_TYPE: BED_TYPE_BEDTECH,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_bedtech_config_entry(
    hass: HomeAssistant, mock_bedtech_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for BedTech bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BedTech Test Bed",
        data=mock_bedtech_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="bedtech_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestBedTechController:
    """Test BedTechController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use BedTech write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == BEDTECH_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_tv(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support TV preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_tv is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support lounge preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_lounge is True

    async def test_supports_memory_presets(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True

    async def test_memory_slot_count(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should have 2 memory slots."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.memory_slot_count == 2

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support lights."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should be toggle-only because it has no explicit ON command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is False
        assert coordinator.controller.supports_light_toggle_control is True

    async def test_has_pillow_support(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """BedTech should support pillow/leg motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_pillow_support is True

    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_supports_stop_all(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
    ):
        """BedTech should support stop_all (BT6500 compatibility stop)."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_stop_all is True


class TestBedTechPresets:
    """Test BedTech preset commands."""

    @pytest.mark.parametrize(
        ("memory_num", "expected_command"),
        [
            (1, "."),
            (2, "/"),
        ],
    )

    async def test_memory_recall_uses_oem_slot_commands(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
        memory_num: int,
        expected_command: str,
    ):
        """Memory recall should use `.` for slot 1 and `/` for slot 2."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        call_data = coordinator._client.write_gatt_char.call_args_list[0][0][1]
        assert call_data[3] == ord(expected_command)

    @pytest.mark.parametrize(
        ("memory_num", "expected_command"),
        [
            (1, "+"),
            (2, ","),
        ],
    )

    async def test_memory_programming_uses_oem_slot_commands(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
        memory_num: int,
        expected_command: str,
    ):
        """Memory save should use `+` for slot 1 and `,` for slot 2."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        call_data = coordinator._client.write_gatt_char.call_args_list[0][0][1]
        assert call_data[3] == ord(expected_command)


class TestBedTechLights:
    """Test BedTech light commands."""

    async def test_lights_on_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """lights_on should use TOGGLE because the APK has no discrete ON command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_on()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord("<")

    async def test_lights_off_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """lights_off should send LIGHT_OFF command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord("u")

    async def test_lights_toggle_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_bedtech_config_entry,
        mock_coordinator_connected,
    ):
        """lights_toggle should send LIGHT_TOGGLE command."""
        coordinator = AdjustableBedCoordinator(hass, mock_bedtech_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.lights_toggle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data[3] == ord("<")
