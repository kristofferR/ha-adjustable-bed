"""Renewable holds (#483) on the Jensen LinOn route of the ``svane`` bed type.

The Jensen app refreshes a held control every 800 ms until release, then writes
STOP to the head and then the foot. The lease tests run the real controller on
its wire-snapshot scenario on virtual time.
"""

from __future__ import annotations

from typing import Any

from custom_components.adjustable_bed.beds.jensen_linon import (
    HOLD_INTERVAL_MS,
    JensenLinonCommands,
)
from tests.hold_lease_wire import intervals, leased_hold

SCENARIO = "svane:jensen_linon"
MOVE = JensenLinonCommands.MOVE.hex()
STOP = JensenLinonCommands.STOP.hex()


async def _head_up(controller: Any) -> None:
    await controller.move_head_up()


async def test_a_lease_streams_past_a_finite_press_then_expiry_stops_head_and_foot() -> None:
    wire = await leased_hold(SCENARIO, _head_up, end_after_s=4, end="expire")
    finite = await leased_hold(SCENARIO, _head_up, end_after_s=4, end="expire", leased=False)
    moves = tuple(write for write in wire.held if write.data.hex() == MOVE)

    assert {write.data.hex() for write in wire.held} == {MOVE}
    # The app's 800 ms refresh, plus one write's acknowledgement.
    assert all(HOLD_INTERVAL_MS <= gap <= HOLD_INTERVAL_MS + 10 for gap in intervals(moves))
    assert len(moves) > sum(write.data.hex() == MOVE for write in finite.held)
    # Expiry ends the 800 ms wait at once, then STOP goes to the head and the foot.
    assert [write.data.hex() for write in wire.after] == [STOP, STOP]
    assert wire.after[0].at_ms - wire.ended_ms <= 10


async def test_stop_preempts_the_lease() -> None:
    wire = await leased_hold(SCENARIO, _head_up, end_after_s=2, end="stop")
    after = [write.data.hex() for write in wire.after]
    # The hold's own STOP pair, then the explicit STOP's.
    assert after[:2] == [STOP, STOP]
    assert MOVE not in after
