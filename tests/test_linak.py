"""Tests for Linak bed controller."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.linak import (
    LinakCommands,
    LinakPositionSeekPolicy,
)
from custom_components.adjustable_bed.beds.linak_protocol import (
    LinakCapabilitySnapshot,
    LinakModelVariant,
    LinakProfile,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    CONF_PROTOCOL_VARIANT,
    LINAK_CONFIG_CHAR_UUID,
    LINAK_CONTROL_CHAR_UUID,
    LINAK_ERROR_CHAR_UUID,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_FEET_UUID,
    LINAK_POSITION_LEG_UUID,
    LINAK_POSITION_MASK_UUID,
    LINAK_POSITION_SERVICE_UUID,
    LINAK_TIMER_CHAR_UUID,
    LINAK_TIMER_SERVICE_UUID,
    LINAK_VARIANT_PERFORMANCE,
    requires_pairing,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.position_seek import (
    PositionSeekPolicy,
    PositionSeekRunner,
    SeekOutcome,
    SeekResult,
    SeekSample,
)


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


@pytest.fixture(autouse=True)
def mock_advanced_linak_gatt(
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model the default test bed as Advanced with back and legs references."""
    position_service = SimpleNamespace(
        uuid=LINAK_POSITION_SERVICE_UUID,
        characteristics=[],
    )
    mock_bleak_client.services.__iter__ = lambda self: iter([position_service])
    mock_bleak_client.services.__len__ = lambda self: 1
    mock_bleak_client.services.get_service.side_effect = lambda uuid: (
        position_service if str(uuid).lower() == position_service.uuid else None
    )
    original_read = mock_bleak_client.read_gatt_char.side_effect

    async def read(uuid: str) -> bytes:
        if str(uuid).lower() == LINAK_POSITION_MASK_UUID:
            return bytes((0xC0,))
        return await original_read(uuid)

    mock_bleak_client.read_gatt_char.side_effect = read
    monkeypatch.setattr(
        AdjustableBedCoordinator,
        "_async_verify_bonded",
        AsyncMock(return_value=True),
    )


async def _run_position_seek(
    policy: PositionSeekPolicy,
    *,
    initial: float,
    readings: list[float],
) -> tuple[SeekResult, AsyncMock, AsyncMock]:
    """Run a synthetic back-axis seek with the supplied policy."""
    samples = iter(readings)
    issue_step = AsyncMock()
    stop = AsyncMock()
    runner = PositionSeekRunner(
        position_key="back",
        target_angle=0.0,
        policy=policy,
        cancel_event=asyncio.Event(),
        read_position=AsyncMock(side_effect=lambda: next(samples)),
        issue_step=issue_step,
        stop=stop,
    )

    with patch(
        "custom_components.adjustable_bed.position_seek.asyncio.sleep",
        new=AsyncMock(),
    ):
        result = await runner.async_run(initial)

    return result, issue_step, stop


class TestLinakController:
    """Test Linak controller."""

    def test_linak_does_not_require_os_pairing(self) -> None:
        """App-requested bonding must not become a hardware requirement."""
        assert requires_pairing(BED_TYPE_LINAK) is False

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

    async def test_seek_position_step_refreshes_without_intermediate_release(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Each seek step should refresh motion without releasing the motor."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.seek_position_step("legs", True, remaining_distance=25.0)
        await coordinator.controller.seek_position_step("legs", True, remaining_distance=2.0)

        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_LEGS_UP,
            LinakCommands.MOVE_LEGS_UP,
        ]

    async def test_linak_uses_tighter_seek_tolerance(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Linak set-position seeks should finish much closer than the global default."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.position_seek_tolerance == pytest.approx(0.3)

    async def test_downward_seek_releases_early_from_live_speed(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Signed reference speed should compensate for observed downward coast."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._controller_state["linak_back_raw_speed"] = -44
        policy = coordinator.controller.position_seek_policy

        assert policy.accepts_position(
            SeekSample(
                position_key="back",
                target=55.0,
                current=56.4,
                previous=56.8,
                moving_up=False,
                elapsed=2.0,
            )
        )

    async def test_seek_to_flat_does_not_release_early(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A 0° target cannot overshoot its end stop, so coast lead must not apply."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._controller_state["linak_legs_raw_speed"] = -44
        policy = coordinator.controller.position_seek_policy

        assert not policy.accepts_position(
            SeekSample(
                position_key="legs",
                target=0.0,
                current=1.4,
                previous=1.8,
                moving_up=False,
                elapsed=2.0,
            )
        )

    async def test_upward_seek_does_not_apply_downward_coast_lead(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Gravity-sensitive downward compensation must not shorten upward seeks."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        coordinator._controller_state["linak_back_raw_speed"] = 44
        policy = coordinator.controller.position_seek_policy

        assert not policy.accepts_position(
            SeekSample(
                position_key="back",
                target=62.4,
                current=61.0,
                previous=60.6,
                moving_up=True,
                elapsed=2.0,
            )
        )

    async def test_seek_uses_fresh_reference_notifications_without_gatt_read(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Fresh Linak notifications should drive the seek without slow active reads."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        data_without_snapshot = dict(mock_config_entry.data)
        data_without_snapshot.pop("capabilities", None)
        hass.config_entries.async_update_entry(mock_config_entry, data=data_without_snapshot)
        coordinator._handle_position_update("back", 10.0)

        async def finish_step(
            position_key: str,
            moving_up: bool,
            remaining_distance: float | None,
        ) -> None:
            assert (position_key, moving_up, remaining_distance) == ("back", True, 10.0)
            coordinator._handle_position_update("back", 20.0)

        read_positions = AsyncMock()
        with (
            patch.object(
                coordinator.controller,
                "seek_position_step",
                new=AsyncMock(side_effect=finish_step),
            ),
            patch.object(coordinator, "_async_read_positions", new=read_positions),
        ):
            await coordinator.async_seek_position(
                "back",
                20.0,
                lambda controller: controller.move_back_up(),
                lambda controller: controller.move_back_down(),
                lambda controller: controller.move_back_stop(),
            )

        read_positions.assert_not_awaited()
        assert coordinator._seek_outcomes["back"]["outcome"] == "reached_target"

    async def test_seek_falls_back_to_gatt_read_when_notification_is_stale(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A stopped Linak notification stream must retain conservative readback."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        coordinator._handle_position_update("back", 10.0)
        coordinator._position_data_updated_monotonic["back"] = 0.0

        async def refresh_position() -> None:
            coordinator._handle_position_update("back", 20.0)

        read_positions = AsyncMock(side_effect=refresh_position)
        with (
            patch.object(
                coordinator.controller,
                "seek_position_step",
                new=AsyncMock(),
            ),
            patch.object(coordinator, "_async_read_positions", new=read_positions),
        ):
            await coordinator.async_seek_position(
                "back",
                20.0,
                lambda controller: controller.move_back_up(),
                lambda controller: controller.move_back_down(),
                lambda controller: controller.move_back_stop(),
            )

        read_positions.assert_awaited_once_with()
        assert coordinator._seek_outcomes["back"]["outcome"] == "reached_target"

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
        assert coordinator.controller.position_seek_check_interval == pytest.approx(0.1)
        assert coordinator.controller.position_seek_stall_threshold == pytest.approx(0.2)

    async def test_seek_refreshes_continuously_then_releases_once(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """A feedback seek should be one held movement followed by one release."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        coordinator._handle_position_update("back", 10.0)
        mock_bleak_client.write_gatt_char.reset_mock()
        current_angle = 10.0

        async def advance_position(
            _uuid: str,
            command: bytes,
            *,
            response: bool,
        ) -> None:
            nonlocal current_angle
            assert response is True
            if command == LinakCommands.MOVE_BACK_UP:
                current_angle += 1.0
                coordinator._handle_position_update("back", current_angle)

        mock_bleak_client.write_gatt_char.side_effect = advance_position
        with patch(
            "custom_components.adjustable_bed.position_seek.asyncio.sleep",
            new=AsyncMock(),
        ):
            await coordinator.async_seek_position(
                "back",
                13.0,
                lambda controller: controller.move_back_up(),
                lambda controller: controller.move_back_down(),
                lambda controller: controller.move_back_stop(),
            )

        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_BACK_UP,
            LinakCommands.MOVE_BACK_UP,
            LinakCommands.MOVE_BACK_UP,
            LinakCommands.MOVE_STOP,
        ]
        assert coordinator._seek_outcomes["back"]["outcome"] == "reached_target"
        assert mock_config_entry.data["capabilities"]["linak"]["discovery_complete"] is True

    async def test_lower_endpoint_requires_two_stalled_checks_and_releases_motor(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A seek starting near Linak's lower limit should finish after one bounded retry."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        policy = coordinator.controller.position_seek_policy
        assert isinstance(policy, LinakPositionSeekPolicy)

        result, issue_step, stop = await _run_position_seek(
            policy,
            initial=1.1,
            readings=[1.1, 1.1],
        )

        assert result.outcome is SeekOutcome.ENDPOINT_REACHED
        assert result.final_angle == pytest.approx(1.1)
        assert issue_step.await_args_list == [call(False, 1.1), call(False, 1.1)]
        stop.assert_awaited_once_with()

    async def test_movement_to_lower_endpoint_has_one_endpoint_retry(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Progressing to the physical limit should not enter an endpoint write storm."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        result, issue_step, _stop = await _run_position_seek(
            coordinator.controller.position_seek_policy,
            initial=40.0,
            readings=[10.0, 1.1, 1.1, 1.1],
        )

        assert result.outcome is SeekOutcome.ENDPOINT_REACHED
        assert issue_step.await_args_list == [
            call(False, 40.0),
            call(False, 10.0),
            call(False, 1.1),
            call(False, 1.1),
        ]

    async def test_lower_endpoint_rebound_requires_fresh_stall_confirmations(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Movement away and back must invalidate an earlier endpoint stall."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        result, issue_step, _stop = await _run_position_seek(
            coordinator.controller.position_seek_policy,
            initial=1.1,
            readings=[1.1, 0.8, 1.1, 1.1, 1.1],
        )

        assert result.outcome is SeekOutcome.ENDPOINT_REACHED
        assert issue_step.await_args_list == [
            call(False, 1.1),
            call(False, 1.1),
            call(False, 0.8),
            call(False, 1.1),
            call(False, 1.1),
        ]

    async def test_lower_endpoint_policy_retries_mid_range_stall(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A normal mid-range stall must not be promoted to endpoint completion."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        result, issue_step, _stop = await _run_position_seek(
            coordinator.controller.position_seek_policy,
            initial=40.0,
            readings=[15.0, 15.0, 0.2],
        )

        assert result.outcome is SeekOutcome.REACHED_TARGET
        assert issue_step.await_args_list == [
            call(False, 40.0),
            call(False, 15.0),
            call(False, 15.0),
        ]

    async def test_group_continues_after_lower_endpoint_completion(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Endpoint completion should release the grouped request for its next operation."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        coordinator._handle_position_update("back", 1.1)
        coordinator._position_data_updated_monotonic["back"] = 0.0
        mock_bleak_client.write_gatt_char.reset_mock()
        readings = iter([1.1, 1.1])
        events: list[str] = []

        async def read_position() -> None:
            coordinator._handle_position_update("back", next(readings))

        async def next_operation() -> None:
            events.append("legs")

        with (
            patch.object(
                coordinator,
                "_async_read_positions",
                new=AsyncMock(side_effect=read_position),
            ),
            patch(
                "custom_components.adjustable_bed.position_seek.asyncio.sleep",
                new=AsyncMock(),
            ),
        ):
            await coordinator.async_execute_command_group(
                [
                    lambda: coordinator.async_seek_position(
                        "back",
                        0.0,
                        lambda controller: controller.move_back_up(),
                        lambda controller: controller.move_back_down(),
                        lambda controller: controller.move_back_stop(),
                    ),
                    next_operation,
                ],
                resources=["motor:back", "motor:legs"],
            )

        assert events == ["legs"]
        assert coordinator._seek_outcomes["back"]["outcome"] == "endpoint_reached"
        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_BACK_DOWN,
            LinakCommands.MOVE_BACK_DOWN,
            LinakCommands.MOVE_STOP,
        ]

    async def test_stop_during_endpoint_read_prevents_retry_before_stop(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """A STOP arriving during feedback must win before another endpoint write."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        coordinator._handle_position_update("back", 1.1)
        coordinator._position_data_updated_monotonic["back"] = 0.0
        mock_bleak_client.write_gatt_char.reset_mock()
        read_started = asyncio.Event()
        release_read = asyncio.Event()

        async def read_position() -> None:
            read_started.set()
            await release_read.wait()
            coordinator._handle_position_update("back", 1.1)

        with patch.object(
            coordinator,
            "_async_read_positions",
            new=AsyncMock(side_effect=read_position),
        ):
            seek_task = asyncio.create_task(
                coordinator.async_seek_position(
                    "back",
                    0.0,
                    lambda controller: controller.move_back_up(),
                    lambda controller: controller.move_back_down(),
                    lambda controller: controller.move_back_stop(),
                )
            )
            await read_started.wait()
            stop_task = asyncio.create_task(coordinator.async_stop_command())
            await asyncio.sleep(0)
            release_read.set()
            await asyncio.gather(seek_task, stop_task)

        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_BACK_DOWN,
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_STOP,
        ]
        assert coordinator._seek_outcomes["back"]["outcome"] == "cancelled"

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
        ]

        await controller.start_notify(MagicMock())
        assert controller._deferred_position_notifications == {
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
        }

        await controller.write_command(LinakCommands.MOVE_HEAD_UP)

        assert controller._active_position_notifications == {
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
        }
        assert not controller._deferred_position_notifications
        assert mock_bleak_client.start_notify.call_count == 4
        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_HEAD_UP,
        ]

    async def test_protocol_initial_read_timeout_is_best_effort(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """A stalled optional state read must not block integration setup."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        async def stalled_read(_uuid: str) -> bytes:
            await asyncio.Event().wait()
            return b""

        mock_bleak_client.read_gatt_char.side_effect = stalled_read
        handler = MagicMock()
        with patch(
            "custom_components.adjustable_bed.beds.linak.LINAK_PROTOCOL_READ_TIMEOUT_S",
            0.001,
        ):
            await coordinator.controller._read_protocol_characteristic(
                LINAK_ERROR_CHAR_UUID,
                handler,
            )

        handler.assert_not_called()

    async def test_start_notify_subscribes_exact_capability_mask_axes(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Advanced sessions subscribe only to reference outputs selected by mask."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        mock_bleak_client.start_notify.reset_mock()

        await controller.start_notify(MagicMock())

        subscribed_uuids = [call.args[0] for call in mock_bleak_client.start_notify.call_args_list]
        assert subscribed_uuids == [
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
        ]


class TestLinakCorpusProfiles:
    """Model the complete service-derived and explicit application profiles."""

    async def test_standard_has_no_memories_or_position_feedback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        mock_bleak_client.services.__iter__ = lambda self: iter(())
        mock_bleak_client.services.__len__ = lambda self: 0
        mock_bleak_client.services.get_service = MagicMock(return_value=None)
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        await coordinator.async_connect()

        assert coordinator.controller.protocol_diagnostics["model_variant"] == "standard"
        assert coordinator.controller.memory_slot_count == 0
        assert coordinator.controller.supports_position_feedback is False
        assert coordinator.controller.passive_position_reconciliation_interval is None

    async def test_capability_mask_retries_after_cold_session_auth_window(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """A cold mask read should defer without blocking setup, then retry on control."""
        original_read = mock_bleak_client.read_gatt_char.side_effect
        mask_attempts = 0
        auth_error = BleakError(
            "Bluetooth GATT Error address=CB:3D:68:A7:7B:D0 handle=14 "
            "error=5 description=Insufficient authentication"
        )

        async def read(uuid: str) -> bytes:
            nonlocal mask_attempts
            if str(uuid).lower() == LINAK_POSITION_MASK_UUID:
                mask_attempts += 1
                if mask_attempts == 1:
                    raise auth_error
                return b"\xc0"
            return await original_read(uuid)

        mock_bleak_client.read_gatt_char.side_effect = read
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        await coordinator.async_connect()
        assert mask_attempts == 1
        assert coordinator.controller._capability_discovery_deferred is True
        assert _written_commands(mock_bleak_client) == []

        await coordinator.async_execute_controller_command(
            lambda controller: controller.write_command(LinakCommands.MOVE_HEAD_UP)
        )

        assert mask_attempts == 2
        assert coordinator.controller.protocol_diagnostics["model_variant"] == "advanced"
        assert coordinator.controller.supports_position_feedback is True
        assert coordinator.controller.passive_position_reconciliation_interval == pytest.approx(
            120.0
        )
        assert mock_config_entry.data["capabilities"]["linak"]["actuator_mask"] == 0xC0
        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_HEAD_UP,
        ]

    async def test_direct_ble_factory_reset_uses_configuration_characteristic(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Preserve Bed Connect's reachable BLE-only factory-reset action."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.factory_reset()

        assert mock_bleak_client.write_gatt_char.await_args_list == [
            call(LINAK_CONTROL_CHAR_UUID, LinakCommands.MOVE_STOP, response=True),
            call(LINAK_CONFIG_CHAR_UUID, LinakCommands.FACTORY_RESET, response=True),
        ]

    async def test_td3_mask_zero_keeps_four_memories_without_reference_axes(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        original_read = mock_bleak_client.read_gatt_char.side_effect

        async def read(uuid: str) -> bytes:
            if str(uuid).lower() == LINAK_POSITION_MASK_UUID:
                return b"\x00"
            return await original_read(uuid)

        mock_bleak_client.read_gatt_char.side_effect = read
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        await coordinator.async_connect()

        assert coordinator.controller.protocol_diagnostics["model_variant"] == "td3"
        assert coordinator.controller.memory_slot_count == 4
        assert coordinator.controller.supports_position_feedback is False
        assert coordinator.controller.passive_position_reconciliation_interval is None

    async def test_timer_service_promotes_advanced_model_only_after_subscription(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        position_service = SimpleNamespace(
            uuid=LINAK_POSITION_SERVICE_UUID,
            characteristics=[],
        )
        timer_service = SimpleNamespace(uuid=LINAK_TIMER_SERVICE_UUID, characteristics=[])
        mock_bleak_client.services.__iter__ = lambda self: iter((position_service, timer_service))
        mock_bleak_client.services.__len__ = lambda self: 2
        mock_bleak_client.services.get_service = MagicMock(
            side_effect=lambda uuid: {
                LINAK_POSITION_SERVICE_UUID: position_service,
                LINAK_TIMER_SERVICE_UUID: timer_service,
            }.get(str(uuid).lower())
        )
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)

        await coordinator.async_connect()

        diagnostics = coordinator.controller.protocol_diagnostics
        assert diagnostics["model_variant"] == "advanced_with_alarm"
        assert diagnostics["timer_supported"] is True
        assert coordinator.controller.supports_alarm is True

    async def test_timer_notification_retries_after_cold_session_auth_window(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        """A cold authenticated timer channel must still promote alarm support."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        controller._timer_candidate = True
        controller._session_ready = False
        controller._protocol_notification_uuids.clear()
        controller._deferred_protocol_notifications.clear()
        mock_bleak_client.start_notify.reset_mock()
        mock_bleak_client.write_gatt_char.reset_mock()

        timer_attempts = 0
        auth_error = BleakError(
            "Bluetooth GATT Error address=CB:3D:68:A7:7B:D0 handle=14 "
            "error=5 description=Insufficient authentication"
        )

        async def start_notify(uuid: str, _handler: object) -> None:
            nonlocal timer_attempts
            if uuid == LINAK_TIMER_CHAR_UUID:
                timer_attempts += 1
                if timer_attempts == 1:
                    raise auth_error

        with patch.object(
            controller,
            "_read_protocol_characteristic",
            new=AsyncMock(),
        ):
            mock_bleak_client.start_notify.side_effect = start_notify
            await controller.start_notify(None)

            assert timer_attempts == 1
            assert LINAK_TIMER_CHAR_UUID in controller._deferred_protocol_notifications
            assert _written_commands(mock_bleak_client) == []

            await coordinator.async_execute_controller_command(
                lambda live_controller: live_controller.write_command(LinakCommands.MOVE_HEAD_UP)
            )

        assert timer_attempts == 2
        assert LINAK_TIMER_CHAR_UUID in controller._protocol_notification_uuids
        assert not controller._deferred_protocol_notifications
        assert controller.supports_alarm is True
        assert controller.protocol_diagnostics["model_variant"] == "advanced_with_alarm"
        assert mock_config_entry.data["capabilities"]["linak"]["timer_supported"] is True
        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_STOP,
            LinakCommands.MOVE_HEAD_UP,
        ]

    async def test_performance_profile_uses_300ms_holds_and_one_byte_release(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        hass.config_entries.async_update_entry(
            mock_config_entry,
            data={
                **mock_config_entry.data,
                CONF_PROTOCOL_VARIANT: LINAK_VARIANT_PERFORMANCE,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)
        mock_bleak_client.write_gatt_char.reset_mock()

        with patch(
            "custom_components.adjustable_bed.beds.base.asyncio.sleep",
            new=AsyncMock(),
        ):
            await coordinator.controller.move_back_up()

        assert coordinator.controller.protocol_diagnostics["profile"] == "performance_legacy"
        assert coordinator.controller.memory_slot_count == 4
        assert coordinator.controller.supports_position_feedback is False
        assert coordinator.controller.passive_position_reconciliation_interval is None
        assert coordinator.controller.supports_impulse_control is True
        assert coordinator.controller.supports_wake_control is False
        assert coordinator.controller.supports_factory_reset is False
        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MOVE_BACK_UP,
            LinakCommands.MOVE_BACK_UP,
            LinakCommands.MOVE_BACK_UP,
            LinakCommands.MOVE_BACK_UP,
            b"\xff",
        ]

    async def test_performance_notification_is_required_but_not_interpreted(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ) -> None:
        hass.config_entries.async_update_entry(
            mock_config_entry,
            data={
                **mock_config_entry.data,
                CONF_PROTOCOL_VARIANT: LINAK_VARIANT_PERFORMANCE,
            },
        )
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        notify_call = next(
            item
            for item in mock_bleak_client.start_notify.call_args_list
            if item.args[0] == LINAK_ERROR_CHAR_UUID
        )
        state_before = dict(coordinator.controller_state)
        notify_call.args[1](LINAK_ERROR_CHAR_UUID, bytearray.fromhex("01 00 0D AA"))

        assert coordinator.controller_state == state_before
        assert "linak_protocol_error" not in {
            spec.key for spec in coordinator.controller.controller_state_sensor_specs
        }


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

    async def test_linak_uses_explicit_stop_release(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Linak's proven release frame must not be treated as idle-only stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.auto_stops_on_idle is False

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends a repeated burst followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.move_head_up()

        assert _written_commands(mock_bleak_client) == [
            *([LinakCommands.MOVE_HEAD_UP] * coordinator.motor_pulse_count),
            LinakCommands.MOVE_STOP,
        ]

    async def test_move_legs_down(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move legs down sends a repeated burst followed by STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        await coordinator.controller.move_legs_down()

        assert _written_commands(mock_bleak_client) == [
            *([LinakCommands.MOVE_LEGS_DOWN] * coordinator.motor_pulse_count),
            LinakCommands.MOVE_STOP,
        ]

    async def test_move_cleanup_releases_after_failed_movement_write(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """A failed movement burst must still attempt the Linak release frame."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        write_command = AsyncMock(side_effect=[BleakError("movement failed"), None])

        with (
            patch.object(coordinator.controller, "write_command", new=write_command),
            pytest.raises(BleakError, match="movement failed"),
        ):
            await coordinator.controller.move_head_up()

        assert write_command.await_count == 2
        assert write_command.await_args_list[0] == call(
            LinakCommands.MOVE_HEAD_UP,
            repeat_count=coordinator.motor_pulse_count,
            repeat_delay_ms=coordinator.motor_pulse_delay_ms,
        )
        assert write_command.await_args_list[1].args == (LinakCommands.MOVE_STOP,)
        assert isinstance(write_command.await_args_list[1].kwargs["cancel_event"], asyncio.Event)

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

        with patch(
            "custom_components.adjustable_bed.beds.base.asyncio.sleep",
            new=AsyncMock(),
        ):
            await coordinator.controller.preset_memory(memory_num)

        assert _written_commands(mock_bleak_client) == [
            *([expected_command] * 300),
            LinakCommands.MOVE_STOP,
        ]

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

    async def test_discrete_lights_are_not_exposed(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """The analyzed apps expose AUX toggle, not guessed on/off commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        _mark_session_ready(coordinator)

        assert coordinator.controller.supports_discrete_light_control is False
        with pytest.raises(NotImplementedError):
            await coordinator.controller.lights_on()
        with pytest.raises(NotImplementedError):
            await coordinator.controller.lights_off()
        mock_bleak_client.write_gatt_char.assert_not_called()

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

        with patch(
            "custom_components.adjustable_bed.beds.linak.asyncio.sleep",
            new=AsyncMock(),
        ):
            await coordinator.controller.massage_toggle()

        assert _written_commands(mock_bleak_client) == [
            LinakCommands.MASSAGE_ZONE_1_ON,
            LinakCommands.MASSAGE_ZONE_2_ON,
        ]


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
                return bytes([0x12, 0x01, 0x00, 0x00])  # 274 / 548 = 22.5°
            return b""

        mock_bleak_client.read_gatt_char.side_effect = read_side_effect

        await controller.read_positions()

        callback.assert_called_once_with("legs", 22.5)

    async def test_read_positions_uses_feet_axis_selected_by_mask(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Reference reads follow the capability mask rather than motor count."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        controller._capabilities = LinakCapabilitySnapshot(
            profile=LinakProfile.BED_CONTROL,
            model_variant=LinakModelVariant.ADVANCED,
            actuator_mask=0x90,
            discovery_complete=True,
        )
        callback = MagicMock()
        controller._notify_callback = callback

        async def read_side_effect(uuid: str) -> bytes:
            if uuid == LINAK_POSITION_BACK_UUID:
                return bytes([0x9A, 0x01, 0x00, 0x00])  # 410 / 820 = 34.0°
            if uuid == LINAK_POSITION_FEET_UUID:
                return bytes([0x12, 0x01, 0x00, 0x00])  # 274 / 548 = 22.5°
            return b""

        mock_bleak_client.read_gatt_char.side_effect = read_side_effect

        await controller.read_positions()

        assert callback.call_args_list == [call("back", 34.0), call("feet", 22.5)]

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

    async def test_read_positions_skips_cold_retry_once_session_is_ready(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Ready Linak sessions should not spend time on cold-start read retries."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        controller._session_ready = True

        with (
            patch.object(
                controller,
                "_read_positions_once",
                new=AsyncMock(return_value={"back"}),
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
        data = bytearray([0x9A, 0x01, 0x00, 0x00])  # 410 in little-endian

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
        data = bytearray([0x34, 0x03, 0x00, 0x00])  # 820 in little-endian

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

        data = bytearray([0x00, 0x00, 0x00, 0x00])

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
        assert coordinator.controller_state["linak_back_reported_speed"] == 0
        assert coordinator.controller_state["linak_back_status_flags"] == 0
        assert coordinator.controller_state["linak_position_feedback_fault"] is False

    async def test_extension_just_below_zero_decodes_as_flat(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        """Live beds report 0xFFFE/0xFFFF when resting below the learned zero."""
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller

        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_position_data("back", bytearray.fromhex("FE FF 00 00"), 820, 68.0)
        controller._handle_position_data("back", bytearray.fromhex("FF FF 00 00"), 820, 68.0)
        assert callback.call_args_list == [call("back", 0.0), call("back", 0.0)]

        # Values outside the observed -1/-2 range are still garbage, not a
        # resting position.
        callback.reset_mock()
        controller._handle_position_data("back", bytearray.fromhex("FD FF 00 00"), 820, 68.0)
        callback.assert_not_called()

    async def test_reference_notification_publishes_speed_and_every_status_flag(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
        await coordinator.async_connect()

        coordinator.controller._handle_position_data(
            "back",
            bytearray.fromhex("D2 04 A5 00"),
            820,
            68.0,
        )

        state = coordinator.controller_state
        assert state["linak_back_reported_speed"] == pytest.approx(0.9765625)
        assert state["linak_back_raw_speed"] == 10
        assert state["linak_back_speed_direction"] == "positive"
        assert state["linak_back_extension"] == pytest.approx(12.34)
        assert state["linak_back_status_flags"] == 5
        assert state["linak_back_sls"] is True
        assert state["linak_back_end_position_up"] is False
        assert state["linak_back_end_position_down"] is True
        assert state["linak_back_position_lost"] is False
