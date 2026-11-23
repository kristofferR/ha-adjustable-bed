"""Merged-stream timing on the hold-lease harness's virtual clock (#516, #483).

Deadlines, lease expiry, write teardown and release schedules are checked to
the millisecond, with no real timer. As for a serial hold (#799), expiry never
cuts off a member's cleanup or the last member's release.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest

from custom_components.adjustable_bed.command_scheduler import (
    ALL_COMMAND_RESOURCES,
    CommandContext,
    CommandIntent,
    CommandOutcome,
    DeviceCommandScheduler,
    HoldClaim,
    HoldLease,
    StreamDriver,
    StreamMember,
    command_resources,
)
from tests.hold_lease_wire import virtual_clock

CONCURRENT = command_resources("motor:back", "motor:legs")
TICK_S = 0.1


class Wire:
    """A composing driver that records every frame at virtual milliseconds."""

    stream_tick_s = TICK_S

    def __init__(self, clock: Any) -> None:
        self.clock = clock
        self.frames: list[tuple[int, str]] = []
        self.write_s = 0.0
        self.write_blocks = False
        self.teardown_s = 0.0
        self.cleanup: dict[str, tuple[float, ...]] = {}
        """Per motor, delays before each cleanup frame."""
        self.release: tuple[float, ...] = (0.0,)
        """Delays before each release frame."""

    def at(self) -> int:
        return round(self.clock.now * 1000)

    async def write_stream_tick(self, members: tuple[StreamMember, ...]) -> None:
        self.frames.append((self.at(), "+".join(sorted(m.motor for m in members))))
        try:
            if self.write_blocks:
                await asyncio.Event().wait()
            await asyncio.sleep(self.write_s)
        except asyncio.CancelledError:
            await asyncio.sleep(self.teardown_s)
            raise

    async def end_stream_member(
        self, member: StreamMember, remaining: tuple[StreamMember, ...]
    ) -> None:
        for delay in self.cleanup.get(member.motor, (0.0,)):
            await asyncio.sleep(delay)
            self.frames.append((self.at(), f"end {member.motor}"))

    async def release_stream(self) -> None:
        for delay in self.release:
            await asyncio.sleep(delay)
            self.frames.append((self.at(), "release"))


@pytest.fixture
async def clock() -> AsyncIterator[Any]:
    with virtual_clock() as clock:
        yield clock


def runner(wire: Wire) -> Callable[[Callable[[StreamDriver], Awaitable[None]]], Awaitable[None]]:
    async def run(body: Callable[[StreamDriver], Awaitable[None]]) -> None:
        await body(wire)

    return run


def timed(motor: str, seconds: float, travel: dict[str, float | None]) -> StreamMember:
    """A timed move whose budget starts with its first write."""
    return StreamMember(
        motor=motor,
        resource=f"motor:{motor}",
        action="up",
        deadline=math.inf,
        duration_s=seconds,
        on_wire=lambda: None,
        on_left=lambda value: travel.__setitem__(motor, value),
    )


def held(motor: str, clock: Any, travel: dict[str, float | None], **kwargs: Any) -> StreamMember:
    member = StreamMember(
        motor=motor,
        resource=f"motor:{motor}",
        action="up",
        deadline=clock.now + kwargs.pop("seconds", 30),
        on_wire=lambda: None,
        on_left=lambda value: travel.__setitem__(motor, value),
        **kwargs,
    )
    return member


def join(
    scheduler: DeviceCommandScheduler, wire: Wire, member: StreamMember
) -> asyncio.Task[CommandOutcome | None]:
    return asyncio.ensure_future(
        scheduler.execute_stream_member(member, CONCURRENT, runner(wire))
    )


@pytest.mark.parametrize(
    ("write_s", "starts"),
    [
        # Each tick starts one interval after the previous one started.
        (0.08, [0, 100, 200, 300]),
        # An overrunning write is followed at once, without a catch-up burst.
        (0.25, [0, 250, 500, 750]),
    ],
)
async def test_ticks_run_at_a_fixed_rate_from_each_write_start(
    clock: Any, write_s: float, starts: list[int]
) -> None:
    scheduler, wire, travel = DeviceCommandScheduler("rate"), Wire(clock), {}
    wire.write_s = write_s
    back = join(scheduler, wire, held("back", clock, travel))
    await asyncio.sleep(starts[-1] / 1000 + 0.001)
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    await back
    scheduler.finish_stop(epoch)
    assert [at for at, frame in wire.frames if frame == "back"][: len(starts)] == starts


async def test_a_slow_write_ends_a_timed_move_on_time(clock: Any) -> None:
    scheduler, wire, travel = DeviceCommandScheduler("slow"), Wire(clock), {}
    wire.write_s = 0.08  # a slow write acknowledgement
    assert await join(scheduler, wire, timed("back", 0.02, travel)) is CommandOutcome.EXPIRED
    assert wire.frames == [(0, "back"), (20, "end back"), (20, "release")]
    assert travel == {"back": 0.02}


async def test_a_blocked_write_still_expires_a_renewed_lease(clock: Any) -> None:
    scheduler, wire, travel = DeviceCommandScheduler("blocked"), Wire(clock), {}
    wire.write_blocks = True
    lease = HoldLease(owner="card", generation=1, action="up", duration_s=0.03)
    back = join(scheduler, wire, held("back", clock, travel, seconds=0.03, lease=lease))
    for _ in range(3):
        await asyncio.sleep(0.02)
        assert scheduler.claim_hold(lease, ("motor:back",)) is HoldClaim.RENEW
    assert await back is CommandOutcome.EXPIRED
    # The last renewal, at 60 ms, bought 30 ms more.
    assert wire.frames == [(0, "back"), (90, "end back"), (90, "release")]
    assert travel == {"back": 0.09}


async def test_write_teardown_is_never_travel(clock: Any) -> None:
    scheduler, wire, travel = DeviceCommandScheduler("teardown"), Wire(clock), {}
    wire.write_blocks = True
    wire.teardown_s = 0.15
    assert await join(scheduler, wire, timed("back", 0.02, travel)) is CommandOutcome.EXPIRED
    assert wire.frames == [(0, "back"), (170, "end back"), (170, "release")]
    assert travel == {"back": 0.02}


@pytest.mark.parametrize("ending", ["stop", "replace"])
async def test_stop_or_replacement_stops_travel_before_teardown(
    clock: Any, ending: str
) -> None:
    scheduler, wire, travel = DeviceCommandScheduler(ending), Wire(clock), {}
    wire.write_blocks = True
    wire.teardown_s = 0.15
    back = join(scheduler, wire, held("back", clock, travel))
    await asyncio.sleep(0.02)
    if ending == "stop":
        epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
        await back
        scheduler.finish_stop(epoch)
    else:

        async def preset(_context: CommandContext) -> None:
            return None

        await scheduler.execute(CommandIntent(preset))
        await back
    assert travel == {"back": 0.02}


async def test_stop_during_another_members_teardown_or_cleanup_stops_the_survivor(
    clock: Any,
) -> None:
    for phase in ("teardown", "cleanup"):
        scheduler, wire, travel = DeviceCommandScheduler(phase), Wire(clock), {}
        if phase == "teardown":
            wire.write_blocks = True
            wire.teardown_s = 0.15
        else:
            wire.cleanup = {"back": (0.15,)}
        back = join(scheduler, wire, timed("back", 0.02, travel))
        legs = join(scheduler, wire, held("legs", clock, travel))
        await asyncio.sleep(0.04)
        epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
        await asyncio.gather(back, legs)
        scheduler.finish_stop(epoch)
        assert travel["back"] == pytest.approx(0.02), phase
        # legs stopped as the STOP arrived, 40 ms in, whatever back was doing.
        assert travel["legs"] == pytest.approx(0.04), phase


async def test_expiry_lets_cleanup_and_release_finish(clock: Any) -> None:
    """As for a serial hold (#799): delayed cleanup and release frames all go out."""
    scheduler, wire, travel = DeviceCommandScheduler("expire"), Wire(clock), {}
    wire.cleanup = {"back": (0.0, 0.3)}
    wire.release = (0.0, 0.1, 0.1, 0.1)
    lease = HoldLease(owner="card", generation=1, action="up", duration_s=0.02)
    assert await join(
        scheduler, wire, held("back", clock, travel, seconds=0.02, lease=lease)
    ) is CommandOutcome.EXPIRED
    assert wire.frames == [
        (0, "back"),
        (20, "end back"),
        (320, "end back"),
        (320, "release"),
        (420, "release"),
        (520, "release"),
        (620, "release"),
    ]
    assert travel == {"back": 0.02}


async def test_a_stop_cannot_cut_off_an_expiring_members_cleanup(clock: Any) -> None:
    scheduler, wire, travel = DeviceCommandScheduler("expire-stop"), Wire(clock), {}
    wire.cleanup = {"back": (0.0, 0.3)}
    back = join(scheduler, wire, timed("back", 0.02, travel))
    legs = join(scheduler, wire, held("legs", clock, travel))
    await asyncio.sleep(0.1)  # back's cleanup is under way
    epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
    await asyncio.gather(back, legs)
    scheduler.finish_stop(epoch)
    ends = [(at, frame) for at, frame in wire.frames if frame.startswith("end")]
    assert ends == [(20, "end back"), (320, "end back"), (320, "end legs")]
    assert wire.frames[-1] == (320, "release")
    assert travel == {"back": 0.02, "legs": 0.1}


@pytest.mark.parametrize("ending", ["stop", "replace"])
async def test_a_deadline_passed_during_cleanup_bounds_travel_at_stop(
    clock: Any, ending: str
) -> None:
    scheduler, wire, travel = DeviceCommandScheduler(f"late-{ending}"), Wire(clock), {}
    wire.cleanup = {"back": (0.0, 0.3)}
    back = join(scheduler, wire, timed("back", 0.02, travel))
    legs = join(scheduler, wire, held("legs", clock, travel, seconds=0.05))
    await asyncio.sleep(0.1)  # legs' deadline passed during back's cleanup
    if ending == "stop":
        epoch = scheduler.request_stop(ALL_COMMAND_RESOURCES)
        await asyncio.gather(back, legs)
        scheduler.finish_stop(epoch)
    else:

        async def preset(_context: CommandContext) -> None:
            return None

        await scheduler.execute(CommandIntent(preset))
        await asyncio.gather(back, legs)
    assert travel == {"back": 0.02, "legs": 0.05}
