"""Renewable holds (#483) on the eShine E2000/E3000/E3100/E5000 app (row122).

Every held key writes at once, refreshes every 300 ms with no fixed count while
held, and on release sends STOP 200 ms later. The lease tests run the real
controller on its wire-snapshot scenarios on virtual time.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.adjustable_bed.beds.eshine_okin.protocol import COMMANDS, HELD
from custom_components.adjustable_bed.const import BED_TYPE_ESHINE_OKIN
from custom_components.adjustable_bed.execution import HOLD_CEILING_MS
from tests.hold_lease_wire import intervals, leased_hold
from tests.test_controller_contract import _create_controller_for_bed_type
from tests.test_eshine_okin import VECTORS

HELD_FRAME = COMMANDS["head_up"].hex()
STOP = COMMANDS["stop"].hex()
SCENARIOS = ("eshine_okin:eshine_e2000", "eshine_okin:eshine_e30003100", "eshine_okin:eshine_e5000")


async def test_eshine_okin_declares_a_stream_hold() -> None:
    controller = await _create_controller_for_bed_type(BED_TYPE_ESHINE_OKIN)
    assert controller.execution.hold == "stream"


def test_held_and_release_frames_are_frozen() -> None:
    frozen = {frame for _action, frame in VECTORS}
    assert {COMMANDS[action].hex() for action in HELD} | {STOP} <= frozen


def _hold(duration_ms: int):
    async def move(controller: Any) -> None:
        await controller.hold_control("head_up", duration_ms)

    return move


@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_a_lease_streams_at_300_ms_then_expiry_sends_stop(scenario: str) -> None:
    wire = await leased_hold(scenario, _hold(HOLD_CEILING_MS), end_after_s=3, end="expire")
    held = [write for write in wire.held if write.data.hex() == HELD_FRAME]

    assert held and all(300 <= gap <= 310 for gap in intervals(tuple(held)))
    assert held[-1].at_ms >= wire.ended_ms - 310
    # Expiry sends the app's release: STOP once, 200 ms after the hold ends.
    assert [write.data.hex() for write in wire.after] == [STOP]
    assert 200 <= wire.after[0].at_ms - wire.ended_ms <= 310


@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_stop_preempts_the_lease(scenario: str) -> None:
    wire = await leased_hold(scenario, _hold(HOLD_CEILING_MS), end_after_s=1, end="stop")
    after = [write.data.hex() for write in wire.after]
    assert after and set(after) == {STOP}
