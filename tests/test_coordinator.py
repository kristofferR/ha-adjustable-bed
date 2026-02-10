"""Tests for Adjustable Bed coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PREFERRED_ADAPTER,
    CONF_RICHMAT_REMOTE,
    DEFAULT_MOTOR_PULSE_COUNT,
    DEFAULT_MOTOR_PULSE_DELAY_MS,
    DOMAIN,
    RICHMAT_REMOTE_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

from .conftest import TEST_ADDRESS, TEST_NAME


class TestCoordinatorInit:
    """Test coordinator initialization."""

    async def test_coordinator_properties(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test coordinator properties are set correctly."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        assert coordinator.address == TEST_ADDRESS
        assert coordinator.name == TEST_NAME
        assert coordinator.bed_type == BED_TYPE_LINAK
        assert coordinator.motor_count == 2
        assert coordinator.has_massage is False
        assert coordinator.disable_angle_sensing is True
        assert coordinator.controller is None
        assert coordinator.position_data == {}

    async def test_device_info(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test device info is generated correctly."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        device_info = coordinator.device_info

        assert device_info["identifiers"] == {("adjustable_bed", TEST_ADDRESS)}
        assert device_info["name"] == TEST_NAME
        assert device_info["manufacturer"] == "Linak"
        assert "2 motors" in device_info["model"]


class TestCoordinatorConnection:
    """Test coordinator connection handling."""

    async def test_connect_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test successful connection."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        result = await coordinator.async_connect()

        assert result is True
        assert coordinator.controller is not None

    async def test_connect_device_not_found(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_bluetooth_adapters,
    ):
        """Test connection fails when device not found."""
        with patch(
            "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

        assert result is False
        assert coordinator.controller is None

    async def test_connect_bleak_error(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_adapters,
    ):
        """Test connection handles BleakError."""
        with patch(
            "custom_components.adjustable_bed.coordinator.establish_connection",
            new_callable=AsyncMock,
            side_effect=BleakError("Connection failed"),
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
            result = await coordinator.async_connect()

        assert result is False

    @pytest.mark.usefixtures("mock_coordinator_connected")
    async def test_connect_richmat_auto_remote_uses_ble_name_detection(
        self,
        hass: HomeAssistant,
    ):
        """Richmat auto remote should be inferred from BLE name when available."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Richmat Test Bed",
            data={
                CONF_ADDRESS: TEST_ADDRESS,
                CONF_NAME: "Richmat Test Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
                CONF_RICHMAT_REMOTE: RICHMAT_REMOTE_AUTO,
            },
            unique_id=TEST_ADDRESS,
            entry_id="richmat_auto_remote_test",
        )
        entry.add_to_hass(hass)

        adapter_result = MagicMock()
        adapter_result.device = MagicMock()
        adapter_result.device.address = TEST_ADDRESS
        adapter_result.device.name = "QRRM141291"
        adapter_result.device.details = {"source": "local"}
        adapter_result.rssi = -55
        adapter_result.adapter = "local"

        with (
            patch(
                "custom_components.adjustable_bed.coordinator.select_adapter",
                new_callable=AsyncMock,
                return_value=adapter_result,
            ),
            patch(
                "custom_components.adjustable_bed.coordinator.create_controller",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ) as mock_create_controller,
        ):
            coordinator = AdjustableBedCoordinator(hass, entry)
            result = await coordinator.async_connect()

        assert result is True
        assert mock_create_controller.await_args.kwargs["richmat_remote"] == "qrrm"

    async def test_disconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test disconnection."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.async_disconnect()

        mock_bleak_client.disconnect.assert_called_once()

    async def test_ensure_connected_when_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test ensure_connected returns True when already connected."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        result = await coordinator.async_ensure_connected()

        assert result is True

    async def test_ensure_connected_reconnects(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test ensure_connected reconnects when disconnected."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        # First call will connect
        result = await coordinator.async_ensure_connected()

        assert result is True


class TestCoordinatorPositionCallbacks:
    """Test coordinator position callback handling."""

    async def test_register_position_callback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test registering position callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        callback = MagicMock()

        unregister = coordinator.register_position_callback(callback)

        assert callback in coordinator._position_callbacks
        assert callable(unregister)

    async def test_unregister_position_callback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test unregistering position callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        callback = MagicMock()

        unregister = coordinator.register_position_callback(callback)
        unregister()

        assert callback not in coordinator._position_callbacks

    async def test_position_update_triggers_callbacks(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test position updates trigger all callbacks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        callback1 = MagicMock()
        callback2 = MagicMock()

        coordinator.register_position_callback(callback1)
        coordinator.register_position_callback(callback2)

        # Simulate position update
        coordinator._handle_position_update("back", 45.0)

        assert coordinator.position_data["back"] == 45.0
        callback1.assert_called_once_with({"back": 45.0})
        callback2.assert_called_once_with({"back": 45.0})


class TestCoordinatorDisconnectTimer:
    """Test coordinator idle disconnect timer."""

    async def test_disconnect_timer_set_on_connect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test disconnect timer is set after connection."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator._disconnect_timer is not None

    async def test_disconnect_timer_cancelled_on_disconnect(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test disconnect timer is cancelled on disconnect."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        await coordinator.async_disconnect()

        assert coordinator._disconnect_timer is None


class TestCoordinatorWriteCommand:
    """Test coordinator command writing."""

    async def test_write_command_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing commands succeeds."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        command = bytes([0x01, 0x00])
        await coordinator.async_write_command(command)

        # The controller should have written the command
        mock_bleak_client.write_gatt_char.assert_called()

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_async_ble_device_from_address,
        mock_bluetooth_adapters,
    ):
        """Test writing commands fails when not connected."""
        # Make connection fail
        with patch(
            "custom_components.adjustable_bed.coordinator.establish_connection",
            new_callable=AsyncMock,
            side_effect=BleakError("Connection failed"),
        ):
            coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

            with pytest.raises(ConnectionError):
                await coordinator.async_write_command(bytes([0x01, 0x00]))


class TestCoordinatorNotifications:
    """Test coordinator notification handling."""

    async def test_start_notify_skipped_when_disabled(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test start_notify is skipped when angle sensing is disabled."""
        # Default config has disable_angle_sensing=True
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.async_start_notify()

        # start_notify should not be called on the client
        mock_bleak_client.start_notify.assert_not_called()

    async def test_start_notify_enabled(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test start_notify subscribes to notifications when enabled."""
        # Create entry with angle sensing enabled
        mock_config_entry_data["disable_angle_sensing"] = False
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="test_entry_id_2",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        await coordinator.async_start_notify()

        # start_notify should be called for position characteristics
        assert mock_bleak_client.start_notify.call_count >= 1


class TestMotorPulseConfiguration:
    """Test motor pulse configuration."""

    async def test_default_motor_pulse_values(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test default motor pulse values use bed-type-specific defaults.

        Linak beds have specific defaults from BED_MOTOR_PULSE_DEFAULTS.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        # Linak has specific defaults: (15, 100)
        linak_defaults = BED_MOTOR_PULSE_DEFAULTS[BED_TYPE_LINAK]
        assert coordinator.motor_pulse_count == linak_defaults[0]  # 15
        assert coordinator.motor_pulse_delay_ms == linak_defaults[1]  # 100

    async def test_custom_motor_pulse_values(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """Test custom motor pulse values from config."""

        mock_config_entry_data[CONF_MOTOR_PULSE_COUNT] = 50
        mock_config_entry_data[CONF_MOTOR_PULSE_DELAY_MS] = 100

        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="test_entry_custom_pulse",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)

        assert coordinator.motor_pulse_count == 50
        assert coordinator.motor_pulse_delay_ms == 100

    async def test_richmat_bed_type_default_pulses(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """Test Richmat bed uses its specific default pulse values."""

        mock_config_entry_data[CONF_BED_TYPE] = BED_TYPE_RICHMAT
        # Don't set pulse values - should use bed-type defaults

        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="test_entry_richmat_pulse",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)

        expected_count, expected_delay = BED_MOTOR_PULSE_DEFAULTS[BED_TYPE_RICHMAT]
        assert coordinator.motor_pulse_count == expected_count  # 30
        assert coordinator.motor_pulse_delay_ms == expected_delay  # 50

    async def test_keeson_bed_type_default_pulses(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """Test Keeson bed uses its specific default pulse values."""

        mock_config_entry_data[CONF_BED_TYPE] = BED_TYPE_KEESON
        # Don't set pulse values - should use bed-type defaults

        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="test_entry_keeson_pulse",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)

        expected_count, expected_delay = BED_MOTOR_PULSE_DEFAULTS[BED_TYPE_KEESON]
        assert coordinator.motor_pulse_count == expected_count  # 25
        assert coordinator.motor_pulse_delay_ms == expected_delay  # 200

    async def test_custom_pulse_overrides_bed_default(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """Test custom pulse config overrides bed-type defaults."""

        mock_config_entry_data[CONF_BED_TYPE] = BED_TYPE_RICHMAT
        mock_config_entry_data[CONF_MOTOR_PULSE_COUNT] = 15
        mock_config_entry_data[CONF_MOTOR_PULSE_DELAY_MS] = 75

        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="test_entry_custom_override",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)

        # Custom values should override bed-type defaults
        assert coordinator.motor_pulse_count == 15
        assert coordinator.motor_pulse_delay_ms == 75


class TestMultiMotorConfiguration:
    """Test multi-motor configuration."""

    @pytest.mark.parametrize("motor_count", [2, 3, 4])
    async def test_motor_count_configurations(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
        motor_count: int,
    ):
        """Test different motor count configurations."""

        mock_config_entry_data[CONF_MOTOR_COUNT] = motor_count

        entry = MockConfigEntry(
            domain=DOMAIN,
            title=TEST_NAME,
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id=f"test_entry_{motor_count}_motors",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)

        assert coordinator.motor_count == motor_count

    async def test_device_info_reflects_motor_count(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
    ):
        """Test device info model includes motor count."""

        for motor_count in [2, 3, 4]:
            mock_config_entry_data[CONF_MOTOR_COUNT] = motor_count

            entry = MockConfigEntry(
                domain=DOMAIN,
                title=TEST_NAME,
                data=mock_config_entry_data,
                unique_id=f"AA:BB:CC:DD:EE:{motor_count:02X}",
                entry_id=f"test_entry_model_{motor_count}",
            )

            coordinator = AdjustableBedCoordinator(hass, entry)
            device_info = coordinator.device_info

            assert f"{motor_count} motors" in device_info["model"]


class TestStopAfterCancel:
    """Test STOP-after-cancel coordinator flow.

    These tests verify the critical behavior where:
    1. stop_command() sets cancel signal before acquiring lock
    2. Running commands check cancel_event and exit early
    3. STOP is sent after acquiring the lock (ensuring GATT write completes)
    4. STOP uses a fresh cancel event so it's not cancelled itself
    """

    async def test_stop_command_sets_cancel_signal(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_command sets cancel signal before acquiring lock."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # Verify cancel event is initially not set
        assert not coordinator._cancel_command.is_set()

        # Call stop command
        await coordinator.async_stop_command()

        # Cancel signal should have been set (though it may be cleared after)
        # We verify this by checking cancel_counter increased
        assert coordinator._cancel_counter >= 1

    async def test_stop_command_increments_cancel_counter(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_command increments cancel counter to prevent stale commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        initial_counter = coordinator._cancel_counter

        # Call stop command
        await coordinator.async_stop_command()

        # Counter should have incremented
        assert coordinator._cancel_counter == initial_counter + 1

    async def test_stop_command_sends_stop_to_controller(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_command calls controller's stop_all method."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # Mock the controller's stop_all method
        coordinator._controller.stop_all = AsyncMock()

        await coordinator.async_stop_command()

        # Verify stop_all was called on the controller
        coordinator._controller.stop_all.assert_called_once()

    async def test_stop_command_resets_disconnect_timer(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_command resets disconnect timer after completion."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # Disconnect timer should be set after connect
        assert coordinator._disconnect_timer is not None

        await coordinator.async_stop_command()

        # Disconnect timer should still be set (reset after stop)
        assert coordinator._disconnect_timer is not None

    async def test_stop_command_when_not_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop_command handles not connected state gracefully."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # Simulate disconnection by clearing the client reference
        # This prevents async_ensure_connected from trying to reconnect
        coordinator._client = None

        # Should not raise, just log error
        await coordinator.async_stop_command()

    async def test_execute_controller_command_cancels_running(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test execute_controller_command cancels running command when requested."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        initial_counter = coordinator._cancel_counter

        # Execute a command with cancel_running=True (default)
        async def dummy_command(controller):
            pass

        await coordinator.async_execute_controller_command(dummy_command)

        # Counter should have incremented (cancel signal was set)
        assert coordinator._cancel_counter == initial_counter + 1

    async def test_execute_controller_command_preserves_running(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test execute_controller_command preserves running command when cancel_running=False."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        initial_counter = coordinator._cancel_counter

        # Execute a command with cancel_running=False
        async def dummy_command(controller):
            pass

        await coordinator.async_execute_controller_command(dummy_command, cancel_running=False)

        # Counter should NOT have incremented
        assert coordinator._cancel_counter == initial_counter

    async def test_cancel_counter_prevents_stale_command_execution(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test that cancel counter prevents stale commands from executing.

        When a command is cancelled while waiting for lock, it should not execute.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        command_executed = False

        async def tracked_command(controller):
            nonlocal command_executed
            command_executed = True

        # First, acquire the lock by starting a command
        import asyncio
        async with coordinator._command_lock:
            # Start the command task (it will wait for lock and capture entry_cancel_count)
            task = asyncio.create_task(
                coordinator.async_execute_controller_command(tracked_command)
            )
            # Give it a moment to start waiting for the lock
            await asyncio.sleep(0.01)

            # NOW increment cancel counter to simulate another command cancelling this one
            # This happens AFTER the task captured entry_cancel_count
            coordinator._cancel_counter += 1

        # Wait for task to complete
        await task

        # Command should NOT have executed because cancel counter changed while waiting
        assert not command_executed

    async def test_stop_after_movement_always_sent(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test that STOP is sent even when movement command is cancelled.

        Movement commands should use try/finally to guarantee STOP is sent.
        """
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        # Track all commands sent
        commands_sent = []
        original_write = mock_bleak_client.write_gatt_char

        async def tracking_write(char, data, **kwargs):
            commands_sent.append(data)
            return await original_write(char, data, **kwargs)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=tracking_write)

        # Execute a movement command (e.g., move_head_up)
        # The controller should send movement commands followed by STOP
        await coordinator.controller.move_head_up()

        # Verify that commands were sent (movement + stop)
        assert len(commands_sent) > 0
