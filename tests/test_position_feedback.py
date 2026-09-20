"""Coordinator feedback provenance and freshness at the movement boundary."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.command_scheduler import CommandOutcome
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.position_seek import PositionFeedbackError, PositionSeekPolicy

from .conftest import make_controller_mock


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    coordinator._client = MagicMock(is_connected=True)
    coordinator._position_connection_generation = 1
    coordinator._controller = make_controller_mock(
        supports_direct_position_control=False,
        auto_stops_on_idle=False,
        position_seek_check_interval=0,
    )
    return coordinator


@pytest.mark.parametrize("failure", [TimeoutError(), RuntimeError("read failed"), None])
async def test_feedback_loss_stops_before_reporting_failure(coordinator, failure):
    """A failed or empty read cannot trigger extra movement from the old cache."""
    reads = 0

    async def read(_motor_count):
        nonlocal reads
        reads += 1
        if reads == 1:
            coordinator._handle_position_update("back", 20.0)
        elif failure:
            raise failure

    coordinator.controller.read_positions = AsyncMock(side_effect=read)
    up, down, stop = AsyncMock(), AsyncMock(), AsyncMock()
    with pytest.raises(PositionFeedbackError, match="Lost fresh position feedback"):
        await coordinator.async_seek_position("back", 40, up, down, stop)

    up.assert_awaited_once()
    down.assert_not_awaited()
    stop.assert_awaited_once()
    assert coordinator.position_data["back"] == 20  # Last known display state survives.
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.outcome is CommandOutcome.FAILED


@pytest.mark.parametrize("cached_angle", [20, 40])
async def test_stale_initial_feedback_cannot_choose_direction_or_skip(coordinator, cached_angle):
    coordinator._handle_position_update("back", cached_angle)
    coordinator._position_data_updated_monotonic["back"] -= 60
    coordinator.controller.read_positions = AsyncMock(side_effect=TimeoutError)
    up, down, stop = AsyncMock(), AsyncMock(), AsyncMock()

    with pytest.raises(PositionFeedbackError, match="no fresh position feedback"):
        await coordinator.async_seek_position("back", 40, up, down, stop)

    up.assert_not_awaited()
    down.assert_not_awaited()
    stop.assert_not_awaited()  # Nothing started.


@pytest.mark.parametrize("direct", [False, True])
async def test_cancel_interrupts_initial_read_without_starting_movement(coordinator, direct):
    started = asyncio.Event()
    finished = asyncio.Event()

    async def read(_count):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    controller = coordinator.controller
    controller.supports_direct_position_control = direct
    controller.set_motor_position = AsyncMock()
    controller.read_positions = AsyncMock(side_effect=read)
    move = AsyncMock()
    seek = asyncio.create_task(coordinator.async_seek_position("back", 40, move, move, move))
    try:
        async with asyncio.timeout(1):
            await started.wait()
            coordinator.request_command_cancel()
            await seek
    finally:
        if not seek.done():
            seek.cancel()
            await asyncio.gather(seek, return_exceptions=True)
    assert finished.is_set()
    controller.set_motor_position.assert_not_awaited()
    move.assert_not_awaited()
    assert coordinator._seek_outcomes["back"]["outcome"] == "cancelled"


@pytest.mark.parametrize("axis, expected", [("legs", None), ("back", 20.0)])
async def test_read_must_refresh_requested_axis_even_if_unchanged(coordinator, axis, expected):
    coordinator._handle_position_update("back", 20.0)
    coordinator.controller.read_positions = AsyncMock(
        side_effect=lambda _count: coordinator._handle_position_update(axis, 20.0)
    )
    assert await coordinator._async_read_seek_position(
        "back", coordinator.controller.position_seek_policy
    ) == expected


async def test_new_notification_survives_failed_active_read(coordinator):
    async def read(_count):
        coordinator._handle_position_update("back", 20.0)
        raise TimeoutError

    coordinator.controller.read_positions = AsyncMock(side_effect=read)
    assert await coordinator._async_read_seek_position(
        "back", coordinator.controller.position_seek_policy
    ) == 20


class NotificationPolicy(PositionSeekPolicy):
    @property
    def prefers_cached_position_feedback(self) -> bool:
        return True

    @property
    def cached_position_feedback_max_age(self) -> float:
        return 1.0


async def test_notification_that_ages_out_during_read_is_rejected(coordinator):
    now = 10.0

    async def read(_count):
        nonlocal now
        coordinator._handle_position_update("back", 20)
        now += 2.0  # A read of another characteristic stalls before failing.
        raise TimeoutError

    coordinator.controller.read_positions = AsyncMock(side_effect=read)
    with patch(
        "custom_components.adjustable_bed.coordinator.time",
        SimpleNamespace(monotonic=lambda: now),
    ):
        assert await coordinator._async_read_seek_position(
            "back", NotificationPolicy(coordinator.controller)
        ) is None


@pytest.mark.parametrize("age, generation, expected", [(0.1, 1, 20), (2, 1, None), (0.1, 0, None)])
async def test_cached_notifications_require_age_and_session(coordinator, age, generation, expected):
    coordinator._handle_position_update("back", 20)
    coordinator._position_data_updated_monotonic["back"] = time.monotonic() - age
    coordinator._position_data_generation["back"] = generation
    coordinator.controller.read_positions = AsyncMock(side_effect=TimeoutError)
    assert await coordinator._async_read_seek_position(
        "back", NotificationPolicy(coordinator.controller)
    ) == expected
    assert coordinator.controller.read_positions.await_count == (0 if expected else 1)


async def test_direct_targets_do_not_replace_feedback_or_suppress_retries(coordinator):
    controller = coordinator.controller
    controller.supports_direct_position_control = True
    controller.set_motor_position = AsyncMock()
    controller.angle_to_native_position.return_value = 40
    controller.read_positions = AsyncMock()  # Commands accepted, no device reports.
    coordinator._handle_position_update("back", 20)
    observed_at = coordinator._position_data_updated_monotonic["back"]
    notified_at = coordinator._last_notify_received
    callback = MagicMock()
    coordinator.register_position_callback(callback)
    callback.reset_mock()
    move = AsyncMock()

    for _ in range(2):
        await coordinator.async_seek_position("back", 40, move, move, move)

    assert controller.set_motor_position.await_count == 2
    assert coordinator.position_data["back"] == 20
    assert coordinator._position_data_updated_monotonic["back"] == observed_at
    assert coordinator._last_notify_received == notified_at
    callback.assert_not_called()
    result = coordinator._seek_outcomes["back"]
    assert result["target"] == 40
    assert result["outcome"] == "direct_set"
    assert result["final_angle"] is None

    coordinator._handle_position_update("back", 35)
    assert coordinator.position_data["back"] == 35
    callback.assert_called_once()


async def test_direct_target_can_be_skipped_only_after_fresh_report(coordinator):
    controller = coordinator.controller
    controller.supports_direct_position_control = True
    controller.set_motor_position = AsyncMock()
    controller.read_positions = AsyncMock(
        side_effect=lambda _count: coordinator._handle_position_update("back", 40)
    )
    move = AsyncMock()
    await coordinator.async_seek_position("back", 40, move, move, move)
    controller.set_motor_position.assert_not_awaited()
    assert coordinator._seek_outcomes["back"]["outcome"] == "already_at_target"
