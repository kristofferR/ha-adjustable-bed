"""Tests for Linak bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.linak import LinakCommands
from custom_components.adjustable_bed.const import (
    LINAK_CONTROL_CHAR_UUID,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_FEET_UUID,
    LINAK_POSITION_HEAD_UUID,
    LINAK_POSITION_LEG_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _written_commands(mock_bleak_client: MagicMock) -> list[bytes]:
    """Return the payload bytes written to the Linak control characteristic."""
    return [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]


def _assert_repeated_command(
    mock_bleak_client: MagicMock, command: bytes, repeat_count: int
) -> None:
    """Assert the control characteristic only receives the expected command bytes."""
    assert _written_commands(mock_bleak_client) == [command] * repeat_count


def _mark_session_ready(coordinator: AdjustableBedCoordinator) -> None:
    """Skip the cold-connect readiness probe for command behavior tests."""
    coordinator.controller._session_ready = True


class TestLinakController:
    """Test Linak controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == LINAK_CONTROL_CHAR_UUID

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        command = LinakCommands.MOVE_STOP
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, command, response=True
        )

    async def test_write_command_with_repeat(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command with repeat count."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        command = LinakCommands.MOVE_HEAD_UP
        await coordinator.controller.write_command(command, repeat_count=3, repeat_delay_ms=50)

        _assert_repeated_command(mock_bleak_client, command, repeat_count=3)

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        # Simulate disconnection
        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(LinakCommands.MOVE_STOP)

    async def test_write_command_bleak_error(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command handles BleakError."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        mock_bleak_client.write_gatt_char.side_effect = BleakError("Write failed")

        with pytest.raises(BleakError):
            await coordinator.controller.write_command(LinakCommands.MOVE_STOP)

    async def test_write_command_waits_out_cold_connect_auth_window(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Linak should retry a safe STOP until the fresh session accepts writes."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        auth_error = BleakError(
            "Bluetooth GATT Error address=CB:3D:68:A7:7B:D0 handle=14 error=5 description=Insufficient authentication"
        )
        mock_bleak_client.write_gatt_char.side_effect = [
            auth_error,
            auth_error,
            None,
            None,
            None,
            None,
        ]

        with patch(
            "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
            new=AsyncMock(),
        ) as mock_sleep:
            await coordinator.controller.write_command(
                LinakCommands.MOVE_HEAD_UP,
                repeat_count=3,
                repeat_delay_ms=50,
            )

        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_HEAD_UP,
            LinakCommands.MOVE_HEAD_UP,
            LinakCommands.MOVE_HEAD_UP,
        ]
        assert mock_sleep.await_count >= 2

    async def test_write_command_reuses_ready_session_without_extra_probe(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """After the first accepted write, later commands should skip the readiness probe."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.write_command(LinakCommands.MOVE_HEAD_UP)
        await coordinator.controller.write_command(LinakCommands.MOVE_HEAD_DOWN)

        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_HEAD_UP,
            LinakCommands.MOVE_HEAD_DOWN,
        ]

    async def test_seek_position_step_uses_adaptive_far_pulse(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Linak seeking should use larger pulses when still far from target."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.seek_position_step("legs", True, remaining_distance=25.0)

        _assert_repeated_command(mock_bleak_client, LinakCommands.MOVE_LEGS_UP, repeat_count=6)

    async def test_seek_position_step_uses_micro_pulse_near_target(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Linak seeking should still use tiny pulses near the target for accuracy."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.seek_position_step("legs", True, remaining_distance=2.0)

        _assert_repeated_command(mock_bleak_client, LinakCommands.MOVE_LEGS_UP, repeat_count=1)

    async def test_linak_uses_tighter_seek_tolerance(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Linak set-position seeks should finish much closer than the global default."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.position_seek_tolerance == pytest.approx(0.75)

    async def test_linak_reissues_seek_after_first_stalled_read(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Linak should chain short pulses without the generic multi-read pause."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.position_seek_stall_count == 1
        assert coordinator.controller.position_seek_check_interval == pytest.approx(0.2)
        assert coordinator.controller.position_seek_stall_threshold == pytest.approx(0.2)

    async def test_prepare_for_position_read_waits_for_ready_session(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Linak position reads should wait for the cold-session auth window."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        with patch.object(
            coordinator.controller,
            "_await_control_ready",
            new=AsyncMock(),
        ) as mock_ready:
            await coordinator.controller.prepare_for_position_read()

        mock_ready.assert_awaited_once_with()

    async def test_passive_position_reconciliation_interval_is_enabled(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Linak should request low-frequency reconciliation for external remote moves."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.passive_position_reconciliation_interval == pytest.approx(
            120.0
        )

    async def test_write_command_retries_deferred_position_notifications_after_readiness(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Deferred cold-connect position notifications should recover on first command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        controller._active_position_notifications.clear()
        controller._deferred_position_notifications.clear()
        mock_bleak_client.start_notify.reset_mock()
        mock_bleak_client.write_gatt_char.reset_mock()

        auth_error = BleakError(
            "Bluetooth GATT Error address=CB:3D:68:A7:7B:D0 handle=14 error=5 description=Insufficient authentication"
        )
        mock_bleak_client.start_notify.side_effect = [
            auth_error,
            auth_error,
            None,
            None,
            None,
            None,
        ]

        await controller.start_notify(MagicMock())
        assert controller._deferred_position_notifications == {
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
        }

        await controller.write_command(LinakCommands.MOVE_HEAD_UP)

        assert controller._active_position_notifications == {
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_FEET_UUID,
            LINAK_POSITION_HEAD_UUID,
            LINAK_POSITION_LEG_UUID,
        }
        assert not controller._deferred_position_notifications
        assert mock_bleak_client.start_notify.call_count == 6
        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_HEAD_UP,
        ]

    async def test_start_notify_subscribes_all_two_motor_secondary_candidates(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Fresh 2-motor sessions should listen on all plausible second-axis channels."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        mock_bleak_client.start_notify.reset_mock()

        await controller.start_notify(MagicMock())

        subscribed_uuids = [call.args[0] for call in mock_bleak_client.start_notify.call_args_list]
        assert subscribed_uuids == [
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
            LINAK_POSITION_FEET_UUID,
            LINAK_POSITION_HEAD_UUID,
        ]


class TestLinakMovement:
    """Test Linak movement commands."""

    async def test_disables_polling_during_commands(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Linak should disable movement-time polling to avoid pulse interruption."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.allow_position_polling_during_commands is False

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends repeated commands (Linak auto-stops when commands stop)."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.move_head_up()

        _assert_repeated_command(mock_bleak_client, LinakCommands.MOVE_HEAD_UP, 15)

    async def test_move_legs_down(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs down sends repeated commands (Linak auto-stops when commands stop)."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.move_legs_down()

        _assert_repeated_command(mock_bleak_client, LinakCommands.MOVE_LEGS_DOWN, 15)

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends stop command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.stop_all()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.MOVE_STOP, response=True
        )


class TestLinakPresets:
    """Test Linak preset commands."""

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LinakCommands.PRESET_MEMORY_1),
            (2, LinakCommands.PRESET_MEMORY_2),
            (3, LinakCommands.PRESET_MEMORY_3),
            (4, LinakCommands.PRESET_MEMORY_4),
        ],
    )
    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.preset_memory(memory_num)

        _assert_repeated_command(mock_bleak_client, expected_command, 1)

    async def test_preset_memory_waits_for_active_recent_preset_handoff(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A replacement preset should wait for active motion to settle first."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        coordinator.controller._last_preset_command_monotonic = 100.0

        with (
            patch(
                "custom_components.adjustable_bed.beds.linak.monotonic",
                side_effect=[101.0, 101.2],
            ),
            patch.object(
                coordinator.controller,
                "_await_active_preset_handoff",
                new=AsyncMock(),
            ) as handoff_mock,
            patch.object(
                coordinator.controller,
                "_retry_handoff_preset_if_no_feedback",
                new=AsyncMock(),
            ) as retry_mock,
        ):
            handoff_mock.return_value = True
            await coordinator.controller.preset_memory(1)

        _assert_repeated_command(mock_bleak_client, LinakCommands.PRESET_MEMORY_1, 1)
        handoff_mock.assert_awaited_once_with(1, pytest.approx(1.0))
        retry_mock.assert_awaited_once()
        assert (
            coordinator.controller._last_preset_command_monotonic
            == pytest.approx(101.2)
        )

    async def test_preset_memory_skips_handoff_wait_after_window(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Idle presets should still send only the preset command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        coordinator.controller._last_preset_command_monotonic = 100.0

        with (
            patch(
                "custom_components.adjustable_bed.beds.linak.monotonic",
                side_effect=[116.0, 116.1],
            ),
            patch.object(
                coordinator.controller,
                "_await_active_preset_handoff",
                new=AsyncMock(),
            ) as handoff_mock,
            patch.object(
                coordinator.controller,
                "_retry_handoff_preset_if_no_feedback",
                new=AsyncMock(),
            ) as retry_mock,
        ):
            await coordinator.controller.preset_memory(1)

        _assert_repeated_command(mock_bleak_client, LinakCommands.PRESET_MEMORY_1, 1)
        handoff_mock.assert_not_awaited()
        retry_mock.assert_not_awaited()

    async def test_active_preset_handoff_waits_until_position_settles(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """A recent active preset should wait until position updates go quiet."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        with (
            patch(
                "custom_components.adjustable_bed.beds.linak.monotonic",
                side_effect=[200.0, 200.25, 200.5, 200.75],
            ),
            patch(
                "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep_mock,
            patch.object(
                coordinator,
                "position_changed_recently",
                side_effect=[True, True, False],
            ) as recent_mock,
        ):
            await coordinator.controller._await_active_preset_handoff(1, 1.0)

        assert recent_mock.call_count == 3
        assert sleep_mock.await_count == 2

    async def test_handoff_retry_resends_preset_without_new_feedback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A queued preset handoff should retry once if the first resend is ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        coordinator._position_update_sequence = 10
        with patch(
            "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
            new=AsyncMock(),
        ):
            await coordinator.controller._retry_handoff_preset_if_no_feedback(
                1,
                LinakCommands.PRESET_MEMORY_1,
                10,
            )

        _assert_repeated_command(mock_bleak_client, LinakCommands.PRESET_MEMORY_1, 1)

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, LinakCommands.PROGRAM_MEMORY_1),
            (2, LinakCommands.PROGRAM_MEMORY_2),
            (3, LinakCommands.PROGRAM_MEMORY_3),
            (4, LinakCommands.PROGRAM_MEMORY_4),
        ],
    )
    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.program_memory(memory_num)

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, expected_command, response=True
        )


class TestLinakLights:
    """Test Linak light commands."""

    async def test_lights_on(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights on command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.lights_on()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.LIGHTS_ON, response=True
        )

    async def test_lights_off(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.lights_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.LIGHTS_OFF, response=True
        )

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.lights_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.LIGHTS_TOGGLE, response=True
        )


class TestLinakMassage:
    """Test Linak massage commands."""

    async def test_massage_off(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage off command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.massage_off()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.MASSAGE_ALL_OFF, response=True
        )

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test massage toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.massage_toggle()

        mock_bleak_client.write_gatt_char.assert_called_with(
            LINAK_CONTROL_CHAR_UUID, LinakCommands.MASSAGE_ALL_TOGGLE, response=True
        )


class TestLinakPositionData:
    """Test Linak position data handling."""

    async def test_read_positions_continues_after_single_timeout(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A hung Linak characteristic should not block other position reads."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        callback = MagicMock()
        controller._notify_callback = callback

        async def read_side_effect(uuid: str) -> bytes:
            if uuid == LINAK_POSITION_BACK_UUID:
                raise TimeoutError
            if uuid == LINAK_POSITION_LEG_UUID:
                return bytes([0x12, 0x01])  # 274 / 548 = 22.5°
            return b""

        mock_bleak_client.read_gatt_char.side_effect = read_side_effect

        await controller.read_positions()

        callback.assert_called_once_with("legs", 22.5)

    async def test_read_positions_resolves_two_motor_secondary_axis_from_feet_channel(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A 2-motor Linak bed should fall back to the reporting second actuator."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        callback = MagicMock()
        controller._notify_callback = callback

        async def read_side_effect(uuid: str) -> bytes:
            if uuid == LINAK_POSITION_BACK_UUID:
                return bytes([0x9A, 0x01])  # 410 / 820 = 34.0°
            if uuid == LINAK_POSITION_LEG_UUID:
                return bytes([0xFF, 0xFF])  # invalid
            if uuid == LINAK_POSITION_FEET_UUID:
                return bytes([0x12, 0x01])  # 274 / 548 = 22.5°
            return b""

        mock_bleak_client.read_gatt_char.side_effect = read_side_effect

        await controller.read_positions()

        assert callback.call_args_list == [call("back", 34.0), call("legs", 22.5)]
        assert controller._resolved_two_motor_secondary_spec is not None
        assert controller._resolved_two_motor_secondary_spec.source_name == "feet"

    async def test_read_positions_keeps_default_primary_axis_on_invalid_back_sample(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A transient invalid back sample should not rebind the primary 2-motor axis."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        callback = MagicMock()
        controller._notify_callback = callback

        back_reads = 0

        async def read_side_effect(uuid: str) -> bytes:
            nonlocal back_reads
            if uuid == LINAK_POSITION_BACK_UUID:
                back_reads += 1
                if back_reads == 1:
                    return bytes([0xFF, 0xFF])  # transient invalid
                return bytes([0x9A, 0x01])  # 410 / 820 = 34.0°
            if uuid == LINAK_POSITION_LEG_UUID:
                return bytes([0x12, 0x01])  # 274 / 548 = 22.5°
            return b""

        mock_bleak_client.read_gatt_char.side_effect = read_side_effect

        await controller.read_positions()
        await controller.read_positions()

        assert callback.call_args_list[0] == call("legs", 22.5)
        assert call("back", 34.0) in callback.call_args_list
        assert LINAK_POSITION_HEAD_UUID not in [
            call_args.args[0]
            for call_args in mock_bleak_client.read_gatt_char.await_args_list
        ]

    async def test_read_positions_retries_cold_session_until_data_arrives(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Cold Linak reads should retry briefly when the session has not settled yet."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        controller._deferred_position_notifications = {LINAK_POSITION_BACK_UUID}

        with (
            patch.object(
                controller,
                "_read_positions_once",
                new=AsyncMock(side_effect=[{"back"}, {"back", "legs"}]),
            ) as mock_read_positions_once,
            patch.object(
                controller,
                "_ensure_position_notifications_started",
                new=AsyncMock(),
            ) as mock_ensure_notifications,
            patch(
                "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep,
        ):
            await controller.read_positions()

        assert mock_read_positions_once.await_count == 2
        mock_sleep.assert_awaited_once()
        mock_ensure_notifications.assert_awaited_once()

    async def test_read_positions_retries_missing_axes_once_when_session_is_ready(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Ready Linak sessions should retry once if a logical axis is missing."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        controller._session_ready = True

        with (
            patch.object(
                controller,
                "_read_positions_once",
                new=AsyncMock(side_effect=[{"back"}, {"back", "legs"}]),
            ) as mock_read_positions_once,
            patch(
                "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep,
        ):
            await controller.read_positions()

        assert mock_read_positions_once.await_count == 2
        mock_sleep.assert_awaited_once()

    async def test_read_positions_skips_retry_when_ready_session_has_all_axes(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Ready Linak sessions should not retry when all expected axes are already present."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        controller._session_ready = True

        with (
            patch.object(
                controller,
                "_read_positions_once",
                new=AsyncMock(return_value={"back", "legs"}),
            ) as mock_read_positions_once,
            patch(
                "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
                new=AsyncMock(),
            ) as mock_sleep,
        ):
            await controller.read_positions()

        mock_read_positions_once.assert_awaited_once()
        mock_sleep.assert_not_awaited()

    async def test_handle_position_data(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test position data handling."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Simulate position data: 410 out of 820 max = 50% = 34 degrees
        data = bytearray([0x9A, 0x01])  # 410 in little-endian

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_called_once_with("back", 34.0)

    async def test_handle_position_data_max(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test position data at maximum."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Max position
        data = bytearray([0x34, 0x03])  # 820 in little-endian

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_called_once_with("back", 68.0)

    async def test_handle_position_data_zero(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test position data at zero."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        data = bytearray([0x00, 0x00])

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_called_once_with("back", 0.0)

    async def test_handle_position_data_invalid(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test invalid position data is ignored."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller

        # Too short data
        data = bytearray([0x00])

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", data, 820, 68.0)

        callback.assert_not_called()
