"""Caller cancellation survives the shared operation's child-task drains."""

import asyncio
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_coordinator_diagnostic_polling import coordinator as coordinator


class DrainingEvent(asyncio.Event):
    """Expose the cancellation acknowledgement of the real event-wait child."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.draining = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def wait(self) -> Literal[True]:
        self.started.set()
        try:
            return await super().wait()
        except asyncio.CancelledError:
            self.draining.set()
            await self.release.wait()
            raise
        finally:
            self.finished.set()


@pytest.mark.parametrize("raise_on_cancel", [False, True])
async def test_caller_cancel_during_completed_operation_waiter_drain(
    coordinator: AdjustableBedCoordinator, raise_on_cancel: bool
) -> None:
    cancellation = DrainingEvent()

    async def completed_operation() -> str:
        await cancellation.started.wait()
        return "completed"

    operation = asyncio.create_task(completed_operation())
    waiting = asyncio.create_task(
        coordinator._async_wait_for_controller_operation(
            operation,
            cancel_event=cancellation,
            operation_name="query",
            raise_on_cancel=raise_on_cancel,
        )
    )
    try:
        async with asyncio.timeout(1):
            await cancellation.draining.wait()
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        assert waiting.cancelled()
        assert operation.result() == "completed"
        assert cancellation.finished.is_set()
    finally:
        cancellation.release.set()
        if not waiting.done():
            waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.parametrize("raise_on_cancel", [False, True])
async def test_event_preemption_preserves_requested_cancel_result(
    coordinator: AdjustableBedCoordinator, raise_on_cancel: bool
) -> None:
    cancellation = asyncio.Event()
    operation_started = asyncio.Event()
    released = asyncio.Event()

    async def active_operation() -> None:
        operation_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    operation = asyncio.create_task(active_operation())
    waiting = asyncio.create_task(
        coordinator._async_wait_for_controller_operation(
            operation,
            cancel_event=cancellation,
            operation_name="command",
            raise_on_cancel=raise_on_cancel,
        )
    )
    try:
        async with asyncio.timeout(1):
            await operation_started.wait()
            cancellation.set()
            if raise_on_cancel:
                with pytest.raises(asyncio.CancelledError):
                    await waiting
            else:
                assert await waiting is None
        assert operation.cancelled()
        assert released.is_set()
    finally:
        if not waiting.done():
            waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


async def test_initial_caller_cancel_cancels_both_children_before_draining(
    coordinator: AdjustableBedCoordinator,
) -> None:
    cancellation = DrainingEvent()
    operation_started = asyncio.Event()
    release_started = asyncio.Event()
    release_finished = asyncio.Event()
    allow_release = asyncio.Event()

    async def active_operation() -> None:
        operation_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            release_started.set()
            await allow_release.wait()
            release_finished.set()

    operation = asyncio.create_task(active_operation())
    waiting = asyncio.create_task(
        coordinator._async_wait_for_controller_operation(
            operation,
            cancel_event=cancellation,
            operation_name="command",
            raise_on_cancel=False,
        )
    )
    try:
        async with asyncio.timeout(1):
            await operation_started.wait()
            await cancellation.started.wait()
            waiting.cancel()
            await release_started.wait()
            # The sibling receives cancellation while the controller drains release.
            await cancellation.draining.wait()
            cancellation.release.set()
            await cancellation.finished.wait()
            allow_release.set()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        assert operation.cancelled()
        assert release_finished.is_set()
        assert cancellation.finished.is_set()
    finally:
        allow_release.set()
        cancellation.release.set()
        if not waiting.done():
            waiting.cancel()
        await asyncio.gather(waiting, operation, return_exceptions=True)


async def test_real_vmat_poll_terminates_when_cancelled_during_waiter_drain(
    coordinator: AdjustableBedCoordinator,
) -> None:
    cancellation = DrainingEvent()
    original_wait = coordinator._async_wait_for_controller_operation

    async def wait_with_draining_event[T](
        operation_task: asyncio.Task[T],
        *,
        cancel_event: asyncio.Event,
        operation_name: str,
        raise_on_cancel: bool,
    ) -> T | None:
        # Extend only the helper's waiter, keeping all controller reads unchanged.
        assert cancel_event is coordinator.cancel_command
        return await original_wait(
            operation_task,
            cancel_event=cancellation,
            operation_name=operation_name,
            raise_on_cancel=raise_on_cancel,
        )

    with patch.object(
        coordinator, "_async_wait_for_controller_operation", new=wait_with_draining_event
    ):
        coordinator._refresh_diagnostic_polling_schedule()
        poll = coordinator._diagnostic_poll_task
        advertisement = coordinator._diagnostic_advertisement_task
        assert poll is not None and advertisement is not None
        try:
            async with asyncio.timeout(1):
                await cancellation.draining.wait()
                assert coordinator.controller_state["vmatbasic_ed"] is True
                assert coordinator.client is not None
                read = coordinator.client.read_gatt_char
                assert isinstance(read, AsyncMock)
                reads = read.await_count
                assert reads == 5
                coordinator._cancel_diagnostic_polling()
                with pytest.raises(asyncio.CancelledError):
                    await poll
                await asyncio.gather(advertisement, return_exceptions=True)
            assert poll.cancelled()
            assert coordinator._diagnostic_poll_task is None
            assert coordinator.controller_state["vmatbasic_ed"] is None
            assert read.await_count == reads
            assert not coordinator._command_lock.locked()
            assert coordinator.controller is not None
            assert not coordinator.controller.ble_lock.locked()
        finally:
            cancellation.release.set()
            for task in (poll, advertisement):
                if not task.done():
                    task.cancel()
            await asyncio.gather(poll, advertisement, return_exceptions=True)
            coordinator._cancel_diagnostic_polling()
