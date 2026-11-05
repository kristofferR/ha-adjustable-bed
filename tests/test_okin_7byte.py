"""Tests for Okin 7-byte bed controller."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_nordic import OkinNordicController
from custom_components.adjustable_bed.codec.okin_5a import command as _cmd
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_7BYTE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    NECTAR_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_okin_7byte_config_entry_data() -> dict:
    """Return mock config entry data for Okin 7-byte bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin 7-byte Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIN_7BYTE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_7byte_config_entry(
    hass: HomeAssistant, mock_okin_7byte_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin 7-byte bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin 7-byte Test Bed",
        data=mock_okin_7byte_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_7byte_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


# -----------------------------------------------------------------------------
# Controller Tests
# -----------------------------------------------------------------------------


class TestOkin7ByteController:
    """Test Okin7ByteController."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Control characteristic should use Nectar write UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == NECTAR_WRITE_CHAR_UUID

    async def test_supports_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support zero-g preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True

    async def test_supports_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support anti-snore preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_anti_snore is True

    async def test_supports_preset_lounge(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lounge preset."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_lounge is True

    async def test_has_lumbar_support(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lumbar motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.has_lumbar_support is True

    async def test_supports_lights(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support lights."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_supports_discrete_light_control(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support discrete light control."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_discrete_light_control is True

    async def test_memory_presets_supported(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Okin 7-byte should support memory presets."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_memory_presets is True


class TestOkin7ByteMovement:
    """Test Okin 7-byte movement commands."""

    async def test_move_lumbar_up_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """move_lumbar_up should send LUMBAR_UP command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_lumbar_up()

        calls = mock_client.write_gatt_char.call_args_list
        first_call_data = calls[0][0][1]
        assert first_call_data == _cmd(0x04)

    async def test_move_head_up_writes_without_response(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Nectar commands should use write-without-response."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.move_head_up()

        first_call = mock_client.write_gatt_char.call_args_list[0]
        assert first_call.kwargs["response"] is False


class TestOkin7ByteMassage:
    """Test Okin 7-byte massage commands."""

    async def test_massage_toggle_starts_massage(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """The exposed massage toggle button should send the verified on command."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.massage_toggle()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x58)

    async def test_massage_off_sends_verified_off_command(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Nectar massage off is 0x5A; 0x6F was captured as no-op."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        mock_client = coordinator._client

        await coordinator.controller.massage_off()

        calls = mock_client.write_gatt_char.call_args_list
        call_data = calls[0][0][1]
        assert call_data == _cmd(0x5A)

    async def test_massage_intensity_follows_variant(
        self,
        hass: HomeAssistant,
        mock_okin_7byte_config_entry,
        mock_coordinator_connected,
    ):
        """Nectar has no intensity bytes, so no intensity buttons are advertised."""
        del mock_coordinator_connected

        coordinator = AdjustableBedCoordinator(hass, mock_okin_7byte_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        assert controller.supports_massage_intensity_step_control is False
        assert controller.supports_massage_intensity_up_control is False
        assert OkinNordicController(coordinator).supports_massage_intensity_step_control is True


