"""Tests for OKIN Smart Remote RF ECO BT single-actuator profile."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_rf_eco_bt import (
    STAIR_IN_COMMAND,
    STAIR_OUT_COMMAND,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_RF_ECO_BT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
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

    @pytest.mark.parametrize("disconnect_after_command", [False, True])
    async def test_connection_remains_open_after_commands(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_establish_connection: AsyncMock,
        disconnect_after_command: bool,
    ) -> None:
        """Neither idle timeout nor quick handoff should release the stair link."""
        hass.config_entries.async_update_entry(
            mock_okin_rf_eco_bt_config_entry,
            data={
                **mock_okin_rf_eco_bt_config_entry.data,
                CONF_DISCONNECT_AFTER_COMMAND: disconnect_after_command,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        assert await coordinator.async_connect()
        try:
            assert coordinator._disconnect_timer is None

            await coordinator.async_execute_controller_command(
                lambda controller: controller.move_back_up(),
            )
            await coordinator.async_stop_command()
            coordinator.resume_disconnect_timer()

            assert coordinator.is_connected
            assert coordinator._disconnect_timer is None
            mock_bleak_client.disconnect.assert_not_awaited()
            mock_establish_connection.assert_awaited_once()
            assert _payloads(mock_bleak_client) == [STAIR_OUT_PACKET]
        finally:
            await coordinator.async_disconnect()

    async def test_unexpected_disconnect_reconnects_on_next_command(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        mock_establish_connection: AsyncMock,
    ) -> None:
        """A lost persistent link permits command recovery without a retry loop."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        assert await coordinator.async_connect()
        try:
            mock_bleak_client.is_connected = False
            coordinator._on_disconnect(mock_bleak_client)

            assert coordinator.client is None
            assert coordinator.controller is None
            assert coordinator._reconnect_timer is None
            mock_establish_connection.assert_awaited_once()
            assert _payloads(mock_bleak_client) == []

            await coordinator.async_execute_controller_command(
                lambda controller: controller.move_back_down(),
            )

            assert coordinator.is_connected
            assert mock_establish_connection.await_count == 2
            assert coordinator._disconnect_timer is None
            assert _payloads(mock_bleak_client) == [STAIR_IN_PACKET]
        finally:
            await coordinator.async_disconnect()

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
        finally:
            await coordinator.async_disconnect()

    async def test_open_sends_only_m2_out(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """The fallback table defines movement but no DisobeyStandbyTime row."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.move_back_up()

            assert _payloads(mock_bleak_client) == [STAIR_OUT_PACKET]
        finally:
            await coordinator.async_disconnect()

    async def test_close_sends_only_m2_in(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Closing must not send the zero payload that toggles the receiver light."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.move_back_down()

            assert _payloads(mock_bleak_client) == [STAIR_IN_PACKET]
        finally:
            await coordinator.async_disconnect()

    async def test_stop_all_ends_refresh_without_a_packet(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """STOP cancels refresh without inventing a release frame."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            mock_bleak_client.write_gatt_char.reset_mock()

            await coordinator.controller.stop_all()

            assert _payloads(mock_bleak_client) == []
        finally:
            await coordinator.async_disconnect()

    async def test_stop_cancels_running_refresh_without_a_release_frame(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_okin_rf_eco_bt_config_entry)
        await coordinator.async_connect()
        try:
            coordinator._motor_pulse_count = 100
            mock_bleak_client.write_gatt_char.reset_mock()
            first_write = asyncio.Event()
            mock_bleak_client.write_gatt_char.side_effect = lambda *args, **kwargs: first_write.set()
            movement = asyncio.create_task(coordinator.async_execute_controller_command(
                lambda controller: controller.move_back_up(), cancel_running=False,
            ))
            await asyncio.wait_for(first_write.wait(), timeout=1)
            await asyncio.wait_for(coordinator.async_stop_command(), timeout=1)
            await asyncio.wait_for(movement, timeout=1)
            assert _payloads(mock_bleak_client) == [STAIR_OUT_PACKET]
            assert coordinator.controller._motor_state == {}
        finally:
            await coordinator.async_disconnect()

    async def test_timed_move_pulse_sequence_uses_m2_only(
        self,
        hass: HomeAssistant,
        mock_okin_rf_eco_bt_config_entry: MockConfigEntry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Timed movement ends its held-command refresh."""
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
            ]
        finally:
            await coordinator.async_disconnect()
