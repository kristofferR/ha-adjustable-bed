"""Tests for SUTA Smart Home controller."""

from __future__ import annotations

from unittest.mock import MagicMock

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
    return f"{command}\r\n".encode("utf-8")


class TestSutaController:
    """Test SUTA controller behavior."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ) -> None:
        """Controller should expose fallback write UUID before dynamic discovery."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SUTA Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
                CONF_NAME: "SUTA-B803",
                CONF_BED_TYPE: BED_TYPE_SUTA,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:01",
            entry_id="suta_test_entry",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == SUTA_DEFAULT_WRITE_CHAR_UUID

    async def test_move_back_up_sends_back_and_stop(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Back-up movement should send BACK UP and then STOP."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SUTA Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
                CONF_NAME: "SUTA-B207",
                CONF_BED_TYPE: BED_TYPE_SUTA,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:02",
            entry_id="suta_test_entry_2",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls
        first_payload = calls[0][0][1]
        last_payload = calls[-1][0][1]
        assert first_payload == _to_packet(SutaCommands.BACK_UP)
        assert last_payload == _to_packet(SutaCommands.STOP_ALL)

    async def test_lights_on_and_off(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Light commands should send discrete ENABLE/DISABLE commands."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SUTA Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:03",
                CONF_NAME: "SUTA-B410",
                CONF_BED_TYPE: BED_TYPE_SUTA,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:03",
            entry_id="suta_test_entry_3",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_on()
        await coordinator.controller.lights_off()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == _to_packet(SutaCommands.LIGHT_ON)
        assert calls[1][0][1] == _to_packet(SutaCommands.LIGHT_OFF)

    async def test_preset_memory_2_sends_m2_command(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Memory preset 2 should send M2 recall command."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SUTA Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:04",
                CONF_NAME: "SUTA-B505",
                CONF_BED_TYPE: BED_TYPE_SUTA,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:04",
            entry_id="suta_test_entry_4",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(2)

        first_payload = mock_bleak_client.write_gatt_char.call_args_list[0][0][1]
        assert first_payload == _to_packet(SutaCommands.PRESET_MEMORY_2)
