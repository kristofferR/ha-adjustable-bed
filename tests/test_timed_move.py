"""Elapsed service limits and cleanup, independent of any bed's wire protocol."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.entity_specs import MotorControlSpec
from custom_components.adjustable_bed.services import _timed_move_plan


async def build_movement(move, stop, *, duration_ms=50):
    controller = MagicMock(prepare_for_movement=AsyncMock())
    controller.motor_control_specs = (
        MotorControlSpec("back", "back", move, move, stop, position_key="back"),
    )
    controller.motor_pulse_settings.return_value = (10, 100)
    controller.timed_move_repeat_count.return_value = 10
    coordinator = MagicMock()
    with patch(
        "custom_components.adjustable_bed.services._validation_controller",
        new=AsyncMock(return_value=controller),
    ):
        movement, _, _, _ = await _timed_move_plan(
            coordinator, coordinator, [], "back", "up", duration_ms,
        )
    return movement, controller


async def test_timed_move_bounds_slow_writes_and_waits_for_release():
    """Transport latency cannot multiply the user's duration; release may take longer."""
    writes = 0
    released = asyncio.Event()

    async def move(_controller):
        nonlocal writes
        for _ in range(10):
            writes += 1
            await asyncio.sleep(.03)

    async def stop(_controller):
        # Cleanup is outside the movement deadline, even on a slow link.
        await asyncio.sleep(.07)
        released.set()

    movement, controller = await build_movement(move, stop)
    await movement(controller)
    assert 1 <= writes < 10
    assert released.is_set()


async def test_timed_move_readiness_does_not_consume_movement_budget():
    ready = False
    moved = False

    async def prepare():
        nonlocal ready
        await asyncio.sleep(.06)
        ready = True

    async def move(_controller):
        nonlocal moved
        if not ready:
            await prepare()
        await asyncio.sleep(.01)
        moved = True

    stop = AsyncMock()
    movement, controller = await build_movement(move, stop, duration_ms=30)
    controller.prepare_for_movement = AsyncMock(side_effect=prepare)
    await movement(controller)
    assert moved
    controller.prepare_for_movement.assert_awaited_once()
    stop.assert_awaited_once_with(controller)


async def test_timed_move_cancel_during_readiness_does_not_start_movement():
    started, finished = asyncio.Event(), asyncio.Event()

    async def prepare():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    move, stop = AsyncMock(), AsyncMock()
    movement, controller = await build_movement(move, stop)
    controller.prepare_for_movement = AsyncMock(side_effect=prepare)
    task = asyncio.create_task(movement(controller))
    try:
        async with asyncio.timeout(1):
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert finished.is_set()
    move.assert_not_awaited()
    stop.assert_awaited_once_with(controller)


async def test_timed_move_readiness_failure_is_not_a_successful_deadline():
    move, stop = AsyncMock(), AsyncMock()
    movement, controller = await build_movement(move, stop)
    controller.prepare_for_movement = AsyncMock(side_effect=TimeoutError("readiness failed"))
    with pytest.raises(TimeoutError, match="readiness failed"):
        await movement(controller)
    move.assert_not_awaited()
    stop.assert_awaited_once_with(controller)


@pytest.mark.parametrize("failure", [TimeoutError("transport"), BleakError("write failed")])
async def test_timed_move_does_not_hide_transport_failure(failure):
    stop = AsyncMock()
    movement, controller = await build_movement(AsyncMock(side_effect=failure), stop)
    with pytest.raises(type(failure), match=str(failure)):
        await movement(controller)
    stop.assert_awaited_once_with(controller)


async def test_timed_move_deadline_does_not_hide_failed_stop():
    async def move(_controller):
        await asyncio.sleep(.15)

    movement, controller = await build_movement(
        move, AsyncMock(side_effect=BleakError("stop failed")),
    )
    with pytest.raises(BleakError, match="stop failed"):
        await movement(controller)


async def test_timed_move_does_not_hide_controller_cleanup_timeout_at_deadline():
    async def move(_controller):
        try:
            await asyncio.Event().wait()
        finally:
            raise TimeoutError("controller release timed out")

    stop = AsyncMock()
    movement, controller = await build_movement(move, stop)
    with pytest.raises(TimeoutError, match="controller release timed out"):
        await movement(controller)
    stop.assert_awaited_once_with(controller)


@pytest.mark.parametrize("movement_error", [RuntimeError("movement failed"), asyncio.CancelledError()])
async def test_timed_move_reports_failed_release_with_original_error_as_context(movement_error):
    movement, controller = await build_movement(
        AsyncMock(side_effect=movement_error), AsyncMock(side_effect=BleakError("release failed")),
    )
    with pytest.raises(BleakError, match="release failed") as caught:
        await movement(controller)
    assert caught.value.__context__ is movement_error


async def test_timed_move_cancel_during_stop_waits_for_cleanup():
    stopping = asyncio.Event()
    allow_release = asyncio.Event()
    released = asyncio.Event()

    async def stop(_controller):
        stopping.set()
        await allow_release.wait()
        released.set()

    movement, controller = await build_movement(AsyncMock(), stop)
    task = asyncio.create_task(movement(controller))
    await stopping.wait()
    task.cancel()
    await asyncio.sleep(0)
    still_cleaning_up = not task.done()
    allow_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert still_cleaning_up
    assert released.is_set()


async def test_timed_move_external_cancel_still_stops():
    started = asyncio.Event()

    async def move(_controller):
        started.set()
        await asyncio.Event().wait()

    stop = AsyncMock()
    movement, controller = await build_movement(move, stop, duration_ms=1000)
    task = asyncio.create_task(movement(controller))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stop.assert_awaited_once_with(controller)
