"""Tests for TiMOTION AHF controller."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.timotion_ahf import (
    TiMOTIONAhfCommands,
    build_timotion_ahf_command,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_TIMOTION_AHF,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    TIMOTION_AHF_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


class TestTiMOTIONAhfController:
    """Test TiMOTION AHF controller behavior."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ) -> None:
        """Controller should use Nordic UART write characteristic."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="AHF Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:11",
                CONF_NAME: "AHF-1234",
                CONF_BED_TYPE: BED_TYPE_TIMOTION_AHF,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:11",
            entry_id="timotion_ahf_test_entry",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == TIMOTION_AHF_WRITE_CHAR_UUID

    def test_build_command_packet(self) -> None:
        """Command builder should duplicate group bytes and keep reserved bytes zero."""
        packet = build_timotion_ahf_command(group1=0x04, group2=0x20)
        assert len(packet) == 11
        assert packet[:3] == bytes([0xDD, 0xDD, 0xFF])
        assert packet[3] == 0x04 and packet[4] == 0x04
        assert packet[5] == 0x20 and packet[6] == 0x20
        assert packet[7:] == bytes([0x00, 0x00, 0x00, 0x00])

    async def test_move_back_up_sends_motor1_and_stop(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Back-up movement should use motor1 up bit and end with stop packet."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="AHF Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:12",
                CONF_NAME: "AHF-1235",
                CONF_BED_TYPE: BED_TYPE_TIMOTION_AHF,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:12",
            entry_id="timotion_ahf_test_entry_2",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.move_back_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls
        first_packet = calls[0][0][1]
        last_packet = calls[-1][0][1]
        assert first_packet == build_timotion_ahf_command(group1=TiMOTIONAhfCommands.MOTOR1_UP)
        assert last_packet == build_timotion_ahf_command()

    async def test_move_head_up_uses_motor3_bit(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Head-up should map to motor3 up bit in group1."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="AHF Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
                CONF_NAME: "AHF-1236",
                CONF_BED_TYPE: BED_TYPE_TIMOTION_AHF,
                CONF_MOTOR_COUNT: 3,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:13",
            entry_id="timotion_ahf_test_entry_3",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        first_packet = mock_bleak_client.write_gatt_char.call_args_list[0][0][1]
        assert first_packet == build_timotion_ahf_command(group1=TiMOTIONAhfCommands.MOTOR3_UP)

    async def test_lights_toggle_uses_under_bed_bit(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Light toggle should send under-bed light bit in group2."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="AHF Test Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:14",
                CONF_NAME: "AHF-1237",
                CONF_BED_TYPE: BED_TYPE_TIMOTION_AHF,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:14",
            entry_id="timotion_ahf_test_entry_4",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        first_packet = mock_bleak_client.write_gatt_char.call_args_list[0][0][1]
        assert first_packet == build_timotion_ahf_command(
            group2=TiMOTIONAhfCommands.UNDER_BED_LIGHT_TOGGLE
        )
