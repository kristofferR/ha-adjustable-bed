"""The #483 hold lease in the device scheduler, against fake held operations.

A fake hold streams one frame per tick until its command's cancel event is
set, then runs its release with a fresh event, as a family controller does.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import pytest

from custom_components.adjustable_bed.command_scheduler import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandOutcome,
    DeviceCommandScheduler,
    HoldClaim,
    HoldLease,
    StaleHoldLease,
    command_resources,
)

BACK = command_resources("motor:back")
TICK = 0.005


class FakeHold:
    """A controller-shaped held write loop with a release in ``finally``."""

    def __init__(self) -> None:
        self.frames: list[str] = []
        self.started = asyncio.Event()
        self.runs = 0

    async def __call__(self, context: CommandContext) -> None:
        self.runs += 1
        self.started.set()
        try:
            while not context.cancel_event.is_set():
                self.frames.append("hold")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(context.cancel_event.wait(), TICK)
        finally:
            self.frames.append("release")


def lease(generation: int = 1, *, action: str = "up", duration_s: float = 0.2) -> HoldLease:
    return HoldLease(owner="card", generation=generation, action=action, duration_s=duration_s)


def hold_intent(fake: Callable, held: HoldLease) -> CommandIntent:
    return CommandIntent(fake, resources=BACK, kind=CommandKind.HOLD, lease=held)


async def start_hold(
    scheduler: DeviceCommandScheduler, fake: FakeHold, held: HoldLease
) -> asyncio.Task[None]:
    task = asyncio.create_task(scheduler.execute(hold_intent(fake, held)))
    async with asyncio.timeout(1):
        await fake.started.wait()
    return task


async def test_renewal_replaces_the_deadline_without_a_frame_or_release() -> None:
    scheduler = DeviceCommandScheduler("renew")
    fake = FakeHold()
    task = await start_hold(scheduler, fake, lease(duration_s=0.05))
    handle = scheduler._active
    assert handle is not None and handle.context.hold_deadline is not None
    first_deadline = handle.context.hold_deadline

    for _ in range(4):
        await asyncio.sleep(0.03)
        frames_before = list(fake.frames)
        # A renewal through admission returns at once and runs nothing new.
        await asyncio.wait_for(
            scheduler.execute(hold_intent(FakeHold(), lease(duration_s=0.05))), 0.01
        )
        assert fake.frames == frames_before
        assert "release" not in fake.frames

    assert handle.context.hold_deadline > first_deadline + 0.1
    assert fake.runs == 1
    await asyncio.wait_for(task, 1)
    assert handle.outcome is CommandOutcome.EXPIRED
    assert fake.frames.count("release") == 1


async def test_renewal_can_shorten_the_hold() -> None:
    scheduler = DeviceCommandScheduler("shorten")
    fake = FakeHold()
    task = await start_hold(scheduler, fake, lease(duration_s=30))
    assert scheduler.claim_hold(lease(duration_s=0.01), BACK) is HoldClaim.RENEW
    await asyncio.wait_for(task, 1)
    assert scheduler._recent_records[-1].outcome is CommandOutcome.EXPIRED


async def test_expiry_runs_the_controller_release_once() -> None:
    scheduler = DeviceCommandScheduler("expire")
    fake = FakeHold()
    task = await start_hold(scheduler, fake, lease(duration_s=0.03))
    await asyncio.wait_for(task, 1)
    record = scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED
    assert fake.frames[-1] == "release"
    assert fake.frames.count("release") == 1
    # The ended generation cannot be renewed or restarted.
    assert scheduler.claim_hold(lease(), BACK) is HoldClaim.STALE
    with pytest.raises(StaleHoldLease):
        await scheduler.execute(hold_intent(FakeHold(), lease()))


async def test_stop_outranks_renewal() -> None:
    scheduler = DeviceCommandScheduler("stop")
    fake = FakeHold()
    task = await start_hold(scheduler, fake, lease(duration_s=30))
    epoch = scheduler.request_stop(BACK)
    # Cleanup is still running; a renewal must not revive it.
    assert scheduler.claim_hold(lease(), BACK) is HoldClaim.STALE
    await asyncio.wait_for(task, 1)
    scheduler.finish_stop(epoch)
    assert scheduler.recent_records[-1].outcome is CommandOutcome.STOPPED
    assert fake.frames.count("release") == 1
    with pytest.raises(StaleHoldLease):
        await scheduler.execute(hold_intent(FakeHold(), lease()))


async def test_stale_and_superseded_generations_are_refused() -> None:
    scheduler = DeviceCommandScheduler("generations")
    first = FakeHold()
    first_task = await start_hold(scheduler, first, lease(2, duration_s=30))
    assert scheduler.claim_hold(lease(1), BACK, reserve=False) is HoldClaim.STALE
    # Another motion needs a new generation.
    assert scheduler.claim_hold(lease(2, action="down"), BACK) is HoldClaim.STALE

    second = FakeHold()
    second_task = await start_hold(scheduler, second, lease(3, action="down", duration_s=0.03))
    await asyncio.wait_for(first_task, 1)
    assert scheduler.recent_records[0].outcome is CommandOutcome.REPLACED
    assert first.frames[-1] == "release"
    assert scheduler.claim_hold(lease(2), BACK) is HoldClaim.STALE
    await asyncio.wait_for(second_task, 1)


async def test_owner_and_resource_scope_the_lease() -> None:
    scheduler = DeviceCommandScheduler("scope")
    fake = FakeHold()
    task = await start_hold(scheduler, fake, lease(duration_s=30))
    other_owner = HoldLease(owner="phone", generation=1, action="up", duration_s=1)
    assert scheduler.claim_hold(other_owner, BACK, reserve=False) is HoldClaim.START
    assert (
        scheduler.claim_hold(lease(), command_resources("motor:legs"), reserve=False)
        is HoldClaim.START
    )
    scheduler.request_stop(BACK)
    await asyncio.wait_for(task, 1)


async def test_reservation_is_renewed_before_admission_and_ended_by_stop() -> None:
    scheduler = DeviceCommandScheduler("reserve")
    assert scheduler.claim_hold(lease(duration_s=0.05), BACK) is HoldClaim.START
    # A renewal sent while the starting call is still preflighting.
    assert scheduler.claim_hold(lease(duration_s=30), BACK) is HoldClaim.RENEW
    scheduler.finish_stop(scheduler.request_stop(BACK))
    assert scheduler.claim_hold(lease(), BACK, reserve=False) is HoldClaim.STALE
    fake = FakeHold()
    with pytest.raises(StaleHoldLease):
        await scheduler.execute(hold_intent(fake, lease()))
    assert fake.runs == 0


async def test_reservation_that_expired_before_admission_never_writes() -> None:
    scheduler = DeviceCommandScheduler("late")
    held = lease(duration_s=0.01)
    assert scheduler.claim_hold(held, BACK) is HoldClaim.START
    await asyncio.sleep(0.03)
    fake = FakeHold()
    with pytest.raises(StaleHoldLease):
        await scheduler.execute(hold_intent(fake, held))
    assert fake.runs == 0


async def test_released_reservation_cannot_start_later() -> None:
    scheduler = DeviceCommandScheduler("release")
    assert scheduler.claim_hold(lease(), BACK) is HoldClaim.START
    scheduler.release_hold_claim(lease(), BACK)
    assert scheduler.claim_hold(lease(), BACK, reserve=False) is HoldClaim.STALE


@pytest.mark.parametrize("ending", ["disconnect", "shutdown"])
async def test_disconnect_and_shutdown_end_holds_without_replay(ending: str) -> None:
    scheduler = DeviceCommandScheduler("end")
    fake = FakeHold()
    task = await start_hold(scheduler, fake, lease(duration_s=30))
    if ending == "disconnect":
        scheduler.end_holds(CommandOutcome.DISCONNECTED)
        await asyncio.wait_for(task, 1)
        assert scheduler.recent_records[-1].outcome is CommandOutcome.DISCONNECTED
    else:
        await scheduler.async_shutdown()
        await asyncio.wait_for(task, 1)
        assert scheduler.recent_records[-1].outcome is CommandOutcome.SHUTDOWN
    assert fake.frames[-1] == "release"
    assert scheduler.claim_hold(lease(), BACK) is HoldClaim.STALE
    assert fake.runs == 1


async def test_queued_hold_expires_without_running() -> None:
    scheduler = DeviceCommandScheduler("queued")
    blocker_started = asyncio.Event()
    release_blocker = asyncio.Event()

    async def blocker(_context: CommandContext) -> None:
        blocker_started.set()
        await release_blocker.wait()

    blocking = asyncio.create_task(
        scheduler.execute(CommandIntent(blocker, resources=command_resources("motor:legs")))
    )
    await blocker_started.wait()
    fake = FakeHold()
    held = asyncio.create_task(scheduler.execute(hold_intent(fake, lease(duration_s=0.02))))
    await asyncio.wait_for(held, 1)
    assert fake.runs == 0
    assert scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED
    release_blocker.set()
    await blocking


def test_hold_intents_carry_a_lease() -> None:
    async def noop(_context: CommandContext) -> None:
        return None

    with pytest.raises(ValueError):
        CommandIntent(noop, kind=CommandKind.HOLD)
    with pytest.raises(ValueError):
        CommandIntent(noop, lease=lease())
    with pytest.raises(ValueError):
        HoldLease(owner="card", generation=-1, action="up", duration_s=1)
    with pytest.raises(ValueError):
        HoldLease(owner="card", generation=1, action="up", duration_s=0)
