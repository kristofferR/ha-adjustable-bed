"""The #516 merged-stream strategy, against a fake composing controller."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable

import pytest

from custom_components.adjustable_bed.command_scheduler import (
    ALL_COMMAND_RESOURCES,
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandOutcome,
    CommandRecord,
    DeviceCommandScheduler,
    HoldClaim,
    HoldLease,
    StaleHoldLease,
    StreamDriver,
    StreamMember,
    command_resources,
)

CONCURRENT = command_resources("motor:back", "motor:legs", "motor:head")
TICK = 0.01


class FakeDriver:
    """Records composed ticks, member cleanups and the profile release."""

    stream_tick_s = TICK

    def __init__(self, *, fail_end: str | None = None) -> None:
        self.events: list[tuple[str, ...]] = []
        self.ticked = asyncio.Event()
        self._fail_end = fail_end

    async def write_stream_tick(self, members: tuple[StreamMember, ...]) -> None:
        self.events.append(("tick", *sorted(f"{m.motor}:{m.action}" for m in members)))
        self.ticked.set()
        await asyncio.sleep(0)

    async def end_stream_member(
        self, member: StreamMember, remaining: tuple[StreamMember, ...]
    ) -> None:
        if member.motor == self._fail_end:
            raise RuntimeError("cleanup failed")
        self.events.append(("end", f"{member.motor}:{member.action}", *sorted(
            m.motor for m in remaining
        )))

    async def release_stream(self) -> None:
        self.events.append(("release",))

    def ticks(self) -> list[tuple[str, ...]]:
        return [event[1:] for event in self.events if event[0] == "tick"]


def runner_for(driver: StreamDriver) -> Callable[[Callable[[StreamDriver], Awaitable[None]]], Awaitable[None]]:
    async def runner(body: Callable[[StreamDriver], Awaitable[None]]) -> None:
        await body(driver)

    return runner


def member(
    motor: str, action: str = "up", *, seconds: float = 30, lease: HoldLease | None = None
) -> StreamMember:
    loop = asyncio.get_running_loop()
    return StreamMember(
        motor=motor,
        resource=f"motor:{motor}",
        action=action,
        deadline=loop.time() + seconds,
        lease=lease,
    )


def join(
    scheduler: DeviceCommandScheduler, driver: FakeDriver, item: StreamMember
) -> asyncio.Task[CommandOutcome | None]:
    return asyncio.create_task(
        scheduler.execute_stream_member(item, CONCURRENT, runner_for(driver))
    )


async def last_record(scheduler: DeviceCommandScheduler) -> CommandRecord:
    """The streamer's record lands just after its members resolve."""
    async with asyncio.timeout(1):
        while not scheduler.recent_records or scheduler._streams:
            await asyncio.sleep(0)
    return scheduler.recent_records[-1]


async def settle(driver: FakeDriver, ticks: int = 2) -> None:
    for _ in range(ticks):
        driver.ticked.clear()
        await asyncio.wait_for(driver.ticked.wait(), 1)


async def test_every_member_appears_in_each_composed_tick() -> None:
    scheduler = DeviceCommandScheduler("compose")
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    await settle(driver, 1)
    legs = join(scheduler, driver, member("legs", "down"))
    await settle(driver, 3)
    assert driver.ticks()[-1] == ("back:up", "legs:down")
    assert scheduler.recent_records == ()  # one live streamer, no serial records
    scheduler.finish_stop(scheduler.request_stop(ALL_COMMAND_RESOURCES))
    assert await asyncio.wait_for(back, 1) is CommandOutcome.STOPPED
    assert await asyncio.wait_for(legs, 1) is CommandOutcome.STOPPED
    assert (await last_record(scheduler)).kind is CommandKind.STREAM
    assert (await last_record(scheduler)).scheduler_strategy == "merged_stream"


async def test_replacing_one_member_leaves_the_other_streaming() -> None:
    scheduler = DeviceCommandScheduler("replace")
    driver = FakeDriver()
    back_up = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)
    back_down = join(scheduler, driver, member("back", "down"))
    assert await asyncio.wait_for(back_up, 1) is CommandOutcome.REPLACED
    await settle(driver)
    # The replaced member's own cleanup ran while legs (and its successor) moved.
    assert ("end", "back:up", "back", "legs") in driver.events
    assert driver.ticks()[-1] == ("back:down", "legs:up")
    assert ("release",) not in driver.events
    scheduler.finish_stop(scheduler.request_stop(ALL_COMMAND_RESOURCES))
    await asyncio.gather(legs, back_down)


async def test_members_expire_independently_and_the_last_one_releases() -> None:
    scheduler = DeviceCommandScheduler("expire")
    driver = FakeDriver()
    short = join(scheduler, driver, member("back", seconds=0.03))
    long = join(scheduler, driver, member("legs", seconds=0.08))
    assert await asyncio.wait_for(short, 1) is CommandOutcome.EXPIRED
    assert ("end", "back:up", "legs") in driver.events
    assert ("release",) not in driver.events
    assert await asyncio.wait_for(long, 1) is CommandOutcome.EXPIRED
    assert driver.events[-2:] == [("end", "legs:up"), ("release",)]
    assert (await last_record(scheduler)).outcome is CommandOutcome.COMPLETED


async def test_bed_wide_stop_clears_every_member_before_a_later_member() -> None:
    scheduler = DeviceCommandScheduler("stop")
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    later = join(scheduler, driver, member("head"))
    assert await asyncio.wait_for(back, 1) is CommandOutcome.STOPPED
    assert await asyncio.wait_for(legs, 1) is CommandOutcome.STOPPED
    released = driver.events.index(("release",))
    await asyncio.sleep(0.03)
    # The later member waits for the STOP to finish on the wire.
    assert all("head:up" not in event for event in driver.events)
    scheduler.finish_stop(epoch)
    await settle(driver)
    assert driver.ticks()[-1] == ("head:up",)
    assert driver.events.index(("tick", "head:up")) > released
    scheduler.finish_stop(scheduler.request_stop(ALL_COMMAND_RESOURCES))
    await later


async def test_motor_scoped_stop_ends_only_its_member() -> None:
    scheduler = DeviceCommandScheduler("motor-stop")
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:back")))
    assert await asyncio.wait_for(back, 1) is CommandOutcome.STOPPED
    await settle(driver)
    assert driver.ticks()[-1] == ("legs:up",)
    assert not legs.done()
    scheduler.finish_stop(scheduler.request_stop(ALL_COMMAND_RESOURCES))
    await legs


async def test_member_cleanup_failure_ends_the_stream_and_releases() -> None:
    scheduler = DeviceCommandScheduler("failure")
    driver = FakeDriver(fail_end="back")
    back = join(scheduler, driver, member("back", seconds=0.03))
    legs = join(scheduler, driver, member("legs"))
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await asyncio.wait_for(back, 1)
    # The failure ended legs too, and its caller sees it.
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await asyncio.wait_for(legs, 1)
    assert ("end", "legs:up") in driver.events
    assert driver.events[-1] == ("release",)
    assert (await last_record(scheduler)).outcome is CommandOutcome.FAILED


async def test_serial_command_on_a_member_motor_replaces_the_stream() -> None:
    scheduler = DeviceCommandScheduler("serial")
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    await settle(driver)
    ran = asyncio.Event()

    async def preset(_context: CommandContext) -> None:
        ran.set()

    await scheduler.execute(CommandIntent(preset))
    assert ran.is_set()
    assert await asyncio.wait_for(back, 1) is CommandOutcome.REPLACED
    assert driver.events[-1] == ("release",)


async def test_lease_renewal_moves_a_member_deadline_without_a_frame() -> None:
    scheduler = DeviceCommandScheduler("lease")
    driver = FakeDriver()
    held = HoldLease(owner="card", generation=1, action="up", duration_s=0.05)
    back = join(scheduler, driver, member("back", seconds=0.05, lease=held))
    await settle(driver, 1)
    loop = asyncio.get_running_loop()
    started = loop.time()
    for _ in range(4):
        await asyncio.sleep(0.03)
        assert scheduler.claim_hold(held, ("motor:back",)) is HoldClaim.RENEW
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED
    assert loop.time() - started >= 0.15
    # Frames follow the tick cadence only: no extra write per renewal.
    assert len(driver.ticks()) <= (loop.time() - started) / TICK + 2
    assert scheduler.claim_hold(held, ("motor:back",)) is HoldClaim.STALE
    with pytest.raises(StaleHoldLease):
        await scheduler.execute_stream_member(
            member("back", lease=held), CONCURRENT, runner_for(driver)
        )


async def test_disconnect_ends_the_stream_without_replay() -> None:
    scheduler = DeviceCommandScheduler("disconnect")
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    await settle(driver)
    scheduler.end_holds(CommandOutcome.DISCONNECTED)
    assert await asyncio.wait_for(back, 1) is CommandOutcome.DISCONNECTED
    ticks = len(driver.ticks())
    await asyncio.sleep(0.03)
    assert len(driver.ticks()) == ticks
    assert driver.events[-1] == ("release",)


async def test_tick_failure_reaches_every_member() -> None:
    scheduler = DeviceCommandScheduler("tick-failure")
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)

    async def broken(_members: tuple[StreamMember, ...]) -> None:
        raise ConnectionError("link lost")

    driver.write_stream_tick = broken  # type: ignore[method-assign]
    for task in (back, legs):
        with pytest.raises(ConnectionError, match="link lost"):
            await asyncio.wait_for(task, 1)
    assert driver.events[-1] == ("release",)
    assert (await last_record(scheduler)).outcome is CommandOutcome.FAILED


async def test_stop_runs_every_member_cleanup_despite_a_failure() -> None:
    scheduler = DeviceCommandScheduler("drain")
    driver = FakeDriver(fail_end="back")
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)
    scheduler.finish_stop(scheduler.request_stop(ALL_COMMAND_RESOURCES))
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await asyncio.wait_for(back, 1)
    await asyncio.gather(legs, return_exceptions=True)
    assert ("end", "legs:up") in driver.events
    assert driver.events[-1] == ("release",)


async def test_slow_cleanup_never_lets_an_expired_member_tick() -> None:
    scheduler = DeviceCommandScheduler("slow-cleanup")
    driver = FakeDriver()
    original_end = driver.end_stream_member

    async def slow_end(item: StreamMember, remaining: tuple[StreamMember, ...]) -> None:
        if item.motor == "back":
            await asyncio.sleep(0.05)  # legs expires meanwhile
        await original_end(item, remaining)

    driver.end_stream_member = slow_end  # type: ignore[method-assign]
    back = join(scheduler, driver, member("back", seconds=0.02))
    legs = join(scheduler, driver, member("legs", seconds=0.04))
    await asyncio.wait_for(asyncio.gather(back, legs), 1)
    back_end = driver.events.index(("end", "back:up", "legs"))
    assert not any(event[0] == "tick" for event in driver.events[back_end:])


async def test_overdue_stream_lease_is_not_renewed() -> None:
    import time

    scheduler = DeviceCommandScheduler("overdue-member")
    driver = FakeDriver()
    held = HoldLease(owner="card", generation=1, action="up", duration_s=0.02)
    back = join(scheduler, driver, member("back", lease=held))
    await settle(driver, 1)
    time.sleep(0.04)  # block the loop past the deadline before the streamer wakes
    assert scheduler.claim_hold(held, ("motor:back",)) is HoldClaim.STALE
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED


async def test_motor_stop_keeps_a_queued_stream_for_its_other_members() -> None:
    scheduler = DeviceCommandScheduler("queued-stream")
    blocker_started = asyncio.Event()
    release_blocker = asyncio.Event()

    async def blocker(_context: CommandContext) -> None:
        blocker_started.set()
        await release_blocker.wait()

    blocking = asyncio.create_task(
        scheduler.execute(CommandIntent(blocker, resources=command_resources("light")))
    )
    await blocker_started.wait()
    driver = FakeDriver()
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs", seconds=0.05))
    await asyncio.sleep(0)
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:back")))
    assert await asyncio.wait_for(back, 1) is CommandOutcome.STOPPED
    release_blocker.set()
    await blocking
    assert await asyncio.wait_for(legs, 1) is CommandOutcome.EXPIRED
    assert driver.ticks()[0] == ("legs:up",)
    # back never reached the wire, so it had no cleanup of its own.
    assert not any(event[:2] == ("end", "back:up") for event in driver.events)


async def test_stop_during_the_final_release_lets_it_finish() -> None:
    scheduler = DeviceCommandScheduler("release-cancel")
    driver = FakeDriver()
    release_started = asyncio.Event()
    finish_release = asyncio.Event()

    async def slow_release() -> None:
        release_started.set()
        await finish_release.wait()
        driver.events.append(("release",))

    driver.release_stream = slow_release  # type: ignore[method-assign]

    async def preemptible(body: Callable[[StreamDriver], Awaitable[None]]) -> None:
        # The coordinator cancels the operation task when STOP sets its event.
        task = asyncio.ensure_future(body(driver))
        context_event = scheduler._active.context.cancel_event  # type: ignore[union-attr]
        stop = asyncio.ensure_future(context_event.wait())
        await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        if not task.done():
            task.cancel()
        stop.cancel()
        await asyncio.gather(task, stop, return_exceptions=True)

    back = asyncio.create_task(
        scheduler.execute_stream_member(member("back", seconds=0.02), CONCURRENT, preemptible)
    )
    await asyncio.wait_for(release_started.wait(), 1)
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    await asyncio.sleep(0.01)
    assert not back.done()  # the caller waits for the release
    finish_release.set()
    await asyncio.wait_for(back, 1)
    scheduler.finish_stop(epoch)
    assert driver.events[-1] == ("release",)


async def test_last_member_returns_before_a_newcomer_streams() -> None:
    scheduler = DeviceCommandScheduler("closing")
    driver = FakeDriver()
    original_end = driver.end_stream_member
    cleanup_started = asyncio.Event()

    async def slow_end(item: StreamMember, remaining: tuple[StreamMember, ...]) -> None:
        cleanup_started.set()
        await asyncio.sleep(0.02)
        await original_end(item, remaining)

    driver.end_stream_member = slow_end  # type: ignore[method-assign]
    back = join(scheduler, driver, member("back", seconds=0.02))
    await asyncio.wait_for(cleanup_started.wait(), 1)
    legs = join(scheduler, driver, member("legs", seconds=0.05))
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED
    assert not legs.done()
    assert await asyncio.wait_for(legs, 1) is CommandOutcome.EXPIRED
    # The newcomer started its own stream after the first one's release.
    assert driver.events.index(("release",)) < driver.events.index(("tick", "legs:up"))


async def test_members_ending_back_to_back_close_the_stream() -> None:
    scheduler = DeviceCommandScheduler("back-to-back")
    driver = FakeDriver()
    original_end = driver.end_stream_member
    back_cleanup = asyncio.Event()
    finish_back_cleanup = asyncio.Event()

    async def slow_end(item: StreamMember, remaining: tuple[StreamMember, ...]) -> None:
        if item.motor == "back":
            back_cleanup.set()
            await finish_back_cleanup.wait()
        else:
            await asyncio.sleep(0.02)
        await original_end(item, remaining)

    driver.end_stream_member = slow_end  # type: ignore[method-assign]
    back = join(scheduler, driver, member("back", seconds=0.02))
    legs = join(scheduler, driver, member("legs"))
    await asyncio.wait_for(back_cleanup.wait(), 1)
    # legs stops while back's cleanup is still on the wire.
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:legs")))
    finish_back_cleanup.set()
    while not legs.done() and ("end", "legs:up") not in driver.events:
        await asyncio.sleep(0)
    head = join(scheduler, driver, member("head", seconds=0.02))
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED
    assert await asyncio.wait_for(legs, 1) is CommandOutcome.STOPPED
    assert not head.done()
    assert await asyncio.wait_for(head, 1) is CommandOutcome.EXPIRED
    assert driver.events.index(("release",)) < driver.events.index(("tick", "head:up"))


async def test_newcomer_ready_as_the_last_member_expires_waits_for_release() -> None:
    scheduler = DeviceCommandScheduler("ready-newcomer")
    driver = FakeDriver()
    held = HoldLease(owner="card", generation=1, action="up", duration_s=0.01)
    newcomer: list[asyncio.Task[CommandOutcome | None]] = []

    async def slow_connect(body: Callable[[StreamDriver], Awaitable[None]]) -> None:
        await asyncio.sleep(0.03)  # back's lease runs out while connecting
        # A newcomer becomes ready just before the streamer's first pass.
        newcomer.append(join(scheduler, driver, member("head", seconds=0.02)))
        await body(driver)

    back = asyncio.create_task(
        scheduler.execute_stream_member(member("back", lease=held), CONCURRENT, slow_connect)
    )
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED
    assert await asyncio.wait_for(newcomer[0], 1) is CommandOutcome.EXPIRED
    assert ("end", "back:up") in driver.events
    assert driver.events.index(("release",)) < driver.events.index(("tick", "head:up"))


async def test_a_slow_write_cannot_stretch_a_timed_move() -> None:
    scheduler = DeviceCommandScheduler("slow-write")
    driver = FakeDriver()
    loop = asyncio.get_running_loop()
    writes: list[float] = []
    original_tick = driver.write_stream_tick

    async def slow_tick(members: tuple[StreamMember, ...]) -> None:
        writes.append(loop.time())
        await original_tick(members)
        await asyncio.sleep(0.08)  # a slow write acknowledgement

    driver.write_stream_tick = slow_tick  # type: ignore[method-assign]
    # The timed budget starts as the first write starts and ends mid-write.
    timed = StreamMember(
        motor="legs", resource="motor:legs", action="up", deadline=math.inf, duration_s=0.02
    )
    started = loop.time()
    task = asyncio.create_task(
        scheduler.execute_stream_member(timed, CONCURRENT, runner_for(driver))
    )
    assert await asyncio.wait_for(task, 1) is CommandOutcome.EXPIRED
    assert loop.time() - started < 0.07
    assert len(writes) == 1
    assert driver.events[-1] == ("release",)


async def test_a_blocked_write_still_expires_a_lease_and_honors_renewal() -> None:
    scheduler = DeviceCommandScheduler("blocked-write")
    driver = FakeDriver()
    loop = asyncio.get_running_loop()
    never = asyncio.Event()

    async def blocked_tick(members: tuple[StreamMember, ...]) -> None:
        driver.events.append(("tick", *sorted(f"{m.motor}:{m.action}" for m in members)))
        driver.ticked.set()
        await never.wait()  # the write never completes

    driver.write_stream_tick = blocked_tick  # type: ignore[method-assign]
    held = HoldLease(owner="card", generation=1, action="up", duration_s=0.03)
    started = loop.time()
    back = join(scheduler, driver, member("back", seconds=0.03, lease=held))
    await asyncio.wait_for(driver.ticked.wait(), 1)
    for _ in range(3):
        await asyncio.sleep(0.02)
        assert scheduler.claim_hold(held, ("motor:back",)) is HoldClaim.RENEW
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED
    # Renewals held it past one lease; expiry then ended the blocked write.
    assert 0.08 <= loop.time() - started < 0.2
    assert driver.events[-2:] == [("end", "back:up"), ("release",)]


async def test_stopping_the_last_member_during_cleanup_closes_admission() -> None:
    scheduler = DeviceCommandScheduler("stop-last")
    driver = FakeDriver()
    entered = asyncio.Event()
    finish = asyncio.Event()
    original_end = driver.end_stream_member

    async def gated_end(item: StreamMember, remaining: tuple[StreamMember, ...]) -> None:
        if item.motor == "back":
            entered.set()
            await finish.wait()
        await original_end(item, remaining)

    driver.end_stream_member = gated_end  # type: ignore[method-assign]
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:back")))
    await asyncio.wait_for(entered.wait(), 1)
    # legs, the last live member, stops while back's cleanup is gated.
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:legs")))
    head = join(scheduler, driver, member("head", seconds=0.02))
    await asyncio.sleep(0)
    finish.set()
    await asyncio.wait_for(asyncio.gather(back, legs, head), 1)
    assert driver.events.index(("release",)) < driver.events.index(("tick", "head:up"))


async def test_a_cancelled_cleanup_write_still_settles_its_caller() -> None:
    scheduler = DeviceCommandScheduler("cancelled-cleanup")
    driver = FakeDriver()
    entered = asyncio.Event()
    write = asyncio.get_running_loop().create_future()
    original_end = driver.end_stream_member

    async def end(item: StreamMember, remaining: tuple[StreamMember, ...]) -> None:
        await original_end(item, remaining)
        if item.motor == "back":
            entered.set()
            await write  # cancelled under the cleanup

    driver.end_stream_member = end  # type: ignore[method-assign]
    back = join(scheduler, driver, member("back"))
    legs = join(scheduler, driver, member("legs"))
    await settle(driver)
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:back")))
    await asyncio.wait_for(entered.wait(), 1)
    write.cancel()
    with pytest.raises(RuntimeError, match="cleanup was cancelled"):
        await asyncio.wait_for(back, 1)
    with pytest.raises(RuntimeError, match="cleanup was cancelled"):
        await asyncio.wait_for(legs, 1)
    assert driver.events[-1] == ("release",)
    assert (await last_record(scheduler)).outcome is CommandOutcome.FAILED


async def test_an_unexpected_write_cancellation_fails_the_stream() -> None:
    scheduler = DeviceCommandScheduler("unexpected-cancel")
    driver = FakeDriver()
    pending: list[asyncio.Future[None]] = []

    async def tick(members: tuple[StreamMember, ...]) -> None:
        driver.events.append(("tick", *sorted(f"{m.motor}:{m.action}" for m in members)))
        driver.ticked.set()
        if len(pending) < 2:
            pending.append(asyncio.get_running_loop().create_future())
            await pending[-1]

    driver.write_stream_tick = tick  # type: ignore[method-assign]
    back = join(scheduler, driver, member("back"))
    await asyncio.wait_for(driver.ticked.wait(), 1)
    pending[0].cancel()  # cancelled under the write, not by the scheduler
    with pytest.raises(RuntimeError, match="stream write was cancelled"):
        await asyncio.wait_for(back, 1)
    assert driver.events[-2:] == [("end", "back:up"), ("release",)]


async def test_a_slow_cancellation_is_not_counted_as_travel() -> None:
    scheduler = DeviceCommandScheduler("slow-teardown")
    driver = FakeDriver()
    reported: list[float | None] = []

    async def tick(members: tuple[StreamMember, ...]) -> None:
        driver.events.append(("tick",))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.15)  # a slow teardown after cancellation
            raise

    driver.write_stream_tick = tick  # type: ignore[method-assign]
    timed = StreamMember(
        motor="back",
        resource="motor:back",
        action="up",
        deadline=math.inf,
        duration_s=0.02,
        on_left=reported.append,
    )
    timed.on_wire = lambda: None
    assert await asyncio.wait_for(
        scheduler.execute_stream_member(timed, CONCURRENT, runner_for(driver)), 1
    ) is CommandOutcome.EXPIRED
    assert reported[0] == pytest.approx(0.02, abs=0.01)


@pytest.mark.parametrize("ending", ["stop", "replace"])
async def test_teardown_after_stop_or_replacement_is_not_travel(ending: str) -> None:
    scheduler = DeviceCommandScheduler(f"teardown-{ending}")
    driver = FakeDriver()
    reported: list[float | None] = []
    writing = asyncio.Event()

    async def tick(members: tuple[StreamMember, ...]) -> None:
        driver.events.append(("tick",))
        writing.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.15)  # a slow teardown after cancellation
            raise

    driver.write_stream_tick = tick  # type: ignore[method-assign]
    held = member("back")
    held.on_wire = lambda: None
    held.on_left = reported.append
    back = join(scheduler, driver, held)
    await asyncio.wait_for(writing.wait(), 1)
    await asyncio.sleep(0.02)
    if ending == "stop":
        epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
        await asyncio.wait_for(back, 1)
        scheduler.finish_stop(epoch)
    else:

        async def preset(_context: CommandContext) -> None:
            return None

        await scheduler.execute(CommandIntent(preset))
        await asyncio.wait_for(back, 1)
    assert reported[0] == pytest.approx(0.02, abs=0.015)


async def test_a_failed_write_reaches_a_member_retired_just_before() -> None:
    scheduler = DeviceCommandScheduler("failed-retired")
    driver = FakeDriver()
    reported: list[float | None] = []

    async def tick(members: tuple[StreamMember, ...]) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise ConnectionError("link lost") from None

    driver.write_stream_tick = tick  # type: ignore[method-assign]
    timed = StreamMember(
        motor="back",
        resource="motor:back",
        action="up",
        deadline=math.inf,
        duration_s=0.02,
        on_left=reported.append,
    )
    timed.on_wire = lambda: None
    with pytest.raises(ConnectionError, match="link lost"):
        await asyncio.wait_for(
            scheduler.execute_stream_member(timed, CONCURRENT, runner_for(driver)), 1
        )
    assert timed.outcome is CommandOutcome.FAILED
    assert reported == [None]


async def test_stop_while_a_write_unwinds_stops_the_survivors_clock() -> None:
    scheduler = DeviceCommandScheduler("stop-during-unwind")
    driver = FakeDriver()
    reported: dict[str, float | None] = {}
    unwinding = asyncio.Event()

    async def tick(members: tuple[StreamMember, ...]) -> None:
        driver.events.append(("tick",))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            unwinding.set()
            await asyncio.sleep(0.15)  # a slow teardown after cancellation
            raise

    driver.write_stream_tick = tick  # type: ignore[method-assign]
    short = member("back", seconds=0.02)
    survivor = member("legs")
    for item in (short, survivor):
        item.on_wire = lambda: None
        item.on_left = lambda value, motor=item.motor: reported.__setitem__(motor, value)
    back = join(scheduler, driver, short)
    legs = join(scheduler, driver, survivor)
    # back expires, so its write unwinds; legs is still moving meanwhile.
    await asyncio.wait_for(unwinding.wait(), 1)
    await asyncio.sleep(0.02)
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    await asyncio.wait_for(asyncio.gather(back, legs), 1)
    scheduler.finish_stop(epoch)
    stopped_after = survivor.left_at - survivor.wire_started  # type: ignore[operator]
    assert reported["legs"] == pytest.approx(stopped_after)
    assert stopped_after < 0.08


async def test_a_write_failing_after_a_stop_preemption_reports_the_failure() -> None:
    scheduler = DeviceCommandScheduler("fail-after-preempt")
    driver = FakeDriver()
    reported: list[float | None] = []
    writing = asyncio.Event()

    async def tick(members: tuple[StreamMember, ...]) -> None:
        writing.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise ConnectionError("link lost") from None

    driver.write_stream_tick = tick  # type: ignore[method-assign]

    async def preemptible(body: Callable[[StreamDriver], Awaitable[None]]) -> None:
        # The coordinator cancels the operation task when STOP sets its event.
        task = asyncio.ensure_future(body(driver))
        stop = asyncio.ensure_future(scheduler._active.context.cancel_event.wait())  # type: ignore[union-attr]
        await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        if not task.done():
            task.cancel()
        stop.cancel()
        await asyncio.gather(task, stop, return_exceptions=True)
        if not task.cancelled() and task.exception() is not None:
            raise task.exception()  # type: ignore[misc]

    held = member("back")
    held.on_wire = lambda: None
    held.on_left = reported.append
    back = asyncio.create_task(scheduler.execute_stream_member(held, CONCURRENT, preemptible))
    await asyncio.wait_for(writing.wait(), 1)
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    with pytest.raises(ConnectionError, match="link lost"):
        await asyncio.wait_for(back, 1)
    scheduler.finish_stop(epoch)
    assert reported == [None]


async def test_stop_during_another_members_cleanup_stops_the_survivors_clock() -> None:
    scheduler = DeviceCommandScheduler("stop-during-cleanup")
    driver = FakeDriver()
    reported: dict[str, float | None] = {}
    cleaning = asyncio.Event()
    original_end = driver.end_stream_member

    async def slow_end(item: StreamMember, remaining: tuple[StreamMember, ...]) -> None:
        if item.motor == "back":
            cleaning.set()
            await asyncio.sleep(0.15)  # a slow member cleanup
        await original_end(item, remaining)

    driver.end_stream_member = slow_end  # type: ignore[method-assign]
    short = member("back", seconds=0.02)
    survivor = member("legs")
    for item in (short, survivor):
        item.on_wire = lambda: None
        item.on_left = lambda value, motor=item.motor: reported.__setitem__(motor, value)
    back = join(scheduler, driver, short)
    legs = join(scheduler, driver, survivor)
    await asyncio.wait_for(cleaning.wait(), 1)
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    await asyncio.wait_for(asyncio.gather(back, legs), 1)
    scheduler.finish_stop(epoch)
    # Stopped as the STOP arrived (~20 ms in), not after back's cleanup.
    assert reported["legs"] is not None and reported["legs"] < 0.08
