"""The #516 merged-stream strategy, against a fake composing controller."""

from __future__ import annotations

import asyncio
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
