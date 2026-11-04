"""Merged-stream members feed position estimates like serialized moves (#516, #797)."""

from __future__ import annotations

import asyncio
import math

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.command_scheduler import (
    CommandOutcome,
    DeviceCommandScheduler,
    StreamMember,
    command_resources,
)
from tests.test_merged_stream import CONCURRENT, FakeDriver, runner_for, settle
from tests.test_position_estimate import LEFT, calibrated, controller

# Travel per second with the calibrated full-travel times: back 20 s, legs 10 s.
BACK_PERCENT_PER_S = 100 / 20.0
LEGS_PERCENT_PER_S = 100 / 10.0


def tracked_member(
    hass: HomeAssistant, motor: str, *, duration_s: float, seconds: list[float | None]
) -> StreamMember:
    tracker = pe.track_stream_member(hass, controller(hass, LEFT), motor, "up")
    assert tracker is not None

    def finished(value: float | None) -> None:
        seconds.append(value)
        tracker.finished(value)

    return StreamMember(
        motor=motor,
        resource=f"motor:{motor}",
        action="up",
        deadline=math.inf,
        duration_s=duration_s,
        on_wire=tracker.started,
        on_left=finished,
    )


async def test_members_report_their_own_wire_time(hass: HomeAssistant) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    scheduler = DeviceCommandScheduler("estimate")
    driver = FakeDriver()
    loop = asyncio.get_running_loop()
    back_seconds: list[float | None] = []
    legs_seconds: list[float | None] = []

    back = asyncio.create_task(
        scheduler.execute_stream_member(
            tracked_member(hass, "back", duration_s=0.12, seconds=back_seconds),
            CONCURRENT,
            runner_for(driver),
        )
    )
    legs = asyncio.create_task(
        scheduler.execute_stream_member(
            tracked_member(hass, "legs", duration_s=30, seconds=legs_seconds),
            CONCURRENT,
            runner_for(driver),
        )
    )
    await settle(driver)
    started = loop.time()
    await asyncio.sleep(0.05)
    # A per-motor Stop ends legs while back keeps streaming.
    scheduler.finish_stop(scheduler.request_stop(command_resources("motor:legs")))
    stopped = loop.time()
    assert await asyncio.wait_for(legs, 1) is CommandOutcome.STOPPED
    assert back_seconds == []  # back is still moving: nothing reported at join
    assert await asyncio.wait_for(back, 1) is CommandOutcome.EXPIRED

    assert back_seconds[0] == pytest.approx(0.12, abs=0.03)
    assert legs_seconds[0] == pytest.approx(stopped - started + 0.02, abs=0.03)
    assert bed.motors["back"].percent == pytest.approx(
        back_seconds[0] * BACK_PERCENT_PER_S
    )
    assert bed.motors["legs"].percent == pytest.approx(
        legs_seconds[0] * LEGS_PERCENT_PER_S
    )
    assert bed.tracking(["back", "legs"])


async def test_a_streamed_move_matches_a_serialized_move(hass: HomeAssistant) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]

    async def serial_move(_controller: object) -> None:
        await asyncio.sleep(0.1)

    await pe.track_motor_command(hass, "back", "up", serial_move)(controller(hass, LEFT))
    serial_percent = bed.motors["back"].percent

    seconds: list[float | None] = []
    scheduler = DeviceCommandScheduler("estimate-equal")
    await scheduler.execute_stream_member(
        tracked_member(hass, "back", duration_s=0.1, seconds=seconds),
        CONCURRENT,
        runner_for(FakeDriver()),
    )
    assert bed.motors["back"].percent - serial_percent == pytest.approx(
        serial_percent, abs=0.15
    )


async def test_a_failed_member_makes_its_estimate_unknown(hass: HomeAssistant) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    scheduler = DeviceCommandScheduler("estimate-failed")
    driver = FakeDriver(fail_end="back")
    seconds: list[float | None] = []
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await scheduler.execute_stream_member(
            tracked_member(hass, "back", duration_s=0.03, seconds=seconds),
            CONCURRENT,
            runner_for(driver),
        )
    assert seconds == [None]
    assert not bed.tracking(["back"])
