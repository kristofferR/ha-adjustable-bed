"""Tests for OKIN Smart Remote RF ECO BT single-actuator profile."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_rf_eco_bt import (
    STAIR_IN_COMMAND,
    STAIR_OUT_COMMAND,
    STOP_COMMAND,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_RF_ECO_BT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OKIMAT_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

TEST_ADDRESS = "AA:BB:CC:DD:EE:44"
STAIR_OUT_PACKET = bytes.fromhex("040200000001")
STAIR_IN_PACKET = bytes.fromhex("040200000002")
STOP_PACKET = bytes.fromhex("040200000000")


@pytest.fixture
def mock_okin_rf_eco_bt_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a mock config entry for an OKIN RF ECO BT stair actuator."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Elda Stair",
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: "Elda Stair",
            CONF_BED_TYPE: BED_TYPE_OKIN_RF_ECO_BT,
            CONF_MOTOR_COUNT: 1,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_MOTOR_PULSE_COUNT: 1,
            CONF_MOTOR_PULSE_DELAY_MS: 1,
        },
        unique_id=TEST_ADDRESS,
        entry_id="okin_rf_eco_bt_entry",
    )
    entry.add_to_hass(hass)
    return entry


def _payloads(mock_bleak_client: MagicMock) -> list[bytes]:
    """Return written BLE payloads from the mock client."""
    return [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]


class TestOkinRfEcoBtController:
    """Test OKIN RF ECO BT profile behavior."""

    async def test_control_characteristic_and_capabilities(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
    ) -> None:
        """Controller should expose only the stair surface and stop support."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            controller = coordinator.controller

            assert controller.control_characteristic_uuid == OKIMAT_WRITE_CHAR_UUID
            assert [spec.key for spec in controller.motor_control_specs] == ["stair"]
            assert controller.supports_stop_all is True
            assert controller.supports_preset_flat is False
            assert controller.supports_memory_presets is False
            assert controller.supports_memory_programming is False
            assert controller.supports_lights is False
            assert controller.supports_light_toggle_control is False
            assert controller.supports_massage is False
            assert controller._build_command(STAIR_OUT_COMMAND) == STAIR_OUT_PACKET
            assert controller._build_command(STAIR_IN_COMMAND) == STAIR_IN_PACKET
            assert controller._build_command(STOP_COMMAND) == STOP_PACKET
        finally:
            await coordinator.async_disconnect()

    async def test_open_sends_m2_out_then_stop(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Opening the stair should send M2Out then DisobeyStandbyTime."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.move_back_up()

            assert _payloads(mock_bleak_client) == [STAIR_OUT_PACKET, STOP_PACKET]
        finally:
            await coordinator.async_disconnect()

    async def test_close_sends_m2_in_then_stop(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Closing the stair should send M2In then DisobeyStandbyTime."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.move_back_down()

            assert _payloads(mock_bleak_client) == [STAIR_IN_PACKET, STOP_PACKET]
        finally:
            await coordinator.async_disconnect()

    async def test_stop_all_sends_disobey_standby_time(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Stop should send the APK DisobeyStandbyTime command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.stop_all()

            assert _payloads(mock_bleak_client) == [STOP_PACKET]
        finally:
            await coordinator.async_disconnect()

    async def test_timed_move_pulse_sequence_uses_m2_only(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Timed movement should repeat M2Out and then release with stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            coordinator._motor_pulse_count = 3
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.move_back_up()

            assert _payloads(mock_bleak_client) == [
                STAIR_OUT_PACKET,
                STAIR_OUT_PACKET,
                STAIR_OUT_PACKET,
                STOP_PACKET,
            ]
        finally:
            await coordinator.async_disconnect()
