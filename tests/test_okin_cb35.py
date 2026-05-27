"""Tests for Okin CB35 Star bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_7byte import _cmd
from custom_components.adjustable_bed.beds.okin_cb35 import (
    OKIN_CB35_CONFIG,
    OkinCB35Controller,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CB35,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_okin_cb35_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a mock config entry for an Okin CB35 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin CB35 Test Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Okin CB35 Test Bed",
            CONF_BED_TYPE: BED_TYPE_OKIN_CB35,
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_cb35_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_cb35_client() -> AsyncMock:
    """Return a connected BLE client mock for CB35 tests."""
    client = AsyncMock()
    client.is_connected = True
    client.services = []
    return client


@pytest.mark.asyncio
class TestOkinCB35Controller:
    """Test Okin CB35 controller behavior."""

    async def test_write_command_passes_effective_cancel_event(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """write_command should propagate the coordinator cancel event explicitly."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True

        with patch.object(
            controller, "_write_gatt_with_retry", new=AsyncMock()
        ) as write_mock:
            await controller.write_command(_cmd(0x00))

        write_mock.assert_awaited_once()
        assert write_mock.await_args.kwargs["cancel_event"] is coordinator.cancel_command
        assert write_mock.await_args.kwargs["response"] is OKIN_CB35_CONFIG.write_with_response

    async def test_cancelled_movement_sends_stop_with_fresh_event(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """A pre-cancelled CB35 movement should skip motion and still send STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        coordinator.cancel_command.set()

        await controller.move_head_up()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert _cmd(0x00) not in payloads
        assert payloads[-1] == _cmd(0x0F)
