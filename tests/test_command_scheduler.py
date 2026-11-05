"""Tests for the device-scoped command scheduler."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.adjustable_bed.command_scheduler import (
    ALL_COMMAND_RESOURCES,
    MAX_RECENT_COMMAND_RECORDS,
    CommandIntent,
    CommandKind,
    CommandOutcome,
    CommandState,
    DeviceCommandScheduler,
    PreparedCommandInvalidated,
    command_resources,
    current_command_context,
)


async def test_different_resources_queue_without_cancelling_active() -> None:
    scheduler = DeviceCommandScheduler("queue")
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    events: list[str] = []

    async def first(context) -> None:
        events.append("back:start")
        first_started.set()
        await release_first.wait()
        assert not context.cancel_event.is_set()
        events.append("back:end")

    async def second(_context) -> None:
        events.append("legs")

    first_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(
                first,
                resources=command_resources("motor:back"),
                replacement_key="motor:back",
            )
        )
    )
    await first_started.wait()
    second_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(
                second,
                resources=command_resources("motor:legs"),
                replacement_key="motor:legs",
            )
        )
    )
    await asyncio.sleep(0)

    assert events == ["back:start"]
    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert events == ["back:start", "back:end", "legs"]


async def test_active_resource_replacement_runs_before_disjoint_prepared_group() -> None:
    scheduler = DeviceCommandScheduler("replacement-priority")
    active_started = asyncio.Event()
    events: list[str] = []

    async def active(context) -> None:
        events.append("legs:start")
        active_started.set()
        await context.cancel_event.wait()
        events.append("legs:cleanup")

    async def group(_context) -> None:
        events.append("back:group")

    async def replacement(_context) -> None:
        events.append("legs:replacement")

    active_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(active, resources=command_resources("motor:legs"))
        )
    )
    await active_started.wait()
    group_handle = await scheduler.enqueue(
        CommandIntent(
            group,
            resources=command_resources("motor:back"),
            cancel_running=False,
            group_id="back-group",
        ),
        prepared=True,
    )
    replacement_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(
                replacement,
                resources=command_resources("motor:legs"),
            )
        )
    )

    await asyncio.wait_for(replacement_task, timeout=1)
    assert events == ["legs:start", "legs:cleanup", "legs:replacement"]

    await scheduler.cancel(group_handle)
    await active_task


async def test_same_resource_replaces_only_after_active_cleanup() -> None:
    scheduler = DeviceCommandScheduler("replace")
    first_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()
    events: list[str] = []

    async def first(context) -> None:
        events.append("first:start")
        first_started.set()
        await context.cancel_event.wait()
        events.append("first:cleanup")
        cleanup_started.set()
        await cleanup_release.wait()
        events.append("first:done")

    async def replacement(_context) -> None:
        events.append("replacement")

    first_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(
                first,
                resources=command_resources("motor:back"),
                replacement_key="motor:back",
            )
        )
    )
    await first_started.wait()
    replacement_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(
                replacement,
                resources=command_resources("motor:back"),
                replacement_key="motor:back",
            )
        )
    )
    await cleanup_started.wait()

    assert events == ["first:start", "first:cleanup"]
    cleanup_release.set()
    await asyncio.gather(first_task, replacement_task)
    assert events == ["first:start", "first:cleanup", "first:done", "replacement"]
    assert [record.outcome for record in scheduler.recent_records] == [
        CommandOutcome.REPLACED,
        CommandOutcome.COMPLETED,
    ]


async def test_ticket_cancelled_error_does_not_shutdown_replacement() -> None:
    scheduler = DeviceCommandScheduler("cancelled-operation")
    first_started = asyncio.Event()
    events: list[str] = []

    async def first(context) -> None:
        events.append("first:start")
        first_started.set()
        await context.cancel_event.wait()
        events.append("first:cancelled")
        raise asyncio.CancelledError

    async def replacement(_context) -> None:
        events.append("replacement")

    first_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(first, resources=command_resources("motor:back"))
        )
    )
    await first_started.wait()
    replacement_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(replacement, resources=command_resources("motor:back"))
        )
    )

    await asyncio.gather(first_task, replacement_task)
    assert events == ["first:start", "first:cancelled", "replacement"]


async def test_stop_epoch_invalidates_active_and_queued_work() -> None:
    scheduler = DeviceCommandScheduler("stop")
    active_started = asyncio.Event()
    queued_ran = False

    async def active(context) -> None:
        active_started.set()
        await context.cancel_event.wait()

    async def queued(_context) -> None:
        nonlocal queued_ran
        queued_ran = True

    active_handle = await scheduler.enqueue(
        CommandIntent(
            active,
            resources=command_resources("motor:back"),
            replacement_key="motor:back",
            cancel_running=False,
        )
    )
    await active_started.wait()
    queued_handle = await scheduler.enqueue(
        CommandIntent(
            queued,
            resources=command_resources("motor:legs"),
            replacement_key="motor:legs",
            cancel_running=False,
        )
    )

    assert scheduler.request_stop() == 1
    await asyncio.gather(active_handle.future, queued_handle.future)

    assert active_handle.outcome is CommandOutcome.STOPPED
    assert queued_handle.outcome is CommandOutcome.STOPPED
    assert not queued_ran
    assert {
        (record.outcome, record.invalidated_stop_epoch)
        for record in scheduler.recent_records
    } == {(CommandOutcome.STOPPED, 1)}


async def test_command_admitted_during_stop_waits_for_safety_lane() -> None:
    scheduler = DeviceCommandScheduler("stop-barrier")
    stop_epoch = scheduler.request_stop()
    ran = False

    async def command(_context) -> None:
        nonlocal ran
        ran = True

    task = asyncio.create_task(scheduler.execute(CommandIntent(command)))
    await asyncio.sleep(0.01)
    assert not ran

    scheduler.finish_stop(stop_epoch)
    await task
    assert ran


async def test_only_newest_overlapping_stop_releases_safety_lane() -> None:
    scheduler = DeviceCommandScheduler("overlapping-stop")
    first_epoch = scheduler.request_stop()
    second_epoch = scheduler.request_stop()
    ran = False

    async def command(_context) -> None:
        nonlocal ran
        ran = True

    task = asyncio.create_task(scheduler.execute(CommandIntent(command)))
    scheduler.finish_stop(first_epoch)
    await asyncio.sleep(0.01)
    assert not ran

    scheduler.finish_stop(second_epoch)
    await task
    assert ran


async def test_prepared_command_does_not_run_before_commit() -> None:
    scheduler = DeviceCommandScheduler("prepared")
    ran = False

    async def operation(_context) -> None:
        nonlocal ran
        ran = True

    handle = await scheduler.enqueue(
        CommandIntent(
            operation,
            resources=command_resources("motor:back"),
            group_id="group-1",
        ),
        prepared=True,
    )
    await scheduler.wait_ready(handle)
    assert handle.state is CommandState.PREPARED
    assert not ran

    scheduler.commit(handle)
    await scheduler.wait_prepared_result(handle)
    assert ran
    assert handle.outcome is CommandOutcome.COMPLETED


async def test_prepared_command_invalidated_by_stop_never_runs() -> None:
    scheduler = DeviceCommandScheduler("prepared-stop")
    ran = False

    async def operation(_context) -> None:
        nonlocal ran
        ran = True

    handle = await scheduler.enqueue(CommandIntent(operation, group_id="group-1"), prepared=True)
    await scheduler.wait_ready(handle)
    scheduler.request_stop(ALL_COMMAND_RESOURCES)

    with pytest.raises(PreparedCommandInvalidated):
        await scheduler.wait_prepared_result(handle)
    assert not ran


async def test_caller_cancellation_drops_queued_one_shot() -> None:
    scheduler = DeviceCommandScheduler("caller")
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    queued_ran = False

    async def first(_context) -> None:
        first_started.set()
        await release_first.wait()

    async def queued(_context) -> None:
        nonlocal queued_ran
        queued_ran = True

    first_task = asyncio.create_task(scheduler.execute(CommandIntent(first, cancel_running=False)))
    await first_started.wait()
    queued_task = asyncio.create_task(
        scheduler.execute(
            CommandIntent(
                queued,
                resources=command_resources("motor:legs"),
                cancel_running=False,
            )
        )
    )
    await asyncio.sleep(0)
    queued_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued_task

    assert scheduler.recent_records[-1].outcome is CommandOutcome.CALLER_CANCELLED
    assert scheduler.recent_records[-1].started_at is None

    release_first.set()
    await first_task
    assert not queued_ran


async def test_operation_receives_task_local_context() -> None:
    scheduler = DeviceCommandScheduler("context")
    seen = None

    async def operation(context) -> None:
        nonlocal seen
        seen = current_command_context()
        assert seen is context

    await scheduler.execute(
        CommandIntent(
            operation,
            resources=command_resources("motor:back"),
            pulse_count=42,
            pulse_delay_ms=17,
        )
    )

    assert seen is not None
    assert seen.pulse_count == 42
    assert seen.pulse_delay_ms == 17
    assert current_command_context() is None


async def test_context_copied_to_background_task_expires_with_command() -> None:
    scheduler = DeviceCommandScheduler("background-context")
    inspect_context = asyncio.Event()
    background_context = object()

    async def background() -> None:
        nonlocal background_context
        await inspect_context.wait()
        background_context = current_command_context()

    async def operation(_context) -> None:
        asyncio.create_task(background())

    await scheduler.execute(CommandIntent(operation))
    inspect_context.set()
    await asyncio.sleep(0)

    assert background_context is None


async def test_completed_record_contains_shared_diagnostic_metadata() -> None:
    scheduler = DeviceCommandScheduler("record")

    async def operation(_context) -> None:
        await asyncio.sleep(0)

    handle = await scheduler.enqueue(
        CommandIntent(
            operation,
            resources=command_resources("motor:back", "motor:legs"),
            kind=CommandKind.GROUP,
            group_id="group-1",
            intent_id="intent-1",
        )
    )
    await handle.future

    record = scheduler.recent_records[-1]
    assert record.intent_id == "intent-1"
    assert record.kind is CommandKind.GROUP
    assert record.group_id == "group-1"
    assert record.resources == ("motor:back", "motor:legs")
    assert record.scheduler_strategy == "serial_opaque"
    assert record.stop_epoch == 0
    assert record.invalidated_stop_epoch is None
    assert record.started_at is not None
    assert record.admitted_at <= record.started_at <= record.finished_at
    assert record.outcome is CommandOutcome.COMPLETED
    assert record.queue_wait_seconds >= 0
    assert record.active_duration_seconds is not None
    assert record.active_duration_seconds >= 0
    recent_diagnostics = scheduler.diagnostics["recent_records"]
    assert isinstance(recent_diagnostics, list)
    assert recent_diagnostics[-1] == record.as_dict()


async def test_recent_record_history_is_bounded() -> None:
    scheduler = DeviceCommandScheduler("bounded")

    async def operation(_context) -> None:
        return

    for index in range(MAX_RECENT_COMMAND_RECORDS + 3):
        await scheduler.execute(
            CommandIntent(operation, intent_id=f"intent-{index}")
        )

    assert len(scheduler.recent_records) == MAX_RECENT_COMMAND_RECORDS
    assert scheduler.recent_records[0].intent_id == "intent-3"


async def test_admitted_stop_records_stop_intent_and_releases_barrier() -> None:
    scheduler = DeviceCommandScheduler("stop-record")
    seen_context = None

    async def stop(context) -> None:
        nonlocal seen_context
        seen_context = current_command_context()
        assert seen_context is context

    stop_task = scheduler.admit_stop(
        stop,
        command_resources("motor:back"),
        group_id="stop-group",
    )
    assert not scheduler._stop_barrier.is_set()

    await stop_task

    record = scheduler.recent_records[-1]
    assert record.kind is CommandKind.STOP
    assert record.group_id == "stop-group"
    assert record.resources == ("motor:back",)
    assert record.stop_epoch == 1
    assert record.outcome is CommandOutcome.COMPLETED
    assert scheduler._stop_barrier.is_set()
    assert seen_context is not None


async def test_shutdown_drains_stop_admitted_before_its_task_starts() -> None:
    scheduler = DeviceCommandScheduler("stop-shutdown")
    stop_started = asyncio.Event()
    release_stop = asyncio.Event()

    async def stop(_context) -> None:
        assert scheduler._closed
        stop_started.set()
        await release_stop.wait()

    stop_task = scheduler.admit_stop(stop)

    async def release_after_start() -> None:
        await stop_started.wait()
        assert not stop_task.done()
        release_stop.set()

    release_task = asyncio.create_task(release_after_start())
    await scheduler.async_shutdown()
    await release_task

    assert stop_task.done()
    assert scheduler.recent_records[-1].outcome is CommandOutcome.COMPLETED


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (TimeoutError("too slow"), CommandOutcome.TIMEOUT),
        (RuntimeError("broken"), CommandOutcome.FAILED),
    ],
)
async def test_operation_errors_have_typed_terminal_outcomes(
    error: Exception,
    outcome: CommandOutcome,
) -> None:
    scheduler = DeviceCommandScheduler("error")

    async def operation(_context) -> None:
        raise error

    with pytest.raises(type(error), match=str(error)):
        await scheduler.execute(CommandIntent(operation))

    record = scheduler.recent_records[-1]
    assert record.outcome is outcome
    assert record.active_duration_seconds is not None


async def test_prepared_group_abort_has_terminal_record() -> None:
    scheduler = DeviceCommandScheduler("group-abort")

    async def operation(_context) -> None:
        pytest.fail("aborted prepared operation must not run")

    handle = await scheduler.enqueue(
        CommandIntent(operation, kind=CommandKind.GROUP, group_id="group-abort"),
        prepared=True,
    )
    await scheduler.wait_ready(handle)
    await scheduler.cancel(handle, CommandOutcome.GROUP_ABORTED)

    record = scheduler.recent_records[-1]
    assert record.outcome is CommandOutcome.GROUP_ABORTED
    assert record.group_id == "group-abort"
    assert record.started_at is None


async def test_shutdown_records_active_intent_outcome() -> None:
    scheduler = DeviceCommandScheduler("shutdown")
    started = asyncio.Event()

    async def operation(_context) -> None:
        started.set()
        await asyncio.Future()

    task = asyncio.create_task(scheduler.execute(CommandIntent(operation)))
    await started.wait()
    await scheduler.async_shutdown()
    await task

    record = scheduler.recent_records[-1]
    assert record.outcome is CommandOutcome.SHUTDOWN
    assert record.invalidated_stop_epoch == 1


async def test_repeated_scoped_cancellation_keeps_distinct_generation_and_latest_reason() -> None:
    scheduler = DeviceCommandScheduler("scoped-cancellation-identity")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def held(_context) -> None:
        entered.set()
        await finish.wait()

    async def instant(_context) -> None:
        pass

    right = command_resources("side:right:*")
    handle = await scheduler.enqueue(CommandIntent(held, resources=right))
    await entered.wait()
    other = await scheduler.enqueue(
        CommandIntent(instant, resources=command_resources("side:left:*"))
    )
    assert handle.context.cancel_generation == 0
    assert not handle.context.cancel_event.is_set()

    await scheduler.enqueue(CommandIntent(instant, resources=right))
    assert handle.context.cancel_generation == 1
    assert handle.context.cancel_reason is CommandOutcome.REPLACED
    epoch = scheduler.request_stop(right)
    assert handle.context.cancel_generation == 2
    assert handle.context.cancel_reason is CommandOutcome.STOPPED

    cancelled = asyncio.create_task(scheduler.cancel(handle, CommandOutcome.CALLER_CANCELLED))
    await asyncio.sleep(0)
    assert handle.context.cancel_generation == 3
    assert handle.context.cancel_reason is CommandOutcome.CALLER_CANCELLED
    assert handle.context.cancel_event.is_set()
    assert other.context.cancel_generation == 0
    assert not other.context.cancel_event.is_set()
    finish.set()
    await asyncio.wait_for(cancelled, 1)
    scheduler.finish_stop(epoch)
    await asyncio.wait_for(other.future, 1)
    await scheduler.async_shutdown()


@pytest.mark.parametrize(
    ("holder", "stop", "preempted"),
    [
        # Another motor of the bed: the STOP needs the one writer at once (#516).
        ("motor:back", "motor:legs", True),
        ("side:left:motor:back", "side:left:motor:legs", True),
        # Not motion, or the other side of a one-address pair: never pre-empted.
        ("lighting", "motor:legs", False),
        ("configuration", "motor:legs", False),
        ("side:right:motor:back", "side:left:motor:legs", False),
    ],
)
async def test_motor_stop_preempts_motion_holding_the_writer(
    holder: str, stop: str, preempted: bool
) -> None:
    scheduler = DeviceCommandScheduler("preempt")
    started = asyncio.Event()
    release = asyncio.Event()
    seen: list[CommandOutcome | None] = []

    async def hold(context) -> None:
        started.set()
        waiters = {
            asyncio.ensure_future(context.cancel_event.wait()),
            asyncio.ensure_future(release.wait()),
        }
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)
        seen.append(context.cancel_reason)

    held = asyncio.create_task(
        scheduler.execute(CommandIntent(hold, resources=command_resources(holder)))
    )
    await started.wait()

    async def stop_operation(context) -> None:
        return

    stop_task = scheduler.admit_stop(stop_operation, command_resources(stop))
    await stop_task
    release.set()
    await held
    assert seen == [CommandOutcome.STOPPED if preempted else None]
