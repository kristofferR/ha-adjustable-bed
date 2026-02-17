"""Tests for SUTA Smart Home controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.suta import SutaCommands
from custom_components.adjustable_bed.const import (
    BED_TYPE_SUTA,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SUTA_DEFAULT_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _to_packet(command: str) -> bytes:
    return f"{command}\r\n".encode()


@pytest.fixture
def suta_coordinator(hass: HomeAssistant, mock_coordinator_connected):
    """Create and connect a coordinator for a SUTA test device."""

    async def _create(
        *,
        address: str,
        name: str,
        entry_id: str,
        motor_count: int = 2,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SUTA Test Bed",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: BED_TYPE_SUTA,
                CONF_MOTOR_COUNT: motor_count,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=address,
            entry_id=entry_id,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        return coordinator

    return _create


class TestSutaController:
    """Test SUTA controller behavior."""

    async def test_control_characteristic_uuid(self, suta_coordinator) -> None:
        """Controller should expose fallback write UUID before dynamic discovery."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:01",
            name="SUTA-B803",
            entry_id="suta_test_entry",
        )

        assert coordinator.controller.control_characteristic_uuid == SUTA_DEFAULT_WRITE_CHAR_UUID

    async def test_move_back_up_sends_back_and_stop(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Back-up movement should send BACK UP and then STOP."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:02",
            name="SUTA-B207",
            entry_id="suta_test_entry_2",
        )

        await coordinator.controller.move_back_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls
        first_payload = calls[0][0][1]
        last_payload = calls[-1][0][1]
        assert first_payload == _to_packet(SutaCommands.BACK_UP)
        assert last_payload == _to_packet(SutaCommands.STOP_ALL)

    async def test_lights_on_and_off(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Light commands should send discrete ENABLE/DISABLE commands."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:03",
            name="SUTA-B410",
            entry_id="suta_test_entry_3",
        )

        await coordinator.controller.lights_on()
        await coordinator.controller.lights_off()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == _to_packet(SutaCommands.LIGHT_ON)
        assert calls[1][0][1] == _to_packet(SutaCommands.LIGHT_OFF)

    async def test_lights_toggle_tracks_local_state(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Toggle should alternate between ON and OFF using local state tracking."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:05",
            name="SUTA-B803",
            entry_id="suta_test_entry_5",
        )

        await coordinator.controller.lights_toggle()
        await coordinator.controller.lights_toggle()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == _to_packet(SutaCommands.LIGHT_ON)
        assert calls[1][0][1] == _to_packet(SutaCommands.LIGHT_OFF)

    async def test_preset_memory_2_sends_m2_command(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Memory preset 2 should send one M2 recall command without STOP."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:04",
            name="SUTA-B505",
            entry_id="suta_test_entry_4",
        )

        await coordinator.controller.preset_memory(2)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][1] == _to_packet(SutaCommands.PRESET_MEMORY_2)

    async def test_preset_tv_sends_single_command_without_stop(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """TV preset should send one preset command and let firmware run continuously."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:06",
            name="SUTA-B201B",
            entry_id="suta_test_entry_6",
        )

        await coordinator.controller.preset_tv()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][1] == _to_packet(SutaCommands.PRESET_TV)
